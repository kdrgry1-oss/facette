import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Heart, Share2, ChevronDown, ChevronUp, Minus, Plus } from "lucide-react";
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
            <div className="aspect-[3/4] bg-gray-200 animate-pulse" />
            <div className="space-y-4">
              <div className="h-4 bg-gray-200 w-1/4 animate-pulse" />
              <div className="h-8 bg-gray-200 w-3/4 animate-pulse" />
              <div className="h-6 bg-gray-200 w-1/3 animate-pulse" />
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

  // Images excluding size chart
  const displayImages = product.images?.filter((_, i) => !product.size_chart_images?.includes(product.images[i])) || [];
  const sizeChartImages = product.size_chart_images || [];

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
            {/* Thumbnails */}
            <div className="hidden md:flex flex-col gap-2 w-20">
              {displayImages.map((img, index) => (
                <button
                  key={index}
                  onClick={() => setSelectedImage(index)}
                  className={`gallery-thumb ${selectedImage === index ? "active" : ""}`}
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
                className="w-full aspect-[3/4] object-cover"
                data-testid="main-product-image"
              />
              
              {/* Mobile Image Dots */}
              <div className="md:hidden absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
                {displayImages.map((_, index) => (
                  <button
                    key={index}
                    onClick={() => setSelectedImage(index)}
                    className={`w-2 h-2 rounded-full ${selectedImage === index ? "bg-black" : "bg-gray-400"}`}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* Product Info */}
          <div className="lg:max-w-md">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-2">{product.brand}</p>
            <h1 className="text-2xl md:text-3xl font-medium mb-4">{product.name}</h1>
            
            {/* Price */}
            <div className="flex items-center gap-3 mb-6">
              {hasDiscount && (
                <span className="text-lg text-gray-400 line-through">{product.price.toFixed(2)} TL</span>
              )}
              <span className={`text-2xl font-medium ${hasDiscount ? "text-red-500" : ""}`}>
                {displayPrice.toFixed(2)} TL
              </span>
            </div>

            {/* Size Selection */}
            <div className="mb-6">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium">Beden Seçiniz</span>
                {sizeChartImages.length > 0 && (
                  <button 
                    onClick={() => setShowSizeChart(true)}
                    className="text-sm underline"
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
                    className={`size-btn ${selectedSize === variant.size ? "selected" : ""} ${variant.stock === 0 ? "out-of-stock" : ""}`}
                    data-testid={`size-${variant.size}`}
                  >
                    {variant.size}
                  </button>
                ))}
              </div>
            </div>

            {/* Quantity */}
            <div className="mb-6">
              <span className="text-sm font-medium block mb-3">Adet</span>
              <div className="flex items-center border border-gray-300 w-fit">
                <button 
                  onClick={() => setQuantity(Math.max(1, quantity - 1))}
                  className="p-3 hover:bg-gray-100"
                  data-testid="decrease-qty"
                >
                  <Minus size={16} />
                </button>
                <span className="px-6 font-medium">{quantity}</span>
                <button 
                  onClick={() => setQuantity(quantity + 1)}
                  className="p-3 hover:bg-gray-100"
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
                className="btn-primary flex-1"
                data-testid="add-to-cart-btn"
              >
                Sepete Ekle
              </button>
              <button className="w-12 h-12 border border-gray-300 flex items-center justify-center hover:border-black">
                <Heart size={20} />
              </button>
            </div>

            {/* Combo Products */}
            {product.combo_product_ids?.length > 0 && (
              <div className="mb-8 p-4 bg-gray-50">
                <h3 className="text-sm font-medium mb-3">Görünümü Tamamla</h3>
                <div className="flex gap-2">
                  {/* Would fetch and display combo products here */}
                  <span className="text-xs text-gray-500">Kombin ürünler yükleniyor...</span>
                </div>
              </div>
            )}

            {/* Accordion Details */}
            <Accordion type="single" collapsible className="border-t">
              <AccordionItem value="description">
                <AccordionTrigger className="text-sm font-medium py-4">Ürün Özellikleri</AccordionTrigger>
                <AccordionContent>
                  <div 
                    className="prose prose-sm max-w-none text-gray-600"
                    dangerouslySetInnerHTML={{ __html: product.description || "Ürün açıklaması bulunmamaktadır." }}
                  />
                </AccordionContent>
              </AccordionItem>

              {Object.keys(product.technical_details || {}).length > 0 && (
                <AccordionItem value="technical">
                  <AccordionTrigger className="text-sm font-medium py-4">Teknik Detaylar</AccordionTrigger>
                  <AccordionContent>
                    <dl className="space-y-2">
                      {Object.entries(product.technical_details).map(([key, value]) => (
                        <div key={key} className="flex">
                          <dt className="w-32 text-sm text-gray-500">{key}</dt>
                          <dd className="text-sm">{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </AccordionContent>
                </AccordionItem>
              )}

              <AccordionItem value="shipping">
                <AccordionTrigger className="text-sm font-medium py-4">Kargo ve Teslimat</AccordionTrigger>
                <AccordionContent>
                  <ul className="text-sm text-gray-600 space-y-2">
                    <li>• 500 TL ve üzeri siparişlerde ücretsiz kargo</li>
                    <li>• 1-3 iş günü içinde kargoya verilir</li>
                    <li>• MNG Kargo ile gönderim yapılmaktadır</li>
                  </ul>
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="return">
                <AccordionTrigger className="text-sm font-medium py-4">İade ve Değişim</AccordionTrigger>
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
            <h2 className="text-xl font-medium mb-8">Benzer Ürünler</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
              {similarProducts.map((p) => (
                <ProductCard key={p.id} product={p} />
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Size Chart Modal */}
      {showSizeChart && sizeChartImages.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowSizeChart(false)}>
          <div className="bg-white max-w-2xl max-h-[90vh] overflow-auto p-6" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-medium">Beden Tablosu</h3>
              <button onClick={() => setShowSizeChart(false)} className="text-2xl">&times;</button>
            </div>
            {sizeChartImages.map((img, i) => (
              <img key={i} src={img} alt="Beden tablosu" className="w-full" />
            ))}
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}
