import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Heart, Minus, Plus, X } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { useCart } from "../context/CartContext";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "../components/ui/accordion";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function ProductDetail() {
  const { slug } = useParams();
  const { addItem } = useCart();
  const [product, setProduct] = useState(null);
  const [similarProducts, setSimilarProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(0);
  const [selectedSize, setSelectedSize] = useState(null);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [showSizeChart, setShowSizeChart] = useState(false);

  useEffect(() => {
    fetchProduct();
  }, [slug]);

  const fetchProduct = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/products/${slug}`);
      setProduct(res.data);
      
      // Fetch similar products
      if (res.data?.category_name) {
        const similarRes = await axios.get(`${API}/products?category=${res.data.category_name}&limit=4`);
        setSimilarProducts(similarRes.data?.products?.filter(p => p.id !== res.data.id) || []);
      }
    } catch (err) {
      console.error(err);
      toast.error("Ürün yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const handleAddToCart = () => {
    if (product.variants?.length > 0 && !selectedVariant) {
      toast.error("Lütfen beden seçiniz");
      return;
    }
    addItem(product, selectedVariant, quantity);
    toast.success("Ürün sepete eklendi");
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
        <div className="container-main py-8">
          <div className="grid md:grid-cols-2 gap-8">
            <div className="aspect-[3/4] bg-gray-100 animate-pulse" />
            <div className="space-y-4">
              <div className="h-4 bg-gray-100 w-1/4 animate-pulse" />
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
        <div className="container-main py-16 text-center">
          <p className="text-gray-500">Ürün bulunamadı</p>
          <Link to="/" className="btn-primary mt-4 inline-block">Ana Sayfaya Dön</Link>
        </div>
        <Footer />
      </div>
    );
  }

  const hasDiscount = product.sale_price && product.sale_price < product.price;
  const displayPrice = product.sale_price || product.price;

  // Son görsel beden tablosu olarak kullanılacak, diğerleri galeri için
  const allImages = product.images || [];
  const hasSizeChart = allImages.length > 1;
  const sizeChartImage = hasSizeChart ? allImages[allImages.length - 1] : null;
  const displayImages = hasSizeChart ? allImages.slice(0, -1) : allImages;

  return (
    <div className="min-h-screen" data-testid="product-detail-page">
      <Header />

      {/* Breadcrumb */}
      <div className="container-main py-4 border-b">
        <nav className="text-xs">
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

      <div className="container-main py-8">
        <div className="grid md:grid-cols-2 gap-8 lg:gap-16">
          {/* Images */}
          <div className="flex gap-4">
            {/* Thumbnails - Son görsel hariç */}
            <div className="hidden md:flex flex-col gap-2 w-20">
              {displayImages.map((img, index) => (
                <button
                  key={index}
                  onClick={() => setSelectedImage(index)}
                  className={`aspect-[3/4] overflow-hidden border-2 transition-colors ${
                    selectedImage === index ? "border-black" : "border-transparent hover:border-gray-300"
                  }`}
                >
                  <img src={img} alt={`${product.name} ${index + 1}`} className="w-full h-full object-cover" />
                </button>
              ))}
            </div>

            {/* Main Image */}
            <div className="flex-1 relative">
              <img
                src={displayImages[selectedImage] || "/placeholder.jpg"}
                alt={product.name}
                className="w-full aspect-[3/4] object-cover object-top"
                data-testid="main-product-image"
              />
              
              {/* Mobile Image Dots */}
              <div className="md:hidden absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
                {displayImages.map((_, index) => (
                  <button
                    key={index}
                    onClick={() => setSelectedImage(index)}
                    className={`w-2 h-2 rounded-full transition-colors ${
                      selectedImage === index ? "bg-black" : "bg-gray-400"
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Product Info */}
          <div className="lg:max-w-md">
            <p className="text-xs text-gray-400 uppercase tracking-wider mb-2">FACETTE</p>
            <h1 className="text-2xl md:text-3xl font-light mb-4">{product.name}</h1>
            
            {/* Price */}
            <div className="flex items-center gap-3 mb-8">
              <span className={`text-xl ${hasDiscount ? "text-red-600" : ""}`}>
                {displayPrice.toFixed(2).replace('.', ',')} TL
              </span>
              {hasDiscount && (
                <span className="text-lg text-gray-400 line-through">{product.price.toFixed(2).replace('.', ',')} TL</span>
              )}
            </div>

            {/* Size Selection */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm">Beden Seçiniz</span>
                {sizeChartImage && (
                  <button 
                    onClick={() => setShowSizeChart(true)}
                    className="text-sm underline hover:no-underline"
                    data-testid="size-chart-btn"
                  >
                    Beden Tablosu
                  </button>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {sizes.map((variant, index) => (
                  <button
                    key={index}
                    onClick={() => handleSizeSelect(variant)}
                    disabled={variant.stock === 0}
                    className={`min-w-[48px] h-10 px-3 border text-sm transition-colors ${
                      selectedSize === variant.size 
                        ? "border-black bg-black text-white" 
                        : variant.stock === 0 
                          ? "border-gray-200 text-gray-300 cursor-not-allowed line-through" 
                          : "border-gray-300 hover:border-black"
                    }`}
                    data-testid={`size-${variant.size}`}
                  >
                    {variant.size}
                  </button>
                ))}
              </div>
            </div>

            {/* Quantity */}
            <div className="mb-6">
              <span className="text-sm block mb-3">Adet</span>
              <div className="flex items-center border border-gray-300 w-fit">
                <button 
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  className="p-3 hover:bg-gray-50 transition-colors"
                  data-testid="decrease-qty"
                >
                  <Minus size={16} />
                </button>
                <span className="px-6 text-sm">{quantity}</span>
                <button 
                  onClick={() => setQuantity(quantity + 1)}
                  className="p-3 hover:bg-gray-50 transition-colors"
                  data-testid="increase-qty"
                >
                  <Plus size={16} />
                </button>
              </div>
            </div>

            {/* Add to Cart */}
            <div className="flex gap-3 mb-8">
              <button 
                onClick={handleAddToCart}
                className="flex-1 bg-black text-white py-4 text-sm uppercase tracking-wider hover:bg-gray-900 transition-colors"
                data-testid="add-to-cart-btn"
              >
                Sepete Ekle
              </button>
              <button className="w-14 h-14 border border-gray-300 flex items-center justify-center hover:border-black transition-colors">
                <Heart size={20} strokeWidth={1.5} />
              </button>
            </div>

            {/* Accordion Details */}
            <Accordion type="single" collapsible className="border-t">
              <AccordionItem value="description">
                <AccordionTrigger className="text-sm py-4">Ürün Özellikleri</AccordionTrigger>
                <AccordionContent>
                  <div 
                    className="text-sm text-gray-600 leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: product.description || "Ürün açıklaması bulunmamaktadır." }}
                  />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="shipping">
                <AccordionTrigger className="text-sm py-4">Kargo ve Teslimat</AccordionTrigger>
                <AccordionContent>
                  <ul className="text-sm text-gray-600 space-y-2">
                    <li>• 500 TL ve üzeri siparişlerde ücretsiz kargo</li>
                    <li>• 1-3 iş günü içinde kargoya verilir</li>
                    <li>• MNG Kargo ile gönderim yapılmaktadır</li>
                  </ul>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="return">
                <AccordionTrigger className="text-sm py-4">İade ve Değişim</AccordionTrigger>
                <AccordionContent>
                  <p className="text-sm text-gray-600">
                    Ürünlerimizi teslim aldığınız tarihten itibaren 14 gün içerisinde iade veya değişim yapabilirsiniz.
                    Ürünün kullanılmamış, etiketli ve orijinal ambalajında olması gerekmektedir.
                  </p>
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </div>

        {/* Similar Products */}
        {similarProducts.length > 0 && (
          <section className="mt-16 pt-16 border-t">
            <h2 className="text-lg font-light mb-8">Benzer Ürünler</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
              {similarProducts.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Size Chart Modal - Son ürün görseli burada görünecek */}
      {showSizeChart && sizeChartImage && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" 
          onClick={() => setShowSizeChart(false)}
          data-testid="size-chart-modal"
        >
          <div 
            className="bg-white max-w-lg w-full max-h-[90vh] overflow-auto relative" 
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-white flex justify-between items-center p-4 border-b">
              <h3 className="text-sm font-medium uppercase tracking-wider">Beden Tablosu</h3>
              <button 
                onClick={() => setShowSizeChart(false)} 
                className="p-1 hover:bg-gray-100 rounded-full"
                data-testid="close-size-chart"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-4">
              <img 
                src={sizeChartImage} 
                alt="Beden tablosu" 
                className="w-full h-auto"
              />
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
