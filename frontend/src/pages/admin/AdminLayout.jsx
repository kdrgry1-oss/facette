import { useState, useEffect, useRef } from "react";
import { Outlet, Link, NavLink, useLocation, Navigate } from "react-router-dom";
import {
  LayoutDashboard, Package, ShoppingCart, Tags, Image,
  Megaphone, FileText, Settings, LogOut, Menu, X, ChevronDown,
  Palette, Plug, RotateCcw, Store, GitMerge, Cable, Building2, Shield, Factory,
  Users, Ruler, MessageSquare, PenTool, Truck, CreditCard, TrendingUp, Link2,
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

// Navigation structure with dropdowns — organised by functional domain
const navigation = [
  {
    label: "Dashboard",
    path: "/admin",
    icon: LayoutDashboard,
    exact: true,
  },
  {
    label: "Katalog",
    icon: Package,
    children: [
      { label: "Tüm Ürünler", path: "/admin/urunler", icon: Package },
      { label: "Kategoriler", path: "/admin/kategoriler", icon: Tags },
      { label: "Ürün Özellikleri", path: "/admin/urun-ozellikleri", icon: Tags },
      { label: "Varyantlar", path: "/admin/varyantlar", icon: GitMerge },
      { label: "Ölçü Tabloları", path: "/admin/olcu-tablolari", icon: Ruler },
    ],
  },
  {
    label: "Siparişler",
    icon: ShoppingCart,
    children: [
      { label: "Tüm Siparişler", path: "/admin/siparisler", icon: ShoppingCart },
      { label: "İadeler & İptaller", path: "/admin/iadeler", icon: RotateCcw },
    ],
  },
  {
    label: "Üretim",
    icon: Factory,
    children: [
      { label: "İmalat Takip", path: "/admin/imalat", icon: Factory },
    ],
  },
  {
    label: "Üyeler",
    icon: Users,
    children: [
      { label: "Üye Listesi", path: "/admin/uyeler", icon: Users },
      { label: "Müşteri Soruları", path: "/admin/sorular", icon: MessageSquare },
    ],
  },
  {
    label: "İçerik",
    icon: PenTool,
    children: [
      { label: "Bannerlar & Sliderlar", path: "/admin/bannerlar", icon: Image },
      { label: "Sayfa Tasarımı", path: "/admin/sayfa-tasarimi", icon: Palette },
      { label: "Sayfalar (CMS)", path: "/admin/sayfalar", icon: FileText },
    ],
  },
  {
    label: "Pazarlama",
    icon: Megaphone,
    children: [
      { label: "Kampanyalar", path: "/admin/kampanyalar", icon: Megaphone },
      { label: "Kuponlar", path: "/admin/kuponlar", icon: Tags },
      { label: "Ürün Yorumları", path: "/admin/yorumlar", icon: MessageSquare },
      { label: "Terkedilmiş Sepetler", path: "/admin/terkedilmis-sepet", icon: ShoppingCart },
      { label: "Kaynak & Funnel", path: "/admin/kaynak", icon: TrendingUp },
    ],
  },
  {
    label: "Raporlar",
    icon: LayoutDashboard,
    children: [
      { label: "Satış Raporları", path: "/admin/raporlar/satis", icon: TrendingUp },
      { label: "Ürün Raporları", path: "/admin/raporlar/urun", icon: Package },
      { label: "Stok Raporu", path: "/admin/raporlar/stok", icon: Package },
      { label: "Üye Raporu", path: "/admin/raporlar/uye", icon: Users },
    ],
  },
  {
    label: "SEO",
    icon: FileText,
    children: [
      { label: "Meta Yönetimi", path: "/admin/seo/meta", icon: FileText },
      { label: "301 Yönlendirmeler", path: "/admin/seo/yonlendirmeler", icon: Link2 },
    ],
  },
  {
    label: "Entegrasyonlar",
    icon: Cable,
    children: [
      { label: "Tüm Entegrasyonlar", path: "/admin/entegrasyonlar", icon: Cable },
      { label: "Trendyol Eşleştir", path: "/admin/trendyol-eslestir", icon: Store },
      { label: "Hepsiburada Eşleştir", path: "/admin/hepsiburada-eslestir", icon: Store },
      { label: "Temu Eşleştir", path: "/admin/temu-eslestir", icon: Store },
      { label: "Trendyol Logları", path: "/admin/trendyol-loglar", icon: FileText },
    ],
  },
  {
    label: "Ayarlar",
    icon: Settings,
    children: [
      { label: "Genel Ayarlar", path: "/admin/ayarlar", icon: Settings },
      { label: "Kullanıcılar & Roller", path: "/admin/kullanicilar", icon: Shield },
      { label: "Cariler", path: "/admin/cariler", icon: Building2 },
    ],
  },
];

function NavItem({ item, closeMobile }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const location = useLocation();

  const isChildActive = item.children?.some((c) =>
    c.path === location.pathname || location.pathname.startsWith(c.path + "/")
  );

  useEffect(() => {
    function handleOutside(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, []);

  if (!item.children) {
    return (
      <NavLink
        to={item.path}
        end={item.exact}
        onClick={closeMobile}
        className={({ isActive }) =>
          `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
            isActive ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800"
          }`
        }
      >
        <item.icon size={16} />
        {item.label}
      </NavLink>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors outline-none ${
          isChildActive || open ? "bg-gray-800 text-white" : "text-gray-400 hover:text-white hover:bg-gray-800"
        }`}
      >
        <item.icon size={16} />
        {item.label}
        <ChevronDown size={13} className={`ml-0.5 transition-transform duration-200 ${open ? "rotate-180" : ""}`} />
      </button>

      {/* Desktop dropdown */}
      {open && (
        <div className="hidden lg:block absolute left-0 mt-1 w-52 bg-gray-900 border border-gray-700 rounded-lg shadow-xl z-50 overflow-hidden">
          {item.children.map((child) => {
            const isActive = location.pathname === child.path || location.pathname.startsWith(child.path + "/");
            return (
              <Link
                key={child.path}
                to={child.path}
                onClick={() => { setOpen(false); }}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-colors ${
                  isActive ? "bg-gray-800 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
                }`}
              >
                <child.icon size={15} className={isActive ? "text-orange-400" : "text-gray-600"} />
                {child.label}
              </Link>
            );
          })}
        </div>
      )}

      {/* Mobile inline expansion */}
      {open && (
        <div className="lg:hidden ml-4 mt-1 space-y-1">
          {item.children.map((child) => {
            const isActive = location.pathname === child.path || location.pathname.startsWith(child.path + "/");
            return (
              <Link
                key={child.path}
                to={child.path}
                onClick={() => { setOpen(false); if (closeMobile) closeMobile(); }}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  isActive ? "bg-gray-800 text-white" : "text-gray-400 hover:bg-gray-800 hover:text-white"
                }`}
              >
                <child.icon size={15} />
                {child.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function AdminLayout() {
  const { user, isAdmin, logout, loading } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p>Yükleniyor...</p>
      </div>
    );
  }

  if (!user || !isAdmin) {
    return <Navigate to="/admin/login" />;
  }

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col" data-testid="admin-layout">
      {/* Top Navigation Bar */}
      <header className="fixed top-0 left-0 right-0 z-50 h-14 bg-gray-900 text-white border-b border-gray-800 flex items-center px-4 gap-6">
        {/* Logo */}
        <Link to="/admin" className="text-lg font-bold tracking-[0.2em] shrink-0">
          FACETTE
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden lg:flex items-center gap-1 flex-1">
          {navigation.map((item) => (
            <NavItem key={item.label} item={item} />
          ))}
        </nav>

        {/* User area */}
        <div className="hidden lg:flex items-center gap-3 ml-auto shrink-0 border-l border-gray-800 pl-5">
          <div className="text-right">
            <p className="text-xs text-white font-medium leading-tight">{user.email}</p>
            <p className="text-xs text-gray-500">Admin</p>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-red-400 transition-colors px-2 py-1 rounded hover:bg-red-500/10"
          >
            <LogOut size={15} />
            Çıkış
          </button>
        </div>

        {/* Mobile menu toggle */}
        <button
          className="lg:hidden ml-auto text-gray-400 hover:text-white"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </header>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="lg:hidden fixed top-14 left-0 right-0 z-40 bg-gray-900 border-b border-gray-800 px-4 py-4 space-y-1 max-h-[80vh] overflow-y-auto shadow-2xl">
          {navigation.map((item) => (
            <NavItem key={item.label} item={item} closeMobile={() => setMobileOpen(false)} />
          ))}
          <div className="pt-4 mt-4 border-t border-gray-800 flex items-center justify-between">
            <div>
              <p className="text-sm text-white">{user.email}</p>
              <p className="text-xs text-gray-500">Admin</p>
            </div>
            <button onClick={logout} className="text-gray-400 hover:text-red-400">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      )}

      {/* Page Content */}
      <main className="pt-14 flex-1">
        <div className="p-4 md:p-6 lg:p-8 max-w-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
