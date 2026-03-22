import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, Play } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Default/Fallback content
const DEFAULT_HERO_BANNERS = [
  { id: 1, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/en-yeniler-dc2e.jpg", link: "/kategori/en-yeniler" },
  { id: 2, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/ae79c961-ba0b-49e3-b274-2c6cc78ab700.jpg", link: "/kategori/sale" }
];

const DEFAULT_INSTASHOP = [
  { id: 1, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-ce09fd5d-c580-40eb-87f2-e4637265bad9.jpg", link: "/urun/basic-atki" },
  { id: 2, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-114d3d37-9c7f-495c-8bc2-28d32781818d.jpg", link: "/kategori/ceket" },
  { id: 3, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-e18eff06-8597-4f10-92cb-64b11151a74d.jpg", link: "/kategori/kaban" },
  { id: 4, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-fa071a71-bcaf-452b-90d5-e8cb0c352fe0.jpg", link: "/kategori/pantolon" },
  { id: 5, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-87d15ba0-0081-4b65-acc5-b12328de368b.jpg", link: "/kategori/elbise" }
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

  return (
    <section className="relative" data-testid="hero-slider">
      <div className="relative overflow-hidden">
        {images.map((img, index) => (
          <Link
            key={index}
            to={links[index] || "/"}
            className={`block transition-opacity duration-700 ${index === currentSlide ? "opacity-100" : "opacity-0 absolute inset-0"}`}
          >
            <img src={img} alt={block?.title || ""} className="w-full h-auto block" />
          </Link>
        ))}
      </div>
      {images.length > 1 && (
        <>
          <button onClick={prevSlide} className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronLeft size={20} />
          </button>
          <button onClick={nextSlide} className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
            <ChevronRight size={20} />
          </button>
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
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
  
  return (
    <Link to={block.links?.[0] || "/"} className="block" data-testid="full-banner">
      <img src={block.images[0]} alt={block.title || ""} className="w-full h-auto block" />
    </Link>
  );
}

function HalfBanners({ block }) {
  if (!block?.images || block.images.length < 2) return null;
  
  return (
    <div className="grid grid-cols-2" data-testid="half-banners">
      {block.images.slice(0, 2).map((img, index) => (
        <Link key={index} to={block.links?.[index] || "/"} className="block">
          <img src={img} alt="" className="w-full h-auto block" />
        </Link>
      ))}
    </div>
  );
}

function ProductSlider({ block, products }) {
  const displayProducts = products?.slice(0, block?.settings?.limit || 8) || [];
  
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
        <Link to="/kategori/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
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
              <img src={img} alt="" className="w-full aspect-square object-cover group-hover:scale-105 transition-transform duration-500" />
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
          <img src={block.images[0]} alt={block.title || ""} className="w-full h-auto" />
        </Link>
      )}
    </section>
  );
}

function RotatingText({ block }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const texts = block?.settings?.texts || ["Ücretsiz Kargo", "Güvenli Ödeme", "Kolay İade"];

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % texts.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [texts.length]);

  return (
    <div className="bg-black text-white py-2 text-center text-xs tracking-wider" data-testid="rotating-text">
      <span className="animate-fade-in">{texts[currentIndex]}</span>
    </div>
  );
}

// Block Renderer
function BlockRenderer({ block, products }) {
  switch (block.type) {
    case "hero_slider":
      return <HeroSlider block={block} />;
    case "full_banner":
      return <FullBanner block={block} />;
    case "half_banners":
      return <HalfBanners block={block} />;
    case "product_slider":
      return <ProductSlider block={block} products={products} />;
    case "instashop":
      return <InstaShop block={block} />;
    case "text_block":
      return <TextBlock block={block} />;
    case "video_banner":
      return <VideoBanner block={block} />;
    case "rotating_text":
      return <RotatingText block={block} />;
    default:
      return null;
  }
}

export default function Home() {
  const [products, setProducts] = useState([]);
  const [blocks, setBlocks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [productsRes, blocksRes] = await Promise.all([
        axios.get(`${API}/products?limit=20&sort=created_at&order=desc`),
        axios.get(`${API}/page-blocks?page=home`).catch(() => ({ data: [] }))
      ]);
      
      setProducts(productsRes.data?.products || []);
      
      // Sort blocks by sort_order and filter active ones
      const activeBlocks = (blocksRes.data || [])
        .filter(b => b.is_active)
        .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
      
      setBlocks(activeBlocks);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  // Check if we have CMS blocks to render
  const hasCMSBlocks = blocks.length > 0;
  
  // Check if specific block types exist
  const hasHeroSlider = blocks.some(b => b.type === "hero_slider");
  const hasProductSlider = blocks.some(b => b.type === "product_slider");
  const hasInstaShop = blocks.some(b => b.type === "instashop");

  return (
    <div className="min-h-screen bg-white" data-testid="home-page">
      <Header />
      
      {/* Render CMS Blocks if available */}
      {hasCMSBlocks ? (
        <>
          {blocks.map((block) => (
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
                <Link to="/kategori/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
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
          <Link to="/kategori/en-yeniler" className="block">
            <img src="https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-cb23757c-6.jpg" alt="" className="w-full h-auto block" />
          </Link>

          {/* Two Half-Width Banners */}
          <div className="grid grid-cols-2">
            <Link to="/kategori/gomlek" className="block">
              <img src="https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-65777bd3-0.jpg" alt="" className="w-full h-auto block" />
            </Link>
            <Link to="/kategori/aksesuar" className="block">
              <img src="https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-7b3e27f9-5.jpg" alt="" className="w-full h-auto block" />
            </Link>
          </div>

          {/* Products Grid */}
          <section className="max-w-screen-2xl mx-auto px-4 py-12">
            {loading ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 gap-y-8">
                {[...Array(8)].map((_, i) => (
                  <div key={i} className="animate-pulse">
                    <div className="aspect-[3/4] bg-gray-100 mb-3" />
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
              <Link to="/kategori/en-yeniler" className="inline-block border border-black px-10 py-2.5 text-xs tracking-wider uppercase hover:bg-black hover:text-white transition-colors">
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
