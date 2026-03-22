import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Header() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [popularSearches, setPopularSearches] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  
  const { itemCount, setIsOpen } = useCart();
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  // Fetch popular searches when search opens
  useEffect(() => {
    if (searchOpen && popularSearches.length === 0) {
      fetchPopularSearches();
    }
  }, [searchOpen]);

  // Live search as user types
  useEffect(() => {
    if (searchQuery.length >= 1) {
      const timer = setTimeout(() => {
        performSearch(searchQuery);
      }, 300);
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
      // Fallback popular searches
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
    setSearchLoading(true);
    try {
      const res = await axios.get(`${API}/products?search=${encodeURIComponent(query)}&limit=6`);
      setSearchResults(res.data?.products || []);
    } catch (err) {
      console.error(err);
    } finally {
      setSearchLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      // Log search for analytics
      axios.post(`${API}/search/log`, { term: searchQuery }).catch(() => {});
      navigate(`/arama?q=${encodeURIComponent(searchQuery)}`);
      setSearchOpen(false);
      setSearchQuery("");
      setSearchResults([]);
    }
  };

  const handlePopularClick = (term) => {
    setSearchQuery(term);
    navigate(`/arama?q=${encodeURIComponent(term)}`);
    setSearchOpen(false);
    setSearchQuery("");
  };

  const handleProductClick = (slug) => {
    navigate(`/urun/${slug}`);
    setSearchOpen(false);
    setSearchQuery("");
    setSearchResults([]);
  };

  return (
    <>
      {/* Main Header - facette.com.tr style */}
      <header className="sticky top-0 z-40 bg-white border-b border-gray-100">
        <div className="container-main">
          <div className="flex items-center h-16 md:h-20">
            {/* Left: Navigation Menu */}
            <div className="flex-1 flex items-center">
              {/* Mobile Menu Button */}
              <button 
                className="lg:hidden p-2 -ml-2"
                onClick={() => setMobileMenuOpen(true)}
                data-testid="mobile-menu-btn"
              >
                <Menu size={24} />
              </button>

              {/* Desktop Navigation - Left aligned */}
              <nav className="hidden lg:flex items-center gap-8">
                <Link
                  to="/kategori/en-yeniler"
                  className="text-sm tracking-wider uppercase hover:opacity-60 transition-opacity"
                  data-testid="nav-en-yeniler"
                >
                  EN YENİLER
                </Link>
                <Link
                  to="/kategori/giyim"
                  className="text-sm tracking-wider uppercase hover:opacity-60 transition-opacity"
                  data-testid="nav-giyim"
                >
                  GİYİM
                </Link>
                <Link
                  to="/kategori/aksesuar"
                  className="text-sm tracking-wider uppercase hover:opacity-60 transition-opacity"
                  data-testid="nav-aksesuar"
                >
                  AKSESUAR
                </Link>
                <Link
                  to="/kategori/sale"
                  className="text-sm tracking-wider uppercase text-red-600 hover:opacity-60 transition-opacity"
                  data-testid="nav-sale"
                >
                  SALE
                </Link>
              </nav>
            </div>

            {/* Center: Logo */}
            <Link 
              to="/" 
              className="text-2xl md:text-3xl font-medium tracking-[0.15em]" 
              data-testid="logo"
              style={{ fontFamily: "'Times New Roman', serif" }}
            >
              FACETTE
            </Link>

            {/* Right: Icons */}
            <div className="flex-1 flex items-center justify-end gap-2 md:gap-4">
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

              {isAdmin && (
                <Link 
                  to="/admin" 
                  className="hidden md:block text-xs tracking-wider uppercase text-gray-400 hover:text-black ml-2"
                  data-testid="admin-link"
                >
                  Admin
                </Link>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Menu */}
      <div className={`mobile-menu ${mobileMenuOpen ? "open" : ""}`}>
        <div className="flex items-center justify-between p-4 border-b">
          <span className="text-xl tracking-[0.15em]" style={{ fontFamily: "'Times New Roman', serif" }}>FACETTE</span>
          <button onClick={() => setMobileMenuOpen(false)} data-testid="close-mobile-menu">
            <X size={24} />
          </button>
        </div>
        <nav className="p-4">
          <Link to="/kategori/en-yeniler" className="block py-4 text-sm tracking-wider uppercase border-b border-gray-100" onClick={() => setMobileMenuOpen(false)}>
            EN YENİLER
          </Link>
          <Link to="/kategori/giyim" className="block py-4 text-sm tracking-wider uppercase border-b border-gray-100" onClick={() => setMobileMenuOpen(false)}>
            GİYİM
          </Link>
          <Link to="/kategori/aksesuar" className="block py-4 text-sm tracking-wider uppercase border-b border-gray-100" onClick={() => setMobileMenuOpen(false)}>
            AKSESUAR
          </Link>
          <Link to="/kategori/sale" className="block py-4 text-sm tracking-wider uppercase text-red-600 border-b border-gray-100" onClick={() => setMobileMenuOpen(false)}>
            SALE
          </Link>
          <div className="mt-6 pt-6 border-t">
            <Link to="/hesabim" className="block py-2 text-sm text-gray-600" onClick={() => setMobileMenuOpen(false)}>
              Hesabım
            </Link>
            {isAdmin && (
              <Link to="/admin" className="block py-2 text-sm text-gray-600" onClick={() => setMobileMenuOpen(false)}>
                Admin Panel
              </Link>
            )}
          </div>
        </nav>
      </div>

      {/* Search Overlay - Enhanced with popular searches and live results */}
      {searchOpen && (
        <div className="fixed inset-0 bg-white z-50 overflow-y-auto animate-fade-in">
          <div className="container-main py-6">
            {/* Close button */}
            <div className="flex justify-end mb-8">
              <button 
                onClick={() => { setSearchOpen(false); setSearchQuery(""); setSearchResults([]); }}
                className="p-2 hover:opacity-60"
                data-testid="close-search"
              >
                <X size={24} />
              </button>
            </div>

            {/* Search Input */}
            <form onSubmit={handleSearch} className="max-w-2xl mx-auto mb-12">
              <div className="relative">
                <Search size={20} className="absolute left-0 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Ara..."
                  className="w-full text-2xl md:text-3xl font-light pl-8 pr-4 py-4 border-0 border-b border-gray-200 bg-transparent focus:outline-none focus:border-black transition-colors"
                  autoFocus
                  data-testid="search-input"
                />
              </div>
            </form>

            {/* Search Results or Popular Searches */}
            <div className="max-w-4xl mx-auto">
              {searchQuery.length === 0 ? (
                /* Popular Searches */
                <div>
                  <h3 className="text-xs tracking-widest uppercase text-gray-500 mb-6">
                    EN ÇOK ARANANLAR
                  </h3>
                  <div className="flex flex-wrap gap-3">
                    {popularSearches.map((item, index) => (
                      <button
                        key={index}
                        onClick={() => handlePopularClick(item.term)}
                        className="px-4 py-2 border border-gray-200 text-sm hover:border-black hover:bg-black hover:text-white transition-all"
                        data-testid={`popular-search-${index}`}
                      >
                        {item.term}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                /* Live Search Results */
                <div>
                  {searchLoading ? (
                    <div className="text-center py-8">
                      <p className="text-gray-500">Aranıyor...</p>
                    </div>
                  ) : searchResults.length > 0 ? (
                    <div>
                      <h3 className="text-xs tracking-widest uppercase text-gray-500 mb-6">
                        ÜRÜNLER ({searchResults.length})
                      </h3>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                        {searchResults.map((product) => (
                          <button
                            key={product.id}
                            onClick={() => handleProductClick(product.slug)}
                            className="text-left group"
                            data-testid={`search-result-${product.id}`}
                          >
                            <div className="aspect-[3/4] bg-gray-50 mb-3 overflow-hidden">
                              <img
                                src={product.images?.[0] || "/placeholder.jpg"}
                                alt={product.name}
                                className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
                              />
                            </div>
                            <p className="text-xs text-gray-500 mb-1">FACETTE</p>
                            <p className="text-sm mb-1 line-clamp-1">{product.name}</p>
                            <p className="text-sm font-medium">
                              {product.sale_price ? (
                                <>
                                  <span className="text-red-600">{product.sale_price.toFixed(2)} TL</span>
                                  <span className="text-gray-400 line-through ml-2">{product.price.toFixed(2)} TL</span>
                                </>
                              ) : (
                                `${product.price.toFixed(2)} TL`
                              )}
                            </p>
                          </button>
                        ))}
                      </div>
                      {searchResults.length >= 6 && (
                        <div className="text-center mt-8">
                          <button
                            onClick={handleSearch}
                            className="text-sm underline hover:no-underline"
                          >
                            Tüm sonuçları gör
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-8">
                      <p className="text-gray-500">"{searchQuery}" için sonuç bulunamadı</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Cart Drawer */}
      <CartDrawer />
    </>
  );
}
