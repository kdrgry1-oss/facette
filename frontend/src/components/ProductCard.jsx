import { useState, useRef } from "react";
import { Link } from "react-router-dom";
import { Bookmark, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";
import { toast } from "sonner";

export default function ProductCard({ product }) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [isFavorite, setIsFavorite] = useState(false);
  const { addItem } = useCart();
  const imageContainerRef = useRef(null);

  // Remove duplicate first image
  const allImages = product.images || [];
  const images = allImages.length > 1 && allImages[0] === allImages[1] 
    ? allImages.slice(1) 
    : allImages;
  
  const hasMultipleImages = images.length > 1;
  const hasDiscount = Boolean(product.sale_price && product.sale_price < product.price);
  const displayPrice = product.sale_price || product.price;

  const handleQuickAdd = (e) => {
    e.preventDefault();
    e.stopPropagation();
    addItem(product);
    toast.success("Ürün sepete eklendi");
  };

  const handleFavorite = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsFavorite(!isFavorite);
    toast.success(isFavorite ? "Favorilerden çıkarıldı" : "Favorilere eklendi");
  };

  // Handle mouse move for image hover change
  const handleMouseMove = (e) => {
    if (!hasMultipleImages || !imageContainerRef.current) return;
    
    const rect = imageContainerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const width = rect.width;
    const segmentWidth = width / Math.min(images.length, 4);
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
      <Link to={`/urun/${product.slug || product.id}`}>
        {/* Image Container */}
        <div 
          ref={imageContainerRef}
          className="relative aspect-[3/4] bg-white overflow-hidden"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <img
            src={images[currentImageIndex] || "/placeholder.jpg"}
            alt={product.name}
            className="w-full h-full object-cover object-top transition-opacity duration-200"
            loading="lazy"
          />
          
          {/* Favorite Button - Top Right */}
          <button
            onClick={handleFavorite}
            className="absolute top-3 right-3 z-10"
            data-testid={`favorite-${product.id}`}
          >
            <Bookmark 
              size={20} 
              strokeWidth={1.5}
              className={`transition-colors ${isFavorite ? "fill-black text-black" : "text-gray-400 hover:text-black"}`} 
            />
          </button>

          {/* Image Indicators - show which segment is active */}
          {hasMultipleImages && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
              {images.slice(0, 4).map((_, index) => (
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
              className="flex-shrink-0 p-1 hover:opacity-60 transition-opacity"
              data-testid={`quick-add-${product.id}`}
              title="Sepete Ekle"
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
