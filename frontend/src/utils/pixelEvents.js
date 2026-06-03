/**
 * =============================================================================
 * pixelEvents.js — Backwards-compatible bridge to new dataLayer.js
 * =============================================================================
 * Eski API (trackViewContent, trackAddToCart, trackInitiateCheckout, trackPurchase)
 * geriye uyumlu olacak şekilde, yeni `lib/dataLayer.js` (GA4 schema + CAPI
 * mirror + event_id dedup) üzerinden çalıştırılır.
 *
 * Bu sayede mevcut sayfalardaki import'ları değiştirmeden sunucu taraflı
 * (Conversions API) gönderim devreye girer.
 * =============================================================================
 */
import {
  trackViewItem,
  trackAddToCart as _trackAddToCart,
  trackBeginCheckout,
  trackPurchase as _trackPurchase,
  trackViewItemList,
  trackAddPaymentInfo,
  trackRemoveFromCart,
  trackSearch as _trackSearch,
} from "../lib/dataLayer";

/** Ürün detay görüntüleme — eski imza */
export function trackViewContent({ product_id, name, category, price, brand, color }) {
  return trackViewItem({
    product: {
      id: product_id, name, category_name: category,
      brand: brand || "FACETTE", color: color || "",
      sale_price: Number(price) || 0, price: Number(price) || 0,
    },
  });
}

/** Sepete ekleme — eski imza */
export function trackAddToCart({ product_id, name, category, price, quantity = 1, size, color }) {
  return _trackAddToCart({
    product: {
      id: product_id, name, category_name: category,
      sale_price: Number(price) || 0, price: Number(price) || 0,
    },
    variant: size || color ? { size, color, price: Number(price) || 0 } : null,
    quantity,
  });
}

/** Checkout başladı — eski imza */
export function trackInitiateCheckout({ total, items = [], coupon }) {
  const mapped = items.map((i) => ({
    item_id: String(i.product_id || i.productId || i.id || ""),
    item_name: i.name || i.title || "",
    price: Number(i.price) || 0,
    quantity: Number(i.quantity) || 1,
  }));
  return trackBeginCheckout({
    items: mapped, value: Number(total) || 0, coupon,
  });
}

/** Satın alma tamamlandı — eski imza */
export function trackPurchase({ order_id, total, items = [], coupon, currency = "TRY", user }) {
  const mapped = items.map((i) => ({
    item_id: String(i.product_id || i.productId || i.id || ""),
    item_name: i.name || i.title || "",
    price: Number(i.price) || 0,
    quantity: Number(i.quantity) || 1,
  }));
  return _trackPurchase({
    orderNumber: order_id, value: Number(total) || 0,
    items: mapped, coupon, currency, user,
  });
}

// Re-exports — new API kullanmak isteyenler için
export {
  trackViewItem, trackViewItemList,
  trackAddPaymentInfo, trackRemoveFromCart, trackBeginCheckout,
};
export const trackSearch = _trackSearch;
