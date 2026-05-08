import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import axios from "axios";
import { X, Plus, Minus, ShoppingBag, Sparkles } from "lucide-react";
import { useCart } from "../context/CartContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function CartDrawer() {
  const { items, isOpen, setIsOpen, removeItem, updateQuantity, addItem, total, itemCount } = useCart();
  const freeShippingLimit = 500;
  const remaining = Math.max(0, freeShippingLimit - total);

  const [suggestions, setSuggestions] = useState([]);
  const [bestsellers, setBestsellers] = useState([]);

  // Sepet ürünlerine göre kombin önerisi (cart-suggestions API)
  useEffect(() => {
    if (!isOpen || items.length === 0) return;
    const productIds = items.map((i) => i.product_id || i.id).filter(Boolean);
    if (!productIds.length) return;
    axios.post(`${API}/products/cart-suggestions`, { product_ids: productIds, limit: 4 })
      .then((r) => setSuggestions((r.data?.suggestions || []).slice(0, 4)))
      .catch(() => setSuggestions([]));
  }, [isOpen, items.length]);

  // Bu ay en çok satan ürünler (sort=popular)
  useEffect(() => {
    if (!isOpen) return;
    if (bestsellers.length > 0) return;
    axios.get(`${API}/products?limit=6&sort=popular`)
      .then((r) => setBestsellers((r.data?.products || []).slice(0, 6)))
      .catch(() => setBestsellers([]));
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 animate-fade-in"
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <div
        className="fixed inset-y-0 right-0 z-50 w-full sm:w-[400px] bg-white shadow-2xl flex flex-col animate-slide-right"
        data-testid="cart-drawer"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-black/10">
          <h2 className="text-[11px] tracking-[0.3em] uppercase text-black">
            Sepetim ({itemCount})
          </h2>
          <button
            onClick={() => setIsOpen(false)}
            className="p-2 -mr-2 hover:opacity-60 transition-opacity"
            data-testid="close-cart"
            aria-label="Kapat"
          >
            <X size={18} strokeWidth={1.4} />
          </button>
        </div>

        {/* Free Shipping Progress */}
        {remaining > 0 && items.length > 0 && (
          <div className="px-5 py-3 bg-stone-50 border-b border-black/5">
            <p className="text-[11px] text-center mb-2 text-black/70">
              Ücretsiz kargo için <span className="font-medium text-black">{remaining.toFixed(2)} TL</span> daha
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
        <div className="flex-1 overflow-y-auto px-5">
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-center py-16">
              <ShoppingBag size={36} strokeWidth={1.2} className="text-black/30 mb-4" />
              <p className="text-sm text-black/60 mb-6">Sepetiniz boş</p>
              <button
                onClick={() => setIsOpen(false)}
                className="px-6 h-10 border border-black text-xs uppercase tracking-[0.25em] hover:bg-black hover:text-white transition-colors"
              >
                Alışverişe başla
              </button>
            </div>
          ) : (
            <ul className="divide-y divide-black/10">
              {items.map((item) => (
                <li key={item.id} className="flex gap-4 py-5">
                  <Link
                    to={`/urun/${item.slug || item.productId}`}
                    onClick={() => setIsOpen(false)}
                    className="flex-shrink-0"
                  >
                    <img
                      src={item.image}
                      alt={item.name}
                      className="w-20 h-28 object-cover bg-stone-100 hover:opacity-90 transition-opacity"
                    />
                  </Link>
                  <div className="flex-1 min-w-0">
                    <Link
                      to={`/urun/${item.slug || item.productId}`}
                      onClick={() => setIsOpen(false)}
                      className="block hover:underline"
                    >
                      <h3 className="text-sm font-medium leading-tight line-clamp-2">{item.name}</h3>
                    </Link>
                    <div className="mt-1 space-y-0.5 text-[11px] text-black/55">
                      {item.color && <p>Renk: {item.color}</p>}
                      {item.size && <p>Beden: {item.size}</p>}
                    </div>
                    <p className="text-sm font-medium mt-2 tabular-nums">{item.price.toFixed(2)} TL</p>

                    <div className="flex items-center justify-between mt-3">
                      <div className="inline-flex items-center border border-black/15">
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          className="p-1.5 hover:bg-black/5 transition-colors disabled:opacity-30"
                          disabled={item.quantity <= 1}
                          data-testid={`decrease-${item.id}`}
                          aria-label="Azalt"
                        >
                          <Minus size={12} />
                        </button>
                        <span className="px-3 text-xs tabular-nums">{item.quantity}</span>
                        <button
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          className="p-1.5 hover:bg-black/5 transition-colors"
                          data-testid={`increase-${item.id}`}
                          aria-label="Arttır"
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                      <button
                        onClick={() => removeItem(item.id)}
                        className="text-[11px] text-black/55 hover:text-black underline"
                        data-testid={`remove-${item.id}`}
                      >
                        Kaldır
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        {items.length > 0 && (
          <>
            {/* Kombin Önerileri (cart-suggestions) */}
            {suggestions.length > 0 && (
              <div className="border-t border-black/5 px-5 py-3 bg-gray-50/60" data-testid="drawer-combo">
                <p className="text-[10px] tracking-[0.25em] uppercase text-black/70 mb-2 flex items-center gap-1.5">
                  <Sparkles size={11} /> Stilini Tamamla
                </p>
                <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1">
                  {suggestions.map((s) => (
                    <Link
                      key={s.id}
                      to={`/urun/${s.slug || s.id}`}
                      className="flex-shrink-0 w-20 group"
                      onClick={() => setIsOpen(false)}
                      data-testid={`drawer-combo-${s.id}`}
                    >
                      <div className="w-20 h-24 bg-white border border-gray-100 overflow-hidden">
                        <img src={(s.images?.[0]) || s.thumbnail || ""} alt={s.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                      </div>
                      <p className="text-[10px] mt-1 line-clamp-1 leading-tight">{s.name}</p>
                      <p className="text-[10px] tabular-nums text-black/70">{((s.sale_price && s.sale_price > 0) ? s.sale_price : s.price || 0).toFixed(0)} TL</p>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Bu Ay En Çok Satanlar */}
            {bestsellers.length > 0 && (
              <div className="border-t border-black/5 px-5 py-3" data-testid="drawer-bestsellers">
                <p className="text-[10px] tracking-[0.25em] uppercase text-black/70 mb-2">
                  Bu Ay En Çok Satanlar
                </p>
                <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-1 px-1">
                  {bestsellers.map((s) => (
                    <Link
                      key={s.id}
                      to={`/urun/${s.slug || s.id}`}
                      className="flex-shrink-0 w-20 group"
                      onClick={() => setIsOpen(false)}
                      data-testid={`drawer-bs-${s.id}`}
                    >
                      <div className="w-20 h-24 bg-gray-50 border border-gray-100 overflow-hidden">
                        <img src={(s.images?.[0]) || s.thumbnail || ""} alt={s.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform" />
                      </div>
                      <p className="text-[10px] mt-1 line-clamp-1 leading-tight">{s.name}</p>
                      <p className="text-[10px] tabular-nums text-black/70">{((s.sale_price && s.sale_price > 0) ? s.sale_price : s.price || 0).toFixed(0)} TL</p>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            <div className="border-t border-black/10 px-5 py-4 space-y-3">
            <div className="flex justify-between items-baseline">
              <span className="text-xs tracking-[0.2em] uppercase text-black/60">Ara Toplam</span>
              <span className="text-base font-medium tabular-nums">{total.toFixed(2)} TL</span>
            </div>
            {remaining <= 0 && (
              <p className="text-[11px] text-emerald-700 text-center">
                Ücretsiz kargo kazandınız
              </p>
            )}
            <Link
              to="/odeme"
              className="flex items-center justify-center w-full h-12 bg-black text-white text-xs uppercase tracking-[0.25em] hover:bg-black/85 transition-colors"
              onClick={() => setIsOpen(false)}
              data-testid="go-to-checkout"
            >
              Ödemeye Geç
            </Link>
            <Link
              to="/sepet"
              className="flex items-center justify-center w-full h-11 border border-black text-xs uppercase tracking-[0.25em] hover:bg-black hover:text-white transition-colors"
              onClick={() => setIsOpen(false)}
              data-testid="go-to-cart"
            >
              Sepete Git
            </Link>
            </div>
          </>
        )}
      </div>
    </>
  );
}
