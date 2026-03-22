import { useState } from "react";
import { Link } from "react-router-dom";
import { Bookmark, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";

export default function ProductCard({ product }) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [isFavorite, setIsFavorite] = useState(false);
  const { addItem } = useCart();

  const images = product.images || [];
  const hasMultipleImages = images.length > 1;
  
  const hasDiscount = product.sale_price && product.sale_price < product.price;
  const displayPrice = product.sale_price || product.price;

  const handleQuickAdd = (e) => {
    e.preventDefault();
    e.stopPropagation();
    addItem(product);
  };

  const handleFavorite = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsFavorite(!isFavorite);
  };

  return (
    <div 
      className="product-card group"
      data-testid={`product-card-${product.id}`}
    >
      <Link to={`/urun/${product.slug || product.id}`}>
        {/* Image Container */}
        <div className="relative aspect-[3/4] bg-white overflow-hidden">
          <img
            src={images[currentImageIndex] || "/placeholder.jpg"}
            alt={product.name}
            className="w-full h-full object-cover object-top"
            loading="lazy"
          />
          
          {/* Bookmark/Favorite Button - Top Right */}
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

          {/* Image Dots - Bottom Center */}
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
                  data-testid={`image-dot-${index}`}
                />
              ))}
            </div>
          )}

          {/* Quick Add Button - Shows on hover */}
          <button
            onClick={handleQuickAdd}
            className="absolute bottom-3 right-3 w-8 h-8 bg-white rounded-sm flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-sm z-10"
            data-testid={`quick-add-${product.id}`}
          >
            <ShoppingBag size={16} strokeWidth={1.5} />
          </button>
        </div>

        {/* Product Info */}
        <div className="mt-3 px-1">
          <p className="text-[11px] text-gray-400 uppercase tracking-wider mb-0.5">
            FACETTE
          </p>
          <h3 className="text-sm leading-snug line-clamp-1">
            {product.name}
          </h3>
          <div className="mt-1.5 flex items-center gap-2">
            {hasDiscount ? (
              <>
                <span className="text-sm text-red-600">{displayPrice.toFixed(2).replace('.', ',')} TL</span>
                <span className="text-xs text-gray-400 line-through">{product.price.toFixed(2).replace('.', ',')} TL</span>
              </>
            ) : (
              <span className="text-sm">{displayPrice.toFixed(2).replace('.', ',')} TL</span>
            )}
          </div>
        </div>
      </Link>
    </div>
  );
}
