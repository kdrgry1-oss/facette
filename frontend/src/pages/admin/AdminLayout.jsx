import { useState, useEffect, useRef, useMemo } from "react";
import { Outlet, Link, NavLink, useLocation, Navigate } from "react-router-dom";
import { LogOut, Menu, X, ChevronDown } from "lucide-react";
import { useAuth } from "../../context/AuthContext";
import { AppConfirmRoot } from "../../components/admin/AppConfirm";
import { getNavigationFor } from "../../lib/adminNav";

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
        data-testid={`nav-${item.key}`}
        className={({ isActive }) =>
          `flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
            isActive ? "bg-gray-800 text-white" : "text-white hover:bg-gray-800"
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
        data-testid={`nav-${item.key}`}
        className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors outline-none ${
          isChildActive || open ? "bg-gray-800 text-white" : "text-white hover:bg-gray-800"
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
                  isActive ? "bg-gray-800 text-white" : "text-white hover:bg-gray-800"
                }`}
              >
                <child.icon size={15} className={isActive ? "text-orange-400" : "text-gray-300"} />
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
                  isActive ? "bg-gray-800 text-white" : "text-white hover:bg-gray-800"
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
  const navigation = useMemo(() => getNavigationFor(user?.id || user?.email), [user?.id, user?.email]);

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
        {/* Logo — Dashboard linki */}
        <Link
          to="/admin"
          data-testid="admin-logo-home"
          className="text-lg font-bold tracking-[0.2em] shrink-0 text-white hover:text-gray-300 transition-colors"
        >
          FACETTE
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden lg:flex items-center gap-1 flex-1 overflow-x-auto scrollbar-none">
          {navigation.map((item) => (
            <NavItem key={item.key} item={item} />
          ))}
        </nav>

        {/* User area */}
        <div className="hidden lg:flex items-center gap-3 ml-auto shrink-0 border-l border-gray-800 pl-5">
          <div className="text-right">
            <p className="text-xs text-white font-medium leading-tight">{user.email}</p>
            <p className="text-xs text-gray-300">Admin</p>
          </div>
          <button
            onClick={logout}
            data-testid="admin-logout-btn"
            className="flex items-center gap-1 text-xs text-white hover:text-red-400 transition-colors px-2 py-1 rounded hover:bg-red-500/10"
          >
            <LogOut size={15} />
            Çıkış
          </button>
        </div>

        {/* Mobile menu toggle */}
        <button
          className="lg:hidden ml-auto text-white hover:text-gray-300"
          onClick={() => setMobileOpen(!mobileOpen)}
          data-testid="admin-mobile-toggle"
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </header>

      {/* Mobile Menu */}
      {mobileOpen && (
        <div className="lg:hidden fixed top-14 left-0 right-0 z-40 bg-gray-900 border-b border-gray-800 px-4 py-4 space-y-1 max-h-[80vh] overflow-y-auto shadow-2xl">
          {navigation.map((item) => (
            <NavItem key={item.key} item={item} closeMobile={() => setMobileOpen(false)} />
          ))}
          <div className="pt-4 mt-4 border-t border-gray-800 flex items-center justify-between">
            <div>
              <p className="text-sm text-white">{user.email}</p>
              <p className="text-xs text-gray-300">Admin</p>
            </div>
            <button onClick={logout} className="text-white hover:text-red-400">
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
      <AppConfirmRoot />
    </div>
  );
}
