import { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { Heart, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useFavorites } from "../context/FavoritesContext";
import { optimizeImg } from "../lib/img";
import { trackSelectItem } from "../lib/dataLayer";
import { toast } from "sonner";

export default function ProductCard({ product, listId = "", listName = "", index }) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
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

  // Efektif stok: varyant varsa varyant stokları toplamı, yoksa ürün stoğu.
  const variants = product.variants || [];
  const variantStock = variants.reduce((s, v) => s + (Number(v.stock) || 0), 0);
  const effectiveStock = variants.length > 0 ? variantStock : (Number(product.stock) || 0);
  const isSoldOut = effectiveStock <= 0;

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

  const handleFavorite = (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleFavorite(product);
  };

  // Liste → ürün tıklaması (GA4 select_item). Favori/hızlı-ekle butonları
  // stopPropagation yaptığı için yalnızca gerçek ürün tıklamasında tetiklenir.
  const handleSelect = () => {
    try {
      trackSelectItem({ product, listId, listName, index });
    } catch (_) { /* silent */ }
  };

  // Handle mouse move for image hover change
  const handleMouseMove = (e) => {
    if (!hasMultipleImages || !imageContainerRef.current) return;
    
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
      <Link to={`/${product.slug || product.id}`} onClick={handleSelect}>
        {/* Image Container */}
        <div 
          ref={imageContainerRef}
          className="relative aspect-[2/3] bg-white overflow-hidden"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <img
            src={optimizeImg(images[currentImageIndex] || "/placeholder.jpg", 700)}
            alt={product.name}
            className="w-full h-full object-cover object-top transition-opacity duration-200"
            loading="lazy"
            decoding="async"
          />

          {/* Tükendi rozeti — efektif stok yoksa (görsel net kalır) */}
          {isSoldOut && (
            <div className="absolute top-3 left-3 z-10 bg-black/80 text-white text-[10px] uppercase tracking-wider px-2 py-1">
              Tükendi
            </div>
          )}

          {/* Favorite Button - Top Right */}
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

          {/* Image Indicators - show which segment is active */}
          {hasMultipleImages && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
              {images.map((_, index) => (
                <div
                  key={index}
                  className={`transition-all ${
                    index === currentImageIndex 
                      ? "w-5 h-1.5 bg-black rounded-full" 
                      : "w-1.5 h-1.5 bg-gray-300 rounded-full"
                  }`}
                />
              ))}
            </div>
          )}
        </div>

        {/* Product Info - facette.com.tr style */}
        <div className="mt-3">
          {/* Name and Add to Cart in same row */}
          <div className="flex items-start justify-between gap-2">
            <h3 className="text-sm leading-snug flex-1 line-clamp-2">
              {product.name}
            </h3>
            {/* Add to cart icon next to name */}
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
        </div>
      </Link>
    </div>
  );
}
