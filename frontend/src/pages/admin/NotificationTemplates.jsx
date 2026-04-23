/**
 * =============================================================================
 * NotificationTemplates.jsx — Event × Kanal şablon editörü
 * =============================================================================
 *   GET /api/notifications/templates   → {templates: [...]}
 *   POST /api/notifications/templates  → upsert tek template
 *   POST /api/notifications/templates/seed → default'ları oluştur
 *
 * Değişken etiketleri: {customer_name} {order_number} {amount}
 *   {tracking_number} {otp_code} {cart_url}
 * =============================================================================
 */
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Save, RefreshCw, Mail, MessageSquare, Phone } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const CHANNEL_META = {
  sms: { label: "SMS", icon: Phone, color: "text-blue-600" },
  email: { label: "E-posta", icon: Mail, color: "text-purple-600" },
  whatsapp: { label: "WhatsApp", icon: MessageSquare, color: "text-green-600" },
};

const VARIABLES = [
  "{customer_name}", "{order_number}", "{amount}", "{tracking_number}",
  "{otp_code}", "{cart_url}", "{status_label}",
];

export default function NotificationTemplates() {
  const [catalog, setCatalog] = useState({ events: [], channels: [] });
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(null); // "event|channel"

  const token = localStorage.getItem("token");
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const load = async () => {
    setLoading(true);
    const [cat, tpl] = await Promise.all([
      axios.get(`${API}/notifications/providers/catalog`, auth),
      axios.get(`${API}/notifications/templates`, auth),
    ]);
    setCatalog(cat.data);
    setTemplates(tpl.data?.templates || []);
    setLoading(false);
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const map = useMemo(() => {
    const m = {};
    for (const t of templates) m[`${t.event}|${t.channel}`] = t;
    return m;
  }, [templates]);

  const update = (event, channel, patch) => {
    setTemplates(ts => {
      const key = `${event}|${channel}`;
      const existing = ts.find(t => t.event === event && t.channel === channel);
      if (existing) return ts.map(t => (t.event === event && t.channel === channel) ? { ...t, ...patch } : t);
      return [...ts, { event, channel, enabled: true, subject: "", body: "", ...patch }];
    });
  };

  const save = async (event, channel) => {
    const t = map[`${event}|${channel}`] || { event, channel, enabled: true, subject: "", body: "" };
    setSaving(`${event}|${channel}`);
    try {
      await axios.post(`${API}/notifications/templates`, t, auth);
      toast.success(`Kaydedildi: ${event} / ${channel}`);
    } catch (e) {
      toast.error("Hata: " + (e?.response?.data?.detail || e.message));
    } finally { setSaving(null); }
  };

  const seed = async () => {
    try {
      const r = await axios.post(`${API}/notifications/templates/seed`, {}, auth);
      toast.success(`${r.data.created} varsayılan şablon oluşturuldu`);
      await load();
    } catch (e) { toast.error("Seed hatası"); }
  };

  if (loading) return <div className="p-6 text-gray-500">Yükleniyor...</div>;

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-6" data-testid="notification-templates-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Bildirim Şablonları</h1>
          <p className="text-sm text-gray-500 mt-1">Her event × kanal için metni özelleştirin.</p>
        </div>
        <button onClick={seed} className="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 px-3 py-2 rounded text-sm">
          <RefreshCw size={14} /> Default Şablonları Oluştur
        </button>
      </div>

      <div className="text-xs text-gray-600 bg-amber-50 border border-amber-200 rounded p-3">
        <b>Kullanılabilir değişkenler:</b> {VARIABLES.join(" ")}
      </div>

      <div className="space-y-3">
        {catalog.events.map(ev => (
          <div key={ev.key} className="bg-white border border-gray-200 rounded-lg">
            <div className="bg-gray-50 px-4 py-3 border-b font-semibold">{ev.name} <span className="text-xs text-gray-500">({ev.key})</span></div>
            <div className="grid grid-cols-1 lg:grid-cols-3 divide-x divide-gray-100">
              {["sms", "email", "whatsapp"].map(ch => {
                const meta = CHANNEL_META[ch];
                const Ico = meta.icon;
                const t = map[`${ev.key}|${ch}`] || { enabled: false, subject: "", body: "" };
                return (
                  <div key={ch} className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Ico size={16} className={meta.color} />
                        <span className="font-medium text-sm">{meta.label}</span>
                      </div>
                      <label className="flex items-center gap-1 text-xs cursor-pointer">
                        <input type="checkbox" checked={!!t.enabled}
                          onChange={(e) => update(ev.key, ch, { enabled: e.target.checked })}
                          data-testid={`tpl-enable-${ev.key}-${ch}`} />
                        Aktif
                      </label>
                    </div>
                    {ch === "email" && (
                      <input value={t.subject || ""} onChange={(e) => update(ev.key, ch, { subject: e.target.value })}
                        placeholder="Konu"
                        className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs"
                        data-testid={`tpl-subject-${ev.key}`} />
                    )}
                    <textarea value={t.body || ""} onChange={(e) => update(ev.key, ch, { body: e.target.value })}
                      rows={4} placeholder={`${meta.label} mesajı (değişken kullanabilirsiniz)`}
                      className="w-full border border-gray-200 rounded px-2 py-1.5 text-xs font-mono"
                      data-testid={`tpl-body-${ev.key}-${ch}`} />
                    <button onClick={() => save(ev.key, ch)} disabled={saving === `${ev.key}|${ch}`}
                      className="w-full bg-black text-white py-1.5 rounded text-xs disabled:opacity-60 inline-flex items-center justify-center gap-1"
                      data-testid={`tpl-save-${ev.key}-${ch}`}>
                      <Save size={12} /> {saving === `${ev.key}|${ch}` ? "..." : "Kaydet"}
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
