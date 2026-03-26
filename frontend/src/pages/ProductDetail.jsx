import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Heart, Minus, Plus, X, Bookmark, ChevronUp, ChevronDown } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { useCart } from "../context/CartContext";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ProductDetail() {
  const { slug } = useParams();
  const { addItem } = useCart();
  const [product, setProduct] = useState(null);
  const [similarProducts, setSimilarProducts] = useState([]);
  const [comboProducts, setComboProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(0);
  const [selectedSize, setSelectedSize] = useState(null);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [showSizeChart, setShowSizeChart] = useState(false);
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const [expandedSections, setExpandedSections] = useState({
    description: false,
    shipping: false,
    returns: false
  });

  useEffect(() => {
    window.scrollTo(0, 0);
    fetchProduct();
  }, [slug]);

  // Sticky header on scroll
  useEffect(() => {
    const handleScroll = () => {
      setShowStickyHeader(window.scrollY > 400);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const fetchProduct = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/products/${slug}`);
      setProduct(res.data);
      
      if (res.data?.variants?.length > 0) {
        const firstAvailable = res.data.variants.find(v => v.stock > 0);
        if (firstAvailable) {
          setSelectedVariant(firstAvailable);
          setSelectedSize(firstAvailable.size);
        }
      }
      
      // Fetch similar products
      try {
        const similarRes = await axios.get(`${API}/products/${res.data.id}/similar?limit=4`);
        setSimilarProducts(similarRes.data || []);
      } catch {
        // Fallback to category-based similar products
        if (res.data?.category_name) {
          const fallbackRes = await axios.get(`${API}/products?category=${res.data.category_name}&limit=4`);
          setSimilarProducts(fallbackRes.data?.products?.filter(p => p.id !== res.data.id) || []);
        }
      }
      
      // Fetch combo products
      try {
        const comboRes = await axios.get(`${API}/products/${res.data.id}/combo?limit=4`);
        setComboProducts(comboRes.data || []);
      } catch {
        setComboProducts([]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddToCart = () => {
    if (product.variants?.length > 0 && !selectedVariant) {
      toast.error("Lütfen beden seçiniz");
      return;
    }
    
    // Check stock for selected variant
    if (selectedVariant && selectedVariant.stock < quantity) {
      toast.error(`Yetersiz stok! Mevcut stok: ${selectedVariant.stock}`);
      return;
    }
    
    addItem(product, selectedVariant, quantity);
    toast.success(selectedVariant 
      ? `${product.name} - ${selectedVariant.size} sepete eklendi` 
      : "Ürün sepete eklendi"
    );
  };

  const handleSizeSelect = (variant) => {
    if (variant.stock > 0) {
      setSelectedVariant(variant);
      setSelectedSize(variant.size);
    }
  };

  const sizes = product?.variants?.length > 0 
    ? product.variants 
    : ["XS", "S", "M", "L", "XL"].map(s => ({ size: s, stock: 10 }));

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="max-w-screen-2xl mx-auto px-4 py-8">
          <div className="grid md:grid-cols-2 gap-8">
            <div className="aspect-[3/4] bg-gray-100 animate-pulse" />
            <div className="space-y-4">
              <div className="h-8 bg-gray-100 w-3/4 animate-pulse" />
              <div className="h-6 bg-gray-100 w-1/3 animate-pulse" />
            </div>
          </div>
        </div>
        <Footer />
      </div>
    );
  }

  if (!product) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="max-w-screen-2xl mx-auto px-4 py-16 text-center">
          <p className="text-gray-500">Ürün bulunamadı</p>
          <Link to="/" className="btn-primary mt-4 inline-block">Ana Sayfaya Dön</Link>
        </div>
        <Footer />
      </div>
    );
  }

  const hasDiscount = Boolean(product.sale_price && product.sale_price < product.price);
  const basePrice = product.sale_price || product.price;
  const variantPriceDiff = selectedVariant?.price_diff || 0;
  const displayPrice = basePrice + variantPriceDiff;

  // Remove duplicate images and separate size chart
  const allImages = product.images || [];
  const uniqueImages = allImages.length > 1 && allImages[0] === allImages[1] ? allImages.slice(1) : allImages;
  const hasSizeChart = uniqueImages.length > 1;
  const sizeChartImage = hasSizeChart ? uniqueImages[uniqueImages.length - 1] : null;
  const displayImages = hasSizeChart ? uniqueImages.slice(0, -1) : uniqueImages;

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  return (
    <div className="min-h-screen">
      <Header />

      {/* Sticky Product Header - facette.com.tr style */}
      {showStickyHeader && (
        <div className="fixed top-0 left-0 right-0 z-50 bg-white border-b shadow-sm">
          <div className="max-w-screen-2xl mx-auto px-4 py-2 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <img src={displayImages[0]} alt="" className="w-10 h-12 object-cover" />
              <div>
                <p className="text-sm font-medium line-clamp-1">{product.name}</p>
                <p className="text-sm">{displayPrice.toFixed(2).replace('.', ',')} TL</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <div className="hidden md:flex items-center gap-1.5">
                {sizes.slice(0, 5).map((v, i) => (
                  <button
                    key={i}
                    onClick={() => handleSizeSelect(v)}
                    className={`w-8 h-8 text-xs border transition-colors ${
                      selectedSize === v.size ? "border-black bg-black text-white" : "border-gray-300 hover:border-black"
                    }`}
                  >
                    {v.size}
                  </button>
                ))}
              </div>
              <button 
                onClick={handleAddToCart}
                className="bg-black text-white px-6 py-2 text-xs uppercase tracking-wider hover:bg-gray-900"
              >
                Sepete Ekle
              </button>
              <button className="p-2 border border-gray-300 hover:border-black">
                <Bookmark size={16} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Breadcrumb */}
      <div className="max-w-screen-2xl mx-auto px-4 py-3 border-b">
        <nav className="text-[11px]">
          <Link to="/" className="text-gray-500 hover:text-black">Ana Sayfa</Link>
          <span className="mx-2 text-gray-300">/</span>
          {product.category_name && (
            <>
              <Link to={`/kategori/${product.category_name.toLowerCase()}`} className="text-gray-500 hover:text-black">
                {product.category_name}
              </Link>
              <span className="mx-2 text-gray-300">/</span>
            </>
          )}
          <span className="text-black">{product.name}</span>
        </nav>
      </div>

      <div className="max-w-screen-2xl mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-12 gap-8 lg:gap-12 items-start">
          {/* All Images in 2 Column Grid - facette.com.tr style */}
          <div className="lg:col-span-8 space-y-2">
            <div className="grid grid-cols-2 gap-2">
              {displayImages.map((img, index) => (
                <div key={index} className="relative aspect-[3/4] bg-gray-50">
                  <img
                    src={img}
                    alt={`${product.name} ${index + 1}`}
                    className="w-full h-full object-cover object-top"
                  />
                </div>
              ))}
            </div>
          </div>

          {/* Product Info */}
          <div className="lg:col-span-4 lg:max-w-md lg:sticky lg:top-24">
            <h1 className="text-xl md:text-2xl font-light mb-3">{product.name}</h1>
            
            {/* Price */}
            <div className="flex items-center gap-3 mb-6">
              <span className={`text-lg ${hasDiscount ? "text-red-600" : ""}`}>
                {displayPrice.toFixed(2).replace('.', ',')} TL
              </span>
              {hasDiscount && (
                <span className="text-base text-gray-400 line-through">{product.price.toFixed(2).replace('.', ',')} TL</span>
              )}
            </div>



            {/* Size Selection */}
            <div className="mb-5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs">Beden Seçiniz</span>
                {selectedVariant && selectedVariant.stock === 0 && (
                  <span className="text-xs text-red-600">Tükendi</span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {sizes.map((variant, index) => (
                  <button
                    key={index}
                    onClick={() => handleSizeSelect(variant)}
                    disabled={variant.stock === 0}
                    data-testid={`size-btn-${variant.size}`}
                    className={`min-w-[44px] h-9 px-3 border text-xs transition-all ${
                      selectedSize === variant.size 
                        ? "border-black bg-black text-white" 
                        : variant.stock === 0 
                          ? "border-gray-200 text-gray-300 cursor-not-allowed line-through bg-gray-50" 
                          : "border-gray-300 hover:border-black"
                    }`}
                  >
                    {variant.size}
                  </button>
                ))}
              </div>
            </div>

            {/* Quantity */}
            <div className="mb-5">
              <span className="text-xs block mb-2">Adet</span>
              <div className="flex items-center border border-gray-300 w-fit">
                <button onClick={() => setQuantity(Math.max(1, quantity - 1))} className="p-2.5 hover:bg-gray-50">
                  <Minus size={14} />
                </button>
                <span className="px-5 text-sm">{quantity}</span>
                <button onClick={() => setQuantity(quantity + 1)} className="p-2.5 hover:bg-gray-50">
                  <Plus size={14} />
                </button>
              </div>
            </div>

            {/* Size Chart Link */}
            {sizeChartImage && (
              <div className="mb-3">
                <button onClick={() => setShowSizeChart(true)} className="text-xs underline hover:no-underline">
                  Beden Tablosu
                </button>
              </div>
            )}

            {/* Add to Cart */}
            <div className="flex gap-2 mb-6">
              <button 
                onClick={handleAddToCart}
                data-testid="add-to-cart-btn"
                disabled={product.variants?.length > 0 && !selectedVariant}
                className={`flex-1 py-3 text-xs uppercase tracking-wider transition-colors ${
                  product.variants?.length > 0 && !selectedVariant
                    ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                    : "bg-black text-white hover:bg-gray-900"
                }`}
              >
                {product.variants?.length > 0 && !selectedVariant ? "Beden Seçiniz" : "Sepete Ekle"}
              </button>
              <button className="w-12 h-12 border border-gray-300 flex items-center justify-center hover:border-black">
                <Heart size={18} strokeWidth={1.5} />
              </button>
            </div>

            {/* Custom Accordion Details - No slider issues */}
            <div className="border-t">
              {/* Ürün Özellikleri */}
              <div className="border-b">
                <button 
                  onClick={() => toggleSection('description')}
                  className="w-full flex items-center justify-between py-3 text-xs hover:bg-gray-50"
                >
                  <span>Ürün Özellikleri</span>
                  {expandedSections.description ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {expandedSections.description && (
                  <div className="pb-3 text-xs text-gray-600 leading-relaxed" dangerouslySetInnerHTML={{ __html: product.description || "Ürün açıklaması bulunmamaktadır." }} />
                )}
              </div>
              
              {/* Kargo ve Teslimat */}
              <div className="border-b">
                <button 
                  onClick={() => toggleSection('shipping')}
                  className="w-full flex items-center justify-between py-3 text-xs hover:bg-gray-50"
                >
                  <span>Kargo ve Teslimat</span>
                  {expandedSections.shipping ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {expandedSections.shipping && (
                  <ul className="pb-3 text-xs text-gray-600 space-y-1.5">
                    <li>• 500 TL ve üzeri siparişlerde ücretsiz kargo</li>
                    <li>• 1-3 iş günü içinde kargoya verilir</li>
                  </ul>
                )}
              </div>
              
              {/* İade ve Değişim */}
              <div className="border-b">
                <button 
                  onClick={() => toggleSection('returns')}
                  className="w-full flex items-center justify-between py-3 text-xs hover:bg-gray-50"
                >
                  <span>İade ve Değişim</span>
                  {expandedSections.returns ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </button>
                {expandedSections.returns && (
                  <p className="pb-3 text-xs text-gray-600">14 gün içinde iade ve değişim hakkınız bulunmaktadır.</p>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Similar Products */}
        {similarProducts.length > 0 && (
          <section className="mt-12 pt-12 border-t">
            <h2 className="text-base font-light mb-6">Benzer Ürünler</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {similarProducts.map((p) => <ProductCard key={p.id} product={p} />)}
            </div>
          </section>
        )}

        {/* Combo Products - "Bu Ürünle Giyin" */}
        {comboProducts.length > 0 && (
          <section className="mt-12 pt-12 border-t">
            <h2 className="text-base font-light mb-6">Bu Ürünle Giyin</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {comboProducts.map((p) => <ProductCard key={p.id} product={p} />)}
            </div>
          </section>
        )}
      </div>

      {/* Size Chart Modal */}
      {showSizeChart && sizeChartImage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowSizeChart(false)}>
          <div className="bg-white max-w-lg w-full max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white flex justify-between items-center p-3 border-b">
              <h3 className="text-xs font-medium uppercase tracking-wider">Beden Tablosu</h3>
              <button onClick={() => setShowSizeChart(false)} className="p-1"><X size={18} /></button>
            </div>
            <div className="p-3">
              <img src={sizeChartImage} alt="Beden tablosu" className="w-full h-auto" />
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
