import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Factory, Plus, ChevronRight, Save, Trash2, Edit, X, Package,
  FileText, Calendar, DollarSign, Users, Clock, CheckCircle2,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const STAGE_COLORS = {
  anlasma: "bg-slate-100 text-slate-700",
  numune_hazirlaniyor: "bg-amber-100 text-amber-700",
  numune_onaylandi: "bg-green-100 text-green-700",
  kumas_siparisi: "bg-blue-100 text-blue-700",
  kumas_teslim: "bg-indigo-100 text-indigo-700",
  aksesuar: "bg-cyan-100 text-cyan-700",
  kesim: "bg-orange-100 text-orange-700",
  dikim: "bg-rose-100 text-rose-700",
  utu_paketleme: "bg-pink-100 text-pink-700",
  kalite_kontrol: "bg-purple-100 text-purple-700",
  teslim_alindi: "bg-emerald-100 text-emerald-700",
  fatura_kesildi: "bg-gray-800 text-white",
};

export default function Manufacturing() {
  const [items, setItems] = useState([]);
  const [stages, setStages] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [stageFilter, setStageFilter] = useState("");
  const [search, setSearch] = useState("");

  const [editing, setEditing] = useState(null);  // null | record
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);

  const [form, setForm] = useState(initialForm());

  function initialForm() {
    return {
      product_name: "",
      partner_name: "FACETTE İç Stok",
      partner_contact: "",
      responsible_user: "",
      agreement_date: new Date().toISOString().substring(0, 10),
      expected_delivery_date: "",
      size_distribution: { S: 0, M: 0, L: 0, XL: 0 },
      unit_price: 0,
      agreed_total: 0,
      payments: [],
      cost_lines: [],
      waste_meters: 0,
      notes: "",
      current_stage: "anlasma",
    };
  }

  useEffect(() => { fetchAll(); }, [stageFilter]);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const hdr = { headers: { Authorization: `Bearer ${token}` } };
      let url = `${API}/manufacturing`;
      const params = [];
      if (stageFilter) params.push(`stage=${stageFilter}`);
      if (search) params.push(`search=${encodeURIComponent(search)}`);
      if (params.length) url += "?" + params.join("&");
      const [stagesRes, listRes] = await Promise.all([
        axios.get(`${API}/manufacturing/stages`, hdr),
        axios.get(url, hdr),
      ]);
      setStages(stagesRes.data.stages || []);
      setItems(listRes.data.items || []);
      setCounts(listRes.data.counts_by_stage || {});
    } catch (err) {
      toast.error("Veriler yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setForm(initialForm());
    setModalOpen(true);
  };

  const openEdit = (item) => {
    setEditing(item);
    setForm({
      product_name: item.product_name || "",
      partner_name: item.partner_name || "",
      partner_contact: item.partner_contact || "",
      responsible_user: item.responsible_user || "",
      agreement_date: (item.agreement_date || "").substring(0, 10),
      expected_delivery_date: (item.expected_delivery_date || "").substring(0, 10),
      size_distribution: item.size_distribution || {},
      unit_price: item.unit_price || 0,
      agreed_total: item.agreed_total || 0,
      payments: item.payments || [],
      cost_lines: item.cost_lines || [],
      waste_meters: item.waste_meters || 0,
      notes: item.notes || "",
      current_stage: item.current_stage || "anlasma",
    });
    setModalOpen(true);
  };

  const saveRecord = async (e) => {
    e?.preventDefault?.();
    if (!form.product_name.trim()) { toast.error("Ürün adı gerekli"); return; }
    setSaving(true);
    try {
      const token = localStorage.getItem("token");
      const hdr = { headers: { Authorization: `Bearer ${token}` } };
      const payload = { ...form };
      // Clean empty sizes
      payload.size_distribution = Object.fromEntries(
        Object.entries(payload.size_distribution || {}).filter(([, v]) => Number(v) > 0)
          .map(([k, v]) => [k, Number(v)])
      );
      payload.unit_price = Number(payload.unit_price || 0);
      payload.agreed_total = Number(payload.agreed_total || 0);
      payload.waste_meters = Number(payload.waste_meters || 0);
      if (editing) {
        await axios.put(`${API}/manufacturing/${editing.id}`, payload, hdr);
        toast.success("Kayıt güncellendi");
      } else {
        await axios.post(`${API}/manufacturing`, payload, hdr);
        toast.success("İmalat kaydı oluşturuldu");
      }
      setModalOpen(false);
      fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const advanceStage = async (item, newStage) => {
    const note = window.prompt(`"${stageLabel(newStage)}" aşamasına geçiyorsunuz. Not (opsiyonel):`);
    if (note === null) return;
    try {
      const token = localStorage.getItem("token");
      await axios.post(`${API}/manufacturing/${item.id}/advance`,
        { stage: newStage, note },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("Aşama güncellendi");
      if (newStage === "teslim_alindi") toast.success("Stok otomatik güncellendi");
      fetchAll();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Aşama değiştirilemedi");
    }
  };

  const deleteRecord = async (item) => {
    if (!window.confirm(`"${item.code}" kaydını silmek istiyor musunuz?`)) return;
    try {
      const token = localStorage.getItem("token");
      await axios.delete(`${API}/manufacturing/${item.id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success("Silindi");
      fetchAll();
    } catch (err) {
      toast.error("Silinemedi");
    }
  };

  const stageLabel = (key) => stages.find(s => s.key === key)?.label || key;
  const nextStage = (current) => {
    const idx = stages.findIndex(s => s.key === current);
    return idx >= 0 && idx < stages.length - 1 ? stages[idx + 1].key : null;
  };

  const updateSize = (size, val) => setForm(f => ({
    ...f,
    size_distribution: { ...f.size_distribution, [size]: val },
  }));

  const addCostLine = () => setForm(f => ({
    ...f,
    cost_lines: [...(f.cost_lines || []), { id: crypto.randomUUID(), label: "", amount: 0, note: "" }],
  }));
  const removeCostLine = (id) => setForm(f => ({ ...f, cost_lines: f.cost_lines.filter(c => c.id !== id) }));

  const addPayment = () => setForm(f => ({
    ...f,
    payments: [...(f.payments || []), { id: crypto.randomUUID(), date: new Date().toISOString().substring(0, 10), amount: 0, method: "Havale", note: "" }],
  }));
  const removePayment = (id) => setForm(f => ({ ...f, payments: f.payments.filter(p => p.id !== id) }));

  const totalCost = (form.cost_lines || []).reduce((sum, c) => sum + Number(c.amount || 0), 0);
  const totalPaid = (form.payments || []).reduce((sum, p) => sum + Number(p.amount || 0), 0);

  return (
    <div className="p-6 max-w-7xl mx-auto" data-testid="manufacturing-page">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Factory className="text-rose-600" /> İmalat Takip
          </h1>
          <p className="text-sm text-gray-500 mt-1">Üretim sürecinin anlaşmadan teslime kadar tüm aşamalarını takip edin.</p>
        </div>
        <button onClick={openCreate} data-testid="create-mfg-btn"
          className="flex items-center gap-2 px-4 py-2 bg-rose-600 text-white rounded-lg text-sm font-bold hover:bg-rose-700">
          <Plus size={16} /> Yeni İmalat Kaydı
        </button>
      </div>

      {/* Stage stats */}
      <div className="grid grid-cols-3 md:grid-cols-6 lg:grid-cols-7 gap-3 mb-6">
        <button
          onClick={() => setStageFilter("")}
          className={`bg-white p-3 rounded-lg shadow-sm hover:shadow-md text-left ${!stageFilter ? "ring-2 ring-black" : ""}`}
        >
          <p className="text-xl font-bold">{items.length}</p>
          <p className="text-xs text-gray-500">Tümü</p>
        </button>
        {stages.map(s => (
          <button
            key={s.key}
            onClick={() => setStageFilter(s.key)}
            data-testid={`stage-filter-${s.key}`}
            className={`bg-white p-3 rounded-lg shadow-sm hover:shadow-md text-left ${stageFilter === s.key ? "ring-2 ring-black" : ""}`}
          >
            <p className="text-xl font-bold">{counts[s.key] || 0}</p>
            <p className="text-xs text-gray-500 truncate">{s.label}</p>
          </button>
        ))}
      </div>

      {/* List */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-gray-500">Yükleniyor...</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-gray-500">Kayıt bulunamadı. Sağ üstten yeni kayıt ekleyebilirsiniz.</div>
        ) : (
          <table className="w-full">
            <thead className="border-b bg-gray-50">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Kod</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Ürün</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">İş Ortağı</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Adet</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Ödeme</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Aşama</th>
                <th className="text-left px-4 py-3 text-xs font-bold text-gray-500 uppercase">Tarih</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id} className="border-b hover:bg-gray-50" data-testid={`mfg-row-${item.code}`}>
                  <td className="px-4 py-3 font-mono text-xs text-rose-600 font-bold">{item.code}</td>
                  <td className="px-4 py-3">
                    <p className="font-medium">{item.product_name}</p>
                    <p className="text-[10px] text-gray-500">
                      {Object.entries(item.size_distribution || {}).map(([s, q]) => `${s}:${q}`).join(" · ")}
                    </p>
                  </td>
                  <td className="px-4 py-3 text-sm">{item.partner_name}</td>
                  <td className="px-4 py-3 text-sm font-bold">{item.total_units}</td>
                  <td className="px-4 py-3 text-xs">
                    <p><b>{(item.paid_total || 0).toFixed(2)}</b>₺ <span className="text-gray-400">/</span> {(item.agreed_total || 0).toFixed(2)}₺</p>
                    <p className={`text-[10px] ${item.remaining > 0 ? 'text-red-600' : 'text-green-600'}`}>
                      {item.remaining > 0 ? `Kalan: ${item.remaining.toFixed(2)}₺` : "Tamamlandı"}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase tracking-wider ${STAGE_COLORS[item.current_stage] || 'bg-gray-100'}`}>
                      {stageLabel(item.current_stage)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-gray-500">
                    {item.agreement_date ? new Date(item.agreement_date).toLocaleDateString('tr-TR') : '—'}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {nextStage(item.current_stage) && (
                      <button
                        onClick={() => advanceStage(item, nextStage(item.current_stage))}
                        data-testid={`advance-${item.id}`}
                        className="px-2 py-1 text-xs text-rose-600 hover:bg-rose-50 rounded font-medium"
                      >
                        <ChevronRight size={13} className="inline" /> İlerlet
                      </button>
                    )}
                    <button onClick={() => openEdit(item)} className="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded">
                      <Edit size={13} className="inline" />
                    </button>
                    <button onClick={() => deleteRecord(item)} className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded">
                      <Trash2 size={13} className="inline" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Create / Edit Modal */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="mfg-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Factory size={18} className="text-rose-600" />
              {editing ? `İmalat Kaydı: ${editing.code}` : "Yeni İmalat Kaydı"}
            </DialogTitle>
          </DialogHeader>
          <form onSubmit={saveRecord} className="space-y-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Ürün Adı / Model <span className="text-red-500">*</span></label>
                <input value={form.product_name} onChange={e => setForm({ ...form, product_name: e.target.value })} required
                  data-testid="mfg-product-name" className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">İş Ortağı / Atölye</label>
                <input value={form.partner_name} onChange={e => setForm({ ...form, partner_name: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">İletişim (Telefon/E-posta)</label>
                <input value={form.partner_contact} onChange={e => setForm({ ...form, partner_contact: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Sorumlu Kullanıcı</label>
                <input value={form.responsible_user} onChange={e => setForm({ ...form, responsible_user: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Anlaşma Tarihi</label>
                <input type="date" value={form.agreement_date} onChange={e => setForm({ ...form, agreement_date: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Tahmini Teslim Tarihi</label>
                <input type="date" value={form.expected_delivery_date} onChange={e => setForm({ ...form, expected_delivery_date: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
            </div>

            {/* Size distribution */}
            <div>
              <label className="block text-xs font-bold text-gray-600 mb-2 flex items-center gap-2">
                <Package size={12} /> Beden Dağılımı
              </label>
              <div className="grid grid-cols-3 md:grid-cols-6 gap-2 bg-rose-50 border border-rose-200 rounded-lg p-3">
                {["XS", "S", "M", "L", "XL", "XXL"].map(s => (
                  <div key={s}>
                    <label className="text-[10px] font-bold text-rose-700">{s}</label>
                    <input type="number" min={0} value={form.size_distribution?.[s] || 0}
                      onChange={e => updateSize(s, e.target.value)}
                      className="w-full border px-2 py-1 rounded text-sm" />
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Toplam: <b>{Object.values(form.size_distribution || {}).reduce((a, b) => Number(a) + Number(b), 0)}</b> adet
              </p>
            </div>

            {/* Finansal */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Birim Fiyat (₺)</label>
                <input type="number" step="0.01" value={form.unit_price}
                  onChange={e => setForm({ ...form, unit_price: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Toplam Anlaşma Bedeli (₺)</label>
                <input type="number" step="0.01" value={form.agreed_total}
                  onChange={e => setForm({ ...form, agreed_total: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-600 mb-1">Fire (metre)</label>
                <input type="number" step="0.1" value={form.waste_meters}
                  onChange={e => setForm({ ...form, waste_meters: e.target.value })}
                  className="w-full border px-3 py-2 rounded text-sm" />
              </div>
            </div>

            {/* Payments */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-bold text-gray-600 flex items-center gap-2">
                  <DollarSign size={12} /> Ödemeler ({totalPaid.toFixed(2)}₺)
                </label>
                <button type="button" onClick={addPayment} className="text-xs text-rose-600 hover:bg-rose-50 px-2 py-1 rounded">
                  <Plus size={12} className="inline" /> Ödeme Ekle
                </button>
              </div>
              {(form.payments || []).map((p, i) => (
                <div key={p.id || i} className="grid grid-cols-12 gap-2 mb-1">
                  <input type="date" value={p.date || ""} onChange={e => setForm(f => ({ ...f, payments: f.payments.map(x => x.id === p.id ? { ...x, date: e.target.value } : x) }))} className="col-span-3 border px-2 py-1 rounded text-xs" />
                  <input type="number" step="0.01" value={p.amount || 0} placeholder="Tutar" onChange={e => setForm(f => ({ ...f, payments: f.payments.map(x => x.id === p.id ? { ...x, amount: e.target.value } : x) }))} className="col-span-3 border px-2 py-1 rounded text-xs" />
                  <input value={p.method || ""} placeholder="Havale/Nakit/Kart" onChange={e => setForm(f => ({ ...f, payments: f.payments.map(x => x.id === p.id ? { ...x, method: e.target.value } : x) }))} className="col-span-2 border px-2 py-1 rounded text-xs" />
                  <input value={p.note || ""} placeholder="Not" onChange={e => setForm(f => ({ ...f, payments: f.payments.map(x => x.id === p.id ? { ...x, note: e.target.value } : x) }))} className="col-span-3 border px-2 py-1 rounded text-xs" />
                  <button type="button" onClick={() => removePayment(p.id)} className="col-span-1 text-red-500 hover:bg-red-50 rounded"><Trash2 size={13} className="mx-auto" /></button>
                </div>
              ))}
            </div>

            {/* Cost lines */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="text-xs font-bold text-gray-600 flex items-center gap-2">
                  <FileText size={12} /> Maliyet Kalemleri ({totalCost.toFixed(2)}₺)
                </label>
                <button type="button" onClick={addCostLine} className="text-xs text-rose-600 hover:bg-rose-50 px-2 py-1 rounded">
                  <Plus size={12} className="inline" /> Kalem Ekle
                </button>
              </div>
              {(form.cost_lines || []).map((c, i) => (
                <div key={c.id || i} className="grid grid-cols-12 gap-2 mb-1">
                  <input value={c.label || ""} placeholder="Kumaş / Aksesuar / Dikim..." onChange={e => setForm(f => ({ ...f, cost_lines: f.cost_lines.map(x => x.id === c.id ? { ...x, label: e.target.value } : x) }))} className="col-span-5 border px-2 py-1 rounded text-xs" />
                  <input type="number" step="0.01" value={c.amount || 0} placeholder="Tutar" onChange={e => setForm(f => ({ ...f, cost_lines: f.cost_lines.map(x => x.id === c.id ? { ...x, amount: e.target.value } : x) }))} className="col-span-3 border px-2 py-1 rounded text-xs" />
                  <input value={c.note || ""} placeholder="Not" onChange={e => setForm(f => ({ ...f, cost_lines: f.cost_lines.map(x => x.id === c.id ? { ...x, note: e.target.value } : x) }))} className="col-span-3 border px-2 py-1 rounded text-xs" />
                  <button type="button" onClick={() => removeCostLine(c.id)} className="col-span-1 text-red-500 hover:bg-red-50 rounded"><Trash2 size={13} className="mx-auto" /></button>
                </div>
              ))}
            </div>

            <div>
              <label className="block text-xs font-bold text-gray-600 mb-1">Notlar</label>
              <textarea rows={3} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })}
                className="w-full border px-3 py-2 rounded text-sm" />
            </div>

            {editing && (
              <div>
                <label className="text-xs font-bold text-gray-600 mb-1 block">Aşama Geçmişi</label>
                <div className="border rounded-lg bg-gray-50 p-3 max-h-40 overflow-y-auto">
                  {(editing.stage_history || []).map((h, i) => (
                    <div key={i} className="text-xs py-1 border-b last:border-0 flex justify-between">
                      <span className={`px-2 py-0.5 rounded ${STAGE_COLORS[h.stage] || 'bg-gray-100'}`}>{h.label}</span>
                      <span className="text-gray-500">
                        {h.by} · {new Date(h.at).toLocaleString('tr-TR')}
                        {h.note && <span className="ml-1">— {h.note}</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4 border-t">
              <button type="button" onClick={() => setModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50 text-sm">İptal</button>
              <button type="submit" disabled={saving} data-testid="save-mfg-btn"
                className="px-4 py-2 bg-rose-600 text-white rounded hover:bg-rose-700 disabled:opacity-50 text-sm font-bold">
                <Save size={14} className="inline mr-1" /> {saving ? "Kaydediliyor..." : "Kaydet"}
              </button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
