import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import axios from "axios";
import Header from "../components/Header";
import Footer from "../components/Footer";
import ProductCard from "../components/ProductCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Hero slider images - full width
const HERO_BANNERS = [
  { id: 1, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/en-yeniler-dc2e.jpg", link: "/kategori/en-yeniler" },
  { id: 2, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/ae79c961-ba0b-49e3-b274-2c6cc78ab700.jpg", link: "/kategori/sale" }
];

// Full width banner (bloom together)
const FULL_WIDTH_BANNER = {
  image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-cb23757c-6.jpg",
  link: "/kategori/en-yeniler"
};

// Two half-width banners
const HALF_BANNERS = [
  { id: 1, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-65777bd3-0.jpg", link: "/kategori/gomlek" },
  { id: 2, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-7b3e27f9-5.jpg", link: "/kategori/aksesuar" }
];

// InstaShop images
const INSTASHOP = [
  { id: 1, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-ce09fd5d-c580-40eb-87f2-e4637265bad9.jpg", link: "/urun/basic-atki" },
  { id: 2, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-114d3d37-9c7f-495c-8bc2-28d32781818d.jpg", link: "/kategori/ceket" },
  { id: 3, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-e18eff06-8597-4f10-92cb-64b11151a74d.jpg", link: "/kategori/kaban" },
  { id: 4, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-fa071a71-bcaf-452b-90d5-e8cb0c352fe0.jpg", link: "/kategori/pantolon" },
  { id: 5, image: "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/orj-87d15ba0-0081-4b65-acc5-b12328de368b.jpg", link: "/kategori/elbise" }
];

export default function Home() {
  const [products, setProducts] = useState([]);
  const [currentSlide, setCurrentSlide] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchProducts();
  }, []);

  const fetchProducts = async () => {
    try {
      const res = await axios.get(`${API}/products?limit=20&sort=created_at&order=desc`);
      setProducts(res.data?.products || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (HERO_BANNERS.length > 1) {
      const interval = setInterval(() => {
        setCurrentSlide((prev) => (prev + 1) % HERO_BANNERS.length);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, []);

  const nextSlide = () => setCurrentSlide((prev) => (prev + 1) % HERO_BANNERS.length);
  const prevSlide = () => setCurrentSlide((prev) => (prev - 1 + HERO_BANNERS.length) % HERO_BANNERS.length);

  return (
    <div className="min-h-screen bg-white">
      <Header />
      
      {/* Hero Slider - Full Width, No Gaps */}
      <section className="relative">
        <div className="relative overflow-hidden">
          {HERO_BANNERS.map((banner, index) => (
            <Link
              key={banner.id}
              to={banner.link}
              className={`block transition-opacity duration-700 ${index === currentSlide ? "opacity-100" : "opacity-0 absolute inset-0"}`}
            >
              <img src={banner.image} alt="" className="w-full h-auto block" />
            </Link>
          ))}
        </div>
        {HERO_BANNERS.length > 1 && (
          <>
            <button onClick={prevSlide} className="absolute left-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
              <ChevronLeft size={20} />
            </button>
            <button onClick={nextSlide} className="absolute right-4 top-1/2 -translate-y-1/2 w-10 h-10 bg-white/80 flex items-center justify-center hover:bg-white">
              <ChevronRight size={20} />
            </button>
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex gap-2">
              {HERO_BANNERS.map((_, i) => (
                <button key={i} onClick={() => setCurrentSlide(i)} className={`w-2 h-2 rounded-full ${i === currentSlide ? 'bg-black' : 'bg-white/70'}`} />
              ))}
            </div>
          </>
        )}
      </section>

      {/* Full Width Banner - No Margin, No Padding */}
      <Link to={FULL_WIDTH_BANNER.link} className="block">
        <img src={FULL_WIDTH_BANNER.image} alt="" className="w-full h-auto block" />
      </Link>

      {/* Two Half-Width Banners - No Gap */}
      <div className="grid grid-cols-2">
        {HALF_BANNERS.map((banner) => (
          <Link key={banner.id} to={banner.link} className="block">
            <img src={banner.image} alt="" className="w-full h-auto block" />
          </Link>
        ))}
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
      <section className="py-10 bg-gray-50">
        <div className="max-w-screen-2xl mx-auto px-4">
          <p className="text-center text-[10px] tracking-[0.3em] uppercase text-gray-500 mb-6">@facette collection</p>
          <div className="grid grid-cols-5 gap-1">
            {INSTASHOP.map((item) => (
              <Link key={item.id} to={item.link} className="block overflow-hidden group">
                <img src={item.image} alt="" className="w-full aspect-square object-cover group-hover:scale-105 transition-transform duration-500" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
