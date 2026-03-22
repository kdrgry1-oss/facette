import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, User, ShoppingBag, Menu, X, ChevronDown } from "lucide-react";
import { useCart } from "../context/CartContext";
import { useAuth } from "../context/AuthContext";
import CartDrawer from "./CartDrawer";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Header() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [menuItems, setMenuItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [rotatingTexts, setRotatingTexts] = useState([]);
  const [currentTextIndex, setCurrentTextIndex] = useState(0);
  
  const { itemCount, setIsOpen } = useCart();
  const { user, isAdmin } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 50);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (rotatingTexts.length > 1) {
      const interval = setInterval(() => {
        setCurrentTextIndex((prev) => (prev + 1) % rotatingTexts.length);
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [rotatingTexts]);

  const fetchData = async () => {
    try {
      const [menuRes, catRes, settingsRes] = await Promise.all([
        axios.get(`${API}/menu`),
        axios.get(`${API}/categories`),
        axios.get(`${API}/settings`),
      ]);
      setMenuItems(menuRes.data || []);
      setCategories(catRes.data || []);
      setRotatingTexts(settingsRes.data?.rotating_texts || ["Yeni Sezon Ürünleri"]);
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
      {/* Rotating Text Banner */}
      <div className="bg-white border-b border-gray-100 py-2">
        <div className="container-main text-center">
          <p className="text-xs tracking-widest uppercase text-gray-600 animate-fade-in" key={currentTextIndex}>
            {rotatingTexts[currentTextIndex]}
          </p>
        </div>
      </div>

      {/* Main Header */}
      <header className={`sticky top-0 z-40 bg-white transition-shadow duration-300 ${isScrolled ? "shadow-sm" : ""}`}>
        <div className="container-main">
          <div className="flex items-center justify-between h-16 md:h-20">
            {/* Mobile Menu Button */}
            <button 
              className="lg:hidden p-2 -ml-2"
              onClick={() => setMobileMenuOpen(true)}
              data-testid="mobile-menu-btn"
            >
              <Menu size={24} />
            </button>

            {/* Logo */}
            <Link to="/" className="text-xl md:text-2xl font-bold tracking-[0.3em] uppercase" data-testid="logo">
              FACETTE
            </Link>

            {/* Desktop Navigation */}
            <nav className="hidden lg:flex items-center gap-8">
              {menuItems.map((item) => (
                <div key={item.id} className="nav-item relative group">
                  <Link
                    to={item.url}
                    className="text-sm tracking-wider uppercase hover:text-gray-500 transition-colors py-6 block"
                    data-testid={`nav-${item.name.toLowerCase()}`}
                  >
                    {item.name}
                  </Link>
                  {item.image_url && (
                    <div className="mega-menu py-8">
                      <div className="container-main flex gap-12">
                        <div className="flex-1">
                          <h3 className="text-sm font-medium mb-4 uppercase tracking-wider">{item.name}</h3>
                          <ul className="space-y-2">
                            {categories.slice(0, 6).map((cat) => (
                              <li key={cat.id}>
                                <Link to={`/kategori/${cat.slug}`} className="text-sm text-gray-600 hover:text-black">
                                  {cat.name}
                                </Link>
                              </li>
                            ))}
                          </ul>
                        </div>
                        <div className="w-80">
                          <img src={item.image_url} alt={item.name} className="w-full h-48 object-cover" />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </nav>

            {/* Right Icons */}
            <div className="flex items-center gap-4">
              <button 
                onClick={() => setSearchOpen(true)} 
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                data-testid="search-btn"
              >
                <Search size={20} />
              </button>
              
              <Link 
                to={user ? "/hesabim" : "/giris"} 
                className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                data-testid="account-btn"
              >
                <User size={20} />
              </Link>
              
              <button 
                onClick={() => setIsOpen(true)} 
                className="p-2 hover:bg-gray-100 rounded-full transition-colors relative"
                data-testid="cart-btn"
              >
                <ShoppingBag size={20} />
                {itemCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-5 h-5 bg-black text-white text-[10px] rounded-full flex items-center justify-center">
                    {itemCount}
                  </span>
                )}
              </button>

              {isAdmin && (
                <Link 
                  to="/admin" 
                  className="hidden md:block text-xs tracking-wider uppercase text-gray-500 hover:text-black"
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
          <span className="text-lg font-bold tracking-[0.2em]">FACETTE</span>
          <button onClick={() => setMobileMenuOpen(false)} data-testid="close-mobile-menu">
            <X size={24} />
          </button>
        </div>
        <nav className="p-4">
          {menuItems.map((item) => (
            <Link
              key={item.id}
              to={item.url}
              className="block py-3 text-lg border-b border-gray-100"
              onClick={() => setMobileMenuOpen(false)}
            >
              {item.name}
            </Link>
          ))}
          <div className="mt-6 pt-6 border-t">
            <Link to="/hesabim" className="block py-2 text-gray-600" onClick={() => setMobileMenuOpen(false)}>
              Hesabım
            </Link>
            {isAdmin && (
              <Link to="/admin" className="block py-2 text-gray-600" onClick={() => setMobileMenuOpen(false)}>
                Admin Panel
              </Link>
            )}
          </div>
        </nav>
      </div>

      {/* Search Overlay */}
      {searchOpen && (
        <div className="search-overlay animate-fade-in">
          <button 
            className="absolute top-6 right-6 p-2"
            onClick={() => setSearchOpen(false)}
            data-testid="close-search"
          >
            <X size={28} />
          </button>
          <div className="w-full max-w-2xl px-4">
            <form onSubmit={handleSearch}>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Ne aramıştınız?"
                className="w-full text-4xl md:text-5xl font-light border-0 border-b-2 border-black bg-transparent pb-4 focus:outline-none"
                autoFocus
                data-testid="search-input"
              />
            </form>
            <p className="mt-4 text-sm text-gray-500">Aramak için Enter'a basın</p>
          </div>
        </div>
      )}

      {/* Cart Drawer */}
      <CartDrawer />
    </>
  );
}
