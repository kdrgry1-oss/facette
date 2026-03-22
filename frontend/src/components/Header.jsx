import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X, ChevronDown } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Menu structure with subcategories
const MENU_ITEMS = [
  { name: "EN YENİLER", slug: "en-yeniler", children: [] },
  {
    name: "GİYİM", slug: "giyim",
    children: [
      { name: "Elbise", slug: "elbise" },
      { name: "Bluz", slug: "bluz" },
      { name: "Gömlek", slug: "gomlek" },
      { name: "Pantolon", slug: "pantolon" },
      { name: "Etek", slug: "etek" },
      { name: "Ceket", slug: "ceket" },
      { name: "Kazak", slug: "kazak" },
      { name: "Triko", slug: "triko" },
      { name: "Kaban", slug: "kaban" },
      { name: "Takım", slug: "takim" },
    ]
  },
  {
    name: "AKSESUAR", slug: "aksesuar",
    children: [
      { name: "Çanta", slug: "canta" },
      { name: "Şal", slug: "sal" },
      { name: "Atkı", slug: "atki" },
      { name: "Kemer", slug: "kemer" },
    ]
  },
  { name: "SALE", slug: "sale", isRed: true, children: [] }
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
      {/* Top Banner - White background, black text */}
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
                    {MENU_ITEMS.map((item) => (
                      <div 
                        key={item.slug}
                        className="relative"
                        onMouseEnter={() => setActiveMenu(item.slug)}
                        onMouseLeave={() => setActiveMenu(null)}
                      >
                        <Link
                          to={`/kategori/${item.slug}`}
                          className={`text-[11px] tracking-wider uppercase flex items-center gap-1 py-4 hover:opacity-60 transition-opacity ${item.isRed ? 'text-red-600' : ''}`}
                        >
                          {item.name}
                          {item.children.length > 0 && <ChevronDown size={10} />}
                        </Link>
                        {item.children.length > 0 && activeMenu === item.slug && (
                          <div className="absolute left-0 top-full bg-white shadow-lg py-3 min-w-[160px] z-50">
                            {item.children.map((child) => (
                              <Link
                                key={child.slug}
                                to={`/kategori/${child.slug}`}
                                className="block px-5 py-1.5 text-xs hover:bg-gray-50"
                              >
                                {child.name}
                              </Link>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
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
          <nav className="p-4">
            {MENU_ITEMS.map((item) => (
              <div key={item.slug}>
                <Link 
                  to={`/kategori/${item.slug}`} 
                  className={`block py-3 text-sm tracking-wider uppercase border-b border-gray-100 ${item.isRed ? 'text-red-600' : ''}`}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
                {item.children.length > 0 && (
                  <div className="pl-4">
                    {item.children.map((child) => (
                      <Link key={child.slug} to={`/kategori/${child.slug}`} className="block py-2 text-sm text-gray-600" onClick={() => setMobileMenuOpen(false)}>
                        {child.name}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
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
