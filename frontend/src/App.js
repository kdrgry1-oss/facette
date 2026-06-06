import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useEffect, lazy, Suspense } from "react";
import { Toaster } from "sonner";
import { CartProvider } from "./context/CartContext";
import { AuthProvider } from "./context/AuthContext";
import { FavoritesProvider } from "./context/FavoritesContext";
import { bootstrapNative } from "./lib/native";

// Storefront sayfaları — hafif ve ilk açılışta gerekli, bu yüzden eager (hemen) yüklenir.
import Home from "./pages/Home";
import GizlilikPolitikasi from "./pages/GizlilikPolitikasi";
import Category from "./pages/Category";
import ProductDetail from "./pages/ProductDetail";
import Cart from "./pages/Cart";
import Checkout from "./pages/Checkout";
import Search from "./pages/Search";
import StaticPage from "./pages/StaticPage";
import Account from "./pages/Account";
import Login from "./pages/Login";
import TrackOrder from "./pages/TrackOrder";
import OrderSuccess from "./pages/OrderSuccess";
import MiuMiuTheme from "./pages/storefront/MiuMiuTheme";

import MarketingPixelsInjector from "./components/MarketingPixelsInjector";
import MaintenanceGate from "./components/MaintenanceGate";
import { trackVisit } from "./lib/attribution";

import "./App.css";

// Admin paneli (~75 sayfa + ağır kütüphaneler) AYRI bir chunk olarak,
// sadece /admin'e girilince yüklenir. Storefront ziyaretçileri bunu indirmez.
const AdminApp = lazy(() => import("./AdminApp"));

function App() {
  useEffect(() => {
    // UTM/referrer yakalama — render'ı bloklamaması için mount sonrası.
    if (typeof window !== "undefined" && !window.__FACETTE_TRACKED__) {
      window.__FACETTE_TRACKED__ = true;
      trackVisit();
    }
    // Capacitor native bootstrap (web mode'da no-op)
    bootstrapNative();
  }, []);

  return (
    <AuthProvider>
      <CartProvider>
        <FavoritesProvider>
          <BrowserRouter>
            <Toaster position="top-center" richColors />
            <MarketingPixelsInjector />
            <MaintenanceGate>
              <Routes>
                {/* Storefront */}
                <Route path="/" element={<Home />} />
                <Route path="/kategori/:slug" element={<Category />} />
                <Route path="/sepet" element={<Cart />} />
                <Route path="/odeme" element={<Checkout />} />
                <Route path="/arama" element={<Search />} />
                <Route path="/sayfa/:slug" element={<StaticPage />} />
                <Route path="/gizlilik" element={<GizlilikPolitikasi />} />
                <Route path="/hesabim" element={<Account />} />
                <Route path="/giris" element={<Login />} />
                <Route path="/siparis-takip" element={<TrackOrder />} />
                <Route path="/siparis-takip/:trackingCode" element={<TrackOrder />} />
                <Route path="/order-success/:orderNumber" element={<OrderSuccess />} />
                <Route path="/siparis-tamamlandi/:orderNumber" element={<OrderSuccess />} />

                {/* Tema önizleme */}
                <Route path="/tema/:slug" element={<MiuMiuTheme />} />
                <Route path="/tema" element={<MiuMiuTheme />} />

                {/* Admin — lazy yüklenen ayrı chunk. /admin/login dahil tüm admin
                    rotaları AdminApp içindeki kendi <Routes>'unda tanımlı. */}
                <Route
                  path="/admin/*"
                  element={
                    <Suspense fallback={<div style={{ padding: 40, textAlign: "center", color: "#888" }}>Yükleniyor…</div>}>
                      <AdminApp />
                    </Suspense>
                  }
                />

                {/* Ürün detay — SEO dostu kök URL. Statik rotalar dinamikten önce
                    eşleştiği için /sepet, /giris, /admin vb. her zaman önceliklidir. */}
                <Route path="/urun/:slug" element={<ProductDetail />} />
                <Route path="/:slug" element={<ProductDetail />} />
              </Routes>
            </MaintenanceGate>
          </BrowserRouter>
        </FavoritesProvider>
      </CartProvider>
    </AuthProvider>
  );
}

export default App;
