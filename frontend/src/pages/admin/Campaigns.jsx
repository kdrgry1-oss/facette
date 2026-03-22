import { useState, useEffect } from "react";
import { Plus, Edit, Trash2 } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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

  return (
    <div data-testid="admin-campaigns">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Kampanyalar</h1>
        <button 
          onClick={() => { resetForm(); setModalOpen(true); }}
          className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded hover:bg-gray-800"
        >
          <Plus size={18} />
          Yeni Kampanya
        </button>
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
