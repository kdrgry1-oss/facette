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
      <div className="min-h-screen" data-testid="cart-page">
        <Header />
        <div className="container-main py-16 text-center">
          <h1 className="text-2xl font-medium mb-4">Sepetiniz Boş</h1>
          <p className="text-gray-500 mb-8">Henüz sepetinize ürün eklemediniz.</p>
          <Link to="/" className="btn-primary">Alışverişe Başla</Link>
        </div>
        <Footer />
      </div>
    );
  }

  return (
    <div className="min-h-screen" data-testid="cart-page">
      <Header />

      <div className="container-main py-8">
        <h1 className="text-2xl font-medium mb-8">Sepetim ({itemCount} Ürün)</h1>

        <div className="grid lg:grid-cols-3 gap-8">
          {/* Cart Items */}
          <div className="lg:col-span-2">
            {/* Free Shipping Progress */}
            {remaining > 0 && (
              <div className="mb-6 p-4 bg-gray-50">
                <p className="text-sm text-center mb-2">
                  Ücretsiz kargo için <span className="font-semibold">{remaining.toFixed(2)} TL</span> daha ekleyin
                </p>
                <div className="h-1 bg-gray-200 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-black transition-all duration-500"
                    style={{ width: `${Math.min(100, (total / freeShippingLimit) * 100)}%` }}
                  />
                </div>
              </div>
            )}

            {/* Items */}
            <div className="space-y-4">
              {items.map((item) => (
                <div key={item.id} className="flex gap-4 p-4 border border-gray-100" data-testid={`cart-item-${item.id}`}>
                  <img 
                    src={item.image} 
                    alt={item.name}
                    className="w-24 h-32 object-cover bg-gray-100"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between">
                      <div>
                        <h3 className="font-medium">{item.name}</h3>
                        {item.size && <p className="text-sm text-gray-500 mt-1">Beden: {item.size}</p>}
                        {item.color && <p className="text-sm text-gray-500">Renk: {item.color}</p>}
                      </div>
                      <button 
                        onClick={() => removeItem(item.id)}
                        className="text-gray-400 hover:text-red-500"
                        data-testid={`remove-cart-${item.id}`}
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                    
                    <div className="flex items-center justify-between mt-4">
                      <div className="flex items-center border border-gray-300">
                        <button 
                          onClick={() => updateQuantity(item.id, item.quantity - 1)}
                          className="p-2 hover:bg-gray-100"
                        >
                          <Minus size={14} />
                        </button>
                        <span className="px-4 text-sm">{item.quantity}</span>
                        <button 
                          onClick={() => updateQuantity(item.id, item.quantity + 1)}
                          className="p-2 hover:bg-gray-100"
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                      <p className="font-medium">{(item.price * item.quantity).toFixed(2)} TL</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div className="lg:col-span-1">
            <div className="bg-gray-50 p-6 sticky top-24">
              <h2 className="text-lg font-medium mb-4">Sipariş Özeti</h2>
              
              <div className="space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600">Ara Toplam</span>
                  <span>{total.toFixed(2)} TL</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Kargo</span>
                  <span className={shippingCost === 0 ? "text-green-600" : ""}>
                    {shippingCost === 0 ? "Ücretsiz" : `${shippingCost.toFixed(2)} TL`}
                  </span>
                </div>
                <div className="border-t pt-3 flex justify-between text-base font-medium">
                  <span>Toplam</span>
                  <span>{(total + shippingCost).toFixed(2)} TL</span>
                </div>
              </div>

              <Link 
                to="/odeme" 
                className="btn-primary w-full text-center block mt-6"
                data-testid="checkout-btn"
              >
                Ödemeye Geç
              </Link>
              
              <Link 
                to="/" 
                className="block text-center text-sm underline mt-4 text-gray-600 hover:text-black"
              >
                Alışverişe Devam Et
              </Link>
            </div>
          </div>
        </div>

        {/* Kombin Ürün Önerileri */}
        {(suggestions.length > 0 || suggestionsLoading) && (
          <div className="mt-16 pt-12 border-t border-stone-200" data-testid="cart-suggestions-block">
            <div className="mb-8 text-center">
              <p className="text-[10px] tracking-[0.3em] text-stone-400 uppercase mb-2">
                {suggestions.some((s) => s._source === "combine") ? "BU ÜRÜNLERLE YAKIŞANLAR" : "BEĞENEBİLECEKLERİN"}
              </p>
              <h2 className="text-2xl font-light tracking-wide text-stone-900">Tarzına Tamamla</h2>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 sm:gap-6">
              {suggestions.map((p) => {
                const img = (p.images && p.images[0]) || p.image || "";
                const hasDiscount = p.discount_price && p.discount_price > 0 && p.discount_price < p.price;
                return (
                  <Link key={p.id} to={`/urun/${p.slug || p.id}`}
                    className="group block" data-testid={`cart-suggestion-${p.id}`}>
                    <div className="relative aspect-[3/4] bg-stone-50 overflow-hidden mb-3">
                      <img src={img} alt={p.name}
                        className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                      {p._source === "combine" && (
                        <span className="absolute top-2 left-2 bg-stone-900 text-white text-[9px] tracking-wider px-2 py-1 uppercase">Kombin</span>
                      )}
                      {p._source === "sale" && hasDiscount && (
                        <span className="absolute top-2 left-2 bg-red-600 text-white text-[9px] tracking-wider px-2 py-1 uppercase">İndirim</span>
                      )}
                    </div>
                    <h3 className="text-sm text-stone-900 mb-1 line-clamp-2 group-hover:underline">{p.name}</h3>
                    <div className="flex items-baseline gap-2">
                      {hasDiscount ? (
                        <>
                          <span className="text-sm font-medium text-stone-900">{p.discount_price.toFixed(2)} TL</span>
                          <span className="text-xs text-stone-400 line-through">{p.price.toFixed(2)} TL</span>
                        </>
                      ) : (
                        <span className="text-sm text-stone-900">{(p.price || 0).toFixed(2)} TL</span>
                      )}
                    </div>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <Footer />
    </div>
  );
}
