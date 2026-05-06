import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Trash2, Plus, Minus } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import { useCart } from "../context/CartContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Cart() {
  const { items, removeItem, updateQuantity, total, itemCount } = useCart();
  const freeShippingLimit = 500;
  const remaining = Math.max(0, freeShippingLimit - total);
  const shippingCost = total >= freeShippingLimit ? 0 : 29.90;
  const grandTotal = total + shippingCost;

  // Kombin / sale öneriler
  const [suggestions, setSuggestions] = useState([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);

  useEffect(() => {
    if (items.length === 0) { setSuggestions([]); return; }
    let cancel = false;
    setSuggestionsLoading(true);
    const productIds = items.map((it) => it.productId).filter(Boolean);
    axios.post(`${API}/products/cart-suggestions`, { product_ids: productIds, limit: 8 })
      .then((r) => { if (!cancel) setSuggestions(r.data?.items || []); })
      .catch(() => { if (!cancel) setSuggestions([]); })
      .finally(() => { if (!cancel) setSuggestionsLoading(false); });
    return () => { cancel = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items.length]);

  if (items.length === 0) {
    return (
      <div className="min-h-screen bg-white" data-testid="cart-page">
        <Header />
        <div className="container-main py-24 text-center">
          <p className="text-[10px] tracking-[0.3em] text-black/50 uppercase mb-6">SEPETİM</p>
          <h1 className="text-3xl sm:text-4xl font-light tracking-tight mb-4">Sepetiniz boş</h1>
          <p className="text-sm text-black/60 mb-10 max-w-md mx-auto">
            Henüz sepetinize ürün eklemediniz. Yeni sezon parçaları keşfetmek için alışverişe başlayın.
          </p>
          <Link
            to="/"
            className="inline-flex items-center justify-center h-12 px-10 bg-black text-white text-xs uppercase tracking-[0.25em] hover:bg-black/85 transition-colors"
            data-testid="empty-cart-shop-btn"
          >
            Alışverişe başla
          </Link>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white pb-32 md:pb-12" data-testid="cart-page">
      <Header />

      <div className="container-main py-6 md:py-12">
        <div className="mb-8 md:mb-10">
          <p className="text-[10px] tracking-[0.3em] text-black/50 uppercase mb-2">SEPETİM</p>
          <h1 className="text-2xl sm:text-3xl font-light tracking-tight">
            {itemCount} ürün
          </h1>
        </div>

        <div className="grid lg:grid-cols-3 gap-8 lg:gap-12">
          {/* Cart Items */}
          <div className="lg:col-span-2">
            {/* Free Shipping Progress */}
            {remaining > 0 && (
              <div className="mb-8 p-4 bg-stone-50 border border-black/5">
                <p className="text-xs text-center mb-2 text-black/70">
                  Ücretsiz kargo için <span className="font-medium text-black">{remaining.toFixed(2)} TL</span> daha ekleyin
                </p>
                <div className="h-[2px] bg-black/10 overflow-hidden">
                  <div
                    className="h-full bg-black transition-all duration-700 ease-out"
                    style={{ width: `${Math.min(100, (total / freeShippingLimit) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Items */}
            <div className="divide-y divide-black/10">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="flex gap-4 sm:gap-6 py-6"
                  data-testid={`cart-item-${item.id}`}
                >
                  <Link to={`/urun/${item.slug || item.productId || ""}`} className="shrink-0">
                    <img
                      src={item.image}
                      alt={item.name}
                      className="w-24 h-32 sm:w-32 sm:h-40 object-cover bg-stone-100"
                    />
                  </Link>
                  <div className="flex-1 min-w-0 flex flex-col">
                    <div className="flex justify-between items-start gap-3">
                      <div className="min-w-0">
                        <Link
                          to={`/urun/${item.slug || item.productId || ""}`}
                          className="block"
                        >
                          <h3 className="text-sm sm:text-base font-medium leading-tight line-clamp-2 hover:underline">
                            {item.name}
                          </h3>
                        </Link>
                        <div className="mt-2 space-y-0.5 text-xs text-black/60">
                          {item.color && <p>Renk: {item.color}</p>}
                          {item.size && <p>Beden: {item.size}</p>}
                        </div>
                      </div>
                      <button
                        onClick={() => removeItem(item.id)}
                        className="text-black/40 hover:text-black transition-colors p-1 -m-1"
                        data-testid={`remove-cart-${item.id}`}
                        aria-label="Ürünü kaldır"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>

                    <div className="flex items-center justify-between mt-auto pt-4">
                      <div className="inline-flex items-center border border-black/15">
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          className="p-2 hover:bg-black/5 transition-colors disabled:opacity-30"
                          disabled={item.quantity <= 1}
                          aria-label="Azalt"
                        >
                          <Minus size={12} />
                        </button>
                        <span className="px-3 sm:px-4 text-xs sm:text-sm tabular-nums">{item.quantity}</span>
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          className="p-2 hover:bg-black/5 transition-colors"
                          aria-label="Arttır"
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                      <p className="text-sm sm:text-base font-medium tabular-nums">
                        {(item.price * item.quantity).toFixed(2)} TL
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Summary - desktop only sticky sidebar */}
          <div className="lg:col-span-1">
            <div className="bg-stone-50 p-6 lg:sticky lg:top-32 border border-black/5">
              <h2 className="text-[10px] tracking-[0.3em] uppercase text-black/60 mb-5">Sipariş Özeti</h2>

              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-black/60">Ara toplam</span>
                  <span className="tabular-nums">{total.toFixed(2)} TL</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-black/60">Kargo</span>
                  <span className={shippingCost === 0 ? "text-emerald-700" : "tabular-nums"}>
                    {shippingCost === 0 ? "Ücretsiz" : `${shippingCost.toFixed(2)} TL`}
                  </span>
                </div>
                <div className="border-t border-black/10 pt-3 flex justify-between text-base">
                  <span className="font-medium">Toplam</span>
                  <span className="font-medium tabular-nums">{grandTotal.toFixed(2)} TL</span>
                </div>
              </div>

              <Link
                to="/odeme"
                className="hidden md:flex items-center justify-center w-full h-14 mt-6 bg-black text-white text-xs uppercase tracking-[0.25em] hover:bg-black/85 transition-colors"
                data-testid="checkout-btn-desktop"
              >
                Ödemeye Geç
              </Link>

              <Link
                to="/"
                className="block text-center text-xs underline mt-4 text-black/60 hover:text-black transition-colors"
              >
                Alışverişe devam et
              </Link>
            </div>
          </div>
        </div>

        {/* Stilini Tamamla — sadece görsel grid */}
        {(suggestions.length > 0 || suggestionsLoading) && (
          <div className="mt-16 md:mt-24 pt-10 md:pt-14 border-t border-black/10" data-testid="cart-suggestions-block">
            <div className="mb-6 md:mb-10">
              <p className="text-[10px] tracking-[0.3em] text-black/50 uppercase mb-2">Tarzını Tamamla</p>
              <h2 className="text-xl sm:text-2xl font-light tracking-tight">Stilini tamamla</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 sm:gap-5">
              {suggestions.map((p) => {
                const img = (p.images && p.images[0]) || p.image || "";
                return (
                  <Link
                    key={p.id}
                    to={`/urun/${p.slug || p.id}`}
                    className="group relative block overflow-hidden bg-stone-100 aspect-[3/4]"
                    data-testid={`cart-suggestion-${p.id}`}
                    aria-label={p.name}
                  >
                    <img
                      src={img}
                      alt={p.name}
                      className="w-full h-full object-cover transition-transform duration-700 ease-out group-hover:scale-105"
                      loading="lazy"
                    />
                    <div className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-3 sm:p-4">
                      <span className="text-white text-[10px] uppercase tracking-[0.25em] translate-y-3 group-hover:translate-y-0 transition-transform duration-300 ease-out">
                        Detayı gör
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Sticky bottom mobile CTA */}
      <div
        className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-black/10 px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)+12px)] md:hidden shadow-[0_-4px_20px_rgba(0,0,0,0.05)]"
        data-testid="cart-mobile-sticky-cta"
      >
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-black/60">Toplam</span>
          <span className="text-sm font-medium tabular-nums">{grandTotal.toFixed(2)} TL</span>
        </div>
        <Link
          to="/odeme"
          className="flex items-center justify-center w-full h-12 bg-black text-white text-xs uppercase tracking-[0.25em] hover:bg-black/85 active:bg-black/85 transition-colors"
          data-testid="checkout-btn"
        >
          Ödemeye Geç
        </Link>
      </div>

      <Footer />
    </div>
  );
}
