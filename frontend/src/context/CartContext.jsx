import { createContext, useContext, useState, useEffect } from "react";

const CartContext = createContext();

export function CartProvider({ children }) {
  const [items, setItems] = useState(() => {
    // Y26: Bozuk/eski bir "cart" değeri (ör. "null") JSON.parse'ta hataya ya da items=null'a
    // yol açıp items.reduce'u patlatarak TÜM mağazayı beyaz ekran yapıyordu. Güvenli parse.
    try {
      const saved = localStorage.getItem("cart");
      const parsed = saved ? JSON.parse(saved) : [];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      try { localStorage.removeItem("cart"); } catch {}
      return [];
    }
  });
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem("cart", JSON.stringify(items));
  }, [items]);

  // TERK EDİLEN SEPET TAKİBİ: sepet değişince (debounce 2.5sn) backend'e kaydet
  // (POST /api/cart/track). Daha önce storefront bunu HİÇ çağırmıyordu → cart_sessions
  // boş kalıyor, "Terk Edilen Sepet" paneli hep 0 gösteriyordu. Sipariş sonrası sepet
  // boşalınca (items=[]) kayıt "total 0" olur ve admin listesinde (total>0 filtresi) çıkmaz.
  useEffect(() => {
    if (!items || items.length === 0) return;
    const t = setTimeout(() => {
      try {
        const API = process.env.REACT_APP_BACKEND_URL;
        if (!API) return;
        let sid = localStorage.getItem("cart_session_id");
        if (!sid) {
          sid = (window.crypto?.randomUUID?.() || (String(Date.now()) + Math.random().toString(36).slice(2)));
          localStorage.setItem("cart_session_id", sid);
        }
        const payload = {
          session_id: sid,
          items: items.map((it) => ({
            product_id: it.productId, name: it.name, qty: it.quantity,
            price: it.price, image: it.image,
          })),
          total: items.reduce((s, it) => s + (Number(it.price) || 0) * (it.quantity || 1), 0),
        };
        try {
          const u = JSON.parse(localStorage.getItem("user") || "null");
          if (u && u.email) payload.email = u.email;
          if (u && u.id) payload.user_id = u.id;
          if (u && u.phone) payload.phone = u.phone;
        } catch (_) { /* yoksay */ }
        fetch(`${API}/api/cart/track`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          keepalive: true,
        }).catch(() => {});
      } catch (_) { /* sessiz */ }
    }, 2500);
    return () => clearTimeout(t);
  }, [items]);

  const addItem = (product, variant = null, quantity = 1) => {
    // Y28: Kimliksiz (uydurma) varyantı varyantsız gibi işle — aksi halde variantId=null ile
    // her ekleme yeni satır oluşturup birleşmiyordu.
    if (variant && !variant.id) variant = null;
    setItems((prev) => {
      const key = variant ? `${product.id}-${variant.id}` : product.id;
      const existing = prev.find((item) =>
        variant ? item.variantId === variant.id : item.productId === product.id && !item.variantId
      );

      if (existing) {
        return prev.map((item) => {
          if (!(variant ? item.variantId === variant.id : item.productId === product.id && !item.variantId)) return item;
          const cap = item.stock || Infinity;   // stok tavanı (eski sepet kalemlerinde stock yoksa sınırsız)
          return { ...item, quantity: Math.min(item.quantity + quantity, cap) };
        });
      }

      // Fiyat: para hesabı için sale_price tabanı (kampanya sepet/sunucu tarafında uygulanır).
      // listPrice + campaignPct: sepette "indirim uygulandı" görünümü için (üstü çizili + indirimli).
      const listBase = Number(product.price) || 0;
      const saleBase = product.sale_price && product.sale_price < listBase ? product.sale_price : listBase;
      const priceDiff = variant?.price_diff || variant?.price_adjustment || 0;
      const finalPrice = saleBase + priceDiff;

      return [
        ...prev,
        {
          id: key,
          productId: product.id,
          categoryId: product.category_id || null,
          slug: product.slug || product.id,
          variantId: variant?.id || null,
          name: product.name,
          price: finalPrice,
          listPrice: listBase + priceDiff,
          campaignPct: Number(product.campaign_discount_percent || 0),
          image: product.images?.[0] || "",
          size: variant?.size || null,
          color: variant?.color || null,
          stockCode: variant?.stock_code || product.stock_code || null,
          barcode: variant?.barcode || product.barcode || null,
          stock: (variant ? variant.stock : product.stock) ?? null,   // stok tavanı (oversell engeli)
          quantity: Math.min(quantity, (variant ? variant.stock : product.stock) || Infinity),
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
      prev.map((item) =>
        item.id === itemId
          ? { ...item, quantity: Math.min(quantity, item.stock || Infinity) }  // stok üstüne çıkma (oversell engeli)
          : item
      )
    );
  };

  const clearCart = () => {
    // Sipariş sonrası (veya elle boşaltma) sunucudaki terk-sepet kaydını SİL → satın alan
    // müşteri "terkedilmiş sepet" sayılıp hatırlatma maili almasın (denetim bulgusu #38).
    try {
      const API = process.env.REACT_APP_BACKEND_URL;
      const sid = localStorage.getItem("cart_session_id");
      if (API && sid) {
        fetch(`${API}/api/cart/mark-ordered`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sid }),
          keepalive: true,
        }).catch(() => {});
      }
    } catch (_) { /* sessiz */ }
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
