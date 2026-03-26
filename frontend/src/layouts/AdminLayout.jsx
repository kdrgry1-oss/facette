import { useState } from "react";
import { Outlet, Link, useLocation, Navigate } from "react-router-dom";
import { 
  LayoutDashboard, Package, ShoppingCart, 
  Megaphone, Settings, LogOut, Menu, X, ChevronDown, MonitorPlay, FileText, Blocks, BarChart
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const menuGroups = [
  {
    label: "Dashboard",
    icon: LayoutDashboard,
    path: "/admin",
  },
  {
    label: "Ürünler",
    icon: Package,
    submenus: [
      {
        title: "Ürünler",
        items: [
          { label: "Ürün Yönetimi", path: "/admin/urunler" },
          { label: "Kategori Yönetimi", path: "/admin/kategoriler" },
        ]
      },
      {
        title: "Varyantlar",
        items: [
          { label: "Varyant Yönetimi", path: "/admin/varyantlar" },
        ]
      }
    ]
  },
  {
    label: "Siparişler",
    icon: ShoppingCart,
    submenus: [
      {
        title: "Siparişler",
        items: [
          { label: "Tüm Siparişler", path: "/admin/siparisler" },
        ]
      }
    ]
  },
  {
    label: "Tasarım",
    icon: MonitorPlay,
    submenus: [
      {
        title: "Tasarım Ayarları",
        items: [
          { label: "Sayfa Tasarımı", path: "/admin/sayfa-tasarimi" },
          { label: "Banner Yönetimi", path: "/admin/bannerlar" },
        ]
      },
      {
        title: "İçerik Yönetimi",
        items: [
          { label: "Sayfalar", path: "/admin/sayfalar" },
        ]
      }
    ]
  },
  {
    label: "Modüller",
    icon: Blocks,
    submenus: [
      {
        title: "Dış Bağlantılar",
        items: [
          { label: "Entegrasyonlar", path: "/admin/entegrasyonlar" },
        ]
      }
    ]
  },
  {
    label: "Kampanyalar",
    icon: Megaphone,
    submenus: [
      {
        title: "Kampanyalar",
        items: [
          { label: "Tüm Kampanyalar", path: "/admin/kampanyalar" },
        ]
      }
    ]
  },
  {
    label: "Ayarlar",
    icon: Settings,
    submenus: [
      {
        title: "Genel",
        items: [
          { label: "Genel Ayarlar", path: "/admin/ayarlar" },
        ]
      }
    ]
  }
];

export default function AdminLayout() {
  const { user, isAdmin, logout, loading } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

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

  // Active state checker
  const isGroupActive = (group) => {
    if (group.path && location.pathname === group.path) return true;
    if (group.submenus) {
      return group.submenus.some(col => col.items.some(item => location.pathname.startsWith(item.path)));
    }
    return false;
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col" data-testid="admin-layout">
      {/* Top Navbar */}
      <header className="bg-[#1f2937] text-[#9ca3af] sticky top-0 z-50 border-b border-gray-700">
        <div className="flex items-center justify-between px-4 h-14 w-full">
          
          <div className="flex items-center gap-6 flex-none">
            <button className="xl:hidden p-1 text-white" onClick={() => setMenuOpen(!menuOpen)}>
              {menuOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
            <Link 
              to="/admin" 
              className="font-bold text-white tracking-wider flex items-center gap-2"
            >
              <div className="w-6 h-6 bg-white rounded flex items-center justify-center text-[#1f2937] text-xs">F</div>
              FACETTE
            </Link>
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden xl:flex items-center h-full flex-1 ml-6">
            {menuGroups.map((group, idx) => {
              const active = isGroupActive(group);
              const Icon = group.icon;

              if (!group.submenus) {
                return (
                  <Link
                    key={idx}
                    to={group.path}
                    className={`flex items-center gap-2 px-4 h-full border-b-2 hover:text-white transition-colors ${
                      active ? "border-blue-500 text-white bg-gray-800/50" : "border-transparent text-gray-300"
                    }`}
                  >
                    <Icon size={16} />
                    <span className="text-sm font-medium">{group.label}</span>
                  </Link>
                );
              }

              // Dropdown Menu
              return (
                <div key={idx} className="group relative h-full flex items-center">
                  <button
                    className={`flex items-center gap-2 px-4 h-full border-b-2 hover:text-white transition-colors ${
                      active ? "border-blue-500 text-white bg-gray-800/50" : "border-transparent text-gray-300"
                    }`}
                  >
                    <Icon size={16} />
                    <span className="text-sm font-medium">{group.label}</span>
                  </button>

                  <div className="absolute top-14 left-0 bg-white shadow-xl rounded-b-md border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200 z-50 flex text-gray-800 text-sm min-w-[200px] whitespace-nowrap overflow-hidden">
                    {group.submenus.map((col, cIdx) => (
                      <div key={cIdx} className="p-4 border-r last:border-0 border-gray-100 min-w-[180px]">
                        <h4 className="font-bold text-gray-900 mb-3 ml-2 border-b pb-1">{col.title}</h4>
                        <ul className="space-y-1">
                          {col.items.map((item, iIdx) => (
                            <li key={iIdx}>
                              <Link 
                                to={item.path} 
                                className="block px-2 py-1.5 text-gray-600 hover:text-blue-600 hover:bg-blue-50/50 rounded transition-colors"
                              >
                                &raquo; {item.label}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </nav>

          <div className="flex items-center justify-end gap-4 flex-none">
            <div className="hidden sm:block text-right">
              <p className="text-xs text-gray-400">Hoş Geldiniz,</p>
              <p className="text-sm font-medium text-white">{user.email}</p>
            </div>
            <button 
              onClick={logout} 
              className="text-gray-400 hover:text-white p-2" 
              title="Çıkış Yap"
            >
              <LogOut size={18} />
            </button>
          </div>
        </div>

        {/* Mobile Dropdown Menu */}
        {menuOpen && (
          <div className="xl:hidden bg-white text-gray-800 absolute top-14 left-0 right-0 shadow-lg pb-4 max-h-[80vh] overflow-y-auto z-40">
            {menuGroups.map((group, idx) => {
              if (!group.submenus) {
                return (
                  <Link
                    key={idx}
                    to={group.path}
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-3 px-6 py-3 font-semibold border-b border-gray-100"
                  >
                    <group.icon size={18} />
                    {group.label}
                  </Link>
                );
              }

              return (
                <div key={idx} className="border-b border-gray-100">
                  <div className="flex items-center gap-3 px-6 py-3 font-semibold text-gray-900 bg-gray-50">
                    <group.icon size={18} />
                    {group.label}
                  </div>
                  <div>
                    {group.submenus.map((col, cIdx) => (
                      <div key={cIdx} className="px-6 py-2">
                        <h4 className="font-bold text-xs text-gray-500 uppercase tracking-wider mb-2">{col.title}</h4>
                        <ul className="space-y-1 mb-2">
                          {col.items.map((item, iIdx) => (
                            <li key={iIdx}>
                              <Link 
                                to={item.path} 
                                onClick={() => setMenuOpen(false)}
                                className="block py-1.5 text-sm text-gray-600 hover:text-blue-600"
                              >
                                - {item.label}
                              </Link>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </header>

      {/* Main Content */}
      <main className="flex-1 w-full bg-[#f8f9fa] pb-12">
        <div className="w-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
