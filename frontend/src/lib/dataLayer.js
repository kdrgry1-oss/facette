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

// GA4'e özgü funnel event'leri — bunların Meta/TikTok/Pinterest/Snapchat'te
// standart karşılığı yok. Native pixel'lere/CAPI'ye custom isimle gönderilirse
// pazaryeri/reklam verisini kirletir. Bu yüzden SADECE dataLayer'a (GTM→GA4)
// push edilir; native pixel ve CAPI atlanır.
const GA4_ONLY_EVENTS = new Set([
  "select_item",
  "view_cart",
  "add_shipping_info",
  "select_promotion",
]);

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

/** Click ID + cookie aggregator (Meta fbp/fbc, Google gclid/wbraid/gbraid,
 *  TikTok ttclid/ttp, Pinterest epik, Snapchat sc_click_id/sc_cookie1). */
export function collectClickIds() {
  const ids = {
    fbp: readCookie("_fbp"),
    fbc: readCookie("_fbc"),
    gclid: readCookie("_gcl_aw") || readCookie("gclid"),
    wbraid: readCookie("wbraid"),
    gbraid: readCookie("gbraid"),
    ttclid: readCookie("ttclid"),
    ttp: readCookie("_ttp"),
    epik: readCookie("_epik"),
    sc_click_id: readCookie("sc_click_id"),
    sc_cookie1: readCookie("_scid"),
  };
  // URL parameters also seed click IDs (first-touch attribution)
  if (typeof window !== "undefined") {
    const usp = new URLSearchParams(window.location.search);
    ["gclid", "wbraid", "gbraid", "ttclid", "epik"].forEach((k) => {
      if (usp.get(k)) ids[k] = usp.get(k);
    });
    // _fbc'yi sentetik olarak fbclid'den üret (Meta önerisi)
    const fbclid = usp.get("fbclid");
    if (fbclid && !ids.fbc) {
      ids.fbc = `fb.1.${Date.now()}.${fbclid}`;
    }
  }
  return ids;
}

/** Push to GA4 dataLayer + dispatch native pixels + POST to backend CAPI. */
async function pushEvent(eventName, eventData, userInfo = {}) {
  const event_id = eventData.event_id || generateEventId();
  const clickIds = collectClickIds();
  const isGa4Only = GA4_ONLY_EVENTS.has(eventName);

  // 1) GA4 / GTM dataLayer — Enhanced E-commerce schema (kalem kalem ayrı parametre)
  if (typeof window !== "undefined") {
    window.dataLayer = window.dataLayer || [];
    // Önce eski ecommerce datasını temizle (best practice — undefined push)
    window.dataLayer.push({ ecommerce: null });
    window.dataLayer.push({
      event: eventName,
      event_id,
      ecommerce: {
        // Genel event parametreleri
        currency: eventData.currency || "TRY",
        value: Number(eventData.value || 0),
        transaction_id: eventData.order_id,
        coupon: eventData.coupon || "",
        // Fiyat / promosyon
        discount: Number(eventData.discount || 0),       // Sepet/sipariş toplam indirim
        original_value: Number(eventData.original_value || 0),  // İndirimsiz toplam
        tax: Number(eventData.tax || 0),
        shipping: Number(eventData.shipping || 0),
        // Ödeme / kargo
        payment_type: eventData.payment_type || "",
        shipping_tier: eventData.shipping_tier || "",
        // Liste / atıf
        affiliation: eventData.affiliation || "FACETTE Online",
        item_list_id: eventData.list_id || "",
        item_list_name: eventData.list_name || "",
        // Promosyon
        promotion_id: eventData.promotion_id || "",
        promotion_name: eventData.promotion_name || "",
        // KALEM KALEM ürünler — ayrı ayrı parametrelerle
        items: eventData.items || [],
      },
    });

    // 2) Meta Pixel (fbq) — eventID parameter for dedup with CAPI
    if (!isGa4Only && typeof window.fbq === "function") {
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
          content_ids: (eventData.items || []).map((i) => String(i.content_id || i.item_id || i.id || "")),
          content_type: "product",
          num_items: (eventData.items || []).reduce((s, i) => s + (i.quantity || 1), 0),
        }, { eventID: event_id });
      } catch (_) { /* silent */ }
    }

    // 3) TikTok Pixel
    if (!isGa4Only && typeof window.ttq === "object" && typeof window.ttq.track === "function") {
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
    if (!isGa4Only && typeof window.pintrk === "function") {
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
    if (!isGa4Only && typeof window.snaptr === "function") {
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

  // GA4-only event'ler native pixel + CAPI'ye gitmez; burada biter.
  if (isGa4Only) return event_id;

  // 6) Server-side CAPI mirror (non-blocking) — TÜM ENHANCED E-COMMERCE PARAMETRELERİYLE
  try {
    await axios.post(`${API}/capi/event`, {
      event_name: eventName,
      event_id,
      event_time: Math.floor(Date.now() / 1000),
      ...userInfo,
      ...clickIds,
      // Genel
      currency: eventData.currency || "TRY",
      value: Number(eventData.value || 0),
      items: eventData.items || [],
      order_id: eventData.order_id,
      coupon: eventData.coupon || "",
      category: eventData.category || "",
      // Promosyon & İndirim
      discount: Number(eventData.discount || 0),
      original_value: Number(eventData.original_value || 0),
      tax: Number(eventData.tax || 0),
      shipping: Number(eventData.shipping || 0),
      // Ödeme & Kargo
      payment_type: eventData.payment_type || "",
      shipping_tier: eventData.shipping_tier || "",
      // Liste / atıf
      affiliation: eventData.affiliation || "FACETTE Online",
      list_id: eventData.list_id || "",
      list_name: eventData.list_name || "",
      promotion_id: eventData.promotion_id || "",
      promotion_name: eventData.promotion_name || "",
      // Context
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

function productToItem(p, variant = null, opts = {}) {
  // GA4 Enhanced E-commerce — kalem bazlı tüm parametreler
  const listPrice = Number(p.price ?? 0);
  const salePrice = Number(p.sale_price ?? p.price ?? 0);
  const finalPrice = Number(opts.unitPrice ?? salePrice);
  const qty = Number(opts.quantity ?? variant?.quantity ?? 1);
  // GA4 spec: 'discount' = liste fiyatı − ödenen fiyat (kalem başı, pozitif sayı)
  const discount = Number((listPrice - finalPrice).toFixed(2));

  // Kategori breadcrumb → item_category, item_category2, …
  const crumbs = (p.breadcrumb || "")
    .split(/[>›\/]/)
    .map((s) => s.trim())
    .filter(Boolean);

  const item = {
    item_id: String(p.id || p.product_id || p.sku || p.stock_code || ""),
    // Meta katalog eşleşmesi: katalog beden başına Ticimax varyant ID'siyle beslendiği
    // için Meta content_ids = SEÇİLİ varyantın id'si olmalı. Varyant id yoksa ana ürün
    // id'sine düşer. (GA4/Google ana id'de kalır; bunu yalnızca Meta kullanır.)
    content_id: String(
      (variant && variant.id != null && variant.id !== "") ? variant.id
      : (p.catalog_id != null && p.catalog_id !== "") ? p.catalog_id
      : (p.id || p.product_id || p.sku || p.stock_code || "")
    ),
    item_name: p.name || "",
    item_brand: p.brand || p.vendor || "FACETTE",
    item_category: crumbs[0] || p.category_name || "",
    item_variant: variant
      ? `${variant.size || ""} ${variant.color || p.color || ""}`.trim()
      : (p.color || ""),
    // Fiyat alanları
    price: finalPrice,              // GA4 uses 'price' as the *unit* price (final)
    list_price: listPrice,          // Custom: indirimsiz liste fiyatı
    sale_price: salePrice,
    discount: discount > 0 ? discount : 0,
    currency: opts.currency || "TRY",
    quantity: qty,
    // Stok varyant ekleri
    sku: p.sku || p.stock_code || "",
    size: variant?.size || "",
    color: variant?.color || p.color || "",
    barcode: variant?.barcode || "",
    // Liste / atıf
    item_list_id: opts.listId || "",
    item_list_name: opts.listName || "",
    index: opts.index ?? undefined,
    affiliation: opts.affiliation || "FACETTE Online",
    // Promosyon
    coupon: opts.coupon || "",
    promotion_id: opts.promotionId || "",
    promotion_name: opts.promotionName || "",
  };
  if (crumbs[1]) item.item_category2 = crumbs[1];
  if (crumbs[2]) item.item_category3 = crumbs[2];
  if (crumbs[3]) item.item_category4 = crumbs[3];
  if (crumbs[4]) item.item_category5 = crumbs[4];
  return item;
}

export const trackViewItem = ({ product, currency = "TRY", listId = "", listName = "", user = {} }) =>
  pushEvent("view_item", {
    currency,
    value: Number(product.sale_price ?? product.price ?? 0),
    original_value: Number(product.price ?? 0),
    discount: Math.max(0, Number(product.price ?? 0) - Number(product.sale_price ?? product.price ?? 0)),
    items: [productToItem(product, null, { currency, listId, listName })],
    list_id: listId, list_name: listName,
  }, user);

export const trackViewItemList = ({ products, listId = "", listName = "", currency = "TRY", user = {} }) =>
  pushEvent("view_item_list", {
    currency, value: 0,
    items: (products || []).map((p, idx) => productToItem(p, null, { currency, listId, listName, index: idx })),
    category: listName,
    list_id: listId, list_name: listName,
  }, user);

export const trackAddToCart = ({ product, variant, quantity = 1, currency = "TRY", coupon = "", user = {} }) => {
  const unitPrice = Number(variant?.price ?? product.sale_price ?? product.price ?? 0);
  const listPrice = Number(product.price ?? unitPrice);
  const lineValue = unitPrice * quantity;
  const lineDiscount = Math.max(0, (listPrice - unitPrice) * quantity);
  return pushEvent("add_to_cart", {
    currency, value: lineValue, original_value: listPrice * quantity, discount: lineDiscount, coupon,
    items: [productToItem(product, variant, { currency, quantity, unitPrice, coupon })],
  }, user);
};

export const trackRemoveFromCart = ({ product, variant, quantity = 1, currency = "TRY", user = {} }) => {
  const unitPrice = Number(variant?.price ?? product.sale_price ?? product.price ?? 0);
  return pushEvent("remove_from_cart", {
    currency, value: unitPrice * quantity,
    items: [productToItem(product, variant, { currency, quantity, unitPrice })],
  }, user);
};

export const trackBeginCheckout = ({ items, value, currency = "TRY", coupon = "", discount = 0,
                                     original_value = 0, shipping = 0, tax = 0, user = {} }) =>
  pushEvent("begin_checkout", {
    currency, value, items, coupon, discount, original_value, shipping, tax,
  }, user);

export const trackAddPaymentInfo = ({ items, value, currency = "TRY", coupon = "", discount = 0,
                                      payment_type = "", shipping = 0, tax = 0, user = {} }) =>
  pushEvent("add_payment_info", {
    currency, value, items, coupon, discount, payment_type, shipping, tax,
  }, user);

export const trackPurchase = ({ orderNumber, items, value, currency = "TRY", coupon = "", discount = 0,
                                original_value = 0, shipping = 0, tax = 0, shipping_tier = "",
                                payment_type = "", user = {} }) =>
  pushEvent("purchase", {
    order_id: orderNumber, currency, value, items, coupon, discount, original_value,
    shipping, tax, shipping_tier, payment_type,
  }, user);

export const trackSearch = ({ keyword, user = {} }) =>
  pushEvent("search", { search_term: keyword }, user);

// --- GA4-only funnel event'leri (yalnızca dataLayer; native pixel/CAPI atlanır) ---

/** Ürün kartına tıklama (liste → ürün). product + liste bağlamı. */
export const trackSelectItem = ({ product, currency = "TRY", listId = "", listName = "", index, user = {} }) =>
  pushEvent("select_item", {
    currency,
    value: 0,
    items: [productToItem(product, null, { currency, listId, listName, index })],
    list_id: listId,
    list_name: listName,
  }, user);

/** Sepet sayfası görüntüleme. items = sepet satırları (eşlenmiş GA4 item'ları), value = sepet toplamı. */
export const trackViewCart = ({ items = [], value = 0, currency = "TRY", coupon = "", user = {} }) =>
  pushEvent("view_cart", { currency, value: Number(value) || 0, items, coupon }, user);

/** Teslimat bilgisi girildi (GA4 funnel: add_shipping_info). */
export const trackAddShippingInfo = ({ items = [], value = 0, currency = "TRY", coupon = "",
                                       discount = 0, shipping = 0, shipping_tier = "", user = {} }) =>
  pushEvent("add_shipping_info", {
    currency, value: Number(value) || 0, items, coupon, discount, shipping, shipping_tier,
  }, user);

/** Promosyon/banner tıklama (hero, kampanya bannerı). */
export const trackSelectPromotion = ({ promotionId = "", promotionName = "", product = null,
                                       currency = "TRY", user = {} }) =>
  pushEvent("select_promotion", {
    currency,
    value: 0,
    promotion_id: promotionId,
    promotion_name: promotionName,
    items: product ? [productToItem(product, null, { currency, promotionId, promotionName })] : [],
  }, user);

export default {
  trackViewItem, trackViewItemList, trackAddToCart, trackRemoveFromCart,
  trackBeginCheckout, trackAddPaymentInfo, trackPurchase, trackSearch,
  trackSelectItem, trackViewCart, trackAddShippingInfo, trackSelectPromotion,
  generateEventId, collectClickIds,
};
