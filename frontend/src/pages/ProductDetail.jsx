import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { X, Bookmark, ChevronUp, ChevronDown, Check, Truck, Star, RotateCcw, CreditCard, Clock } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { optimizeImg } from "../lib/img";
import { slugify } from "../lib/slug";
import { useCart } from "../context/CartContext";
import { useFavorites } from "../context/FavoritesContext";
import { useShipping } from "../lib/shipping";
import { trackViewContent, trackAddToCart } from "../utils/pixelEvents";
import { sortLikeSize } from "../utils/sizeSort";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Tahmini teslimat aralığı (kargoya verilme + iş günü; hafta sonu atlanır)
function estimateDelivery(minDays = 2, maxDays = 4) {
  const addBiz = (base, n) => {
    const r = new Date(base);
    let added = 0;
    while (added < n) {
      r.setDate(r.getDate() + 1);
      const wd = r.getDay();
      if (wd !== 0 && wd !== 6) added++;
    }
    return r;
  };
  const fmt = (d) => d.toLocaleDateString("tr-TR", { day: "numeric", month: "long" });
  const now = new Date();
  return `${fmt(addBiz(now, minDays))} - ${fmt(addBiz(now, maxDays))}`;
}

// "xx saat içinde sipariş ver → bugün/yarın kargoda" aciliyet ibaresi.
// Cutoff: hafta içi 16:00. Öncesinde → bugün kargoda; sonrasında/haftasonu → bir
// sonraki iş günü kargoda.
function shippingCutoff(cutoffHour = 16) {
  const now = new Date();
  const wd = now.getDay(); // 0 Paz, 6 Cmt
  const isWeekend = wd === 0 || wd === 6;
  const beforeCutoff = now.getHours() < cutoffHour;
  if (!isWeekend && beforeCutoff) {
    const remMs = new Date(now).setHours(cutoffHour, 0, 0, 0) - now.getTime();
    const h = Math.floor(remMs / 3600000);
    const m = Math.floor((remMs % 3600000) / 60000);
    const left = h >= 1 ? `${h} saat ${m} dk` : `${m} dk`;
    return { urgent: true, text: `Sonraki ${left} içinde sipariş ver,`, strong: "bugün kargoda." };
  }
  return { urgent: false, text: "Siparişin", strong: "yarın kargoda." };
}

// Son gezilen ürünler — localStorage'da küçük anlık görüntü (snapshot) listesi.
const RV_KEY = "facette_recently_viewed";
const readRecentlyViewed = () => {
  try { return JSON.parse(localStorage.getItem(RV_KEY) || "[]"); } catch { return []; }
};
const pushRecentlyViewed = (snap) => {
  if (!snap || !snap.id) return;
  try {
    const list = readRecentlyViewed().filter((x) => x && x.id !== snap.id);
    list.unshift(snap);
    localStorage.setItem(RV_KEY, JSON.stringify(list.slice(0, 12)));
  } catch { /* sessiz */ }
};

export default function ProductDetail() {
  const { slug } = useParams();
  const navigate = useNavigate();
  const { addItem } = useCart();
  const { isFavorite, toggleFavorite } = useFavorites();
  const { freeShippingThreshold } = useShipping();
  const [product, setProduct] = useState(null);
  const [similarProducts, setSimilarProducts] = useState([]);
  const [comboProducts, setComboProducts] = useState([]);
  const [recentItems, setRecentItems] = useState([]); // son gezilenler (önceki sayfalardan)
  const [loading, setLoading] = useState(true);
  const [selectedImage, setSelectedImage] = useState(0);
  const [selectedSize, setSelectedSize] = useState(null);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [showSizeChart, setShowSizeChart] = useState(false);
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const [mobileImageIdx, setMobileImageIdx] = useState(0);
  const [expandedSections, setExpandedSections] = useState({
    description: true,   // Ürün Özellikleri varsayılan açık — bilgi gizli accordion'da kalmasın
    shipping: false,
    returns: false
  });
  // Sepete eklendi mikro-etkileşimi: buton kısa süre "Eklendi ✓" gösterir
  const [justAdded, setJustAdded] = useState(false);
  // Size Table (HTML) - fetched via public endpoint. Hooks must live at top level.
  const [sizeTableData, setSizeTableData] = useState(null);
  // "Gelince Haber Ver" — stokta olmayan beden için e-posta toplama
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [notifyEmail, setNotifyEmail] = useState("");
  const [notifySubmitting, setNotifySubmitting] = useState(false);

  // Ürün değerlendirmeleri (yorum + puan). Backend: GET /reviews/product/:id (onaylı),
  // POST /reviews (auth, moderasyon → pending). Admin onayı sonrası listede görünür.
  const [reviews, setReviews] = useState([]);
  const [reviewAvg, setReviewAvg] = useState(0);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [rvRating, setRvRating] = useState(0);
  const [rvTitle, setRvTitle] = useState("");
  const [rvComment, setRvComment] = useState("");
  const [rvSubmitting, setRvSubmitting] = useState(false);
  const rvLoggedIn = !!localStorage.getItem("token");

  useEffect(() => {
    if (!product?.id) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/reviews/product/${product.id}`);
        setReviews(data.items || []);
        setReviewAvg(data.average_rating || 0);
        setReviewTotal(data.total || 0);
      } catch { /* yorum yoksa sessiz geç */ }
    })();
  }, [product?.id]);

  const submitReview = async () => {
    if (rvRating < 1) { toast.error("Lütfen 1-5 yıldız seçin"); return; }
    setRvSubmitting(true);
    try {
      await axios.post(`${API}/reviews`,
        { product_id: product.id, rating: rvRating, title: rvTitle, comment: rvComment },
        { headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
      toast.success("Yorumunuz alındı, moderasyon sonrası yayınlanacak");
      setRvRating(0); setRvTitle(""); setRvComment("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Yorum gönderilemedi");
    } finally {
      setRvSubmitting(false);
    }
  };

  // SEO — JSON-LD yapısal veri (Product + BreadcrumbList). react-helmet yok,
  // bu yüzden <head>'e script'i elle enjekte edip temizliyoruz. Google'ın
  // "rich results" (fiyat, stok, marka) göstermesini sağlar.
  useEffect(() => {
    if (!product) return;
    // Edge SEO middleware (functions/_middleware.js) zaten JSON-LD bastıysa
    // client tarafında tekrar ekleme — Google'da duplicate Product/Breadcrumb olmasın.
    if (typeof document !== "undefined" && document.querySelector('script[data-seo="edge"]')) return;
    const origin = (typeof window !== "undefined" && window.location && window.location.origin) || "https://facette.com.tr";
    const canonical = `${origin}/urun/${product.slug || product.id}`;
    const price = product.sale_price || product.price;
    const inStock = Array.isArray(product.variants) && product.variants.length > 0
      ? product.variants.some((v) => (v.stock || 0) > 0)
      : true;

    const productLd = {
      "@context": "https://schema.org/",
      "@type": "Product",
      name: product.name,
      image: Array.isArray(product.images) && product.images.length ? product.images : undefined,
      description: product.description || product.name,
      sku: product.barcode || product.stock_code || product.id,
      brand: product.brand ? { "@type": "Brand", name: product.brand } : undefined,
      offers: {
        "@type": "Offer",
        url: canonical,
        priceCurrency: "TRY",
        price: price != null ? String(price) : undefined,
        availability: inStock ? "https://schema.org/InStock" : "https://schema.org/OutOfStock",
      },
    };

    const crumbs = [{ name: "Ana Sayfa", item: origin }];
    if (product.category_name) {
      crumbs.push({ name: product.category_name, item: `${origin}/${slugify(product.category_name || product.category_slug || "")}` });
    }
    crumbs.push({ name: product.name, item: canonical });
    const breadcrumbLd = {
      "@context": "https://schema.org/",
      "@type": "BreadcrumbList",
      itemListElement: crumbs.map((c, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: c.name,
        item: c.item,
      })),
    };

    const tag = document.createElement("script");
    tag.type = "application/ld+json";
    tag.setAttribute("data-seo", "product");
    tag.text = JSON.stringify([productLd, breadcrumbLd]);
    // Önceki kalmışsa temizle, sonra ekle
    document.querySelectorAll('script[data-seo="product"]').forEach((el) => el.remove());
    document.head.appendChild(tag);

    return () => {
      document.querySelectorAll('script[data-seo="product"]').forEach((el) => el.remove());
    };
  }, [product]);

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [slug]);

  // Sticky header on scroll
  useEffect(() => {
    const handleScroll = () => {
      setShowStickyHeader(window.scrollY > 400);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Fetch HTML size table whenever product loads
  useEffect(() => {
    const pid = product?.id;
    if (!pid) return;
    axios.get(`${API}/size-tables-public/${pid}`)
      .then(res => { if (res.data?.exists) setSizeTableData(res.data); })
      .catch(() => { /* no table */ });
  }, [product?.id]);

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/products/${slug}`);
        setProduct(res.data);

        // Son gezilenler: önceki listeyi (mevcut ürün hariç) göster, sonra mevcut
        // ürünü snapshot olarak kaydet (bir sonraki sayfada görünsün).
        try {
          const _p = res.data;
          setRecentItems(readRecentlyViewed().filter((x) => x && x.id !== _p.id).slice(0, 10));
          pushRecentlyViewed({
            id: _p.id,
            name: _p.name,
            slug: _p.slug || _p.id,
            image: (_p.images && _p.images[0]) || _p.image || "",
            price: _p.price,
            discount_price: _p.discount_price,
            sale_price: _p.sale_price,
          });
        } catch { /* sessiz */ }

        // Canonical URL: ürün id/eski slug ile açıldıysa doğru slug'a yönlendir (SEO + tutarlı URL)
        if (res.data?.slug && res.data.slug !== slug) {
          navigate(`/${res.data.slug}`, { replace: true });
        }

        // Varsayılan/ilk uygun bedeni önce belirle — ViewContent'in Meta content_id'si
        // seçili bedenin Ticimax varyant id'si olsun (katalog eşleşmesi için).
        const defaultVariant =
          (res.data?.variants || []).find((v) => (v.stock || 0) > 0) ||
          (res.data?.variants || [])[0] || null;

        // FAZ 9+ — Pixel ViewContent event
        trackViewContent({
          product_id: res.data.id,
          name: res.data.name,
          category: res.data.category_name,
          price: res.data.sale_price || res.data.price,
          variant_id: defaultVariant?.id,
        });

        if (defaultVariant && (defaultVariant.stock || 0) > 0) {
          setSelectedVariant(defaultVariant);
          setSelectedSize(defaultVariant.size);
        }

        // Benzer ürünler — kategori bazlı. (Eski /similar endpoint'i backend'de
        // yok ve her seferinde 404 dönüyordu; doğrudan kategori sorgusu kullanılıyor.)
        try {
          if (res.data?.category_name) {
            const fallbackRes = await axios.get(`${API}/products?category=${encodeURIComponent(res.data.category_name)}&limit=4`);
            setSimilarProducts(fallbackRes.data?.products?.filter(p => p.id !== res.data.id) || []);
          }
        } catch {
          // benzer ürün getirilemezse sessizce geç
        }

        // Fetch combo products ("Stilini tamamla")
        try {
          const comboRes = await axios.get(`${API}/products/${res.data.id}/combine-products`);
          const comboItems = comboRes.data?.items || [];
          setComboProducts(comboItems);
          // Fallback: kombin atanmamışsa cart-suggestions çağırarak kategori bazlı öner
          if (comboItems.length === 0) {
            try {
              const fb = await axios.post(`${API}/products/cart-suggestions`, {
                product_ids: [res.data.id],
                limit: 4,
              });
              setComboProducts(fb.data?.items || []);
            } catch {
              // ignore
            }
          }
        } catch {
          setComboProducts([]);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    })();
  }, [slug]);

  const handleAddToCart = () => {
    if (product.variants?.length > 0 && !selectedVariant) {
      toast.error("Lütfen beden seçiniz");
      return;
    }

    // Varyantsız ürünlerde ürün stoğu yoksa engelle (tükendi)
    if (!(product.variants?.length > 0) && (Number(product.stock) || 0) <= 0) {
      toast.error("Bu ürün tükendi");
      return;
    }
    
    // Check stock for selected variant
    if (selectedVariant && selectedVariant.stock < quantity) {
      toast.error(`Yetersiz stok! Mevcut stok: ${selectedVariant.stock}`);
      return;
    }
    
    addItem(product, selectedVariant, quantity);
    // FAZ 9+ — Pixel AddToCart event
    trackAddToCart({
      product_id: product.id,
      name: product.name,
      category: product.category_name,
      price: selectedVariant?.price || product.sale_price || product.price,
      quantity,
      size: selectedVariant?.size,
      color: selectedVariant?.color,
      variant_id: selectedVariant?.id,
    });
    toast.success(selectedVariant 
      ? `${product.name} - ${selectedVariant.size} sepete eklendi` 
      : "Ürün sepete eklendi"
    );
    setJustAdded(true);
    setTimeout(() => setJustAdded(false), 1600);
  };

  const handleSizeSelect = (variant) => {
    setSelectedVariant(variant);
    setSelectedSize(variant.size);
    // Beden değişince açık bildirim formunu kapat (stoklu bedene geçilirse gizlenir)
    if (variant.stock > 0) setNotifyOpen(false);
    // Beden değişince ViewContent'i seçili bedenin Meta katalog id'siyle yeniden gönder
    // (Meta content_id = o bedenin Ticimax varyant id'si — her beden için doğru eşleşme).
    if (product) {
      trackViewContent({
        product_id: product.id,
        name: product.name,
        category: product.category_name,
        price: variant.price || product.sale_price || product.price,
        variant_id: variant.id,
      });
    }
  };

  const handleStockNotify = async () => {
    const email = notifyEmail.trim();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      toast.error("Lütfen geçerli bir e-posta adresi giriniz");
      return;
    }
    setNotifySubmitting(true);
    try {
      const res = await axios.post(`${API}/stock-notify`, {
        product_id: product.id,
        size: selectedVariant?.size || selectedSize || "",
        email,
      });
      toast.success(res.data?.message || "Talebiniz alındı, stoğa girince haber vereceğiz.");
      setNotifyOpen(false);
      setNotifyEmail("");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Bir hata oluştu, lütfen tekrar deneyin.");
    } finally {
      setNotifySubmitting(false);
    }
  };

  const sizes = product?.variants?.length > 0 
    ? sortLikeSize(product.variants, v => v.size) 
    : ["XS", "S", "M", "L", "XL"].map(s => ({ size: s, stock: 10 }));

  if (loading) {
    return (
      <div className="min-h-screen">
        <Header />
        <div className="max-w-screen-2xl mx-auto px-4 py-8">
          <div className="grid md:grid-cols-2 gap-8">
            <div className="aspect-[2/3] bg-gray-100 animate-pulse" />
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

  // Remove duplicate images and hide size-table images from customer view
  const allImages = product.images || [];
  const uniqueImages = allImages.length > 1 && allImages[0] === allImages[1] ? allImages.slice(1) : allImages;
  // Ölçü tablosu görselleri {url, is_size_table:true} dict'i olarak işaretli — müşteriden gizle.
  // Kalanları URL string'e normalize et (dict gelse bile <img src> kırılmasın).
  const displayImages = uniqueImages
    .filter((img) => !(typeof img === 'object' && img !== null && img.is_size_table))
    .map((img) => (typeof img === 'object' && img !== null ? (img.url || img.src || img.image || '') : img))
    .filter(Boolean);

  const toggleSection = (section) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  return (
    <div className="min-h-screen">
      <Header />

      {/* Sticky Product Bar — mobile: bottom, desktop: top */}
      {showStickyHeader && (
        <div className="fixed left-0 right-0 z-50 bg-white border-t md:border-t-0 md:border-b shadow-[0_-4px_20px_rgba(0,0,0,0.05)] md:shadow-sm bottom-0 md:top-0 md:bottom-auto pb-[env(safe-area-inset-bottom)]" data-testid="sticky-product-bar">
          <div className="max-w-screen-2xl mx-auto px-3 md:px-4 py-2.5 md:py-2 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0 flex-1">
              <img src={optimizeImg(displayImages[0], 150)} alt="" className="w-10 h-12 object-cover bg-stone-100" />
              <div className="min-w-0">
                <p className="text-[12px] md:text-sm font-light line-clamp-1">{product.name}</p>
                <p className="text-[12px] md:text-sm tabular-nums">{displayPrice.toFixed(2).replace('.', ',')} TL</p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
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
                className="bg-black text-white px-4 md:px-6 py-2.5 md:py-2 text-[11px] md:text-xs uppercase tracking-[0.2em] hover:bg-black/85"
                data-testid="sticky-add-to-cart"
              >
                Sepete Ekle
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
              <Link to={`/${slugify(product.category_name)}`} className="text-gray-500 hover:text-black">
                {product.category_name}
              </Link>
              <span className="mx-2 text-gray-300">/</span>
            </>
          )}
          <span className="text-black">{product.name}</span>
        </nav>
      </div>

      <div className="max-w-screen-2xl mx-auto px-4 py-6">
        <div className="grid lg:grid-cols-12 gap-8 lg:gap-16 items-start">
          {/* Image Gallery — mobile: swipe carousel, desktop: 2-col grid */}
          <div className="lg:col-span-7 space-y-2 min-w-0">
            {/* Mobile: full-width snap carousel with dots */}
            <div className="lg:hidden -mx-4">
              <div
                className="flex overflow-x-auto snap-x snap-mandatory scrollbar-hide"
                onScroll={(e) => {
                  const idx = Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth);
                  setMobileImageIdx(idx);
                }}
              >
                {displayImages.map((img, index) => (
                  <div key={index} className="snap-center shrink-0 w-screen aspect-[2/3] bg-stone-50">
                    <img
                      src={optimizeImg(img, 1200)}
                      alt={`${product.name} ${index + 1}`}
                      className="w-full h-full object-cover object-top"
                      loading={index === 0 ? "eager" : "lazy"}
                      fetchPriority={index === 0 ? "high" : "auto"}
                      decoding="async"
                    />
                  </div>
                ))}
              </div>
              {displayImages.length > 1 && (
                <div className="flex items-center justify-center gap-1.5 py-3">
                  {displayImages.map((_, i) => (
                    <span
                      key={i}
                      className={`h-[2px] transition-all ${i === mobileImageIdx ? "w-6 bg-black" : "w-3 bg-black/25"}`}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Desktop: sol thumbnail şeridi + orta büyük görsel (Simon Miller usulü) */}
            <div className="hidden lg:flex gap-4">
              {displayImages.length > 1 && (
                <div className="flex flex-col gap-2 w-[70px] shrink-0">
                  {displayImages.map((img, index) => (
                    <button
                      key={index}
                      onClick={() => setSelectedImage(index)}
                      onMouseEnter={() => setSelectedImage(index)}
                      className={`relative aspect-[2/3] bg-stone-50 overflow-hidden border transition-colors ${
                        index === selectedImage ? "border-black" : "border-transparent hover:border-gray-300"
                      }`}
                      aria-label={`Görsel ${index + 1}`}
                      data-testid={`pdp-thumb-${index}`}
                    >
                      <img
                        src={optimizeImg(img, 200)}
                        alt=""
                        className="w-full h-full object-cover object-top"
                        loading="lazy"
                        decoding="async"
                      />
                    </button>
                  ))}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <div className="relative aspect-[2/3] bg-stone-50">
                  <img
                    src={optimizeImg(displayImages[selectedImage] || displayImages[0], 1400)}
                    alt={product.name}
                    className="w-full h-full object-cover object-top"
                    loading="eager"
                    fetchPriority="high"
                    decoding="async"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Product Info */}
          <div className="lg:col-span-5 lg:sticky lg:top-24 min-w-0 lg:max-w-[420px] lg:mx-auto w-full">
            <h1 className="text-xl md:text-2xl font-light mb-2">{product.name}</h1>

            {/* Yıldız derecelendirme — ürün adı ile fiyat arasında; tıkla → yorumlara git */}
            <button
              type="button"
              onClick={() => document.getElementById("reviews")?.scrollIntoView({ behavior: "smooth" })}
              className="mb-3 flex items-center gap-1.5 group"
              data-testid="pdp-rating-jump"
              aria-label="Değerlendirmeleri gör"
            >
              <span className="flex">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Star key={i} size={14} className={i <= Math.round(reviewAvg || 0) ? "fill-black text-black" : "text-gray-300"} />
                ))}
              </span>
              <span className="text-xs text-gray-500 group-hover:text-black transition-colors underline-offset-2 group-hover:underline">
                {reviewTotal > 0 ? `${(reviewAvg || 0).toFixed(1)} · ${reviewTotal} değerlendirme` : "İlk değerlendirmeyi yap"}
              </span>
            </button>

            {/* Price */}
            <div className="mb-6">
              <div className="flex items-center gap-3">
                <span className={`text-lg ${hasDiscount ? "text-red-600" : ""}`}>
                  {displayPrice.toFixed(2).replace('.', ',')} TL
                </span>
                {hasDiscount && (
                  <span className="text-base text-gray-400 line-through">{product.price.toFixed(2).replace('.', ',')} TL</span>
                )}
              </div>

              {displayPrice > 0 && (
                <p className="text-xs text-gray-500 mt-2" data-testid="installment-hint">
                  💳 9 taksite kadar · <span className="font-medium text-gray-700">{(displayPrice / 9).toFixed(2).replace('.', ',')} TL</span>/ay'dan başlayan taksitlerle
                </p>
              )}
            </div>


            {/* Color Siblings (diğer renk) — varsa swatch'ler */}
            <ColorSiblings productId={product.id} currentColor={product.attributes?.find?.((a) => (a.name || "").toLowerCase().includes("color") || (a.name || "").toLowerCase().includes("renk"))?.value} />

            {/* Size Selection */}
            <div className="mb-5">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs">
                  Beden Seçiniz
                  {selectedVariant && selectedVariant.stock === 0 && (
                    <span className="text-red-600 ml-2">Tükendi</span>
                  )}
                </span>
              </div>
              <div className="flex items-end justify-between gap-3">
                <div className="flex flex-wrap gap-2">
                {sizes.map((variant, index) => {
                  const isSelected = selectedSize === variant.size;
                  const isOOS = variant.stock === 0;
                  return (
                    <button
                      key={index}
                      onClick={() => handleSizeSelect(variant)}
                      data-testid={`size-btn-${variant.size}`}
                      className={`min-w-[44px] h-9 px-3 border text-xs transition-all ${
                        isSelected
                          ? isOOS
                            ? "border-red-500 bg-red-50 text-red-600 line-through"
                            : "border-black bg-black text-white"
                          : isOOS
                            ? "border-gray-200 text-gray-300 line-through bg-gray-50 hover:border-gray-400"
                            : "border-gray-300 hover:border-black"
                      }`}
                    >
                      {variant.size}
                    </button>
                  );
                })}
                </div>
                {/* Beden Tablosu — bedenlerin alt hizasında, sağda */}
                {sizeTableData && (
                  <button onClick={() => setShowSizeChart(true)} className="text-xs underline underline-offset-2 hover:no-underline whitespace-nowrap shrink-0" data-testid="show-size-table-btn">
                    Beden Tablosu
                  </button>
                )}
              </div>
            </div>

            {/* Quantity input removed by request — sepete her zaman 1 adet eklenir */}

            {/* Add to Cart */}
            {(() => {
              const _hasVariants = (product.variants?.length || 0) > 0;
              const _productOOS = !_hasVariants && (Number(product.stock) || 0) <= 0;
              const oosSelected = (selectedVariant && selectedVariant.stock === 0) || _productOOS;
              return (
                <div className="mb-6">
                  <div className="flex gap-2">
                    {oosSelected ? (
                      <button
                        onClick={() => setNotifyOpen((v) => !v)}
                        data-testid="notify-toggle-btn"
                        className="flex-1 py-2.5 sm:py-3 text-[11px] sm:text-xs uppercase tracking-normal sm:tracking-wider transition-colors border border-black bg-white text-black hover:bg-black hover:text-white"
                      >
                        Gelince Haber Ver
                      </button>
                    ) : (
                      <button
                        onClick={handleAddToCart}
                        data-testid="add-to-cart-btn"
                        disabled={product.variants?.length > 0 && !selectedVariant}
                        className={`flex-1 py-2.5 sm:py-3 text-[11px] sm:text-xs uppercase tracking-normal sm:tracking-wider transition-colors ${
                          product.variants?.length > 0 && !selectedVariant
                            ? "bg-gray-300 text-gray-500 cursor-not-allowed"
                            : justAdded
                              ? "bg-emerald-600 text-white"
                              : "bg-black text-white hover:bg-gray-900"
                        }`}
                      >
                        {product.variants?.length > 0 && !selectedVariant
                          ? "Beden Seçiniz"
                          : justAdded
                            ? (<span className="inline-flex items-center justify-center gap-1.5"><Check size={15} strokeWidth={2.5} /> Eklendi</span>)
                            : "Sepete Ekle"}
                      </button>
                    )}
                    <button
                      onClick={() => toggleFavorite(product)}
                      data-testid="pdp-favorite-btn"
                      aria-label="Kaydet"
                      title="Kaydet"
                      className={`w-12 h-12 border flex items-center justify-center transition-colors ${
                        isFavorite(product.id) ? "border-black bg-gray-50" : "border-gray-300 hover:border-black"
                      }`}
                    >
                      <Bookmark size={18} strokeWidth={1.5} className={isFavorite(product.id) ? "fill-black text-black" : ""} />
                    </button>
                  </div>

                  {/* Kargo aciliyeti — xx saat içinde sipariş ver → bugün/yarın kargoda */}
                  {(() => {
                    const c = shippingCutoff();
                    return (
                      <p className="mt-3 text-xs flex items-center gap-1.5" data-testid="pdp-shipping-cutoff">
                        <Clock size={14} strokeWidth={1.7} className={c.urgent ? "text-emerald-600" : "text-gray-500"} />
                        <span className={c.urgent ? "text-gray-700" : "text-gray-600"}>
                          {c.text} <span className={`font-semibold ${c.urgent ? "text-emerald-700" : "text-black"}`}>{c.strong}</span>
                        </span>
                      </p>
                    );
                  })()}

                  {/* Güven banner'ı — ücretsiz iade / hızlı teslimat / taksitli ödeme */}
                  <div className="mt-4 grid grid-cols-3 gap-2 border-y border-black/10 py-3.5" data-testid="pdp-trust-badges">
                    <div className="flex flex-col items-center text-center gap-1.5 px-1">
                      <RotateCcw size={18} strokeWidth={1.4} className="text-black/75" />
                      <span className="text-[10px] leading-tight text-black/65">Ücretsiz<br />İade</span>
                    </div>
                    <div className="flex flex-col items-center text-center gap-1.5 px-1 border-x border-black/10">
                      <Truck size={18} strokeWidth={1.4} className="text-black/75" />
                      <span className="text-[10px] leading-tight text-black/65">Hızlı<br />Teslimat</span>
                    </div>
                    <div className="flex flex-col items-center text-center gap-1.5 px-1">
                      <CreditCard size={18} strokeWidth={1.4} className="text-black/75" />
                      <span className="text-[10px] leading-tight text-black/65">Taksitli<br />Ödeme</span>
                    </div>
                  </div>

                  {/* Stok bildirim formu */}
                  {oosSelected && notifyOpen && (
                    <div className="mt-3 border border-black/10 bg-gray-50 p-3" data-testid="stock-notify-form">
                      <p className="text-[11px] text-black/60 mb-2">
                        <span className="font-medium text-black">{selectedVariant.size}</span> bedeni tükendi. Stoğa girince e-posta ile haber verelim.
                      </p>
                      <div className="flex gap-2">
                        <input
                          type="email"
                          value={notifyEmail}
                          onChange={(e) => setNotifyEmail(e.target.value)}
                          onKeyDown={(e) => { if (e.key === "Enter") handleStockNotify(); }}
                          placeholder="E-posta adresiniz"
                          data-testid="stock-notify-email-input"
                          className="flex-1 h-10 px-3 border border-gray-300 text-xs focus:outline-none focus:border-black"
                        />
                        <button
                          onClick={handleStockNotify}
                          disabled={notifySubmitting}
                          data-testid="stock-notify-submit-btn"
                          className="px-4 h-10 text-xs uppercase tracking-wider bg-black text-white hover:bg-gray-900 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                        >
                          {notifySubmitting ? "Gönderiliyor..." : "Gönder"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Görünümü Tamamla — küçük resimler (sepete ekle ile açıklama arası) */}
            {comboProducts.length > 0 && (
              <div className="mb-6 pb-2" data-testid="product-combo-mini">
                <p className="text-[10px] tracking-[0.25em] uppercase text-black/60 mb-3">Görünümü Tamamla</p>
                <div className="flex gap-2 overflow-x-auto scrollbar-hide -mx-4 px-4 lg:mx-0 lg:px-0">
                  {comboProducts.slice(0, 6).map((p) => {
                    const img = (p.images && p.images[0]) || p.image || "/placeholder.jpg";
                    return (
                      <Link
                        key={p.id}
                        to={`/${p.slug || p.id}`}
                        className="shrink-0 w-[64px] group"
                        data-testid={`combo-mini-${p.id}`}
                        title={p.name}
                      >
                        <div className="relative w-16 h-20 bg-stone-100 overflow-hidden">
                          <img src={optimizeImg(img, 200)} alt={p.name} className="w-full h-full object-cover object-top group-hover:scale-[1.05] transition-transform duration-500" loading="lazy" decoding="async" />
                        </div>
                        <p className="text-[9px] text-black/50 tabular-nums mt-1 truncate">
                          {((p.discount_price && p.discount_price > 0) ? p.discount_price : p.price || 0).toFixed(0)} TL
                        </p>
                      </Link>
                    );
                  })}
                </div>
              </div>
            )}

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
                    <li>• {(freeShippingThreshold != null ? Number(freeShippingThreshold) : 4000).toLocaleString("tr-TR")} TL ve üzeri siparişlerde ücretsiz kargo</li>
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

        {/* Combo Products — mobile: yatay snap-scroll, desktop: 4-col grid */}
        {comboProducts.length > 0 && (
          <section className="mt-12 md:mt-16 pt-8 md:pt-10 border-t border-black/10" data-testid="product-combo-section">
            <h2 className="text-base md:text-xl font-light tracking-tight mb-5 md:mb-8 px-1">Görünümü Tamamla</h2>
            {/* Mobile horizontal scroll */}
            <div className="md:hidden -mx-4 px-4 overflow-x-auto snap-x snap-mandatory scrollbar-hide">
              <div className="flex gap-3" style={{ minWidth: "max-content" }}>
                {comboProducts.map((p) => {
                  const img = (p.images && p.images[0]) || p.image || "";
                  const hasDiscount = p.discount_price && p.discount_price > 0 && p.discount_price < p.price;
                  return (
                    <div
                      key={p.id}
                      className="snap-start shrink-0 w-[44vw]"
                      data-testid={`combo-product-${p.id}`}
                    >
                      <Link to={`/${p.slug || p.id}`} className="block relative overflow-hidden bg-stone-100 aspect-[2/3]" aria-label={p.name}>
                        <img src={optimizeImg(img, 700)} alt={p.name} className="w-full h-full object-cover object-top" loading="lazy" decoding="async" />
                        <button
                          type="button"
                          onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
                          className="absolute top-1.5 right-1.5 w-7 h-7 flex items-center justify-center"
                          aria-label="Favorilere ekle"
                        >
                          <Bookmark size={15} strokeWidth={1.4} className="text-black" />
                        </button>
                      </Link>
                      <div className="mt-2">
                        <Link to={`/${p.slug || p.id}`} className="block text-[12px] font-light text-black/85 line-clamp-1">
                          {p.name}
                        </Link>
                        <div className="flex items-baseline gap-1.5 mt-0.5">
                          {hasDiscount ? (
                            <>
                              <span className="text-[11px] text-black/40 line-through tabular-nums">{(p.price || 0).toFixed(2)} TL</span>
                              <span className="text-[12px] font-medium tabular-nums">{p.discount_price.toFixed(2)} TL</span>
                            </>
                          ) : (
                            <span className="text-[12px] font-light tabular-nums">{(p.price || 0).toFixed(2)} TL</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Desktop grid */}
            <div className="hidden md:grid grid-cols-4 gap-5">
              {comboProducts.map((p) => {
                const img = (p.images && p.images[0]) || p.image || "";
                const hasDiscount = p.discount_price && p.discount_price > 0 && p.discount_price < p.price;
                return (
                  <div key={p.id} className="group relative">
                    <Link to={`/${p.slug || p.id}`} className="block relative overflow-hidden bg-stone-100 aspect-[2/3]" aria-label={p.name}>
                      <img src={img} alt={p.name} className="w-full h-full object-cover object-top transition-transform duration-700 ease-out group-hover:scale-[1.03]" loading="lazy" />
                      <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
                        className="absolute top-2 right-2 w-8 h-8 flex items-center justify-center bg-white/0 hover:bg-white/80 transition-colors"
                        aria-label="Favorilere ekle"
                      >
                        <Bookmark size={16} strokeWidth={1.4} className="text-black/80" />
                      </button>
                    </Link>
                    <div className="mt-2.5">
                      <Link to={`/${p.slug || p.id}`} className="block text-sm font-light text-black/85 line-clamp-1 hover:underline">{p.name}</Link>
                      <div className="flex items-baseline gap-2 mt-1">
                        {hasDiscount ? (
                          <>
                            <span className="text-sm text-black/40 line-through tabular-nums">{(p.price || 0).toFixed(2)} TL</span>
                            <span className="text-sm font-medium tabular-nums">{p.discount_price.toFixed(2)} TL</span>
                          </>
                        ) : (
                          <span className="text-sm font-light tabular-nums">{(p.price || 0).toFixed(2)} TL</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* Değerlendirmeler (yorum + puan) */}
        <section id="reviews" className="mt-12 pt-12 border-t scroll-mt-24" data-testid="product-reviews">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-base font-light">Değerlendirmeler{reviewTotal > 0 ? ` (${reviewTotal})` : ""}</h2>
            {reviewTotal > 0 && (
              <div className="flex items-center gap-1.5 text-sm">
                <div className="flex">
                  {[1, 2, 3, 4, 5].map((i) => (
                    <Star key={i} size={16} className={i <= Math.round(reviewAvg) ? "fill-black text-black" : "text-gray-300"} />
                  ))}
                </div>
                <span className="text-gray-600">{reviewAvg.toFixed(1)} / 5</span>
              </div>
            )}
          </div>

          {reviews.length > 0 ? (
            <div className="space-y-5 mb-10">
              {reviews.map((r) => (
                <div key={r.id} className="border-b border-black/5 pb-5">
                  <div className="flex items-center gap-2 mb-1">
                    <div className="flex">
                      {[1, 2, 3, 4, 5].map((i) => (
                        <Star key={i} size={13} className={i <= r.rating ? "fill-black text-black" : "text-gray-300"} />
                      ))}
                    </div>
                    <span className="text-xs font-medium">{r.user_name || "Müşteri"}</span>
                    <span className="text-[11px] text-gray-400">
                      {r.created_at ? new Date(r.created_at).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" }) : ""}
                    </span>
                  </div>
                  {r.title && <p className="text-sm font-medium mb-0.5">{r.title}</p>}
                  {r.comment && <p className="text-sm text-gray-600 leading-relaxed">{r.comment}</p>}
                  {r.admin_reply && (
                    <div className="mt-2 ml-3 pl-3 border-l-2 border-black/10">
                      <p className="text-[11px] font-medium text-gray-500 mb-0.5">FACETTE</p>
                      <p className="text-xs text-gray-600">{r.admin_reply}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 mb-10">Bu ürün için henüz değerlendirme yok. İlk yorumu siz yapın.</p>
          )}

          {rvLoggedIn ? (
            <div className="max-w-xl">
              <h3 className="text-sm font-medium mb-3">Değerlendirme yaz</h3>
              <div className="flex items-center gap-1 mb-3">
                {[1, 2, 3, 4, 5].map((i) => (
                  <button key={i} type="button" onClick={() => setRvRating(i)} className="p-0.5" aria-label={`${i} yıldız`}>
                    <Star size={24} className={i <= rvRating ? "fill-black text-black" : "text-gray-300"} />
                  </button>
                ))}
              </div>
              <input
                type="text" value={rvTitle} onChange={(e) => setRvTitle(e.target.value)}
                placeholder="Başlık (opsiyonel)" maxLength={120}
                className="w-full border border-black/15 px-3 py-2 text-sm mb-3 focus:outline-none focus:border-black"
              />
              <textarea
                value={rvComment} onChange={(e) => setRvComment(e.target.value)}
                placeholder="Deneyiminizi paylaşın…" rows={4} maxLength={2000}
                className="w-full border border-black/15 px-3 py-2 text-sm mb-3 focus:outline-none focus:border-black resize-none"
              />
              <button
                type="button" onClick={submitReview} disabled={rvSubmitting}
                className="bg-black text-white text-sm px-6 py-2.5 hover:bg-gray-800 transition disabled:opacity-50"
              >
                {rvSubmitting ? "Gönderiliyor…" : "Gönder"}
              </button>
              <p className="text-[11px] text-gray-400 mt-2">Yorumunuz moderasyon sonrası yayınlanır.</p>
            </div>
          ) : (
            <div className="text-sm text-gray-500">
              Değerlendirme yapmak için <Link to="/giris" className="underline hover:text-black">giriş yapın</Link>.
            </div>
          )}
        </section>

        {/* Similar Products */}
        {similarProducts.length > 0 && (
          <section className="mt-12 pt-12 border-t">
            <h2 className="text-base font-light mb-6">Benzer Ürünler</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {similarProducts.map((p) => <ProductCard key={p.id} product={p} />)}
            </div>
          </section>
        )}

        {/* Son Gezdiklerin — Benzer Ürünler ile aynı 4'lü grid (tek üründe sayfayı kaplamaz) */}
        {recentItems.length > 0 && (
          <section className="mt-12 pt-12 border-t" data-testid="recently-viewed">
            <h2 className="text-base font-light mb-6">Son Gezdiklerin</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {recentItems.slice(0, 4).map((p) => {
                const disc = (p.discount_price && p.discount_price > 0) ? p.discount_price : (p.sale_price && p.sale_price > 0 ? p.sale_price : null);
                const shown = disc || p.price || 0;
                return (
                  <Link key={p.id} to={`/${p.slug || p.id}`} className="group" data-testid={`recent-${p.id}`}>
                    <div className="aspect-[2/3] bg-stone-100 overflow-hidden">
                      <img src={optimizeImg(p.image, 500)} alt={p.name} className="w-full h-full object-cover object-top group-hover:scale-[1.03] transition-transform duration-500" loading="lazy" decoding="async" />
                    </div>
                    <p className="text-[12px] md:text-sm font-light text-black/85 line-clamp-1 mt-2">{p.name}</p>
                    <p className="text-[12px] md:text-sm tabular-nums mt-0.5">{(shown).toFixed(2).replace('.', ',')} TL</p>
                  </Link>
                );
              })}
            </div>
          </section>
        )}
      </div>

      {/* Size Chart Modal – HTML table */}
      {showSizeChart && sizeTableData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setShowSizeChart(false)}>
          <div className="bg-white max-w-2xl w-full max-h-[90vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-white flex justify-between items-center p-4 border-b">
              <h3 className="text-sm font-bold uppercase tracking-wider">Beden Tablosu</h3>
              <button onClick={() => setShowSizeChart(false)} className="p-1"><X size={18} /></button>
            </div>
            <div className="p-6" data-testid="size-table-html">
              <p className="text-xs text-gray-500 mb-4">Tüm ölçüler cm cinsindendir.</p>
              <div className="overflow-x-auto border rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b">
                    <tr>
                      <th className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider">Beden</th>
                      {sizeTableData.columns.map(c => (
                        <th key={c} className="text-left px-4 py-3 text-xs font-bold uppercase tracking-wider">{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sizeTableData.sizes.map((s, i) => (
                      <tr key={s} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                        <td className="px-4 py-3 font-bold text-gray-900">{s}</td>
                        {sizeTableData.columns.map(c => (
                          <td key={c} className="px-4 py-3 text-gray-700">{sizeTableData.values?.[s]?.[c] || '—'}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-xs text-gray-400 mt-4">Değerler ± 1-2 cm tolerans taşıyabilir.</p>
            </div>
          </div>
        </div>
      )}

      <Footer />
    </div>
  );
}

/**
 * ColorSiblings — Aynı modelin (csv_card_id paylaşan) farklı renk ürünlerini
 * miniatür kare swatch'lerle gösterir. Hover ile ürün adı tooltip, click ile
 * o renk varyantının ürün sayfasına yönlendirir.
 */
function ColorSiblings({ productId, currentColor }) {
  const [siblings, setSiblings] = useState([]);
  useEffect(() => {
    if (!productId) return;
    let cancel = false;
    axios.get(`${API}/products/${productId}/color-siblings`)
      .then((r) => { if (!cancel) setSiblings(r.data?.siblings || []); })
      .catch(() => { if (!cancel) setSiblings([]); });
    return () => { cancel = true; };
  }, [productId]);
  if (!siblings.length) return null;
  return (
    <div className="mb-5" data-testid="color-siblings">
      <p className="text-xs uppercase tracking-[0.18em] text-gray-700 mb-2">
        Renk: <span className="text-black font-medium">{currentColor || "—"}</span>
        <span className="text-gray-400 ml-2">+ {siblings.length} renk daha</span>
      </p>
      <div className="flex flex-wrap gap-2">
        {/* Mevcut ürün ilk swatch — siyah border */}
        <div className="w-12 h-12 border-2 border-black bg-gray-50 overflow-hidden flex-shrink-0" title={currentColor || ""}>
          {/* Boş — bu mevcut ürün */}
          <div className="w-full h-full flex items-center justify-center text-[10px] text-black font-bold">●</div>
        </div>
        {siblings.map((s) => (
          <a
            key={s.id}
            href={`/${s.slug || s.id}`}
            className="w-12 h-12 border border-gray-300 hover:border-black bg-white overflow-hidden flex-shrink-0 transition-colors"
            title={`${s.color || s.name || ""}`}
            data-testid={`color-sibling-${s.id}`}
          >
            {s.image
              ? <img src={optimizeImg(s.image, 150)} alt={s.color || ""} className="w-full h-full object-cover" loading="lazy" decoding="async" />
              : <div className="w-full h-full bg-gradient-to-br from-gray-100 to-gray-300" />}
          </a>
        ))}
      </div>
    </div>
  );
}
