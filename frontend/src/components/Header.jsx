import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
import CountdownBar from "./CountdownBar";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Mega menu structure - facette.com.tr exact structure
const GIYIM_MENU = {
  "ÜST GİYİM": [
    { name: "Elbise", slug: "elbise" },
    { name: "Bluz", slug: "bluz" },
    { name: "Kazak", slug: "kazak" },
    { name: "Sweatshirt", slug: "sweatshirt" },
    { name: "Takım", slug: "takim" },
    { name: "Tişört", slug: "tisort" },
    { name: "Gömlek", slug: "gomlek" },
  ],
  "ALT GİYİM": [
    { name: "Etek", slug: "etek" },
    { name: "Pantolon", slug: "pantolon" },
    { name: "Şort", slug: "sort" },
    { name: "Jean", slug: "jean" },
  ],
  "DIŞ GİYİM": [
    { name: "Kaban", slug: "kaban" },
    { name: "Mont", slug: "mont" },
    { name: "Hırka", slug: "hirka" },
    { name: "Trençkot", slug: "trenckot" },
    { name: "Ceket", slug: "ceket" },
  ]
};

const AKSESUAR_MENU = [
  { name: "Çanta", slug: "canta" },
  { name: "Şal", slug: "sal" },
  { name: "Atkı", slug: "atki" },
  { name: "Kemer", slug: "kemer" },
  { name: "Şapka", slug: "sapka" },
];

// Menu images for right side
const MENU_IMAGES = {
  giyim: [
    "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-65777bd3-0.jpg",
    "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-7b3e27f9-5.jpg"
  ],
  aksesuar: [
    "https://static.ticimax.cloud/cdn-cgi/image/width=-,quality=99/37439/uploads/sayfatasarim/sayfa7/title-7b3e27f9-5.jpg"
  ]
};

export default function Header({ hideMenu = false }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [popularSearches, setPopularSearches] = useState([]);
  const [activeMenu, setActiveMenu] = useState(null);
  const [hoveredCategory, setHoveredCategory] = useState(null); // alt kategori slug (ceket, sort, ...)
  const [megaProducts, setMegaProducts] = useState({}); // {slug: [products]}
  
  const { itemCount, setIsOpen } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isCheckout = location.pathname.includes('/odeme') || location.pathname.includes('/checkout');

  // Mega menü: hoveredCategory veya activeMenu için en çok satan ürünleri lazy fetch (3 ürün)
  useEffect(() => {
    const slug = hoveredCategory || activeMenu;
    if (slug && !megaProducts[slug]) {
      axios.get(`${API}/products?category=${slug}&limit=3&sort=popular`)
        .then(r => setMegaProducts(prev => ({ ...prev, [slug]: r.data?.products || [] })))
        .catch(() => setMegaProducts(prev => ({ ...prev, [slug]: [] })));
    }
  }, [hoveredCategory, activeMenu]);

  // Aktif olarak gösterilecek ürün listesi: önce alt kategori hover, yoksa ana kategori (3 ürün)
  const activeMegaSlug = hoveredCategory || activeMenu;
  const activeMegaProducts = (megaProducts[activeMegaSlug] || []).slice(0, 3);

  // Mega menü kapanma timer'ı — fare üzerine geldiğinde anında kapanmasın, 200ms gecikme
  const [closeTimer, setCloseTimer] = useState(null);
  const openMenu = (m) => {
    if (closeTimer) { clearTimeout(closeTimer); setCloseTimer(null); }
    setActiveMenu(m);
  };
  const scheduleClose = () => {
    const t = setTimeout(() => { setActiveMenu(null); setHoveredCategory(null); }, 250);
    setCloseTimer(t);
  };
  const cancelClose = () => {
    if (closeTimer) { clearTimeout(closeTimer); setCloseTimer(null); }
  };

  useEffect(() => {
    if (searchOpen && popularSearches.length === 0) {
      fetchPopularSearches();
    }
  }, [searchOpen]);

  useEffect(() => {
    if (searchQuery.length >= 1) {
      const timer = setTimeout(() => performSearch(searchQuery), 300);
      return () => clearTimeout(timer);
    } else {
      setSearchResults([]);
    }
  }, [searchQuery]);

  const fetchPopularSearches = async () => {
    try {
      const res = await axios.get(`${API}/search/popular`);
      setPopularSearches(res.data || []);
    } catch (err) {
      setPopularSearches([
        { term: "elbise", count: 150 },
        { term: "bluz", count: 120 },
        { term: "pantolon", count: 100 },
      ]);
    }
  };

  const performSearch = async (query) => {
    try {
      const res = await axios.get(`${API}/products?search=${encodeURIComponent(query)}&limit=6`);
      setSearchResults(res.data?.products || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/arama?q=${encodeURIComponent(searchQuery)}`);
      setSearchOpen(false);
      setSearchQuery("");
    }
  };

  return (
    <>
      {/* Top Banner — admin tarafından yönetilen geri sayım barı (countdown_bar block) */}
      {!isCheckout && <CountdownBar />}

      {/* Statik üst duyuru — countdown ile beraber HER ZAMAN görünür.
          Admin > Sayfa Tasarımı'ndaki "rotating_text" bloğundan yönetilebilir;
          o blok aktif değilse de varsayılan "500 TL Üzeri Ücretsiz Kargo" gösterilir. */}
      {!isCheckout && (
        <div className="bg-white text-black border-b border-gray-100 text-center py-1">
          <p className="text-[9px] md:text-[10px] tracking-[0.3em] uppercase font-light text-gray-700">
            500 TL Üzeri Ücretsiz Kargo · İlk Üyeliklere Özel %10 İndirim
          </p>
        </div>
      )}

      {/* Main Header */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-xl border-b border-black/5 transition-all duration-300">
        <div className="max-w-screen-2xl mx-auto px-3 md:px-6">
          <div className="relative flex items-center h-12 md:h-14">
            {/* Left: Navigation Menu */}
            <div className="flex-1 flex items-center">
              {!isCheckout && (
                <>
                  <button
                    className="lg:hidden p-2 -ml-2"
                    onClick={() => setMobileMenuOpen(true)}
                    aria-label="Menü"
                    data-testid="mobile-menu-btn"
                  >
                    <Menu size={20} strokeWidth={1.4} />
                  </button>

                  <nav className="hidden lg:flex items-center gap-5">
                    {/* EN YENİLER */}
                    <Link
                      to="/kategori/en-yeniler"
                      className="text-xs font-light tracking-[0.2em] uppercase py-4 hover:opacity-60"
                    >
                      EN YENİLER
                    </Link>

                    {/* GİYİM - Mega Menu */}
                    <div 
                      className="relative"
                      onMouseEnter={() => openMenu('giyim')}
                      onMouseLeave={scheduleClose}
                    >
                      <Link
                        to="/kategori/giyim"
                        className="text-xs font-light tracking-[0.2em] uppercase py-4 hover:opacity-60 flex items-center"
                      >
                        GİYİM
                      </Link>
                    </div>

                    {/* AKSESUAR */}
                    <div 
                      className="relative"
                      onMouseEnter={() => openMenu('aksesuar')}
                      onMouseLeave={scheduleClose}
                    >
                      <Link
                        to="/kategori/aksesuar"
                        className="text-xs font-light tracking-[0.2em] uppercase py-4 hover:opacity-60"
                      >
                        AKSESUAR
                      </Link>
                    </div>

                    {/* SALE */}
                    <Link
                      to="/kategori/sale"
                      className="text-xs font-light tracking-[0.2em] uppercase py-4 hover:opacity-60 text-red-700"
                    >
                      SALE
                    </Link>
                  </nav>
                </>
              )}
            </div>

            {/* Center: Logo (text on mobile, image on desktop) */}
            <Link to="/" className="flex-shrink-0 absolute left-1/2 -translate-x-1/2 lg:static lg:translate-x-0" data-testid="header-logo">
              <span className="lg:hidden text-[13px] tracking-[0.45em] font-light">FACETTE</span>
              <img src="/logo.webp" alt="FACETTE" className="hidden lg:block h-6" />
            </Link>

            {/* Right: Icons (mobile: search + cart only; desktop: full set) */}
            <div className="flex-1 flex items-center justify-end gap-0.5 md:gap-2">
              {!isCheckout && (
                <>
                  <button onClick={() => setSearchOpen(true)} className="p-2 hover:opacity-60" aria-label="Ara" data-testid="search-btn">
                    <Search size={17} strokeWidth={1.4} />
                  </button>
                  <Link to={user ? "/hesabim" : "/giris"} className="hidden lg:inline-flex p-2 hover:opacity-60" aria-label="Hesap">
                    <User size={17} strokeWidth={1.4} />
                  </Link>
                  <button onClick={() => setIsOpen(true)} className="p-2 hover:opacity-60 relative" aria-label="Sepet" data-testid="cart-btn">
                    <ShoppingBag size={17} strokeWidth={1.4} />
                    {itemCount > 0 && (
                      <span className="absolute top-1 right-1 min-w-[14px] h-[14px] px-0.5 bg-black text-white text-[8px] font-light rounded-full flex items-center justify-center">
                        {itemCount}
                      </span>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Full Width Mega Menu Dropdown - GİYİM */}
        {activeMenu === 'giyim' && (
          <div 
            className="absolute left-0 right-0 top-full bg-white shadow-lg border-t z-50"
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
          >
            <div className="max-w-screen-2xl mx-auto px-8 py-6">
              <div className="flex gap-12">
                {/* Categories */}
                <div className="flex-1 grid grid-cols-3 gap-8">
                  {Object.entries(GIYIM_MENU).map(([category, items]) => (
                    <div key={category}>
                      <h3 className="text-xs font-bold tracking-wider mb-3 text-gray-900">{category}</h3>
                      <ul className="space-y-1">
                        {items.map((item) => (
                          <li key={item.slug}>
                            <Link
                              to={`/kategori/${item.slug}`}
                              className="block py-1 text-sm text-gray-600 hover:text-black transition-colors"
                              onClick={() => setActiveMenu(null)}
                              onMouseEnter={() => setHoveredCategory(item.slug)}
                            >
                              {item.name}
                            </Link>
                          </li>
                        ))}
                        <li className="pt-1.5">
                          <Link
                            to={`/kategori/${category.toLowerCase().replace(/\s/g, '-').replace(/ş/g, 's').replace(/ı/g, 'i')}`}
                            className="text-xs font-medium underline hover:no-underline"
                            onClick={() => setActiveMenu(null)}
                          >
                            Tümünü Gör
                          </Link>
                        </li>
                      </ul>
                    </div>
                  ))}
                </div>
                
                {/* Right: Hover edilen kategorinin en çok satan 3 ürünü */}
                <div className="flex-shrink-0 flex gap-3 min-w-[564px]">
                  {activeMegaProducts.length > 0 ? (
                    activeMegaProducts.map((p) => (
                      <Link
                        key={p.id}
                        to={`/urun/${p.slug || p.id}`}
                        className="block w-44 group"
                        onClick={() => setActiveMenu(null)}
                      >
                        <div className="w-44 h-56 overflow-hidden bg-stone-100">
                          <img
                            src={(p.images && p.images[0]) || p.image || ""}
                            alt={p.name}
                            className="w-full h-full object-cover group-hover:scale-[1.04] transition-transform duration-500"
                          />
                        </div>
                        <p className="text-[11px] mt-2 line-clamp-1 text-black/85">{p.name}</p>
                        <p className="text-[11px] tabular-nums text-black/65">{(p.discount_price && p.discount_price > 0 ? p.discount_price : p.price || 0).toFixed(2)} TL</p>
                      </Link>
                    ))
                  ) : (
                    MENU_IMAGES.giyim.map((img, i) => (
                      <Link key={i} to="/kategori/giyim" className="block w-44 h-56 overflow-hidden bg-stone-100" onClick={() => setActiveMenu(null)}>
                        <img src={img} alt="" className="w-full h-full object-cover" />
                      </Link>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Full Width Mega Menu Dropdown - AKSESUAR */}
        {activeMenu === 'aksesuar' && (
          <div 
            className="absolute left-0 right-0 top-full bg-white shadow-lg border-t z-50"
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
          >
            <div className="max-w-screen-2xl mx-auto px-8 py-6">
              <div className="flex gap-12">
                {/* Categories */}
                <div className="flex-1">
                  <h3 className="text-xs font-bold tracking-wider mb-3 text-gray-900">AKSESUAR</h3>
                  <ul className="grid grid-cols-2 gap-x-12 gap-y-1">
                    {AKSESUAR_MENU.map((item) => (
                      <li key={item.slug}>
                        <Link
                          to={`/kategori/${item.slug}`}
                          className="block py-1 text-sm text-gray-600 hover:text-black transition-colors"
                          onClick={() => setActiveMenu(null)}
                          onMouseEnter={() => setHoveredCategory(item.slug)}
                        >
                          {item.name}
                        </Link>
                      </li>
                    ))}
                  </ul>
                  <Link
                    to="/kategori/aksesuar"
                    className="inline-block mt-3 text-xs font-medium underline hover:no-underline"
                    onClick={() => setActiveMenu(null)}
                  >
                    Tümünü Gör
                  </Link>
                </div>
                
                {/* Right: Hover edilen kategorinin en çok satan 3 ürünü */}
                <div className="flex-shrink-0 flex gap-3 min-w-[564px]">
                  {activeMegaProducts.length > 0 ? (
                    activeMegaProducts.map((p) => (
                      <Link
                        key={p.id}
                        to={`/urun/${p.slug || p.id}`}
                        className="block w-44 group"
                        onClick={() => setActiveMenu(null)}
                      >
                        <div className="w-44 h-56 overflow-hidden bg-stone-100">
                          <img
                            src={(p.images && p.images[0]) || p.image || ""}
                            alt={p.name}
                            className="w-full h-full object-cover group-hover:scale-[1.04] transition-transform duration-500"
                          />
                        </div>
                        <p className="text-[11px] mt-2 line-clamp-1 text-black/85">{p.name}</p>
                        <p className="text-[11px] tabular-nums text-black/65">{(p.discount_price && p.discount_price > 0 ? p.discount_price : p.price || 0).toFixed(2)} TL</p>
                      </Link>
                    ))
                  ) : (
                    <Link to="/kategori/aksesuar" className="block w-44 h-56 overflow-hidden bg-stone-100" onClick={() => setActiveMenu(null)}>
                      <img src={MENU_IMAGES.aksesuar[0]} alt="" className="w-full h-full object-cover" />
                    </Link>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </header>

      {/* Mobile Menu */}
      {!isCheckout && (
        <div className={`mobile-menu ${mobileMenuOpen ? "open" : ""}`}>
          <div className="flex items-center justify-between px-5 h-14 border-b border-black/5">
            <Link to="/" onClick={() => setMobileMenuOpen(false)}>
              <span className="text-base tracking-[0.4em] font-light">FACETTE</span>
            </Link>
            <button onClick={() => setMobileMenuOpen(false)} className="-mr-2 p-2" aria-label="Kapat">
              <X size={20} strokeWidth={1.4} />
            </button>
          </div>
          <nav className="overflow-y-auto h-[calc(100vh-56px)] flex flex-col">
            {/* Primary Categories */}
            <div className="px-5 pt-6 pb-4">
              <Link
                to="/kategori/en-yeniler"
                className="block py-3 text-sm tracking-[0.15em] uppercase font-light"
                onClick={() => setMobileMenuOpen(false)}
              >
                En Yeniler
              </Link>

              {/* GİYİM accordion */}
              <details className="group border-t border-black/5">
                <summary className="flex items-center justify-between py-3 cursor-pointer list-none">
                  <span className="text-sm tracking-[0.15em] uppercase font-light">Giyim</span>
                  <span className="text-base font-thin transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="pb-3 pl-1 space-y-3">
                  {Object.entries(GIYIM_MENU).map(([category, items]) => (
                    <div key={category}>
                      <p className="text-[10px] tracking-[0.25em] uppercase text-black/40 mb-1.5">{category}</p>
                      {items.map((item) => (
                        <Link
                          key={item.slug}
                          to={`/kategori/${item.slug}`}
                          className="block py-1.5 text-[13px] font-light text-black/75"
                          onClick={() => setMobileMenuOpen(false)}
                        >
                          {item.name}
                        </Link>
                      ))}
                    </div>
                  ))}
                </div>
              </details>

              {/* AKSESUAR accordion */}
              <details className="group border-t border-black/5">
                <summary className="flex items-center justify-between py-3 cursor-pointer list-none">
                  <span className="text-sm tracking-[0.15em] uppercase font-light">Aksesuar</span>
                  <span className="text-base font-thin transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="pb-3 pl-1">
                  {AKSESUAR_MENU.map((item) => (
                    <Link
                      key={item.slug}
                      to={`/kategori/${item.slug}`}
                      className="block py-1.5 text-[13px] font-light text-black/75"
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      {item.name}
                    </Link>
                  ))}
                </div>
              </details>

              <Link
                to="/kategori/sale"
                className="block py-3 text-sm tracking-[0.15em] uppercase font-light text-red-700 border-t border-black/5"
                onClick={() => setMobileMenuOpen(false)}
              >
                Sale
              </Link>
            </div>

            {/* Bottom: Account + Service */}
            <div className="mt-auto px-5 py-6 bg-stone-50 border-t border-black/5 space-y-2.5">
              <Link to={user ? "/hesabim" : "/giris"} className="block text-[13px] font-light text-black/85" onClick={() => setMobileMenuOpen(false)}>
                {user ? "Hesabım" : "Giriş Yap / Üye Ol"}
              </Link>
              <Link to="/siparis-takip" className="block text-[13px] font-light text-black/85" onClick={() => setMobileMenuOpen(false)}>
                Sipariş Takibi
              </Link>
              <Link to="/sayfa/iletisim" className="block text-[13px] font-light text-black/85" onClick={() => setMobileMenuOpen(false)}>
                İletişim
              </Link>
              <Link to="/sayfa/iade-kosullari" className="block text-[13px] font-light text-black/85" onClick={() => setMobileMenuOpen(false)}>
                İade & Değişim
              </Link>
            </div>
          </nav>
        </div>
      )}

      {/* Search Overlay */}
      {searchOpen && (
        <div className="fixed inset-0 bg-white z-50 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-4 py-6">
            <div className="flex justify-end mb-6">
              <button onClick={() => { setSearchOpen(false); setSearchQuery(""); }}><X size={22} /></button>
            </div>
            <form onSubmit={handleSearch} className="mb-10">
              <div className="relative">
                <Search size={18} className="absolute left-0 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Ara..."
                  className="w-full text-xl font-light pl-7 py-3 border-0 border-b border-gray-200 bg-transparent focus:outline-none focus:border-black"
                  autoFocus
                />
              </div>
            </form>
            <div>
              {searchQuery.length === 0 ? (
                <div>
                  <h3 className="text-[10px] tracking-widest uppercase text-gray-500 mb-4">EN ÇOK ARANANLAR</h3>
                  <div className="flex flex-wrap gap-2">
                    {popularSearches.map((item, i) => (
                      <button
                        key={i}
                        onClick={() => { navigate(`/arama?q=${encodeURIComponent(item.term)}`); setSearchOpen(false); }}
                        className="px-3 py-1.5 border text-xs hover:border-black hover:bg-black hover:text-white transition-all"
                      >
                        {item.term}
                      </button>
                    ))}
                  </div>
                </div>
              ) : searchResults.length > 0 ? (
                <div>
                  <h3 className="text-[10px] tracking-widest uppercase text-gray-500 mb-4">ÜRÜNLER</h3>
                  <div className="grid grid-cols-3 gap-3">
                    {searchResults.map((p) => (
                      <button key={p.id} onClick={() => { navigate(`/urun/${p.slug}`); setSearchOpen(false); }} className="text-left">
                        <div className="aspect-[3/4] bg-gray-50 mb-2 overflow-hidden">
                          <img src={p.images?.[0]} alt={p.name} className="w-full h-full object-cover" />
                        </div>
                        <p className="text-xs line-clamp-1">{p.name}</p>
                        <p className="text-xs">{p.price?.toFixed(2).replace('.', ',')} TL</p>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-center text-gray-500 text-sm">Sonuç bulunamadı</p>
              )}
            </div>
          </div>
        </div>
      )}

      <CartDrawer />
    </>
  );
}
