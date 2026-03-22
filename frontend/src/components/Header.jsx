import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
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

export default function Header({ hideMenu = false }) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [popularSearches, setPopularSearches] = useState([]);
  const [activeMenu, setActiveMenu] = useState(null);
  
  const { itemCount, setIsOpen } = useCart();
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const isCheckout = location.pathname.includes('/odeme') || location.pathname.includes('/checkout');

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
      {/* Top Banner */}
      {!isCheckout && (
        <div className="bg-white text-black text-center py-2 border-b">
          <p className="text-xs tracking-wider">500 TL ÜZERİ ÜCRETSİZ KARGO</p>
        </div>
      )}

      {/* Main Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-100">
        <div className="max-w-screen-2xl mx-auto px-4">
          <div className="flex items-center h-14">
            {/* Left: Navigation Menu */}
            <div className="flex-1 flex items-center">
              {!isCheckout && (
                <>
                  <button 
                    className="lg:hidden p-2 -ml-2"
                    onClick={() => setMobileMenuOpen(true)}
                  >
                    <Menu size={22} />
                  </button>

                  <nav className="hidden lg:flex items-center gap-6">
                    {/* EN YENİLER */}
                    <Link
                      to="/kategori/en-yeniler"
                      className="text-[11px] tracking-wider uppercase py-4 hover:opacity-60"
                    >
                      EN YENİLER
                    </Link>

                    {/* GİYİM - Mega Menu */}
                    <div 
                      className="relative"
                      onMouseEnter={() => setActiveMenu('giyim')}
                      onMouseLeave={() => setActiveMenu(null)}
                    >
                      <Link
                        to="/kategori/giyim"
                        className="text-[11px] tracking-wider uppercase py-4 hover:opacity-60 flex items-center"
                      >
                        GİYİM
                      </Link>

                      {/* Mega Menu Dropdown */}
                      {activeMenu === 'giyim' && (
                        <div className="absolute left-0 top-full bg-white shadow-lg py-6 px-8 min-w-[500px] z-50 border-t">
                          <div className="grid grid-cols-3 gap-8">
                            {Object.entries(GIYIM_MENU).map(([category, items]) => (
                              <div key={category}>
                                <h3 className="text-xs font-medium tracking-wider mb-3">{category}</h3>
                                <ul className="space-y-2">
                                  {items.map((item) => (
                                    <li key={item.slug}>
                                      <Link
                                        to={`/kategori/${item.slug}`}
                                        className="text-sm text-gray-600 hover:text-black transition-colors"
                                      >
                                        {item.name}
                                      </Link>
                                    </li>
                                  ))}
                                  <li className="pt-2">
                                    <Link
                                      to={`/kategori/${category.toLowerCase().replace(/\s/g, '-').replace(/ş/g, 's').replace(/ı/g, 'i')}`}
                                      className="text-xs underline hover:no-underline"
                                    >
                                      Tümünü Gör
                                    </Link>
                                  </li>
                                </ul>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* AKSESUAR */}
                    <div 
                      className="relative"
                      onMouseEnter={() => setActiveMenu('aksesuar')}
                      onMouseLeave={() => setActiveMenu(null)}
                    >
                      <Link
                        to="/kategori/aksesuar"
                        className="text-[11px] tracking-wider uppercase py-4 hover:opacity-60"
                      >
                        AKSESUAR
                      </Link>

                      {activeMenu === 'aksesuar' && (
                        <div className="absolute left-0 top-full bg-white shadow-lg py-4 min-w-[160px] z-50 border-t">
                          <ul className="space-y-1">
                            {AKSESUAR_MENU.map((item) => (
                              <li key={item.slug}>
                                <Link
                                  to={`/kategori/${item.slug}`}
                                  className="block px-5 py-1.5 text-sm text-gray-600 hover:text-black hover:bg-gray-50"
                                >
                                  {item.name}
                                </Link>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* SALE */}
                    <Link
                      to="/kategori/sale"
                      className="text-[11px] tracking-wider uppercase py-4 hover:opacity-60 text-red-600"
                    >
                      SALE
                    </Link>
                  </nav>
                </>
              )}
            </div>

            {/* Center: Logo */}
            <Link to="/" className="flex-shrink-0">
              <img src="/logo.webp" alt="FACETTE" className="h-8" />
            </Link>

            {/* Right: Icons */}
            <div className="flex-1 flex items-center justify-end gap-3">
              {!isCheckout && (
                <>
                  <button onClick={() => setSearchOpen(true)} className="p-1.5 hover:opacity-60">
                    <Search size={18} strokeWidth={1.5} />
                  </button>
                  <Link to={user ? "/hesabim" : "/giris"} className="p-1.5 hover:opacity-60">
                    <User size={18} strokeWidth={1.5} />
                  </Link>
                  <button onClick={() => setIsOpen(true)} className="p-1.5 hover:opacity-60 relative">
                    <ShoppingBag size={18} strokeWidth={1.5} />
                    {itemCount > 0 && (
                      <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-black text-white text-[9px] rounded-full flex items-center justify-center">
                        {itemCount}
                      </span>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Menu */}
      {!isCheckout && (
        <div className={`mobile-menu ${mobileMenuOpen ? "open" : ""}`}>
          <div className="flex items-center justify-between p-4 border-b">
            <img src="/logo.webp" alt="FACETTE" className="h-5" />
            <button onClick={() => setMobileMenuOpen(false)}><X size={22} /></button>
          </div>
          <nav className="p-4 overflow-y-auto h-[calc(100vh-60px)]">
            {/* EN YENİLER */}
            <Link 
              to="/kategori/en-yeniler" 
              className="block py-3 text-sm tracking-wider uppercase border-b border-gray-100"
              onClick={() => setMobileMenuOpen(false)}
            >
              EN YENİLER
            </Link>

            {/* GİYİM with subcategories */}
            <div className="border-b border-gray-100">
              <Link 
                to="/kategori/giyim" 
                className="block py-3 text-sm tracking-wider uppercase"
                onClick={() => setMobileMenuOpen(false)}
              >
                GİYİM
              </Link>
              <div className="pl-4 pb-3">
                {Object.entries(GIYIM_MENU).map(([category, items]) => (
                  <div key={category} className="mb-3">
                    <p className="text-xs font-medium text-gray-500 mb-1">{category}</p>
                    {items.map((item) => (
                      <Link 
                        key={item.slug}
                        to={`/kategori/${item.slug}`} 
                        className="block py-1 text-sm text-gray-600"
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        {item.name}
                      </Link>
                    ))}
                  </div>
                ))}
              </div>
            </div>

            {/* AKSESUAR */}
            <div className="border-b border-gray-100">
              <Link 
                to="/kategori/aksesuar" 
                className="block py-3 text-sm tracking-wider uppercase"
                onClick={() => setMobileMenuOpen(false)}
              >
                AKSESUAR
              </Link>
              <div className="pl-4 pb-3">
                {AKSESUAR_MENU.map((item) => (
                  <Link 
                    key={item.slug}
                    to={`/kategori/${item.slug}`} 
                    className="block py-1 text-sm text-gray-600"
                    onClick={() => setMobileMenuOpen(false)}
                  >
                    {item.name}
                  </Link>
                ))}
              </div>
            </div>

            {/* SALE */}
            <Link 
              to="/kategori/sale" 
              className="block py-3 text-sm tracking-wider uppercase text-red-600 border-b border-gray-100"
              onClick={() => setMobileMenuOpen(false)}
            >
              SALE
            </Link>
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
