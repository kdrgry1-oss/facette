/**
 * =============================================================================
 * pixelEvents.js — FAZ 9 Potansiyel İyileştirme
 * =============================================================================
 * Meta Pixel + GA4 için e-ticaret olay tetikleyici helper'ı.
 *
 * Kullanım:
 *   import { trackViewContent, trackAddToCart, trackPurchase } from "./pixelEvents";
 *   trackAddToCart({ product_id, name, price, currency: "TRY", quantity });
 *
 * Backend tarafında marketing_pixels aktif olmalı. Bu helper yalnızca
 * window.fbq ve window.gtag varsa çağrı yapar — pasif ise sessizce no-op olur.
 * =============================================================================
 */

const CURRENCY = "TRY";

function _fbq(...args) {
  if (typeof window !== "undefined" && typeof window.fbq === "function") {
    try { window.fbq(...args); } catch { /* no-op */ }
  }
}

function _gtag(...args) {
  if (typeof window !== "undefined" && typeof window.gtag === "function") {
    try { window.gtag(...args); } catch { /* no-op */ }
  }
}

/** Ürün detay görüntüleme */
export function trackViewContent({ product_id, name, category, price }) {
  _fbq("track", "ViewContent", {
    content_type: "product",
    content_ids: [product_id],
    content_name: name,
    content_category: category,
    currency: CURRENCY,
    value: Number(price) || 0,
  });
  _gtag("event", "view_item", {
    currency: CURRENCY,
    value: Number(price) || 0,
    items: [{
      item_id: product_id, item_name: name, item_category: category,
      price: Number(price) || 0, quantity: 1,
    }],
  });
}

/** Sepete ekleme */
export function trackAddToCart({ product_id, name, category, price, quantity = 1 }) {
  const value = (Number(price) || 0) * (quantity || 1);
  _fbq("track", "AddToCart", {
    content_type: "product",
    content_ids: [product_id],
    content_name: name,
    currency: CURRENCY,
    value,
  });
  _gtag("event", "add_to_cart", {
    currency: CURRENCY,
    value,
    items: [{
      item_id: product_id, item_name: name, item_category: category,
      price: Number(price) || 0, quantity,
    }],
  });
}

/** Checkout başladı */
export function trackInitiateCheckout({ total, items = [] }) {
  _fbq("track", "InitiateCheckout", {
    currency: CURRENCY,
    value: Number(total) || 0,
    num_items: items.length,
    content_ids: items.map((i) => i.product_id || i.productId).filter(Boolean),
  });
  _gtag("event", "begin_checkout", {
    currency: CURRENCY,
    value: Number(total) || 0,
    items: items.map((i) => ({
      item_id: i.product_id || i.productId, item_name: i.name,
      price: Number(i.price) || 0, quantity: Number(i.quantity || 1),
    })),
  });
}

/** Satın alma tamamlandı (conversion) */
export function trackPurchase({ order_id, total, tax = 0, shipping = 0, items = [] }) {
  _fbq("track", "Purchase", {
    currency: CURRENCY,
    value: Number(total) || 0,
    content_type: "product",
    content_ids: items.map((i) => i.product_id || i.productId).filter(Boolean),
    num_items: items.length,
  });
  _gtag("event", "purchase", {
    transaction_id: order_id,
    currency: CURRENCY,
    value: Number(total) || 0,
    tax: Number(tax) || 0,
    shipping: Number(shipping) || 0,
    items: items.map((i) => ({
      item_id: i.product_id || i.productId, item_name: i.name,
      price: Number(i.price) || 0, quantity: Number(i.quantity || 1),
    })),
  });
}

/** Arama */
export function trackSearch(query) {
  _fbq("track", "Search", { search_string: query });
  _gtag("event", "search", { search_term: query });
}

/** Üyelik tamamlandı */
export function trackCompleteRegistration(method = "email") {
  _fbq("track", "CompleteRegistration", { status: true });
  _gtag("event", "sign_up", { method });
}
