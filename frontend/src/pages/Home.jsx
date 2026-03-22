import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Home() {
  const [products, setProducts] = useState([]);
  const [banners, setBanners] = useState([]);
  const [categories, setCategories] = useState([]);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [prodRes, bannerRes, catRes] = await Promise.all([
        axios.get(`${API}/products?is_new=true&limit=12`),
        axios.get(`${API}/banners`),
        axios.get(`${API}/categories`),
      ]);
      setProducts(prodRes.data?.products || []);
      setBanners(bannerRes.data || []);
      setCategories(catRes.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const heroSliders = banners.filter(b => b.position === "hero_slider" || b.position === "hero");
  const singleBanner = banners.find(b => b.position === "single_banner");
  const doubleBanners = banners.filter(b => b.position === "double_banner").slice(0, 2);
  const instashopBanners = banners.filter(b => b.position === "instashop");

  const nextSlide = () => setCurrentSlide((prev) => (prev + 1) % Math.max(heroSliders.length, 1));
  const prevSlide = () => setCurrentSlide((prev) => (prev - 1 + Math.max(heroSliders.length, 1)) % Math.max(heroSliders.length, 1));

  // Auto slide
  useEffect(() => {
    if (heroSliders.length > 1) {
      const interval = setInterval(nextSlide, 5000);
      return () => clearInterval(interval);
    }
  }, [heroSliders.length]);

  return (
    <div className="min-h-screen" data-testid="home-page">
      <Header />
      
      {/* Hero Slider */}
      <section className="relative h-[60vh] md:h-[80vh] bg-gray-100 overflow-hidden">
        {heroSliders.length > 0 ? (
          <>
            {heroSliders.map((banner, index) => (
              <div
                key={banner.id}
                className={`absolute inset-0 transition-opacity duration-700 ${index === currentSlide ? "opacity-100" : "opacity-0 pointer-events-none"}`}
              >
                {banner.video_url ? (
                  <video
                    src={banner.video_url}
                    autoPlay
                    muted
                    loop
                    playsInline
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <img
                    src={banner.image_url}
                    alt={banner.title || "Banner"}
                    className="w-full h-full object-cover"
                  />
                )}
                {(banner.title || banner.subtitle) && (
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="text-center text-white">
                      {banner.title && <h1 className="text-4xl md:text-6xl font-light tracking-wider mb-4">{banner.title}</h1>}
                      {banner.subtitle && <p className="text-lg md:text-xl mb-6">{banner.subtitle}</p>}
                      {banner.link_url && (
                        <Link to={banner.link_url} className="btn-primary bg-white text-black hover:bg-gray-100">
                          Keşfet
                        </Link>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))}
            
            {/* Navigation */}
            {heroSliders.length > 1 && (
              <>
                <button 
                  onClick={prevSlide}
                  className="absolute left-4 top-1/2 -translate-y-1/2 w-12 h-12 bg-white/90 flex items-center justify-center hover:bg-white transition-colors"
                  data-testid="slider-prev"
                >
                  <ChevronLeft size={24} />
                </button>
                <button 
                  onClick={nextSlide}
                  className="absolute right-4 top-1/2 -translate-y-1/2 w-12 h-12 bg-white/90 flex items-center justify-center hover:bg-white transition-colors"
                  data-testid="slider-next"
                >
                  <ChevronRight size={24} />
                </button>
                
                {/* Dots */}
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-2">
                  {heroSliders.map((_, index) => (
                    <button
                      key={index}
                      onClick={() => setCurrentSlide(index)}
                      className={`w-2 h-2 rounded-full transition-colors ${index === currentSlide ? "bg-white" : "bg-white/50"}`}
                    />
                  ))}
                </div>
              </>
            )}
          </>
        ) : (
          <div className="w-full h-full bg-gradient-to-b from-gray-100 to-gray-200 flex items-center justify-center">
            <div className="text-center">
              <h1 className="text-5xl md:text-7xl font-light tracking-[0.3em] mb-4">FACETTE</h1>
              <p className="text-lg text-gray-600 tracking-wider">Farkı Hisset</p>
              <Link to="/kategori/en-yeniler" className="btn-primary mt-8 inline-block">
                Koleksiyonu Keşfet
              </Link>
            </div>
          </div>
        )}
      </section>

      {/* Single Banner */}
      {singleBanner && (
        <section className="container-main py-8">
          <Link to={singleBanner.link_url || "#"} className="block relative overflow-hidden group">
            <img 
              src={singleBanner.image_url} 
              alt={singleBanner.title || "Banner"} 
              className="w-full h-48 md:h-64 object-cover transition-transform duration-700 group-hover:scale-105"
            />
            {singleBanner.title && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                <h2 className="text-white text-2xl md:text-4xl font-light tracking-wider">{singleBanner.title}</h2>
              </div>
            )}
          </Link>
        </section>
      )}

      {/* Double Banners */}
      {doubleBanners.length > 0 && (
        <section className="container-main py-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {doubleBanners.map((banner) => (
              <Link key={banner.id} to={banner.link_url || "#"} className="block relative overflow-hidden group">
                <img 
                  src={banner.image_url} 
                  alt={banner.title || "Banner"} 
                  className="w-full h-64 md:h-96 object-cover transition-transform duration-700 group-hover:scale-105"
                />
                {banner.title && (
                  <div className="absolute bottom-6 left-6">
                    <h3 className="text-white text-xl md:text-2xl font-light tracking-wider drop-shadow-lg">{banner.title}</h3>
                  </div>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Category Banners (fallback if no double banners) */}
      {doubleBanners.length === 0 && categories.length > 0 && (
        <section className="container-main py-8">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {categories.slice(0, 3).map((cat) => (
              <Link key={cat.id} to={`/kategori/${cat.slug}`} className="block relative overflow-hidden group bg-gray-100 aspect-[3/4]">
                {cat.image_url && (
                  <img 
                    src={cat.image_url} 
                    alt={cat.name} 
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
                )}
                <div className="absolute inset-0 flex items-end p-6 bg-gradient-to-t from-black/50 to-transparent">
                  <h3 className="text-white text-lg md:text-xl font-medium tracking-wider">{cat.name}</h3>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Products Section */}
      <section className="container-main py-12">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-xl md:text-2xl font-light tracking-wider uppercase">En Yeniler</h2>
          <Link to="/kategori/en-yeniler" className="text-sm underline hover:no-underline">
            Tümünü Gör
          </Link>
        </div>

        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {[...Array(8)].map((_, i) => (
              <div key={i} className="animate-pulse">
                <div className="aspect-[3/4] bg-gray-200" />
                <div className="mt-3 space-y-2">
                  <div className="h-3 bg-gray-200 w-1/3" />
                  <div className="h-4 bg-gray-200 w-2/3" />
                  <div className="h-4 bg-gray-200 w-1/4" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-6">
            {products.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
        )}
      </section>

      {/* InstaShop Section */}
      {instashopBanners.length > 0 && (
        <section className="py-12 bg-gray-50">
          <div className="container-main">
            <h2 className="text-xl md:text-2xl font-light tracking-wider uppercase text-center mb-8">
              @facette collection on instagram
            </h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {instashopBanners.slice(0, 5).map((banner) => (
                <Link key={banner.id} to={banner.link_url || "#"} className="block relative overflow-hidden group aspect-square">
                  <img 
                    src={banner.image_url} 
                    alt="Instagram" 
                    className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                  />
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center">
                    <span className="opacity-0 group-hover:opacity-100 text-white text-sm transition-opacity">
                      Ürünü Gör
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      <Footer />
    </div>
  );
}
