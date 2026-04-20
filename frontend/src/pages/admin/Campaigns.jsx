import { useState, useEffect } from "react";
import { Plus, Edit, Trash2, Percent, Gift, Truck, Tag, ShoppingBag, Users, Clock, Sparkles } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Hazır kampanya şablonları - "kutucuklu modeller halinde"
const CAMPAIGN_TEMPLATES = [
  {
    id: "percent-10",
    name: "%10 İndirim",
    icon: Percent,
    color: "bg-rose-500",
    description: "Sepette %10 iskonto uygulayan klasik kampanya.",
    payload: { type: "percentage", value: 10, min_order_amount: 0, code: "INDIRIM10", usage_limit: 0 },
  },
  {
    id: "percent-20-500",
    name: "500₺+ Sepette %20",
    icon: Percent,
    color: "bg-orange-500",
    description: "500₺ üzeri alışverişlere %20 indirim.",
    payload: { type: "percentage", value: 20, min_order_amount: 500, code: "BUYUK20", usage_limit: 0 },
  },
  {
    id: "free-shipping",
    name: "Ücretsiz Kargo",
    icon: Truck,
    color: "bg-emerald-500",
    description: "Tüm siparişlerde ücretsiz kargo.",
    payload: { type: "free_shipping", value: 0, min_order_amount: 0, code: "KARGO0", usage_limit: 0 },
  },
  {
    id: "free-shipping-300",
    name: "300₺+ Ücretsiz Kargo",
    icon: Truck,
    color: "bg-teal-500",
    description: "Minimum 300₺ alışverişlerde ücretsiz teslimat.",
    payload: { type: "free_shipping", value: 0, min_order_amount: 300, code: "UCRETSIZKARGO", usage_limit: 0 },
  },
  {
    id: "fixed-50",
    name: "50₺ İndirim Çeki",
    icon: Tag,
    color: "bg-sky-500",
    description: "Her siparişte sabit 50₺ düşüm.",
    payload: { type: "fixed", value: 50, min_order_amount: 150, code: "CEK50", usage_limit: 0 },
  },
  {
    id: "welcome-15",
    name: "Hoşgeldin İndirimi",
    icon: Gift,
    color: "bg-pink-500",
    description: "İlk alışverişe özel %15 indirim, tek kullanımlık.",
    payload: { type: "percentage", value: 15, min_order_amount: 0, code: "HOSGELDIN15", usage_limit: 1 },
  },
  {
    id: "buy2-save-25",
    name: "2 Al %25 İndirim",
    icon: ShoppingBag,
    color: "bg-amber-500",
    description: "En az 2 ürün alana %25 toplu indirim.",
    payload: { type: "percentage", value: 25, min_order_amount: 0, code: "IKI25", usage_limit: 0 },
  },
  {
    id: "vip-30",
    name: "VIP Müşteri %30",
    icon: Users,
    color: "bg-violet-500",
    description: "VIP segment için %30 özel kampanya.",
    payload: { type: "percentage", value: 30, min_order_amount: 0, code: "VIP30", usage_limit: 100 },
  },
  {
    id: "flash-sale",
    name: "Flaş Satış %40",
    icon: Clock,
    color: "bg-red-600",
    description: "24 saatlik kısa süreli büyük indirim.",
    payload: { type: "percentage", value: 40, min_order_amount: 0, code: "FLAS40", usage_limit: 500 },
  },
  {
    id: "cart-abandon-12",
    name: "Sepet Hatırlatma %12",
    icon: Sparkles,
    color: "bg-fuchsia-500",
    description: "Sepetini terk eden müşteriye özel %12.",
    payload: { type: "percentage", value: 12, min_order_amount: 0, code: "GERI12", usage_limit: 1 },
  },
];

export default function AdminCampaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    type: "percentage",
    value: 0,
    min_order_amount: 0,
    code: "",
    start_date: new Date().toISOString().split('T')[0],
    end_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
    is_active: true,
    usage_limit: 0,
  });

  useEffect(() => {
    fetchCampaigns();
  }, []);

  const fetchCampaigns = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/campaigns`);
      setCampaigns(res.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const data = {
        ...formData,
        start_date: new Date(formData.start_date).toISOString(),
        end_date: new Date(formData.end_date).toISOString(),
      };
      await axios.post(`${API}/campaigns`, data);
      toast.success("Kampanya oluşturuldu");
      setModalOpen(false);
      resetForm();
      fetchCampaigns();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Hata oluştu");
    }
  };

  const resetForm = () => {
    setFormData({
      name: "", type: "percentage", value: 0, min_order_amount: 0, code: "",
      start_date: new Date().toISOString().split('T')[0],
      end_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      is_active: true, usage_limit: 0
    });
  };

  const getTypeLabel = (type) => {
    const types = {
      percentage: "Yüzde İndirim",
      fixed: "Sabit İndirim",
      free_shipping: "Ücretsiz Kargo",
    };
    return types[type] || type;
  };

  const applyTemplate = (tmpl) => {
    setFormData({
      name: tmpl.name,
      type: tmpl.payload.type,
      value: tmpl.payload.value,
      min_order_amount: tmpl.payload.min_order_amount,
      code: tmpl.payload.code,
      start_date: new Date().toISOString().split('T')[0],
      end_date: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
      is_active: true,
      usage_limit: tmpl.payload.usage_limit || 0,
    });
    setModalOpen(true);
    toast.success(`"${tmpl.name}" şablonu yüklendi. Kontrol edip kaydedin.`);
  };

  return (
    <div data-testid="admin-campaigns">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Kampanyalar</h1>
        <button
          onClick={() => { resetForm(); setModalOpen(true); }}
          data-testid="new-campaign-btn"
          className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
        >
          <Plus size={18} />
          Yeni Kampanya
        </button>
      </div>

      {/* Campaign Templates Gallery */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-3">
          <Sparkles size={18} className="text-amber-500" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-gray-700">Hazır Kampanya Şablonları</h2>
          <span className="text-xs text-gray-400">— kutucuğa tıklayın, formu otomatik doldursun</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3" data-testid="campaign-templates">
          {CAMPAIGN_TEMPLATES.map(tmpl => {
            const Icon = tmpl.icon;
            return (
              <button
                key={tmpl.id}
                onClick={() => applyTemplate(tmpl)}
                data-testid={`campaign-tmpl-${tmpl.id}`}
                className="text-left bg-white border rounded-xl p-4 hover:shadow-lg hover:-translate-y-0.5 transition-all group"
              >
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-white mb-3 ${tmpl.color} group-hover:scale-110 transition-transform`}>
                  <Icon size={18} />
                </div>
                <p className="font-bold text-sm text-gray-900 mb-1">{tmpl.name}</p>
                <p className="text-[11px] text-gray-500 leading-relaxed line-clamp-3">{tmpl.description}</p>
                <div className="mt-2 flex items-center gap-1 text-[10px] text-gray-400">
                  <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">{tmpl.payload.code}</code>
                  {tmpl.payload.min_order_amount > 0 && (
                    <span>· min {tmpl.payload.min_order_amount}₺</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="bg-white rounded-lg shadow-sm overflow-hidden">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Kampanya Adı</th>
              <th>Tür</th>
              <th>Değer</th>
              <th>Kupon Kodu</th>
              <th>Min. Tutar</th>
              <th>Tarih Aralığı</th>
              <th>Durum</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="text-center py-8">Yükleniyor...</td>
              </tr>
            ) : campaigns.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-gray-500">Kampanya bulunamadı</td>
              </tr>
            ) : (
              campaigns.map((campaign) => (
                <tr key={campaign.id}>
                  <td className="font-medium">{campaign.name}</td>
                  <td>{getTypeLabel(campaign.type)}</td>
                  <td>
                    {campaign.type === "percentage" ? `%${campaign.value}` : 
                     campaign.type === "fixed" ? `${campaign.value} TL` : "-"}
                  </td>
                  <td><code className="bg-gray-100 px-2 py-1 text-sm">{campaign.code || "-"}</code></td>
                  <td>{campaign.min_order_amount} TL</td>
                  <td className="text-sm">
                    {new Date(campaign.start_date).toLocaleDateString('tr-TR')} - 
                    {new Date(campaign.end_date).toLocaleDateString('tr-TR')}
                  </td>
                  <td>
                    <span className={`px-2 py-1 text-xs rounded ${campaign.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                      {campaign.is_active ? "Aktif" : "Pasif"}
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Yeni Kampanya</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-1">Kampanya Adı *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                className="w-full border px-3 py-2 rounded text-sm"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Tür</label>
                <select
                  value={formData.type}
                  onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                >
                  <option value="percentage">Yüzde İndirim</option>
                  <option value="fixed">Sabit İndirim (TL)</option>
                  <option value="free_shipping">Ücretsiz Kargo</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Değer</label>
                <input
                  type="number"
                  value={formData.value}
                  onChange={(e) => setFormData({ ...formData, value: parseFloat(e.target.value) })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Kupon Kodu</label>
                <input
                  type="text"
                  value={formData.code}
                  onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                  placeholder="INDIRIM10"
                  className="w-full border px-3 py-2 rounded text-sm uppercase"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Min. Sipariş Tutarı</label>
                <input
                  type="number"
                  value={formData.min_order_amount}
                  onChange={(e) => setFormData({ ...formData, min_order_amount: parseFloat(e.target.value) })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium mb-1">Başlangıç Tarihi</label>
                <input
                  type="date"
                  value={formData.start_date}
                  onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Bitiş Tarihi</label>
                <input
                  type="date"
                  value={formData.end_date}
                  onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm"
                />
              </div>
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              />
              <span className="text-sm">Aktif</span>
            </label>
            <div className="flex justify-end gap-2 pt-4 border-t">
              <button type="button" onClick={() => setModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50">
                İptal
              </button>
              <button type="submit" className="px-4 py-2 bg-black text-white rounded hover:bg-gray-800">
                Oluştur
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
