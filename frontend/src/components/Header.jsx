import { useState, useEffect } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X, ChevronDown } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// facette.com.tr logo
const LOGO_URL = "https://static.ticimax.cloud/37439/Uploads/Editor/logo.png";

// Menu structure with subcategories
const MENU_ITEMS = [
  {
    name: "EN YENİLER",
    slug: "en-yeniler",
    children: []
  },
  {
    name: "GİYİM",
    slug: "giyim",
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
    name: "AKSESUAR",
    slug: "aksesuar",
    children: [
      { name: "Çanta", slug: "canta" },
      { name: "Şal", slug: "sal" },
      { name: "Atkı", slug: "atki" },
      { name: "Kemer", slug: "kemer" },
    ]
  },
  {
    name: "SALE",
    slug: "sale",
    isRed: true,
    children: []
  }
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

  // Check if current page is checkout
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
        { term: "ceket", count: 80 },
        { term: "kazak", count: 70 },
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
      axios.post(`${API}/search/log`, { term: searchQuery }).catch(() => {});
      navigate(`/arama?q=${encodeURIComponent(searchQuery)}`);
      setSearchOpen(false);
      setSearchQuery("");
    }
  };

  return (
    <>
      {/* Top Banner - facette style */}
      {!isCheckout && (
        <div className="bg-black text-white text-center py-2">
          <p className="text-xs tracking-wider">500 TL ÜZERİ ÜCRETSİZ KARGO</p>
        </div>
      )}

      {/* Main Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-100">
        <div className="container-main">
          <div className="flex items-center h-16 md:h-20">
            {/* Left: Navigation Menu - Hidden on checkout */}
            <div className="flex-1 flex items-center">
              {!isCheckout && (
                <>
                  <button 
                    className="lg:hidden p-2 -ml-2"
                    onClick={() => setMobileMenuOpen(true)}
                    data-testid="mobile-menu-btn"
                  >
                    <Menu size={24} />
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
                          className={`text-xs tracking-wider uppercase flex items-center gap-1 py-6 hover:opacity-60 transition-opacity ${item.isRed ? 'text-red-600' : ''}`}
                          data-testid={`nav-${item.slug}`}
                        >
                          {item.name}
                          {item.children.length > 0 && <ChevronDown size={12} />}
                        </Link>

                        {/* Dropdown */}
                        {item.children.length > 0 && activeMenu === item.slug && (
                          <div className="absolute left-0 top-full bg-white shadow-lg py-4 min-w-[180px] z-50 animate-fade-in">
                            {item.children.map((child) => (
                              <Link
                                key={child.slug}
                                to={`/kategori/${child.slug}`}
                                className="block px-6 py-2 text-sm hover:bg-gray-50 transition-colors"
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
            <Link to="/" className="flex-shrink-0" data-testid="logo">
              <img 
                src={LOGO_URL} 
                alt="FACETTE" 
                className="h-6 md:h-8"
                onError={(e) => {
                  e.target.style.display = 'none';
                  e.target.nextSibling.style.display = 'block';
                }}
              />
              <span 
                className="text-2xl tracking-[0.2em] hidden" 
                style={{ fontFamily: "'Times New Roman', serif" }}
              >
                FACETTE
              </span>
            </Link>

            {/* Right: Icons - Hidden on checkout except logo */}
            <div className="flex-1 flex items-center justify-end gap-2 md:gap-4">
              {!isCheckout && (
                <>
                  <button 
                    onClick={() => setSearchOpen(true)} 
                    className="p-2 hover:opacity-60 transition-opacity"
                    data-testid="search-btn"
                  >
                    <Search size={20} strokeWidth={1.5} />
                  </button>
                  
                  <Link 
                    to={user ? "/hesabim" : "/giris"} 
                    className="p-2 hover:opacity-60 transition-opacity"
                    data-testid="account-btn"
                  >
                    <User size={20} strokeWidth={1.5} />
                  </Link>
                  
                  <button 
                    onClick={() => setIsOpen(true)} 
                    className="p-2 hover:opacity-60 transition-opacity relative"
                    data-testid="cart-btn"
                  >
                    <ShoppingBag size={20} strokeWidth={1.5} />
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
            <img src={LOGO_URL} alt="FACETTE" className="h-5" />
            <button onClick={() => setMobileMenuOpen(false)}>
              <X size={24} />
            </button>
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
                      <Link 
                        key={child.slug}
                        to={`/kategori/${child.slug}`} 
                        className="block py-2 text-sm text-gray-600"
                        onClick={() => setMobileMenuOpen(false)}
                      >
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
        <div className="fixed inset-0 bg-white z-50 overflow-y-auto animate-fade-in">
          <div className="container-main py-6">
            <div className="flex justify-end mb-8">
              <button 
                onClick={() => { setSearchOpen(false); setSearchQuery(""); }}
                className="p-2"
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={handleSearch} className="max-w-2xl mx-auto mb-12">
              <div className="relative">
                <Search size={20} className="absolute left-0 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Ara..."
                  className="w-full text-2xl font-light pl-8 py-4 border-0 border-b border-gray-200 bg-transparent focus:outline-none focus:border-black"
                  autoFocus
                  data-testid="search-input"
                />
              </div>
            </form>

            <div className="max-w-4xl mx-auto">
              {searchQuery.length === 0 ? (
                <div>
                  <h3 className="text-xs tracking-widest uppercase text-gray-500 mb-6">EN ÇOK ARANANLAR</h3>
                  <div className="flex flex-wrap gap-3">
                    {popularSearches.map((item, i) => (
                      <button
                        key={i}
                        onClick={() => {
                          navigate(`/arama?q=${encodeURIComponent(item.term)}`);
                          setSearchOpen(false);
                        }}
                        className="px-4 py-2 border text-sm hover:border-black hover:bg-black hover:text-white transition-all"
                      >
                        {item.term}
                      </button>
                    ))}
                  </div>
                </div>
              ) : searchResults.length > 0 ? (
                <div>
                  <h3 className="text-xs tracking-widest uppercase text-gray-500 mb-6">ÜRÜNLER ({searchResults.length})</h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                    {searchResults.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => {
                          navigate(`/urun/${p.slug}`);
                          setSearchOpen(false);
                        }}
                        className="text-left group"
                      >
                        <div className="aspect-[3/4] bg-gray-50 mb-3 overflow-hidden">
                          <img src={p.images?.[0]} alt={p.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                        </div>
                        <p className="text-sm mb-1 line-clamp-1">{p.name}</p>
                        <p className="text-sm">{p.price?.toFixed(2).replace('.', ',')} TL</p>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-center text-gray-500">"{searchQuery}" için sonuç bulunamadı</p>
              )}
            </div>
          </div>
        </div>
      )}

      <CartDrawer />
    </>
  );
}
