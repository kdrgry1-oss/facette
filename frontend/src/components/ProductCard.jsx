import { useState, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { Heart, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useFavorites } from "../context/FavoritesContext";
import { optimizeImg } from "../lib/img";
import { resolveColor, needsBorder, MULTI_GRADIENT } from "../lib/colorMap";
import { sortLikeSize } from "../utils/sizeSort";
import { trackSelectItem } from "../lib/dataLayer";
import { toast } from "sonner";

export default function ProductCard({ product, listId = "", listName = "", index }) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [activeSib, setActiveSib] = useState(null); // hover edilen renk kardeşi
  const { addItem } = useCart();
  const { isFavorite, toggleFavorite } = useFavorites();
  const isFav = isFavorite(product.id);
  const imageContainerRef = useRef(null);

  // Remove duplicate first image
  const allImages = product.images || [];
  const images = allImages.length > 1 && allImages[0] === allImages[1]
    ? allImages.slice(1)
    : allImages;

  const hasMultipleImages = images.length > 1;
  const hasDiscount = Boolean(product.sale_price && product.sale_price < product.price);
  const displayPrice = product.sale_price || product.price;

  // Renk kardeşleri (aynı modelin diğer renkleri) — backend `color_siblings` döndürür.
  const siblings = Array.isArray(product.color_siblings) ? product.color_siblings : [];
  const hasColors = siblings.length > 1;
  const activeId = activeSib?.id || product.id;
  const targetSlug = activeSib?.slug || product.slug || product.id;

  // Bedenler (hover'da görsel altında) — varyantlardan benzersiz beden + stok.
  const sizeList = useMemo(() => {
    const vs = product.variants || [];
    const map = new Map();
    for (const v of vs) {
      const s = (v.size || "").toString().trim();
      if (!s) continue;
      if (!map.has(s)) map.set(s, { size: s, variant: v, stock: Number(v.stock) || 0 });
      else map.get(s).stock += Number(v.stock) || 0;
    }
    const arr = [...map.values()];
    try { return sortLikeSize(arr, (x) => x.size); } catch { return arr; }
  }, [product.variants]);

  // Efektif stok: varyant varsa varyant stokları toplamı, yoksa ürün stoğu.
  const variants = product.variants || [];
  const variantStock = variants.reduce((s, v) => s + (Number(v.stock) || 0), 0);
  const effectiveStock = variants.length > 0 ? variantStock : (Number(product.stock) || 0);
  const isSoldOut = effectiveStock <= 0;

  const displayedImage = activeSib?.image
    ? activeSib.image
    : (images[currentImageIndex] || images[0] || "/placeholder.jpg");

  const handleQuickAdd = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (isSoldOut) {
      toast.error("Bu ürün tükendi");
      return;
    }
    addItem(product);
    toast.success("Ürün sepete eklendi");
  };

  // Hover'da bedene tıklayınca o beden varyantını sepete ekle.
  const handleSizeAdd = (e, s) => {
    e.preventDefault();
    e.stopPropagation();
    if (!s || s.stock <= 0) return;
    addItem(product, s.variant);
    toast.success(`Sepete eklendi · Beden ${s.size}`);
  };

  const handleFavorite = (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleFavorite(product);
  };

  const handleSelect = () => {
    try {
      trackSelectItem({ product, listId, listName, index });
    } catch (_) { /* silent */ }
  };

  // Görseller yatay kaydırma: fare sağa gittikçe sonraki görsel (Mango usulü).
  const handleMouseMove = (e) => {
    if (activeSib || !hasMultipleImages || !imageContainerRef.current) return;
    const rect = imageContainerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const width = rect.width;
    const segmentWidth = width / images.length;
    const newIndex = Math.min(Math.floor(x / segmentWidth), images.length - 1);
    if (newIndex !== currentImageIndex && newIndex >= 0) {
      setCurrentImageIndex(newIndex);
    }
  };

  const handleMouseLeave = () => {
    setCurrentImageIndex(0);
  };

  return (
    <div className="product-card group" data-testid={`product-card-${product.id}`}>
      {/* Image (Link) */}
      <Link to={`/${targetSlug}`} onClick={handleSelect} aria-label={product.name}>
        <div
          ref={imageContainerRef}
          className="relative aspect-[2/3] bg-white overflow-hidden"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <img
            src={optimizeImg(displayedImage, 700)}
            alt={product.name}
            className="w-full h-full object-cover object-top transition-opacity duration-200"
            loading="lazy"
            decoding="async"
          />

          {/* Tükendi rozeti */}
          {isSoldOut && (
            <div className="absolute top-3 left-3 z-10 bg-black/80 text-white text-[10px] uppercase tracking-wider px-2 py-1">
              Tükendi
            </div>
          )}

          {/* Favorite Button */}
          <button
            onClick={handleFavorite}
            className="absolute top-3 right-3 z-10"
            data-testid={`favorite-${product.id}`}
            aria-label={isFav ? "Favorilerden çıkar" : "Favorilere ekle"}
            title={isFav ? "Favorilerden çıkar" : "Favorilere ekle"}
          >
            <Heart
              size={20}
              strokeWidth={1.5}
              className={`transition-colors ${isFav ? "fill-red-500 text-red-500" : "text-gray-400 hover:text-black"}`}
            />
          </button>

          {/* Bedenler — hover'da görselin en altında, Mango usulü (ortalı, ferah aralık) */}
          {sizeList.length > 0 && (
            <>
              {/* Okunabilirlik için alttan beyaz gradyan (hover'da) */}
              <div className="absolute inset-x-0 bottom-0 h-14 z-[5] hidden md:block opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-gradient-to-t from-white via-white/70 to-transparent pointer-events-none" />
              <div className={`absolute inset-x-0 bottom-3 z-10 hidden md:flex opacity-0 group-hover:opacity-100 transition-opacity duration-200 items-end ${sizeList.length <= 3 ? "justify-center gap-6" : "justify-between"} px-5`}>
                {sizeList.map((s) => (
                  <button
                    key={s.size}
                    onClick={(e) => handleSizeAdd(e, s)}
                    disabled={s.stock <= 0}
                    className={`text-[12px] leading-none tracking-[0.06em] transition-colors ${
                      s.stock <= 0
                        ? "text-black/30 line-through decoration-1 cursor-not-allowed"
                        : "text-black/80 hover:text-black hover:underline underline-offset-4"
                    }`}
                    title={s.stock <= 0 ? `${s.size} · Tükendi` : `${s.size} · Sepete ekle`}
                  >
                    {s.size}
                  </button>
                ))}
              </div>
            </>
          )}

          {/* Görsel göstergeleri — hover'da bedenlere yer açmak için gizlenir */}
          {hasMultipleImages && !activeSib && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-0 md:group-hover:opacity-0 transition-opacity">
              {images.map((_, i) => (
                <div
                  key={i}
                  className={`transition-all ${
                    i === currentImageIndex
                      ? "w-5 h-1.5 bg-black rounded-full"
                      : "w-1.5 h-1.5 bg-gray-300 rounded-full"
                  }`}
                />
              ))}
            </div>
          )}
        </div>
      </Link>

      {/* Product Info */}
      <div className="mt-3">
        <Link to={`/${targetSlug}`} onClick={handleSelect}>
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm leading-snug flex-1 line-clamp-2">{product.name}</h3>
            <button
              onClick={handleQuickAdd}
              disabled={isSoldOut}
              className={`flex-shrink-0 p-1 transition-opacity ${isSoldOut ? "opacity-30 cursor-not-allowed" : "hover:opacity-60"}`}
              data-testid={`quick-add-${product.id}`}
              aria-label={isSoldOut ? "Tükendi" : "Sepete ekle"}
              title={isSoldOut ? "Tükendi" : "Sepete Ekle"}
            >
              <ShoppingBag size={18} strokeWidth={1.5} />
            </button>
          </div>

          {/* Price */}
          <div className="mt-1.5 flex items-center gap-2">
            {hasDiscount ? (
              <>
                <span className="text-sm text-red-600">{displayPrice.toFixed(2).replace('.', ',')} TL</span>
                <span className="text-xs text-gray-400 line-through">{product.price.toFixed(2).replace('.', ',')} TL</span>
              </>
            ) : (
              <span className="text-sm">{(displayPrice || 0).toFixed(2).replace('.', ',')} TL</span>
            )}
          </div>
        </Link>

        {/* Renk kutucukları (swatch) — aynı modelin diğer renkleri */}
        {hasColors && (
          <div
            className="mt-2 flex flex-wrap items-center gap-1.5"
            onMouseLeave={() => setActiveSib(null)}
            data-testid={`color-swatches-${product.id}`}
          >
            {siblings.slice(0, 6).map((sib) => {
              const isActive = sib.id === activeId;
              const isSelf = sib.id === product.id;
              const col = resolveColor(sib.color);
              let bgStyle, fallback = false;
              if (col?.type === "solid") bgStyle = { backgroundColor: col.value };
              else if (col?.type === "multi") bgStyle = { background: MULTI_GRADIENT };
              else fallback = true; // renk adı çözülemedi → görsele düş (varsa)
              const lightBorder = col?.type === "solid" && needsBorder(col.value);
              return (
                <Link
                  key={sib.id}
                  to={`/${sib.slug || sib.id}`}
                  onMouseEnter={() => setActiveSib(isSelf ? null : sib)}
                  onClick={(e) => { if (isSelf) e.preventDefault(); }}
                  className={`w-5 h-5 overflow-hidden flex-shrink-0 transition-all ${
                    isActive
                      ? "ring-1 ring-offset-1 ring-black border border-black"
                      : lightBorder
                        ? "border border-gray-300 hover:border-black"
                        : "border border-transparent hover:ring-1 hover:ring-offset-1 hover:ring-black"
                  }`}
                  title={sib.color || ""}
                  aria-label={sib.color || "Renk"}
                >
                  {fallback
                    ? <span className="block w-full h-full bg-gradient-to-br from-gray-200 to-gray-400" />
                    : <span className="block w-full h-full" style={bgStyle} />}
                </Link>
              );
            })}
            {siblings.length > 6 && (
              <span className="text-[11px] text-gray-400">+{siblings.length - 6}</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
