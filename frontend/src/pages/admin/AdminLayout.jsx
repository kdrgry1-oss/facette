import { useState, useEffect } from "react";
import { Outlet, Link, useLocation, Navigate } from "react-router-dom";
import { 
  LayoutDashboard, Package, ShoppingCart, Tags, Image, 
  Megaphone, FileText, Settings, LogOut, Menu, X, ChevronDown, Palette
} from "lucide-react";
import { useAuth } from "../../context/AuthContext";

const menuItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/admin" },
  { icon: Package, label: "Ürünler", path: "/admin/urunler" },
  { icon: ShoppingCart, label: "Siparişler", path: "/admin/siparisler" },
  { icon: Tags, label: "Kategoriler", path: "/admin/kategoriler" },
  { icon: Palette, label: "Sayfa Tasarımı", path: "/admin/sayfa-tasarimi" },
  { icon: Image, label: "Bannerlar", path: "/admin/bannerlar" },
  { icon: Megaphone, label: "Kampanyalar", path: "/admin/kampanyalar" },
  { icon: FileText, label: "Sayfalar", path: "/admin/sayfalar" },
  { icon: Settings, label: "Ayarlar", path: "/admin/ayarlar" },
];

export default function AdminLayout() {
  const { user, isAdmin, logout, loading } = useAuth();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-100">
        <p>Yükleniyor...</p>
      </div>
    );
  }

  if (!user || !isAdmin) {
    return <Navigate to="/giris" />;
  }

  return (
    <div className="min-h-screen bg-gray-100" data-testid="admin-layout">
      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 h-16 bg-gray-900 text-white flex items-center justify-between px-4 z-50">
        <button onClick={() => setSidebarOpen(!sidebarOpen)}>
          {sidebarOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
        <span className="font-bold tracking-wider">FACETTE ADMIN</span>
        <div />
      </div>

      {/* Sidebar */}
      <aside className={`admin-sidebar ${sidebarOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"} transition-transform z-40`}>
        <div className="h-16 flex items-center justify-center border-b border-gray-800">
          <Link to="/admin" className="text-lg font-bold tracking-[0.2em]">FACETTE</Link>
        </div>

        <nav className="py-4">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path || 
              (item.path !== "/admin" && location.pathname.startsWith(item.path));
            
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`admin-sidebar-item ${isActive ? "active" : ""}`}
                onClick={() => setSidebarOpen(false)}
              >
                <Icon size={20} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-gray-800">
          <div className="flex items-center justify-between text-sm">
            <div>
              <p className="text-white">{user.email}</p>
              <p className="text-gray-500 text-xs">Admin</p>
            </div>
            <button onClick={logout} className="text-gray-400 hover:text-white">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile Overlay */}
      {sidebarOpen && (
        <div 
          className="lg:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="lg:ml-64 pt-16 lg:pt-0 min-h-screen">
        <div className="p-4 md:p-6 lg:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
