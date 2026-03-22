import { createContext, useContext, useState, useEffect } from "react";

const CartContext = createContext();

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => {
    const saved = localStorage.getItem("cart");
    return saved ? JSON.parse(saved) : [];
  });
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("cart", JSON.stringify(items));
  }, [items]);

  const addItem = (product, variant = null, quantity = 1) => {
    setItems((prev) => {
      const key = variant ? `${product.id}-${variant.id}` : product.id;
      const existing = prev.find((item) => 
        variant ? item.variantId === variant.id : item.productId === product.id && !item.variantId
      );

      if (existing) {
        return prev.map((item) =>
          (variant ? item.variantId === variant.id : item.productId === product.id && !item.variantId)
            ? { ...item, quantity: item.quantity + quantity }
            : item
        );
      }

      // Calculate price with variant adjustment
      const basePrice = product.sale_price || product.price;
      const priceDiff = variant?.price_diff || variant?.price_adjustment || 0;
      const finalPrice = basePrice + priceDiff;

      return [
        ...prev,
        {
          id: key,
          productId: product.id,
          variantId: variant?.id || null,
          name: product.name,
          price: finalPrice,
          image: product.images?.[0] || "",
          size: variant?.size || null,
          color: variant?.color || null,
          stockCode: variant?.stock_code || product.stock_code || null,
          barcode: variant?.barcode || product.barcode || null,
          quantity,
        },
      ];
    });
    setIsOpen(true);
  };

  const removeItem = (itemId) => {
    setItems((prev) => prev.filter((item) => item.id !== itemId));
  };

  const updateQuantity = (itemId, quantity) => {
    if (quantity < 1) {
      removeItem(itemId);
      return;
    }
    setItems((prev) =>
      prev.map((item) => (item.id === itemId ? { ...item, quantity } : item))
    );
  };

  const clearCart = () => {
    setItems([]);
    setIsOpen(false);
  };

  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const itemCount = items.reduce((sum, item) => sum + item.quantity, 0);

  return (
    <CartContext.Provider
      value={{
        items,
        isOpen,
        setIsOpen,
        addItem,
        removeItem,
        updateQuantity,
        clearCart,
        total,
        itemCount,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  return useContext(CartContext);
}
