import { useState, useEffect } from "react";
import { Store, CreditCard, Truck, MessageSquare, FileText, RefreshCw, Check, X, AlertCircle, Upload, Download, Package, Database, ShoppingBag } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";


const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function Integrations() {
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [importing, setImporting] = useState(false);
  const [statuses, setStatuses] = useState({
    iyzico: { configured: false, mode: "sandbox" },
    trendyol: { configured: false, mode: "sandbox" },
    mng: { configured: true, mode: "live" },
    netgsm: { configured: false, mode: "sandbox" },
    gib: { configured: false, mode: "test" },
    ticimax: { configured: true, mode: "live" }
  });
  const [trendyolOrders, setTrendyolOrders] = useState([]);
  const [trendyolModalOpen, setTrendyolModalOpen] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [trendyolSettings, setTrendyolSettings] = useState({
    supplier_id: "",
    api_key: "",
    api_secret: "",
    mode: "sandbox",
    is_active: false,
    default_markup: 0
  });

  // Ticimax state
  const [ticimaxImportingProducts, setTicimaxImportingProducts] = useState(false);
  const [ticimaxImportingCategories, setTicimaxImportingCategories] = useState(false);
  const [ticimaxImportingOrders, setTicimaxImportingOrders] = useState(false);
  const [ticimaxStatus, setTicimaxStatus] = useState({ configured: true, mode: "live", last_sync: null });

  // XML Feed state
  const [xmlImporting, setXmlImporting] = useState(false);
  const [xmlLastSync, setXmlLastSync] = useState(null);

  // Integration Logs State
  const [logsModalOpen, setLogsModalOpen] = useState(false);
  const [integrationLogs, setIntegrationLogs] = useState([]);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logFilters, setLogFilters] = useState({ platform: "", status: "" });

  const fetchLogs = async () => {
    setLogsLoading(true);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams();
      if (logFilters.platform) params.append("platform", logFilters.platform);
      if (logFilters.status) params.append("status", logFilters.status);
      
      const res = await axios.get(`${API}/integrations/integration-logs?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        setIntegrationLogs(res.data.logs || []);
      }
    } catch (err) {
      toast.error("Loglar alınamadı");
    } finally {
      setLogsLoading(false);
    }
  };

  useEffect(() => {
    if (logsModalOpen) {
      fetchLogs();
    }
  }, [logsModalOpen, logFilters]);

  useEffect(() => {
    fetchStatuses();
  }, []);

  const fetchStatuses = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      // Fetch integration statuses
      const [paymentRes, trendyolRes, gibRes, ticimaxRes, xmlRes] = await Promise.all([
        axios.get(`${API}/integrations/payment/status`, { headers }).catch(() => ({ data: { configured: false, mode: "sandbox" } })),
        axios.get(`${API}/integrations/trendyol/status`, { headers }).catch(() => ({ data: { configured: false, mode: "sandbox" } })),
        axios.get(`${API}/integrations/gib/status`, { headers }).catch(() => ({ data: { configured: false, mode: "test" } })),
        axios.get(`${API}/integrations/ticimax/status`, { headers }).catch(() => ({ data: { configured: true, mode: "live", last_sync: null } })),
        axios.get(`${API}/integrations/xml/status`, { headers }).catch(() => ({ data: { last_sync: null } }))
      ]);

      setStatuses(prev => ({
        ...prev,
        iyzico: paymentRes.data,
        trendyol: trendyolRes.data,
        gib: gibRes.data
      }));
      setTicimaxStatus(ticimaxRes.data);
      setXmlLastSync(xmlRes.data?.last_sync || null);
    } catch (err) {
      console.error("Status fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchTrendyolSettings = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`${API}/integrations/trendyol/settings?t=${Date.now()}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTrendyolSettings(res.data);
      setTrendyolModalOpen(true);
    } catch (err) {
      toast.error("Ayarlar alınamadı");
    }
  };

  const saveTrendyolSettings = async (e) => {
    e.preventDefault();
    setSavingSettings(true);
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API}/integrations/trendyol/settings`, trendyolSettings, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Trendyol ayarları kaydedildi");
      setTrendyolModalOpen(false);
      fetchStatuses();
    } catch (err) {
      toast.error("Ayarlar kaydedilemedi");
    } finally {
      setSavingSettings(false);
    }
  };

  const handleTrendyolSync = async () => {
    setSyncing(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/products/sync`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (res.data.success) {
        toast.success(`${res.data.products_sent} ürün Trendyol'a gönderildi`);
      } else {
        toast.error(res.data.error || "Senkronizasyon başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Senkronizasyon hatası");
    } finally {
      setSyncing(false);
    }
  };

  const handleTrendyolInventorySync = async () => {
    setSyncing(true);
    toast.info("Stok/Fiyat senkronizasyonu başlatılıyor...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/products/inventory-sync`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        toast.success(res.data.message);
      } else {
        toast.error(res.data.message || "Senkronizasyon başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Senkronizasyon hatası");
    } finally {
      setSyncing(false);
    }
  };

  const handleTrendyolCategoriesSync = async () => {
    setSyncing(true);
    toast.info("Trendyol kategorileri çekiliyor...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/categories/sync`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        toast.success(res.data.message);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kategori çekme hatası");
    } finally {
      setSyncing(false);
    }
  };

  const handleTrendyolBrandsSync = async () => {
    setSyncing(true);
    toast.info("Trendyol markaları çekiliyor...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/brands/sync`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.data.success) {
        toast.success(res.data.message);
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Marka çekme hatası");
    } finally {
      setSyncing(false);
    }
  };

  const handleTrendyolImport = async () => {
    setImporting(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/trendyol/orders/import`, null, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (res.data.success) {
        toast.success(res.data.message);
      } else {
        toast.error("İçe aktarma başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "İçe aktarma hatası");
    } finally {
      setImporting(false);
    }
  };

  // ---- Ticimax Handlers ----
  const handleTicimaxImportCategories = async () => {
    setTicimaxImportingCategories(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/ticimax/categories/import`, null, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 120000
      });
      if (res.data.success) {
        toast.success(res.data.message || `${res.data.imported} kategori içe aktarıldı`);
        setTicimaxStatus(prev => ({ ...prev, last_sync: new Date().toISOString() }));
      } else {
        toast.error("Kategori aktarımı başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Ticimax kategori hatası");
    } finally {
      setTicimaxImportingCategories(false);
    }
  };

  const handleTicimaxImportProducts = async () => {
    setTicimaxImportingProducts(true);
    toast.info("Ürünler çekiliyor, bu işlem birkaç dakika sürebilir...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/ticimax/products/import?limit=500`, null, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 300000
      });
      if (res.data.success) {
        toast.success(res.data.message || `${res.data.total} ürün aktarıldı`);
        setTicimaxStatus(prev => ({ ...prev, last_sync: new Date().toISOString() }));
      } else {
        toast.error("Ürün aktarımı başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Ticimax ürün hatası");
    } finally {
      setTicimaxImportingProducts(false);
    }
  };

  const handleTicimaxImportOrders = async () => {
    setTicimaxImportingOrders(true);
    toast.info("Siparişler çekiliyor...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/ticimax/orders/import?limit=200`, null, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 180000
      });
      if (res.data.success) {
        toast.success(res.data.message || `${res.data.total} sipariş aktarıldı`);
        setTicimaxStatus(prev => ({ ...prev, last_sync: new Date().toISOString() }));
      } else {
        toast.error("Sipariş aktarımı başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Ticimax sipariş hatası");
    } finally {
      setTicimaxImportingOrders(false);
    }
  };


  // ---- XML Feed Handler ----
  const handleXmlImport = async () => {
    setXmlImporting(true);
    toast.info("XML feed'den ürünler çekiliyor...");
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/integrations/xml/products/import`, null, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 120000
      });
      if (res.data.success) {
        toast.success(res.data.message || `${res.data.total} ürün aktarıldı`);
        setXmlLastSync(new Date().toISOString());
      } else {
        toast.error("XML aktarımı başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "XML import hatası");
    } finally {
      setXmlImporting(false);
    }
  };

  const integrations = [
    {
      id: "iyzico",
      name: "Iyzico",
      description: "Online ödeme altyapısı - Kredi kartı, banka kartı ödemeleri",
      icon: <CreditCard className="w-8 h-8" />,
      status: statuses.iyzico,
      color: "blue",
      instructions: "Iyzico panel'den API Key ve Secret Key alınız. .env dosyasına ekleyiniz.",
      envKeys: ["IYZICO_API_KEY", "IYZICO_SECRET_KEY", "IYZICO_MODE"]
    },
    {
      id: "trendyol",
      name: "Trendyol Marketplace",
      description: "Ürün senkronizasyonu, sipariş yönetimi, stok güncelleme",
      icon: <Store className="w-8 h-8" />,
      status: statuses.trendyol,
      color: "orange",
      instructions: "Trendyol API bilgilerini yapılandırarak panelden ürün aktarımı yapabilirsiniz.",
      envKeys: [],
      actions: [
        { label: "Ayarları Yapılandır", icon: <Store size={16} />, onClick: fetchTrendyolSettings, loading: false },
        { label: "Kategorileri İndir", icon: <Download size={16} />, onClick: handleTrendyolCategoriesSync, loading: syncing, disabled: !statuses.trendyol?.configured },
        { label: "Markaları İndir", icon: <Download size={16} />, onClick: handleTrendyolBrandsSync, loading: syncing, disabled: !statuses.trendyol?.configured },
        { label: "Ürünleri Gönder", icon: <Upload size={16} />, onClick: handleTrendyolSync, loading: syncing, disabled: !statuses.trendyol?.configured },
        { label: "Fiyat/Stok Güncelle", icon: <RefreshCw size={16} />, onClick: handleTrendyolInventorySync, loading: syncing, disabled: !statuses.trendyol?.configured },
        { label: "Siparişleri Al", icon: <Download size={16} />, onClick: handleTrendyolImport, loading: importing, disabled: !statuses.trendyol?.configured }
      ]
    },
    {
      id: "mng",
      name: "MNG Kargo",
      description: "Kargo takip, etiket basımı, gönderi oluşturma",
      icon: <Truck className="w-8 h-8" />,
      status: statuses.mng,
      color: "green",
      instructions: "MNG Kargo API entegrasyonu aktif. Kargo etiketi basımı Siparişler sayfasından yapılabilir.",
      envKeys: []
    },
    {
      id: "gib",
      name: "GIB E-Fatura / E-Arşiv",
      description: "Elektronik fatura ve e-arşiv fatura oluşturma, GIB entegrasyonu",
      icon: <FileText className="w-8 h-8" />,
      status: statuses.gib,
      color: "blue",
      instructions: "GIB entegrasyonu için Mali Mühür (dijital imza sertifikası) gereklidir. VKN ve şirket bilgilerini .env dosyasına ekleyiniz.",
      envKeys: ["GIB_USERNAME", "GIB_PASSWORD", "GIB_VKN", "GIB_COMPANY_NAME", "GIB_MODE"]
    },
    {
      id: "netgsm",
      name: "Netgsm SMS",
      description: "SMS bildirimleri, sipariş durumu güncellemeleri",
      icon: <MessageSquare className="w-8 h-8" />,
      status: statuses.netgsm,
      color: "purple",
      instructions: "Netgsm panel'den API bilgilerini alınız.",
      envKeys: ["NETGSM_USERNAME", "NETGSM_PASSWORD", "NETGSM_HEADER"]
    }
  ];

  return (
    <div data-testid="integrations-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Entegrasyonlar</h1>
          <p className="text-sm text-gray-500 mt-1">Pazaryeri ve ödeme entegrasyonlarını yönetin</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setLogsModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 border text-sm rounded hover:bg-gray-200"
          >
            <FileText size={16} /> Entegrasyon Logları
          </button>
          <button 
            onClick={fetchStatuses}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 border rounded hover:bg-gray-50 text-sm"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            Durumu Güncelle
          </button>
        </div>
      </div>

      {/* Integration Cards */}
      <div className="grid md:grid-cols-2 gap-6">
        {integrations.map((integration) => (
          <div 
            key={integration.id}
            className={`bg-white rounded-lg border-2 p-6 transition-all ${
              integration.status.configured 
                ? "border-green-200 bg-green-50/30" 
                : "border-gray-200"
            }`}
          >
            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className={`p-3 rounded-lg ${
                integration.status.configured 
                  ? "bg-green-100 text-green-600" 
                  : "bg-gray-100 text-gray-400"
              }`}>
                {integration.icon}
              </div>

              {/* Content */}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="font-semibold text-lg">{integration.name}</h3>
                  {integration.status.configured ? (
                    <span className="flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                      <Check size={12} /> Aktif
                    </span>
                  ) : integration.status.mode === "planned" ? (
                    <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                      Yakında
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full">
                      <AlertCircle size={12} /> Yapılandırılmamış
                    </span>
                  )}
                </div>
                
                <p className="text-sm text-gray-600 mb-3">{integration.description}</p>

                {/* Mode Badge */}
                {integration.status.mode && integration.status.mode !== "planned" && (
                  <div className="mb-3">
                    <span className={`text-xs px-2 py-1 rounded ${
                      integration.status.mode === "live" 
                        ? "bg-green-100 text-green-700" 
                        : "bg-yellow-100 text-yellow-700"
                    }`}>
                      {integration.status.mode === "live" ? "🟢 Canlı Mod" : "🟡 Test Modu (Sandbox)"}
                    </span>
                  </div>
                )}

                {/* Instructions */}
                <div className="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-3">
                  {integration.instructions}
                </div>

                {/* Env Keys */}
                {integration.envKeys.length > 0 && (
                  <div className="text-xs space-y-1 mb-3">
                    <p className="font-medium text-gray-700">Gerekli Çevre Değişkenleri:</p>
                    <div className="flex flex-wrap gap-1">
                      {integration.envKeys.map(key => (
                        <code key={key} className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">
                          {key}
                        </code>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actions */}
                {integration.actions && (
                  <div className="flex flex-wrap gap-2 mt-4 pt-3 border-t">
                    {integration.actions.map((action, idx) => (
                      <button
                        key={idx}
                        onClick={action.onClick}
                        disabled={action.loading || action.disabled}
                        className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                           integration.id === 'trendyol' && action.label.includes('Ayarlar') 
                            ? 'bg-gray-100 text-gray-800 hover:bg-gray-200 border border-gray-300'
                            : 'bg-black text-white hover:bg-gray-800'
                        }`}
                      >
                        {action.loading ? (
                          <RefreshCw size={14} className="animate-spin" />
                        ) : (
                          action.icon
                        )}
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Removed duplicate "Ayarlanmamış" actions code since it handles disabled dynamically */}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Ticimax Integration */}
      <div className="mt-6 bg-white rounded-lg border-2 border-indigo-200 p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-lg bg-indigo-100 text-indigo-600">
            <Database className="w-8 h-8" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold text-lg">Ticimax</h3>
              <span className="flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                <Check size={12} /> Aktif – facette.com.tr
              </span>
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">🟢 Canlı Mod</span>
            </div>
            <p className="text-sm text-gray-600 mb-2">Ticimax e-ticaret platformundan ürünler, kategoriler ve siparişleri içe aktar</p>
            {ticimaxStatus.last_sync && (
              <p className="text-xs text-gray-400 mb-2">Son senkronizasyon: {new Date(ticimaxStatus.last_sync).toLocaleString("tr-TR")}</p>
            )}
            <div className="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-4">
              API Key: <code className="font-mono bg-gray-100 px-1 rounded">HANXFWINXLDBY**</code> · Domain: <code className="font-mono bg-gray-100 px-1 rounded">www.facette.com.tr</code>
            </div>
            <div className="flex flex-wrap gap-3 pt-3 border-t">
              <button
                onClick={handleTicimaxImportCategories}
                disabled={ticimaxImportingCategories}
                className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                {ticimaxImportingCategories ? <RefreshCw size={14} className="animate-spin" /> : <Database size={14} />}
                {ticimaxImportingCategories ? "Kategoriler Yükleniyor..." : "Kategorileri Aktar"}
              </button>
              <button
                onClick={handleTicimaxImportProducts}
                disabled={ticimaxImportingProducts}
                className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-black text-white hover:bg-gray-800 disabled:opacity-50 transition-colors"
              >
                {ticimaxImportingProducts ? <RefreshCw size={14} className="animate-spin" /> : <Package size={14} />}
                {ticimaxImportingProducts ? "Ürünler Yükleniyor..." : "Ürünleri Aktar (500)"}
              </button>
              <button
                onClick={handleTicimaxImportOrders}
                disabled={ticimaxImportingOrders}
                className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-gray-700 text-white hover:bg-gray-600 disabled:opacity-50 transition-colors"
              >
                {ticimaxImportingOrders ? <RefreshCw size={14} className="animate-spin" /> : <ShoppingBag size={14} />}
                {ticimaxImportingOrders ? "Siparişler Yükleniyor..." : "Siparişleri Aktar (Son 20 Gün)"}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* XML Feed Import */}
      <div className="mt-6 bg-white rounded-lg border-2 border-emerald-200 p-6">
        <div className="flex items-start gap-4">
          <div className="p-3 rounded-lg bg-emerald-100 text-emerald-600">
            <Download className="w-8 h-8" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-semibold text-lg">XML Feed (Google Shopping)</h3>
              <span className="flex items-center gap-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                <Check size={12} /> Aktif
              </span>
              <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">🟢 Canlı</span>
            </div>
            <p className="text-sm text-gray-600 mb-2">
              Facette XML export feed'inden tüm ürünleri tek tıkla içe aktar
            </p>
            {xmlLastSync && (
              <p className="text-xs text-gray-400 mb-2">Son senkronizasyon: {new Date(xmlLastSync).toLocaleString("tr-TR")}</p>
            )}
            <div className="text-xs text-gray-500 bg-gray-50 rounded p-2 mb-4 font-mono break-all">
              facette.com.tr/XMLExport/7BECCB0A782647BFAB843E68AD11E468
            </div>
            <div className="flex flex-wrap gap-3 pt-3 border-t">
              <button
                onClick={handleXmlImport}
                disabled={xmlImporting}
                className="flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              >
                {xmlImporting ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
                {xmlImporting ? "XML'den Çekiliyor..." : "XML'den Ürünleri Aktar"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <Dialog open={trendyolModalOpen} onOpenChange={setTrendyolModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Trendyol API Ayarları</DialogTitle>
          </DialogHeader>
          <form onSubmit={saveTrendyolSettings} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Satıcı ID (Supplier ID)</label>
              <input
                type="text"
                value={trendyolSettings.supplier_id}
                onChange={(e) => setTrendyolSettings({ ...trendyolSettings, supplier_id: e.target.value })}
                required
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">API Key</label>
              <input
                type="text"
                value={trendyolSettings.api_key}
                onChange={(e) => setTrendyolSettings({ ...trendyolSettings, api_key: e.target.value })}
                required
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">API Secret</label>
              <input
                type="password"
                value={trendyolSettings.api_secret}
                onChange={(e) => setTrendyolSettings({ ...trendyolSettings, api_secret: e.target.value })}
                placeholder={trendyolSettings.api_secret === "********" ? "********" : "Yeni API Secret"}
                className="w-full border px-3 py-2 rounded text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">Sadece güncellemek istediğinizde doldurun</p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Mod</label>
              <select 
                value={trendyolSettings.mode || "sandbox"} 
                onChange={e => setTrendyolSettings({...trendyolSettings, mode: e.target.value})}
                className="w-full border px-3 py-2 rounded text-sm bg-white"
              >
                <option value="sandbox">Test Modu (Sandbox)</option>
                <option value="live">Canlı Mod (Production)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Varsayılan Trendyol Fiyat Farkı (%)</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={trendyolSettings.default_markup}
                  onChange={(e) => setTrendyolSettings({ ...trendyolSettings, default_markup: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                  placeholder="Örn: 20"
                />
                <span className="text-sm font-medium text-gray-500">%</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">Trendyol'a aktarırken ürün fiyatlarının üzerine eklenecek varsayılan oran.</p>
            </div>
            <label className="flex items-center gap-2 mt-2">
              <input
                type="checkbox"
                checked={trendyolSettings.is_active}
                onChange={(e) => setTrendyolSettings({ ...trendyolSettings, is_active: e.target.checked })}
              />
              <span className="text-sm border-b pb-0.5">Entegrasyon Aktif</span>
            </label>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <button type="button" onClick={() => setTrendyolModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50">
                İptal
              </button>
              <button type="submit" disabled={savingSettings} className="px-4 py-2 bg-[#F27A1A] text-white rounded hover:bg-[#d96810] disabled:opacity-50">
                {savingSettings ? "Kaydediliyor..." : "Kaydet"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>

      {/* Help Section */}
      <div className="mt-8 bg-blue-50 border border-blue-200 rounded-lg p-6">
        <h3 className="font-semibold text-blue-900 mb-2">Entegrasyon Yapılandırması</h3>
        <div className="text-sm text-blue-800 space-y-2">
          <p>
            <strong>1.</strong> İlgili servisin kontrol panelinden API anahtarlarınızı alın.
          </p>
          <p>
            <strong>2.</strong> Sunucunuzdaki <code className="bg-blue-100 px-1 rounded">/app/backend/.env</code> dosyasına gerekli değişkenleri ekleyin.
          </p>
          <p>
            <strong>3.</strong> Backend servisini yeniden başlatın: <code className="bg-blue-100 px-1 rounded">sudo supervisorctl restart backend</code>
          </p>
          <p>
            <strong>4.</strong> Entegrasyon durumunu bu sayfadan kontrol edin.
          </p>
        </div>
      </div>

      {/* Integration Logs Modal */}
      <Dialog open={logsModalOpen} onOpenChange={setLogsModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText size={20} /> Entegrasyon Logları
            </DialogTitle>
          </DialogHeader>
          
          <div className="flex flex-col gap-4 overflow-hidden h-full mt-4">
            {/* Filters */}
            <div className="flex gap-4 p-4 border rounded-lg bg-gray-50">
              <div className="flex flex-col gap-1 w-1/3">
                <label className="text-xs font-medium text-gray-600">Platform</label>
                <select 
                  className="border rounded px-3 py-1.5 text-sm"
                  value={logFilters.platform}
                  onChange={(e) => setLogFilters({...logFilters, platform: e.target.value})}
                >
                  <option value="">Tümü</option>
                  <option value="trendyol">Trendyol</option>
                  <option value="ticimax">Ticimax</option>
                </select>
              </div>
              <div className="flex flex-col gap-1 w-1/3">
                <label className="text-xs font-medium text-gray-600">Durum</label>
                <select 
                  className="border rounded px-3 py-1.5 text-sm"
                  value={logFilters.status}
                  onChange={(e) => setLogFilters({...logFilters, status: e.target.value})}
                >
                  <option value="">Tümü</option>
                  <option value="success">Başarılı</option>
                  <option value="error">Hatalı</option>
                  <option value="warning">Uyarı</option>
                </select>
              </div>
              <div className="flex items-end flex-1">
                 <button onClick={fetchLogs} className="flex items-center gap-1 bg-black text-white px-4 py-1.5 rounded text-sm hover:bg-gray-800">
                    <RefreshCw size={14} className={logsLoading ? "animate-spin" : ""} /> Yenile
                 </button>
              </div>
            </div>

            {/* List */}
            <div className="flex-1 overflow-auto border rounded-lg bg-white relative">
               <table className="w-full text-sm text-left">
                  <thead className="bg-gray-50 sticky top-0 z-10 border-b">
                     <tr>
                        <th className="py-2 px-4 whitespace-nowrap">Tarih</th>
                        <th className="py-2 px-4">Platform</th>
                        <th className="py-2 px-4">Olay/Bölüm</th>
                        <th className="py-2 px-4">Referans</th>
                        <th className="py-2 px-4">Durum</th>
                        <th className="py-2 px-4 w-1/3">Detay</th>
                     </tr>
                  </thead>
                  <tbody>
                     {logsLoading && integrationLogs.length === 0 ? (
                        <tr><td colSpan={6} className="text-center py-8 text-gray-500">Yükleniyor...</td></tr>
                     ) : integrationLogs.length === 0 ? (
                        <tr><td colSpan={6} className="text-center py-8 text-gray-500">Log kaydı bulunamadı.</td></tr>
                     ) : (
                        integrationLogs.map(log => (
                           <tr key={log._id || Math.random()} className="border-b hover:bg-gray-50">
                              <td className="py-2 px-4 whitespace-nowrap text-xs text-gray-500">
                                 {new Date(log.created_at).toLocaleString('tr-TR')}
                              </td>
                              <td className="py-2 px-4 font-medium uppercase text-xs">{log.platform}</td>
                              <td className="py-2 px-4">{log.event_type}</td>
                              <td className="py-2 px-4 font-mono text-xs">{log.reference_id}</td>
                              <td className="py-2 px-4">
                                 <span className={`px-2 py-0.5 rounded text-xs ${
                                    log.status === 'error' ? 'bg-red-100 text-red-700' : 
                                    log.status === 'warning' ? 'bg-yellow-100 text-yellow-700' : 
                                    'bg-green-100 text-green-700'
                                 }`}>
                                    {log.status === 'error' ? 'Hata' : log.status === 'warning' ? 'Uyarı' : 'Başarılı'}
                                 </span>
                              </td>
                              <td className="py-2 px-4 text-xs text-gray-600 max-w-xs truncate" title={log.message}>
                                 {log.message}
                              </td>
                           </tr>
                        ))
                     )}
                  </tbody>
               </table>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
