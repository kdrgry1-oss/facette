import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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
import AdminVariants from "./pages/admin/Variants";
import AdminBanners from "./pages/admin/Banners";
import AdminSettings from "./pages/admin/Settings";
import AdminCampaigns from "./pages/admin/Campaigns";
import AdminPages from "./pages/admin/Pages";
import AdminPageDesign from "./pages/admin/PageDesign";
import AdminIntegrations from "./pages/admin/Integrations";
import AdminLogin from "./pages/admin/AdminLogin";
import AdminReturns from "./pages/admin/Returns";
import AttributeImport from "./pages/admin/AttributeImport";
import AdminQuestions from "./pages/admin/Questions";
import TrendyolLogs from "./pages/admin/TrendyolLogs";
import ProductAttributes from "./pages/admin/ProductAttributes";
import Vendors from "./pages/admin/Vendors";
import AdminUsersRoles from "./pages/admin/UsersRoles";
import Manufacturing from "./pages/admin/Manufacturing";
import Members from "./pages/admin/Members";
import Attribution from "./pages/admin/Attribution";
import HepsiburadaEslestir from "./pages/admin/HepsiburadaEslestir";
import TemuEslestir from "./pages/admin/TemuEslestir";
import SizeTablesList from "./pages/admin/SizeTablesList";
import Coupons from "./pages/admin/Coupons";
import ProductReviews from "./pages/admin/ProductReviews";
import AbandonedCarts from "./pages/admin/AbandonedCarts";
import { SalesReport, ProductsReport, StockReport, MembersReport } from "./pages/admin/Reports";
import { SeoRedirects, SeoMeta } from "./pages/admin/SeoAdmin";
import {
  Brands, ProductTags, MemberGroups, Announcements, Popups,
  StockAlerts, HavaleNotifications, Tickets, ShippingPaymentRules,
  CurrencyRates, BulkMail, ExtraReports,
} from "./pages/admin/CatalogExtras";
import AdminTasks from "./pages/admin/AdminTasks";
import EInvoiceSettings from "./pages/admin/EInvoiceSettings";
import CargoSettings from "./pages/admin/CargoSettings";
import MarketplaceHub from "./pages/admin/MarketplaceHub";
import IntegrationLogs from "./pages/admin/IntegrationLogs";
import FailedTransfers from "./pages/admin/FailedTransfers";
import BrandMapping from "./pages/admin/BrandMapping";
import CategoryMapping from "./pages/admin/CategoryMapping";
import BulkPriceStock from "./pages/admin/BulkPriceStock";
import StockAlerts2 from "./pages/admin/StockAlerts";
import CustomerSegments from "./pages/admin/CustomerSegments";
import MarketplaceProfit from "./pages/admin/MarketplaceProfit";
import { trackVisit } from "./lib/attribution";

import "./App.css";

function App() {
  // Fire-and-forget: capture utm/referrer on first paint.
  if (typeof window !== "undefined" && !window.__FACETTE_TRACKED__) {
    window.__FACETTE_TRACKED__ = true;
    trackVisit();
  }
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
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminDashboard />} />
              <Route path="urunler" element={<AdminProducts />} />
              <Route path="siparisler" element={<AdminOrders />} />
              <Route path="kategoriler" element={<AdminCategories />} />
              <Route path="varyantlar" element={<AdminVariants />} />
              <Route path="ozellik-import" element={<AttributeImport />} />
              <Route path="sorular" element={<AdminQuestions />} />
              <Route path="sayfa-tasarimi" element={<AdminPageDesign />} />
              <Route path="bannerlar" element={<AdminBanners />} />
              <Route path="kampanyalar" element={<AdminCampaigns />} />
              <Route path="entegrasyonlar" element={<AdminIntegrations />} />
              <Route path="iadeler" element={<AdminReturns />} />
              <Route path="sayfalar" element={<AdminPages />} />
              <Route path="ayarlar" element={<AdminSettings />} />
              {/* Provider ayarları — Ticimax'teki "E-Arşiv/E-Fatura Ayarları"
                  ile aynı mantık. Çoklu entegratör şeması backend'de tanımlı. */}
              <Route path="ayarlar/e-fatura" element={<EInvoiceSettings />} />
              <Route path="ayarlar/kargo" element={<CargoSettings />} />
              {/* Pazaryerleri Yönetimi — her e-ticaret platformunun API bilgileri +
                  aktarım kuralları + otomatik senkron ayarları. */}
              <Route path="pazaryerleri" element={<MarketplaceHub />} />
              {/* Entegrasyon Logları — ürün/sipariş/stok/fiyat aktarımlarının
                  kayıtları, filtreli arama, Excel export. */}
              <Route path="entegrasyon-loglari" element={<IntegrationLogs />} />
              {/* Aktarılamayan sipariş/ürün kayıtları + toplu tekrar-aktar. */}
              <Route path="aktarilamayanlar" element={<FailedTransfers />} />
              {/* Multi-marketplace marka eşleştirme. */}
              <Route path="marka-eslestir" element={<BrandMapping />} />
              {/* Multi-marketplace kategori eşleştirme */}
              <Route path="kategori-eslestir" element={<CategoryMapping />} />
              {/* Toplu Excel ile fiyat/stok güncelleme */}
              <Route path="toplu-fiyat-stok" element={<BulkPriceStock />} />
              {/* Kritik stok uyarıları + yeniden sipariş önerileri */}
              <Route path="stok-uyarilari" element={<StockAlerts2 />} />
              {/* RFM müşteri segmentasyonu — hedefli pazarlama için */}
              <Route path="musteri-segmentleri" element={<CustomerSegments />} />
              {/* Marketplace başına net kâr raporu (komisyon + kargo + iade çıkarılmış) */}
              <Route path="pazaryeri-karlilik" element={<MarketplaceProfit />} />
              <Route path="trendyol-eslestir" element={<Navigate to="/admin/kategori-eslestir" replace />} />
              <Route path="trendyol-loglar" element={<TrendyolLogs />} />
              <Route path="urun-ozellikleri" element={<ProductAttributes />} />
              <Route path="cariler" element={<Vendors />} />
              <Route path="kullanicilar" element={<AdminUsersRoles />} />
              <Route path="imalat" element={<Manufacturing />} />
              <Route path="uyeler" element={<Members />} />
              <Route path="kaynak" element={<Attribution />} />
              <Route path="hepsiburada-eslestir" element={<HepsiburadaEslestir />} />
              <Route path="temu-eslestir" element={<TemuEslestir />} />
              <Route path="olcu-tablolari" element={<SizeTablesList />} />
              <Route path="kuponlar" element={<Coupons />} />
              <Route path="yorumlar" element={<ProductReviews />} />
              <Route path="terkedilmis-sepet" element={<AbandonedCarts />} />
              <Route path="raporlar/satis" element={<SalesReport />} />
              <Route path="raporlar/urun" element={<ProductsReport />} />
              <Route path="raporlar/stok" element={<StockReport />} />
              <Route path="raporlar/uye" element={<MembersReport />} />
              <Route path="seo/meta" element={<SeoMeta />} />
              <Route path="seo/yonlendirmeler" element={<SeoRedirects />} />
              <Route path="markalar" element={<Brands />} />
              <Route path="etiketler" element={<ProductTags />} />
              <Route path="uye-gruplari" element={<MemberGroups />} />
              <Route path="duyurular" element={<Announcements />} />
              <Route path="popuplar" element={<Popups />} />
              <Route path="stok-alarm" element={<StockAlerts />} />
              <Route path="havale-bildirimleri" element={<HavaleNotifications />} />
              <Route path="tickets" element={<Tickets />} />
              <Route path="kargo-odeme-kurallari" element={<ShippingPaymentRules />} />
              <Route path="doviz" element={<CurrencyRates />} />
              <Route path="toplu-mail" element={<BulkMail />} />
              <Route path="raporlar/gelismis" element={<ExtraReports />} />
              <Route path="gorevler" element={<AdminTasks />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </CartProvider>
    </AuthProvider>
  );
}

export default App;
