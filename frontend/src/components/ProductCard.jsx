import { useState } from "react";
import { Link } from "react-router-dom";
import { Heart, ShoppingBag } from "lucide-react";
import { useCart } from "../context/CartContext";

export default function ProductCard({ product }) {
  const [isHovered, setIsHovered] = useState(false);
  const [isFavorite, setIsFavorite] = useState(false);
  const { addItem } = useCart();

  const hasDiscount = product.sale_price && product.sale_price < product.price;
  const displayPrice = product.sale_price || product.price;
  const discountPercent = hasDiscount ? Math.round((1 - product.sale_price / product.price) * 100) : 0;

  const handleQuickAdd = (e) => {
    e.preventDefault();
    e.stopPropagation();
    addItem(product);
  };

  return (
    <div 
      className="product-card group"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      data-testid={`product-card-${product.id}`}
    >
      <Link to={`/urun/${product.slug || product.id}`}>
        {/* Image Container */}
        <div className="relative aspect-[3/4] bg-gray-100 overflow-hidden">
          <img
            src={isHovered && product.images?.[1] ? product.images[1] : product.images?.[0]}
            alt={product.name}
            className="w-full h-full object-cover"
            loading="lazy"
          />
          
          {/* Badges */}
          {product.is_new && !hasDiscount && (
            <span className="badge-new">Yeni</span>
          )}
          {hasDiscount && (
            <span className="badge-sale">%{discountPercent}</span>
          )}

          {/* Favorite Button */}
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setIsFavorite(!isFavorite);
            }}
            className="absolute top-2 right-2 w-8 h-8 bg-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
            data-testid={`favorite-${product.id}`}
          >
            <Heart size={16} className={isFavorite ? "fill-red-500 text-red-500" : ""} />
          </button>

          {/* Quick Add Button */}
          <button
            onClick={handleQuickAdd}
            className="absolute bottom-0 left-0 right-0 bg-black text-white py-3 text-xs uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2"
            data-testid={`quick-add-${product.id}`}
          >
            <ShoppingBag size={14} />
            Sepete Ekle
          </button>
        </div>

        {/* Info */}
        <div className="mt-3">
          <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">
            {product.brand || "FACETTE"}
          </p>
          <h3 className="text-sm font-medium line-clamp-2 leading-snug">
            {product.name}
          </h3>
          <div className="mt-2 flex items-center gap-2">
            {hasDiscount && (
              <span className="price-original">{product.price.toFixed(2)} TL</span>
            )}
            <span className={hasDiscount ? "price-sale" : "text-sm font-medium"}>
              {displayPrice.toFixed(2)} TL
            </span>
          </div>
        </div>
      </Link>
    </div>
  );
}
