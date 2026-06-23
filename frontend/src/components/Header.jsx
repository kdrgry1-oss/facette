import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, User, ShoppingBag, X, Bookmark } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import { useFavorites } from "../context/FavoritesContext";
import CartDrawer from "./CartDrawer";
import CountdownBar from "./CountdownBar";
import { optimizeImg } from "../lib/img";
import { slugify } from "../lib/slug";
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
    "https://cdn.facette.com.tr/pagedesign/title-65777bd3-0-1920.webp",
    "https://cdn.facette.com.tr/pagedesign/title-7b3e27f9-5-1920.webp"
  ],
  aksesuar: [
    "https://cdn.facette.com.tr/pagedesign/title-7b3e27f9-5-1920.webp"
  ]
};

// Mega menü sağ panel — ürünler yüklenirken iskelet gösterir (eski/yanlış görsel flash'ını önler).
function MegaProductsPanel({ products, loading, fallback, fallbackLink, onNavigate }) {
  if (loading) {
    return [0, 1, 2].map((i) => (
      <div key={i} className="w-44" data-testid="mega-product-skeleton">
        <div className="w-44 h-56 bg-stone-100 animate-pulse" />
        <div className="h-2.5 bg-stone-100 mt-2 w-3/4 animate-pulse" />
        <div className="h-2.5 bg-stone-100 mt-1 w-1/3 animate-pulse" />
      </div>
    ));
  }
  if (products.length > 0) {
    return products.map((p) => (
      <Link
        key={p.id}
        to={`/${p.slug || p.id}`}
        className="block w-44 group"
        onClick={onNavigate}
      >
        <div className="w-44 h-56 overflow-hidden bg-stone-100">
          <img
            src={optimizeImg((p.images && p.images[0]) || p.image || "", 400)}
            alt={p.name}
            className="w-full h-full object-contain group-hover:scale-[1.04] transition-transform duration-500"
            loading="lazy"
            decoding="async"
          />
        </div>
        <p className="text-[11px] mt-2 line-clamp-1 text-black/85">{p.name}</p>
        <p className="text-[11px] tabular-nums text-black/65">{(p.discount_price && p.discount_price > 0 ? p.discount_price : p.price || 0).toFixed(2)} TL</p>
      </Link>
    ));
  }
  return fallback.map((img, i) => (
    <Link key={i} to={fallbackLink} className="block w-44 h-56 overflow-hidden bg-stone-100" onClick={onNavigate}>
      <img src={optimizeImg(img, 400)} alt="" className="w-full h-full object-cover" loading="lazy" decoding="async" />
    </Link>
  ));
}

export default function Header({ hideMenu = false }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [popularSearches, setPopularSearches] = useState([]);
  const [suggestedProducts, setSuggestedProducts] = useState([]);
  const [activeMenu, setActiveMenu] = useState(null);
  const [hoveredCategory, setHoveredCategory] = useState(null); // alt kategori slug (ceket, sort, ...)
  const [megaProducts, setMegaProducts] = useState({}); // {slug: [products]}
  
  const { itemCount, setIsOpen } = useCart();
  const { user } = useAuth();
  const { count: favCount } = useFavorites();
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
  // Henüz fetch tamamlanmadıysa (undefined) yükleniyor → iskelet göster, fallback görsel flash etme
  const megaLoading = Boolean(activeMegaSlug) && megaProducts[activeMegaSlug] === undefined;

  // Mega menü kapanma timer'ı — fare üzerine geldiğinde anında kapanmasın, 200ms gecikme
  const [closeTimer, setCloseTimer] = useState(null);
  const openMenu = (m) => {
    if (closeTimer) { clearTimeout(closeTimer); setCloseTimer(null); }
    setActiveMenu(m);
  };
  const scheduleClose = () => {
    const t = setTimeout(() => { setActiveMenu(null); setHoveredCategory(null); }, 650);
    setCloseTimer(t);
  };
  const cancelClose = () => {
    if (closeTimer) { clearTimeout(closeTimer); setCloseTimer(null); }
  };

  useEffect(() => {
    if (searchOpen && popularSearches.length === 0) {
      fetchPopularSearches();
    }
    if (searchOpen && suggestedProducts.length === 0) {
      axios.get(`${API}/products?limit=8&sort=popular`)
        .then((r) => setSuggestedProducts(r.data?.products || []))
        .catch(() => {});
    }
  }, [searchOpen]);

  // Zara davranışı: overlay açıkken arka plan scroll kilidi + ESC ile kapat
  useEffect(() => {
    if (!searchOpen) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e) => {
      if (e.key === "Escape") { setSearchOpen(false); setSearchQuery(""); }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [searchOpen]);

  useEffect(() => {
    const q = searchQuery;
    const timer = setTimeout(async () => {
      if (q.length < 1) {
        setSearchResults([]);
        return;
      }
      try {
        const res = await axios.get(`${API}/products?search=${encodeURIComponent(q)}&limit=6`);
        setSearchResults(res.data?.products || []);
      } catch (err) {
        console.error(err);
      }
    }, q.length >= 1 ? 300 : 0);
    return () => clearTimeout(timer);
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

  const submitSearch = () => {
    const q = searchQuery.trim();
    if (q) {
      navigate(`/arama?q=${encodeURIComponent(q)}`);
      setSearchOpen(false);
      setSearchQuery("");
    }
  };

  const closeSearch = () => { setSearchOpen(false); setSearchQuery(""); };

  return (
    <>
      {/* Top Banner — admin tarafından yönetilen geri sayım barı (countdown_bar block) */}
      {!isCheckout && <CountdownBar />}

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
                    {/* Zara tarzı minimal hamburger — iki ince yatay çizgi */}
                    <svg width="22" height="10" viewBox="0 0 22 10" fill="none" aria-hidden="true">
                      <line x1="0" y1="1.5" x2="22" y2="1.5" stroke="currentColor" strokeWidth="1.1" />
                      <line x1="0" y1="8.5" x2="22" y2="8.5" stroke="currentColor" strokeWidth="1.1" />
                    </svg>
                  </button>

                  <nav className="hidden lg:flex items-center gap-5">
                    {/* YENİ KOLEKSİYON — premium flagship menü (Seçenek A: elmas işareti + animasyonlu hairline) */}
                    <Link
                      to="/en-yeniler"
                      className="group relative text-xs font-medium tracking-[0.28em] uppercase py-4 leading-none flex items-center gap-1.5"
                      data-testid="nav-yeni-koleksiyon"
                    >
                      <span className="inline-block w-[5px] h-[5px] rotate-45 bg-black/55 group-hover:bg-black transition-colors duration-300" aria-hidden="true" />
                      YENİ KOLEKSİYON
                      <span className="pointer-events-none absolute left-0 bottom-2.5 h-px w-full bg-black origin-left scale-x-0 group-hover:scale-x-100 transition-transform duration-500 ease-out" aria-hidden="true" />
                    </Link>

                    {/* GİYİM - Mega Menu */}
                    <div 
                      className="relative"
                      onMouseEnter={() => openMenu('giyim')}
                      onMouseLeave={scheduleClose}
                    >
                      <Link
                        to="/giyim"
                        className="text-xs font-normal tracking-[0.2em] uppercase py-4 leading-none flex items-center hover:opacity-60"
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
                        to="/aksesuar"
                        className="text-xs font-normal tracking-[0.2em] uppercase py-4 leading-none flex items-center hover:opacity-60"
                      >
                        AKSESUAR
                      </Link>
                    </div>

                    {/* SALE */}
                    <Link
                      to="/sale"
                      className="text-xs font-normal tracking-[0.2em] uppercase py-4 leading-none flex items-center hover:opacity-60 text-red-700"
                    >
                      SALE
                    </Link>
                  </nav>
                </>
              )}
            </div>

            {/* Center: Logo (image on every breakpoint — mobil dahil) */}
            <Link to="/" className="flex-shrink-0 absolute left-1/2 -translate-x-1/2 lg:static lg:translate-x-0" data-testid="header-logo">
              <img src="/logo.webp" alt="FACETTE" className="h-5 md:h-6" />
            </Link>

            {/* Right: Icons (mobile: search + cart only; desktop: full set) */}
            <div className="flex-1 flex items-center justify-end gap-0.5 md:gap-2">
              {!isCheckout && (
                <>
                  <button onClick={() => setSearchOpen(true)} className="inline-flex flex-col items-start justify-center py-1.5 pr-1 md:pr-4 opacity-80 hover:opacity-100 transition-opacity" aria-label="Ara" data-testid="search-btn">
                    <span className="inline-flex items-center gap-1.5">
                      <Search size={15} strokeWidth={1.4} />
                      <span className="text-[11px] tracking-[0.2em] uppercase leading-none">Ara</span>
                    </span>
                    <span className="mt-1.5 h-px bg-current w-24 md:w-32"></span>
                  </button>
                  {user && (
                    <Link to="/hesabim?tab=favorites" className="hidden lg:inline-flex p-2 hover:opacity-60 relative" aria-label="Kaydedilenler" data-testid="favorites-btn">
                      <Bookmark size={17} strokeWidth={1.4} />
                      {favCount > 0 && (
                        <span className="absolute top-1 right-1 min-w-[14px] h-[14px] px-0.5 bg-black text-white text-[8px] font-light rounded-full flex items-center justify-center">
                          {favCount}
                        </span>
                      )}
                    </Link>
                  )}
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
                {/* Categories — Üst/Alt/Dış Giyim birbirine yakın (genişliğe yayılmaz) */}
                <div className="grid grid-cols-3 gap-x-6 max-w-lg">
                  {Object.entries(GIYIM_MENU).map(([category, items]) => (
                    <div key={category}>
                      <Link
                        to={`/${slugify(category)}`}
                        className="block text-xs font-bold tracking-wider mb-3 text-gray-900 hover:underline cursor-pointer"
                        onClick={() => setActiveMenu(null)}
                      >
                        {category}
                      </Link>
                      <ul className="space-y-1">
                        {items.map((item) => (
                          <li key={item.slug}>
                            <Link
                              to={`/${item.slug}`}
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
                            to={`/${slugify(category)}`}
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
                  <MegaProductsPanel
                    products={activeMegaProducts}
                    loading={megaLoading}
                    fallback={MENU_IMAGES.giyim}
                    fallbackLink="/giyim"
                    onNavigate={() => setActiveMenu(null)}
                  />
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
                          to={`/${item.slug}`}
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
                    to="/aksesuar"
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
                        to={`/${p.slug || p.id}`}
                        className="block w-44 group"
                        onClick={() => setActiveMenu(null)}
                      >
                        <div className="w-44 h-56 overflow-hidden bg-stone-100">
                          <img
                            src={(p.images && p.images[0]) || p.image || ""}
                            alt={p.name}
                            className="w-full h-full object-contain group-hover:scale-[1.04] transition-transform duration-500"
                          />
                        </div>
                        <p className="text-[11px] mt-2 line-clamp-1 text-black/85">{p.name}</p>
                        <p className="text-[11px] tabular-nums text-black/65">{(p.discount_price && p.discount_price > 0 ? p.discount_price : p.price || 0).toFixed(2)} TL</p>
                      </Link>
                    ))
                  ) : (
                    <Link to="/aksesuar" className="block w-44 h-56 overflow-hidden bg-stone-100" onClick={() => setActiveMenu(null)}>
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
              <img src="/logo.webp" alt="FACETTE" className="h-5" />
            </Link>
            <button onClick={() => setMobileMenuOpen(false)} className="-mr-2 p-2" aria-label="Kapat">
              <X size={20} strokeWidth={1.4} />
            </button>
          </div>
          <nav className="overflow-y-auto h-[calc(100vh-56px)] flex flex-col">
            {/* Primary Categories */}
            <div className="px-5 pt-6 pb-4">
              <Link
                to="/en-yeniler"
                className="flex items-center gap-2 py-3 text-sm tracking-[0.18em] uppercase font-medium"
                onClick={() => setMobileMenuOpen(false)}
              >
                <span className="inline-block w-[5px] h-[5px] rotate-45 bg-black" aria-hidden="true" />
                Yeni Koleksiyon
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
                      <Link
                        to={`/${slugify(category)}`}
                        className="block text-[10px] tracking-[0.25em] uppercase text-black/40 mb-1.5 hover:underline"
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        {category}
                      </Link>
                      {items.map((item) => (
                        <Link
                          key={item.slug}
                          to={`/${item.slug}`}
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
                      to={`/${item.slug}`}
                      className="block py-1.5 text-[13px] font-light text-black/75"
                      onClick={() => setMobileMenuOpen(false)}
                    >
                      {item.name}
                    </Link>
                  ))}
                </div>
              </details>

              <Link
                to="/sale"
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
        <div className="fixed inset-0 bg-white z-[60] overflow-y-auto" style={{ animation: "facetteSearchIn .2s ease-out" }}>
          <style>{`@keyframes facetteSearchIn{from{opacity:0}to{opacity:1}}@keyframes facetteSearchUp{from{opacity:0;transform:translateY(-10px)}to{opacity:1;transform:translateY(0)}}`}</style>
          <div className="px-5 md:px-10 pt-5 pb-16" style={{ animation: "facetteSearchUp .28s ease-out" }}>
            {/* Üst bar: logo + kapat */}
            <div className="flex items-center justify-between mb-8 md:mb-12">
              <Link to="/" onClick={closeSearch} className="text-[13px] tracking-[0.4em] font-light">FACETTE</Link>
              <button onClick={closeSearch} className="inline-flex items-center gap-1.5 text-[11px] tracking-[0.18em] uppercase hover:opacity-60 transition-opacity" aria-label="Kapat">
                Kapat <X size={18} strokeWidth={1.4} />
              </button>
            </div>

            {/* 3 kolon: sol kategori | orta arama | sağ hesap (Zara düzeni) */}
            <div className="grid grid-cols-1 md:grid-cols-[170px_1fr_170px] gap-8 md:gap-12 items-start mb-12 md:mb-16">
              {/* SOL: kategoriler (desktop) */}
              <nav className="hidden md:flex flex-col gap-3.5 text-[11px] tracking-[0.18em] uppercase">
                <Link to="/giyim" onClick={closeSearch} className="hover:opacity-60 transition-opacity">Giyim</Link>
                <Link to="/aksesuar" onClick={closeSearch} className="hover:opacity-60 transition-opacity">Aksesuar</Link>
                <Link to="/sale" onClick={closeSearch} className="text-red-700 hover:opacity-60 transition-opacity">Sale</Link>
                <Link to="/" onClick={closeSearch} className="hover:opacity-60 transition-opacity">Ana Sayfa</Link>
              </nav>

              {/* ORTA: büyük arama girişi */}
              <form onSubmit={(e) => { e.preventDefault(); submitSearch(); }} className="w-full">
                <div className="relative border-b border-black max-w-xl mx-auto md:max-w-2xl md:mx-0">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Ne arıyorsunuz?"
                    className="w-full text-xl md:text-3xl font-light py-2.5 pr-10 bg-transparent focus:outline-none placeholder:text-gray-300 text-center md:text-left"
                    autoFocus
                  />
                  {searchQuery ? (
                    <button type="button" onClick={() => setSearchQuery("")} className="absolute right-0 top-1/2 -translate-y-1/2 text-gray-400 hover:text-black transition-colors" aria-label="Temizle"><X size={20} strokeWidth={1.3} /></button>
                  ) : (
                    <Search size={22} strokeWidth={1.2} className="absolute right-0 top-1/2 -translate-y-1/2 text-gray-400" />
                  )}
                </div>
              </form>

              {/* SAĞ: hesap / sepet (desktop) */}
              <nav className="hidden md:flex flex-col gap-3.5 text-[11px] tracking-[0.18em] uppercase md:items-end">
                <button onClick={() => { closeSearch(); setIsOpen(true); }} className="hover:opacity-60 transition-opacity">Sepet{itemCount > 0 ? ` (${itemCount})` : ""}</button>
                <Link to={user ? "/hesabim" : "/giris"} onClick={closeSearch} className="hover:opacity-60 transition-opacity">{user ? "Hesabım" : "Giriş Yap"}</Link>
                {user && (
                  <Link to="/hesabim?tab=favorites" onClick={closeSearch} className="hover:opacity-60 transition-opacity">Kaydedilenler{favCount > 0 ? ` (${favCount})` : ""}</Link>
                )}
              </nav>

              {/* Mobil: kategori + hesap linkleri yatay (md'de gizli) */}
              <div className="md:hidden flex flex-wrap justify-center gap-x-5 gap-y-2.5 text-[11px] tracking-[0.15em] uppercase pt-1">
                <Link to="/giyim" onClick={closeSearch}>Giyim</Link>
                <Link to="/aksesuar" onClick={closeSearch}>Aksesuar</Link>
                <Link to="/sale" onClick={closeSearch} className="text-red-700">Sale</Link>
                <Link to={user ? "/hesabim" : "/giris"} onClick={closeSearch}>{user ? "Hesabım" : "Giriş"}</Link>
                {user && <Link to="/hesabim?tab=favorites" onClick={closeSearch}>Kaydedilenler</Link>}
              </div>
            </div>

            {/* ALT: ürünler — boş aramada öneri, yazınca canlı sonuç */}
            {searchQuery.length === 0 ? (
              suggestedProducts.length > 0 && (
                <div>
                  <h3 className="text-[10px] tracking-widest uppercase text-gray-400 mb-5">İlginizi çekebilecek diğer ürünler</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
                    {suggestedProducts.map((p) => (
                      <button key={p.id} onClick={() => { navigate(`/${p.slug}`); closeSearch(); }} className="text-left group">
                        <div className="aspect-[2/3] bg-gray-50 mb-2.5 overflow-hidden">
                          <img src={optimizeImg(p.images?.[0], 500)} alt={p.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy" decoding="async" />
                        </div>
                        <p className="text-xs font-light line-clamp-1 mb-0.5">{p.name}</p>
                        <p className="text-xs font-light text-gray-600">{p.price?.toFixed(2).replace('.', ',')} TL</p>
                      </button>
                    ))}
                  </div>
                </div>
              )
            ) : searchResults.length > 0 ? (
              <div>
                <h3 className="text-[10px] tracking-widest uppercase text-gray-400 mb-5">Ürünler</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-8">
                  {searchResults.map((p) => (
                    <button key={p.id} onClick={() => { navigate(`/${p.slug}`); closeSearch(); }} className="text-left group">
                      <div className="aspect-[2/3] bg-gray-50 mb-2.5 overflow-hidden">
                        <img src={optimizeImg(p.images?.[0], 500)} alt={p.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" loading="lazy" decoding="async" />
                      </div>
                      <p className="text-xs font-light line-clamp-1 mb-0.5">{p.name}</p>
                      <p className="text-xs font-light text-gray-600">{p.price?.toFixed(2).replace('.', ',')} TL</p>
                    </button>
                  ))}
                </div>
                <button onClick={() => submitSearch()} className="mt-10 text-[11px] tracking-[0.18em] uppercase border-b border-black pb-1 hover:opacity-60 transition-opacity">
                  Tüm sonuçları gör
                </button>
              </div>
            ) : (
              <p className="text-sm font-light text-gray-400">"{searchQuery}" için sonuç bulunamadı.</p>
            )}
          </div>
        </div>
      )}

      <CartDrawer />
    </>
  );
}
