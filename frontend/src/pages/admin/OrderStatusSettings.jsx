import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Save, MessageSquare, Mail, Eye } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function Toggle({ checked, onChange, color }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${checked ? "" : "bg-gray-200"}`}
      style={checked ? { backgroundColor: color || "#111" } : undefined}
    >
      <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${checked ? "translate-x-4" : "translate-x-0.5"}`} />
    </button>
  );
}

export default function OrderStatusSettings() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const res = await axios.get(`${API}/settings/order-statuses`, auth());
      setRows(res.data?.statuses || []);
    } catch (e) {
      toast.error("Durum ayarları yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const patch = (key, field, val) =>
    setRows((rs) => rs.map((r) => (r.key === key ? { ...r, [field]: val } : r)));

  const save = async () => {
    try {
      setSaving(true);
      const active = rows.filter((r) => r.active).map((r) => r.key);
      const notify = {};
      rows.forEach((r) => { notify[r.key] = { sms: !!r.sms, email: !!r.email }; });
      await axios.post(`${API}/settings/order-statuses`, { active, notify }, auth());
      toast.success("Sipariş durumu ayarları kaydedildi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  // grup sırası
  const order = ["Başlangıç", "Hazırlık", "Kargo", "İade", "Son"];
  const groups = order
    .map((g) => ({ name: g, items: rows.filter((r) => r.group === g) }))
    .filter((g) => g.items.length);

  return (
    <div data-testid="order-status-settings" className="max-w-4xl">
      <div className="flex items-start justify-between mb-6 gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sipariş Durumları</h1>
          <p className="text-sm text-gray-500 mt-1">
            Hangi durumlar sistemde kullanılsın ve hangi durumda müşteriye <b>SMS</b> / <b>e-posta</b> gitsin seç.
          </p>
        </div>
        <button onClick={save} disabled={saving}
          data-testid="save-statuses"
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-semibold hover:bg-gray-800 disabled:opacity-50 shrink-0">
          <Save size={16} /> {saving ? "Kaydediliyor..." : "Kaydet"}
        </button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-gray-400">Yükleniyor...</div>
      ) : (
        <div className="space-y-6">
          {groups.map((g) => (
            <div key={g.name}>
              <h2 className="text-xs font-bold text-gray-400 uppercase tracking-wide mb-2">{g.name}</h2>
              <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
                <div className="hidden sm:grid grid-cols-[1fr_auto_auto_auto] gap-4 px-4 py-2 bg-gray-50 text-[11px] font-bold text-gray-400 uppercase">
                  <span>Durum</span>
                  <span className="inline-flex items-center gap-1 justify-center w-20"><Eye size={12} /> Görünür</span>
                  <span className="inline-flex items-center gap-1 justify-center w-16"><MessageSquare size={12} /> SMS</span>
                  <span className="inline-flex items-center gap-1 justify-center w-16"><Mail size={12} /> Mail</span>
                </div>
                <div className="divide-y">
                  {g.items.map((r) => (
                    <div key={r.key} className="grid grid-cols-[1fr_auto_auto_auto] gap-4 px-4 py-3 items-center">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: r.color }} />
                          <span className="font-semibold text-gray-900 text-sm truncate">{r.label}</span>
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5 truncate">Müşteriye: “{r.customer_label}”</div>
                      </div>
                      <div className="w-20 flex justify-center"><Toggle checked={r.active} color={r.color} onChange={(v) => patch(r.key, "active", v)} /></div>
                      <div className="w-16 flex justify-center"><Toggle checked={r.sms} color={r.color} onChange={(v) => patch(r.key, "sms", v)} /></div>
                      <div className="w-16 flex justify-center"><Toggle checked={r.email} color={r.color} onChange={(v) => patch(r.key, "email", v)} /></div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="text-[11px] text-gray-400 mt-4">
        Mesaj içeriklerini <b>Ayarlar → Bildirim Şablonları</b>'ndan düzenleyebilirsin. “Görünür” kapalı durumlar sipariş ekranındaki durum listesinde gösterilmez.
      </p>
    </div>
  );
}
