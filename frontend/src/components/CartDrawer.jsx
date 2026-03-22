import { Link } from "react-router-dom";
import { X, Plus, Minus, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";

export default function CartDrawer() {
  const { items, isOpen, setIsOpen, removeItem, updateQuantity, total, itemCount } = useCart();
  const freeShippingLimit = 500;
  const remaining = Math.max(0, freeShippingLimit - total);

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div 
        className="fixed inset-0 bg-black/50 z-40 animate-fade-in"
        onClick={() => setIsOpen(false)}
      />

      {/* Drawer */}
      <div className="cart-drawer open" data-testid="cart-drawer">
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <h2 className="text-lg font-semibold tracking-wider uppercase">
              Sepetim ({itemCount})
            </h2>
            <button onClick={() => setIsOpen(false)} className="p-2 hover:bg-gray-100 rounded-full" data-testid="close-cart">
              <X size={20} />
            </button>
          </div>

          {/* Free Shipping Progress */}
          {remaining > 0 && items.length > 0 && (
            <div className="p-4 bg-gray-50 border-b">
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
          <div className="flex-1 overflow-y-auto p-4">
            {items.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <ShoppingBag size={48} className="text-gray-300 mb-4" />
                <p className="text-gray-500 mb-4">Sepetiniz boş</p>
                <button 
                  onClick={() => setIsOpen(false)}
                  className="btn-secondary text-xs"
                >
                  Alışverişe Başla
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                {items.map((item) => (
                  <div key={item.id} className="flex gap-4 pb-4 border-b border-gray-100">
                    <img 
                      src={item.image} 
                      alt={item.name}
                      className="w-20 h-28 object-cover bg-gray-100"
                    />
                    <div className="flex-1 min-w-0">
                      <h3 className="text-sm font-medium truncate">{item.name}</h3>
                      {item.size && <p className="text-xs text-gray-500 mt-1">Beden: {item.size}</p>}
                      {item.color && <p className="text-xs text-gray-500">Renk: {item.color}</p>}
                      <p className="text-sm font-medium mt-2">{item.price.toFixed(2)} TL</p>
                      
                      <div className="flex items-center gap-4 mt-3">
                        <div className="flex items-center border border-gray-300">
                          <button 
                            onClick={() => updateQuantity(item.id, item.quantity - 1)}
                            className="p-1 hover:bg-gray-100"
                            data-testid={`decrease-${item.id}`}
                          >
                            <Minus size={14} />
                          </button>
                          <span className="px-3 text-sm">{item.quantity}</span>
                          <button 
                            onClick={() => updateQuantity(item.id, item.quantity + 1)}
                            className="p-1 hover:bg-gray-100"
                            data-testid={`increase-${item.id}`}
                          >
                            <Plus size={14} />
                          </button>
                        </div>
                        <button 
                          onClick={() => removeItem(item.id)}
                          className="text-xs text-gray-500 hover:text-black underline"
                          data-testid={`remove-${item.id}`}
                        >
                          Kaldır
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          {items.length > 0 && (
            <div className="border-t p-4 space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm">Ara Toplam</span>
                <span className="text-lg font-semibold">{total.toFixed(2)} TL</span>
              </div>
              {remaining <= 0 && (
                <p className="text-xs text-green-600 text-center">
                  Ücretsiz kargo kazandınız!
                </p>
              )}
              <Link 
                to="/sepet"
                className="btn-primary w-full text-center block"
                onClick={() => setIsOpen(false)}
                data-testid="go-to-cart"
              >
                Sepete Git
              </Link>
              <Link 
                to="/odeme"
                className="btn-secondary w-full text-center block"
                onClick={() => setIsOpen(false)}
                data-testid="go-to-checkout"
              >
                Ödemeye Geç
              </Link>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
