/**
 * dataLayer.js — Browser-side tracking helpers.
 *
 * - GA4 e-commerce schema event push (window.dataLayer)
 * - Native pixel calls (fbq/ttq/snaptr/pintrk) — best effort
 * - Mirror dispatch to /api/capi/event for server-side delivery
 *
 * Deduplication: each event gets a unique `event_id` (uuid v4-ish), passed both
 * to the browser pixel (Meta/TikTok/Pinterest native support) and to backend.
 *
 * Usage (anywhere in the React tree):
 *   import { trackViewItem, trackAddToCart, trackPurchase } from "@/lib/dataLayer";
 *   trackViewItem({ product, currency: "TRY" });
 */
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// ---------------------------------------------------------------------------
//   Helpers
// ---------------------------------------------------------------------------

/** Crypto-strong uuid v4 (browser-safe, no external deps). */
export function generateEventId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  // Fallback (older browsers / SSR)
  return "ev-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
}

/** Read cookie value by name. */
function readCookie(name) {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
  return m ? decodeURIComponent(m[2]) : null;
}

/** Click ID + cookie aggregator (Meta fbp/fbc, Google gclid, TikTok ttclid, …) */
export function collectClickIds() {
  const ids = {
    fbp: readCookie("_fbp"),
    fbc: readCookie("_fbc"),
    gclid: readCookie("_gcl_aw") || readCookie("gclid"),
    ttclid: readCookie("ttclid"),
    epik: readCookie("_epik"),
    sc_click_id: readCookie("sc_click_id"),
  };
  // URL parameters also seed click IDs (first-touch attribution)
  if (typeof window !== "undefined") {
    const usp = new URLSearchParams(window.location.search);
    ["gclid", "ttclid", "epik"].forEach((k) => {
      if (usp.get(k)) ids[k === "epik" ? "epik" : k] = usp.get(k);
    });
  }
  return ids;
}

/** Push to GA4 dataLayer + dispatch native pixels + POST to backend CAPI. */
async function pushEvent(eventName, eventData, userInfo = {}) {
  const event_id = eventData.event_id || generateEventId();
  const clickIds = collectClickIds();

  // 1) GA4 / GTM dataLayer
  if (typeof window !== "undefined") {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: eventName,
      event_id,
      ecommerce: {
        currency: eventData.currency || "TRY",
        value: eventData.value || 0,
        items: eventData.items || [],
        transaction_id: eventData.order_id,
        coupon: eventData.coupon,
      },
    });

    // 2) Meta Pixel (fbq) — eventID parameter for dedup with CAPI
    if (typeof window.fbq === "function") {
      try {
        const fbEventMap = {
          view_item: "ViewContent", view_item_list: "ViewCategory",
          add_to_cart: "AddToCart", remove_from_cart: "RemoveFromCart",
          begin_checkout: "InitiateCheckout", add_payment_info: "AddPaymentInfo",
          add_to_wishlist: "AddToWishlist", purchase: "Purchase",
          lead: "Lead", search: "Search",
        };
        const fbEv = fbEventMap[eventName] || eventName;
        window.fbq("track", fbEv, {
          currency: eventData.currency || "TRY",
          value: eventData.value || 0,
          content_ids: (eventData.items || []).map((i) => String(i.item_id || i.id || "")),
          content_type: "product",
          num_items: (eventData.items || []).reduce((s, i) => s + (i.quantity || 1), 0),
        }, { eventID: event_id });
      } catch (_) { /* silent */ }
    }

    // 3) TikTok Pixel
    if (typeof window.ttq === "object" && typeof window.ttq.track === "function") {
      try {
        const ttEventMap = {
          view_item: "ViewContent", view_item_list: "ViewContent",
          add_to_cart: "AddToCart", begin_checkout: "InitiateCheckout",
          add_payment_info: "AddPaymentInfo", purchase: "CompletePayment",
        };
        const ttEv = ttEventMap[eventName] || eventName;
        window.ttq.track(ttEv, {
          contents: (eventData.items || []).map((i) => ({
            content_id: String(i.item_id || i.id || ""),
            content_name: i.item_name || i.name || "",
            content_type: "product",
            quantity: i.quantity || 1,
            price: i.price || 0,
          })),
          currency: eventData.currency || "TRY",
          value: eventData.value || 0,
        }, { event_id });
      } catch (_) { /* silent */ }
    }

    // 4) Pinterest
    if (typeof window.pintrk === "function") {
      try {
        const pinMap = {
          view_item: "pagevisit", add_to_cart: "addtocart",
          begin_checkout: "checkout", purchase: "checkout",
        };
        const pinEv = pinMap[eventName] || "custom";
        window.pintrk("track", pinEv, {
          value: eventData.value || 0,
          order_quantity: (eventData.items || []).reduce((s, i) => s + (i.quantity || 1), 0),
          currency: eventData.currency || "TRY",
          line_items: (eventData.items || []).map((i) => ({
            product_id: String(i.item_id || i.id || ""),
            product_name: i.item_name || i.name || "",
            product_price: i.price || 0,
            product_quantity: i.quantity || 1,
          })),
          event_id,
        });
      } catch (_) { /* silent */ }
    }

    // 5) Snapchat
    if (typeof window.snaptr === "function") {
      try {
        const snapMap = {
          view_item: "VIEW_CONTENT", add_to_cart: "ADD_CART",
          begin_checkout: "START_CHECKOUT", purchase: "PURCHASE",
        };
        const snapEv = snapMap[eventName] || eventName.toUpperCase();
        window.snaptr("track", snapEv, {
          currency: eventData.currency || "TRY",
          price: eventData.value || 0,
          item_ids: (eventData.items || []).map((i) => String(i.item_id || i.id || "")),
          number_items: (eventData.items || []).reduce((s, i) => s + (i.quantity || 1), 0),
          transaction_id: eventData.order_id || event_id,
          client_dedup_id: event_id,
        });
      } catch (_) { /* silent */ }
    }
  }

  // 6) Server-side CAPI mirror (non-blocking)
  try {
    await axios.post(`${API}/capi/event`, {
      event_name: eventName,
      event_id,
      event_time: Math.floor(Date.now() / 1000),
      ...userInfo,
      ...clickIds,
      currency: eventData.currency || "TRY",
      value: eventData.value || 0,
      items: eventData.items || [],
      order_id: eventData.order_id,
      coupon: eventData.coupon,
      category: eventData.category,
      event_source_url: typeof window !== "undefined" ? window.location.href : null,
    }, { timeout: 5000 });
  } catch (_) {
    // Network errors don't break UX
  }

  return event_id;
}

// ---------------------------------------------------------------------------
//   Public API — GA4 e-commerce events
// ---------------------------------------------------------------------------

function productToItem(p, variant = null) {
  return {
    item_id: String(p.id || p.product_id || p.sku || ""),
    item_name: p.name || "",
    item_brand: p.brand || "FACETTE",
    item_category: p.category_name || "",
    item_variant: variant ? `${variant.size || ""} ${variant.color || p.color || ""}`.trim() : (p.color || ""),
    price: p.sale_price || p.price || 0,
    quantity: variant?.quantity || 1,
  };
}

export const trackViewItem = ({ product, currency = "TRY", user = {} }) =>
  pushEvent("view_item", {
    currency, value: product.sale_price || product.price || 0,
    items: [productToItem(product)],
  }, user);

export const trackViewItemList = ({ products, listName = "", currency = "TRY", user = {} }) =>
  pushEvent("view_item_list", {
    currency, value: 0,
    items: (products || []).map((p) => productToItem(p)),
    category: listName,
  }, user);

export const trackAddToCart = ({ product, variant, quantity = 1, currency = "TRY", user = {} }) =>
  pushEvent("add_to_cart", {
    currency, value: (variant?.price || product.sale_price || product.price || 0) * quantity,
    items: [{ ...productToItem(product, variant), quantity }],
  }, user);

export const trackRemoveFromCart = ({ product, variant, quantity = 1, currency = "TRY", user = {} }) =>
  pushEvent("remove_from_cart", {
    currency, value: (variant?.price || product.sale_price || product.price || 0) * quantity,
    items: [{ ...productToItem(product, variant), quantity }],
  }, user);

export const trackBeginCheckout = ({ items, value, currency = "TRY", coupon, user = {} }) =>
  pushEvent("begin_checkout", { currency, value, items, coupon }, user);

export const trackAddPaymentInfo = ({ items, value, currency = "TRY", user = {} }) =>
  pushEvent("add_payment_info", { currency, value, items }, user);

export const trackPurchase = ({ orderNumber, items, value, currency = "TRY", coupon, user = {} }) =>
  pushEvent("purchase", { order_id: orderNumber, currency, value, items, coupon }, user);

export const trackSearch = ({ keyword, user = {} }) =>
  pushEvent("search", { search_term: keyword }, user);

export default {
  trackViewItem, trackViewItemList, trackAddToCart, trackRemoveFromCart,
  trackBeginCheckout, trackAddPaymentInfo, trackPurchase, trackSearch,
  generateEventId, collectClickIds,
};
