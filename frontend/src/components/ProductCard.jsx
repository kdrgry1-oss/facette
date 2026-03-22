import { useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";
import { toast } from "sonner";

export default function ProductCard({ product }) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [isFavorite, setIsFavorite] = useState(false);
  const { addItem } = useCart();

  // Remove duplicate first image
  const allImages = product.images || [];
  const images = allImages.length > 1 && allImages[0] === allImages[1] 
    ? allImages.slice(1) 
    : allImages;
  
  const hasMultipleImages = images.length > 1;
  const hasDiscount = product.sale_price && product.sale_price < product.price;
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

  return (
    <div className="product-card group" data-testid={`product-card-${product.id}`}>
      <Link to={`/urun/${product.slug || product.id}`}>
        {/* Image Container */}
        <div className="relative aspect-[3/4] bg-white overflow-hidden">
          <img
            src={images[currentImageIndex] || "/placeholder.jpg"}
            alt={product.name}
            className="w-full h-full object-cover object-top"
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

          {/* Image Dots */}
          {hasMultipleImages && (
            <div className="absolute bottom-3 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
              {images.slice(0, 4).map((_, index) => (
                <button
                  key={index}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setCurrentImageIndex(index);
                  }}
                  className={`transition-all ${
                    index === currentImageIndex 
                      ? "w-5 h-1.5 bg-black rounded-full" 
                      : "w-1.5 h-1.5 bg-gray-300 rounded-full hover:bg-gray-500"
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
