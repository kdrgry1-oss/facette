import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { CartProvider } from "./context/CartContext";
import { AuthProvider } from "./context/AuthContext";

// Pages
import Home from "./pages/Home";
import Category from "./pages/Category";
import ProductDetail from "./pages/ProductDetail";
import Cart from "./pages/Cart";
import Checkout from "./pages/Checkout";
import Search from "./pages/Search";
import StaticPage from "./pages/StaticPage";
import Account from "./pages/Account";
import Login from "./pages/Login";
import TrackOrder from "./pages/TrackOrder";

// Admin Pages
import AdminLayout from "./pages/admin/AdminLayout";
import AdminDashboard from "./pages/admin/Dashboard";
import AdminProducts from "./pages/admin/Products";
import AdminOrders from "./pages/admin/Orders";
import AdminCategories from "./pages/admin/Categories";
import AdminBanners from "./pages/admin/Banners";
import AdminSettings from "./pages/admin/Settings";
import AdminCampaigns from "./pages/admin/Campaigns";
import AdminPages from "./pages/admin/Pages";
import AdminPageDesign from "./pages/admin/PageDesign";
import AdminIntegrations from "./pages/admin/Integrations";

import "./App.css";

function App() {
  return (
    <AuthProvider>
      <CartProvider>
        <BrowserRouter>
          <Toaster position="top-center" richColors />
          <Routes>
            {/* Storefront */}
            <Route path="/" element={<Home />} />
            <Route path="/kategori/:slug" element={<Category />} />
            <Route path="/urun/:slug" element={<ProductDetail />} />
            <Route path="/sepet" element={<Cart />} />
            <Route path="/odeme" element={<Checkout />} />
            <Route path="/arama" element={<Search />} />
            <Route path="/sayfa/:slug" element={<StaticPage />} />
            <Route path="/hesabim" element={<Account />} />
            <Route path="/giris" element={<Login />} />
            <Route path="/siparis-takip" element={<TrackOrder />} />
            <Route path="/siparis-takip/:trackingCode" element={<TrackOrder />} />
            
            {/* Admin */}
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminDashboard />} />
              <Route path="urunler" element={<AdminProducts />} />
              <Route path="siparisler" element={<AdminOrders />} />
              <Route path="kategoriler" element={<AdminCategories />} />
              <Route path="sayfa-tasarimi" element={<AdminPageDesign />} />
              <Route path="bannerlar" element={<AdminBanners />} />
              <Route path="kampanyalar" element={<AdminCampaigns />} />
              <Route path="entegrasyonlar" element={<AdminIntegrations />} />
              <Route path="sayfalar" element={<AdminPages />} />
              <Route path="ayarlar" element={<AdminSettings />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </CartProvider>
    </AuthProvider>
  );
}

export default App;
