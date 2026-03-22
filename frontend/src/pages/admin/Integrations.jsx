import { useState, useEffect } from "react";
import { Store, CreditCard, Truck, MessageSquare, FileText, RefreshCw, Check, X, AlertCircle, Upload, Download, Package } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";

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
    gib: { configured: false, mode: "test" }
  });
  const [trendyolOrders, setTrendyolOrders] = useState([]);

  useEffect(() => {
    fetchStatuses();
  }, []);

  const fetchStatuses = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const headers = { Authorization: `Bearer ${token}` };

      // Fetch integration statuses
      const [paymentRes, trendyolRes, gibRes] = await Promise.all([
        axios.get(`${API}/payment/status`, { headers }).catch(() => ({ data: { configured: false, mode: "sandbox" } })),
        axios.get(`${API}/trendyol/status`, { headers }).catch(() => ({ data: { configured: false, mode: "sandbox" } })),
        axios.get(`${API}/gib/status`, { headers }).catch(() => ({ data: { configured: false, mode: "test" } }))
      ]);

      setStatuses(prev => ({
        ...prev,
        iyzico: paymentRes.data,
        trendyol: trendyolRes.data,
        gib: gibRes.data
      }));
    } catch (err) {
      console.error("Status fetch error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleTrendyolSync = async () => {
    setSyncing(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/trendyol/products/sync`, null, {
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

  const handleTrendyolImport = async () => {
    setImporting(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`${API}/trendyol/orders/import`, null, {
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
      instructions: "Trendyol Partner Panel > Entegrasyon Bilgileri'nden API bilgilerini alınız.",
      envKeys: ["TRENDYOL_API_KEY", "TRENDYOL_API_SECRET", "TRENDYOL_SUPPLIER_ID"],
      actions: [
        { label: "Ürünleri Gönder", icon: <Upload size={16} />, onClick: handleTrendyolSync, loading: syncing },
        { label: "Siparişleri Al", icon: <Download size={16} />, onClick: handleTrendyolImport, loading: importing }
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
        <button 
          onClick={fetchStatuses}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 border rounded hover:bg-gray-50"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Durumu Güncelle
        </button>
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
                {integration.actions && integration.status.configured && (
                  <div className="flex gap-2 mt-4 pt-3 border-t">
                    {integration.actions.map((action, idx) => (
                      <button
                        key={idx}
                        onClick={action.onClick}
                        disabled={action.loading}
                        className="flex items-center gap-2 px-3 py-1.5 bg-black text-white text-sm rounded hover:bg-gray-800 disabled:opacity-50"
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

                {/* Actions for unconfigured Trendyol */}
                {integration.id === "trendyol" && !integration.status.configured && (
                  <div className="flex gap-2 mt-4 pt-3 border-t">
                    <button
                      disabled
                      className="flex items-center gap-2 px-3 py-1.5 bg-gray-200 text-gray-500 text-sm rounded cursor-not-allowed"
                    >
                      <Upload size={14} />
                      Ürünleri Gönder
                    </button>
                    <button
                      disabled
                      className="flex items-center gap-2 px-3 py-1.5 bg-gray-200 text-gray-500 text-sm rounded cursor-not-allowed"
                    >
                      <Download size={14} />
                      Siparişleri Al
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

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
    </div>
  );
}
