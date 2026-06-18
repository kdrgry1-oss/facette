import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Play } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";
import { optimizeImg, aspectFromDims } from "../lib/img";
import { trackSelectPromotion } from "../lib/dataLayer";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Default/Fallback content
const DEFAULT_HERO_BANNERS = [
  { id: 1, image: "https://cdn.facette.com.tr/pagedesign/en-yeniler-dc2e-1920.webp", link: "/en-yeniler" },
  { id: 2, image: "https://cdn.facette.com.tr/pagedesign/ae79c961-ba0b-49e3-b274-2c6cc78ab700-1920.webp", link: "/sale" }
];

const DEFAULT_INSTASHOP = [
  { id: 1, image: "https://cdn.facette.com.tr/pagedesign/orj-ce09fd5d-c580-40eb-87f2-e4637265bad9-1920.webp", link: "/basic-atki" },
  { id: 2, image: "https://cdn.facette.com.tr/pagedesign/orj-114d3d37-9c7f-495c-8bc2-28d32781818d-1920.webp", link: "/ceket" },
  { id: 3, image: "https://cdn.facette.com.tr/pagedesign/orj-e18eff06-8597-4f10-92cb-64b11151a74d-1920.webp", link: "/kaban" },
  { id: 4, image: "https://cdn.facette.com.tr/pagedesign/orj-fa071a71-bcaf-452b-90d5-e8cb0c352fe0-1920.webp", link: "/pantolon" },
  { id: 5, image: "https://cdn.facette.com.tr/pagedesign/orj-87d15ba0-0081-4b65-acc5-b12328de368b-1920.webp", link: "/elbise" }
];

// Block Components
function HeroSlider({ block }) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const images = block?.images?.length > 0 ? block.images : DEFAULT_HERO_BANNERS.map(b => b.image);
  const links = block?.links || DEFAULT_HERO_BANNERS.map(b => b.link);

  useEffect(() => {
    if (images.length > 1) {
      const interval = setInterval(() => {
        setCurrentSlide((prev) => (prev + 1) % images.length);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [images.length]);

  const nextSlide = () => setCurrentSlide((prev) => (prev + 1) % images.length);
  const prevSlide = () => setCurrentSlide((prev) => (prev - 1 + images.length) % images.length);

  const dims = block?.settings?.img_dims?.[0]
    || (block?.settings?.img_width ? [block.settings.img_width, block.settings.img_height] : null);
  const aspect = aspectFromDims(dims, "16 / 9");

  return (
    <section className="relative" data-testid="hero-slider">
      <div className="relative overflow-hidden w-full bg-stone-100" style={{ aspectRatio: aspect }}>
        {images.map((img, index) => (
          <Link
            key={index}
            to={links[index] || "/"}
            onClick={() => {
              try {
                trackSelectPromotion({
                  promotionId: `hero_${index + 1}`,
                  promotionName: block?.title || links[index] || `Hero ${index + 1}`,
                });
              } catch (_) { /* silent */ }
            }}
            className={`absolute inset-0 block transition-opacity duration-700 ${index === currentSlide ? "opacity-100 z-10" : "opacity-0"}`}
          >
            <img
              src={optimizeImg(img, 1920, 78)}
              alt={block?.title || ""}
              className="w-full h-full object-cover block"
              fetchPriority={index === 0 ? "high" : "auto"}
              loading={index === 0 ? "eager" : "lazy"}
              decoding="async"
              width={dims?.[0]}
              height={dims?.[1]}
            />
          </Link>
        ))}
      </div>
      {images.length > 1 && (
        <>
          <button onClick={prevSlide} className="absolute left-4 top-1/2 -translate-y-1/2 z-20 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronLeft size={20} />
          </button>
          <button onClick={nextSlide} className="absolute right-4 top-1/2 -translate-y-1/2 z-20 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronRight size={20} />
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex gap-2">
            {images.map((_, i) => (
              <button key={i} onClick={() => setCurrentSlide(i)} className={`w-2 h-2 rounded-full ${i === currentSlide ? 'bg-black' : 'bg-white/70'}`} />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function FullBanner({ block }) {
  if (!block?.images?.[0]) return null;
  const dims = block?.settings?.img_dims?.[0];
  return (
    <Link to={block.links?.[0] || "/"} className="block w-full bg-stone-100" data-testid="full-banner" style={{ aspectRatio: aspectFromDims(dims, "16 / 6") }}>
      <img src={optimizeImg(block.images[0], 1920)} alt={block.title || ""} className="w-full h-full object-cover block" loading="lazy" decoding="async" />
    </Link>
  );
}

function HalfBanners({ block }) {
  if (!block?.images || block.images.length < 2) return null;
  // İki banner için TEK ve tutarlı en-boy oranı. Yüklenen görselin piksel
  // boyutundan bağımsız: hangi boyutta görsel eklenirse eklensin, ikisi de
  // eşit boyutta ve sayfaya sığarak (object-cover ile) görünür. Eski/karışık
  // kayıtlı boyutların yerleşimi bozmasını engeller. Admin isterse
  // block.settings.aspect ("16 / 9" gibi) ile değiştirebilir.
  const aspect = block?.settings?.aspect || "16 / 9";
  return (
    <div className="grid grid-cols-2" data-testid="half-banners">
      {block.images.slice(0, 2).map((img, index) => (
        <Link key={index} to={block.links?.[index] || "/"} className="block bg-stone-100 overflow-hidden" style={{ aspectRatio: aspect }}>
          <img src={optimizeImg(img, 1000)} alt="" className="w-full h-full object-cover block" loading="lazy" decoding="async" />
        </Link>
      ))}
    </div>
  );
}

function ProductSlider({ block, products }) {
  const selectedIds = block?.settings?.product_ids;
  let displayProducts;
  if (selectedIds && selectedIds.length > 0) {
    // Show only the selected products in the configured order
    displayProducts = selectedIds
      .map(id => products?.find(p => p._id === id || p.id === id))
      .filter(Boolean);
  } else {
    displayProducts = products?.slice(0, block?.settings?.limit || 8) || [];
  }
  
  if (displayProducts.length === 0) return null;

  return (
    <section className="max-w-screen-2xl mx-auto px-4 py-12" data-testid="product-slider">
      {block?.title && (
        <h2 className="text-center text-lg font-medium tracking-wide mb-8">{block.title}</h2>
      )}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
        {displayProducts.map((product) => (
          <ProductCard key={product.id} product={product} />
        ))}
      </div>
      <div className="text-center mt-12">
        <Link to="/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
          Tümünü Gör
        </Link>
      </div>
    </section>
  );
}

function InstaShop({ block }) {
  const images = block?.images?.length > 0 ? block.images : DEFAULT_INSTASHOP.map(i => i.image);
  const links = block?.links?.length > 0 ? block.links : DEFAULT_INSTASHOP.map(i => i.link);

  return (
    <section className="py-10 bg-gray-50" data-testid="instashop">
      <div className="max-w-screen-2xl mx-auto px-4">
        <p className="text-center text-[10px] tracking-[0.3em] uppercase text-gray-500 mb-6">
          {block?.title || "@facette collection"}
        </p>
        <div className="grid grid-cols-5 gap-1">
          {images.slice(0, 5).map((img, index) => (
            <Link key={index} to={links[index] || "/"} className="block overflow-hidden group">
              <img src={optimizeImg(img, 600)} alt="" className="w-full aspect-square object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy" decoding="async" />
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

function TextBlock({ block }) {
  if (!block?.title && !block?.settings?.text) return null;

  return (
    <section className="py-16 text-center" data-testid="text-block">
      <div className="max-w-2xl mx-auto px-4">
        {block.title && (
          <h2 className="text-2xl md:text-3xl font-light tracking-wide mb-4">{block.title}</h2>
        )}
        {block.settings?.text && (
          <p className="text-gray-600">{block.settings.text}</p>
        )}
        {block.links?.[0] && (
          <Link to={block.links[0]} className="inline-block mt-6 border border-black px-8 py-2 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
            Keşfet
          </Link>
        )}
      </div>
    </section>
  );
}

function VideoBanner({ block }) {
  const [playing, setPlaying] = useState(false);
  
  if (!block?.settings?.video_url && !block?.images?.[0]) return null;

  return (
    <section className="relative" data-testid="video-banner">
      {block.settings?.video_url ? (
        <div className="relative aspect-video bg-black">
          {playing ? (
            <video 
              src={block.settings.video_url} 
              autoPlay 
              loop 
              muted 
              playsInline
              className="w-full h-full object-cover"
            />
          ) : (
            <>
              <img 
                src={block.images?.[0] || ""} 
                alt={block.title || ""} 
                className="w-full h-full object-cover"
              />
              <button 
                onClick={() => setPlaying(true)}
                className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/30 transition-colors"
              >
                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center">
                  <Play size={24} className="ml-1" />
                </div>
              </button>
            </>
          )}
        </div>
      ) : (
        <Link to={block.links?.[0] || "/"} className="block">
          <img src={optimizeImg(block.images[0], 1920)} alt={block.title || ""} className="w-full h-auto" loading="lazy" decoding="async" />
        </Link>
      )}
    </section>
  );
}

function RotatingText({ block }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const texts = (block?.settings?.texts || ["500 TL Üzeri Ücretsiz Kargo"]).filter((t) => (t || "").trim());

  useEffect(() => {
    if (texts.length < 2) return;
    const sec = Math.max(2, Number(block?.settings?.interval) || 4);
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % texts.length);
    }, sec * 1000);
    return () => clearInterval(interval);
  }, [texts.length, block]);

  if (texts.length === 0) return null;
  const bg = block?.settings?.bg_color || "#ffffff";
  const fg = block?.settings?.text_color || "#374151";

  return (
    <div
      className="text-center py-1 border-b border-gray-100"
      style={{ backgroundColor: bg }}
      data-testid="rotating-text"
    >
      <span
        key={currentIndex}
        className="text-[9px] md:text-[10px] tracking-[0.3em] uppercase font-light"
        style={{ color: fg }}
      >
        {texts[currentIndex % texts.length]}
      </span>
    </div>
  );
}

// İlk yükleme skeleton'u — page-blocks fetch tamamlanana kadar gösterilir.
// Böylece hardcoded DEFAULT_HERO_BANNERS (eski görseller) bir an flash etmez.
function HomeSkeleton() {
  return (
    <div data-testid="home-skeleton">
      <div className="w-full aspect-[16/7] bg-stone-100 animate-pulse" />
      <section className="max-w-screen-2xl mx-auto px-4 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="animate-pulse">
              <div className="aspect-[2/3] bg-stone-100 mb-3" />
              <div className="h-3 bg-stone-100 w-3/4 mb-2" />
              <div className="h-3 bg-stone-100 w-1/3" />
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// Block Renderer
function BlockRenderer({ block, products }) {
  let component = null;
  switch (block.type) {
    case "hero_slider":   component = <HeroSlider block={block} />; break;
    case "full_banner":   component = <FullBanner block={block} />; break;
    case "half_banners":  component = <HalfBanners block={block} />; break;
    case "product_slider":component = <ProductSlider block={block} products={products} />; break;
    case "instashop":     component = <InstaShop block={block} />; break;
    case "text_block":    component = <TextBlock block={block} />; break;
    case "video_banner":  component = <VideoBanner block={block} />; break;
    case "rotating_text": component = <RotatingText block={block} />; break;
    case "countdown_bar": return null; // Header'da render ediliyor — burada gösterme
    default: return null;
  }
  // Cihaz görünürlüğü — show_desktop / show_mobile false ise tailwind ile gizle
  const showDesktop = block.show_desktop !== false;
  const showMobile  = block.show_mobile  !== false;
  if (!showDesktop && !showMobile) return null;
  let visClass = "";
  if (!showDesktop) visClass = "md:hidden";       // sadece mobil
  else if (!showMobile) visClass = "hidden md:block"; // sadece masaüstü
  return visClass ? <div className={visClass}>{component}</div> : component;
}

export default function Home() {
  const [products, setProducts] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const [productsRes, blocksRes] = await Promise.all([
          axios.get(`${API}/products?limit=100&sort=created_at&order=desc`),
          axios.get(`${API}/page-blocks?page=home`).catch(() => ({ data: [] }))
        ]);
        if (!active) return;
        setProducts(productsRes.data?.products || []);

        const isPreview = new URLSearchParams(window.location.search).get('preview') === 'true';
        // Sort blocks by sort_order and filter active ones (non-mutating)
        const activeBlocks = (blocksRes.data || [])
          .filter(b => isPreview || b.is_active)
          .toSorted((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
        setBlocks(activeBlocks);
      } catch (err) {
        console.error(err);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  // Check if we have CMS blocks to render
  const hasCMSBlocks = blocks.length > 0;
  
  // Check if specific block types exist
  const hasHeroSlider = blocks.some(b => b.type === "hero_slider");
  const hasProductSlider = blocks.some(b => b.type === "product_slider");
  const hasInstaShop = blocks.some(b => b.type === "instashop");

  // Üst duyuru barı (rotating_text) — orijinaldeki gibi en üstte (header üstü) gösterilir,
  // blok akışında tekrar render edilmemesi için ayrılır.
  const rotatingBlock = blocks.find(b => b.type === "rotating_text");
  const flowBlocks = blocks.filter(b => b.type !== "rotating_text");

  return (
    <div className="min-h-screen bg-white" data-testid="home-page">
      {rotatingBlock && <RotatingText block={rotatingBlock} />}
      <Header />
      
      {/* İlk yüklemede eski görsellerin (hardcoded default) flash etmemesi için
          page-blocks fetch tamamlanana kadar skeleton göster. */}
      {loading ? (
        <HomeSkeleton />
      ) : hasCMSBlocks ? (
        <>
          {flowBlocks.map((block) => (
            <BlockRenderer key={block.id} block={block} products={products} />
          ))}
          
          {/* Add default product grid if no product_slider block */}
          {!hasProductSlider && products.length > 0 && (
            <section className="max-w-screen-2xl mx-auto px-4 py-12">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
                {products.slice(0, 8).map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
              <div className="text-center mt-12">
                <Link to="/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
                  Kategoriye Git
                </Link>
              </div>
            </section>
          )}
          
          {/* Add default InstaShop if no instashop block */}
          {!hasInstaShop && (
            <InstaShop block={{}} />
          )}
        </>
      ) : (
        /* Default Layout when no CMS blocks */
        <>
          {/* Hero Slider */}
          <HeroSlider block={{ images: DEFAULT_HERO_BANNERS.map(b => b.image), links: DEFAULT_HERO_BANNERS.map(b => b.link) }} />

          {/* Full Width Banner */}
          <Link to="/en-yeniler" className="block">
            <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-cb23757c-6-1920.webp", 1920)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
          </Link>

          {/* Two Half-Width Banners */}
          <div className="grid grid-cols-2">
            <Link to="/gomlek" className="block">
              <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-65777bd3-0-1920.webp", 1000)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
            </Link>
            <Link to="/aksesuar" className="block">
              <img src={optimizeImg("https://cdn.facette.com.tr/pagedesign/title-7b3e27f9-5-1920.webp", 1000)} alt="" className="w-full h-auto block" loading="lazy" decoding="async" />
            </Link>
          </div>

          {/* Products Grid */}
          <section className="max-w-screen-2xl mx-auto px-4 py-12">
            {loading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 gap-y-8">
                {[...Array(8)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-[2/3] bg-gray-100 mb-3" />
                    <div className="h-4 bg-gray-100 w-3/4 mb-2" />
                    <div className="h-4 bg-gray-100 w-1/3" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
                {products.map((product) => (
                  <ProductCard key={product.id} product={product} />
                ))}
              </div>
            )}
            <div className="text-center mt-12">
              <Link to="/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
                Kategoriye Git
              </Link>
            </div>
          </section>

          {/* InstaShop */}
          <InstaShop block={{}} />
        </>
      )}

      <Footer />
    </div>
  );
}
