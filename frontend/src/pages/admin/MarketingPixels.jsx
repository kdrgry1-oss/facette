/**
 * =============================================================================
 * MarketingPixels.jsx — FAZ 9 Pazarlama Pixel Yönetimi
 * =============================================================================
 * GA4, Meta Pixel, Google Ads, TikTok, Yandex, Hotjar, Clarity, Özel HTML
 * Sadece tag_id yapıştır → template otomatik üretilir. Gelişmiş: özel snippet.
 * =============================================================================
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Plus, Trash2, Save, Code } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const PROVIDER_HINTS = {
  ga4: "ör. G-XXXXXXXXXX",
  meta: "ör. 1234567890123456",
  google_ads: "ör. AW-1234567890",
  tiktok: "ör. C1234567890",
  yandex: "ör. 12345678",
  hotjar: "ör. 3456789",
  clarity: "ör. ab1234cd",
  custom: "— gerek yok, aşağıya HTML yapıştır —",
};

export default function MarketingPixels() {
  const [providers, setProviders] = useState([]);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ provider: "ga4", name: "", tag_id: "", head_snippet: "", body_snippet: "", is_active: true });
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const token = localStorage.getItem("token");
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const load = async () => {
    const [p, l] = await Promise.all([
      axios.get(`${API}/marketing-pixels/providers`, auth),
      axios.get(`${API}/marketing-pixels`, auth),
    ]);
    setProviders(p.data?.providers || []);
    setItems(l.data?.items || []);
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...form };
      if (editing) payload.id = editing;
      await axios.post(`${API}/marketing-pixels`, payload, auth);
      toast.success("Pixel kaydedildi");
      setForm({ provider: "ga4", name: "", tag_id: "", head_snippet: "", body_snippet: "", is_active: true });
      setEditing(null);
      setShowAdvanced(false);
      await load();
    } catch (e) {
      toast.error("Kaydedilemedi: " + (e?.response?.data?.detail || e.message));
    } finally { setSaving(false); }
  };

  const edit = (px) => {
    setEditing(px.id);
    setForm({
      provider: px.provider, name: px.name, tag_id: px.tag_id || "",
      head_snippet: px.head_snippet || "", body_snippet: px.body_snippet || "",
      is_active: px.is_active,
    });
    setShowAdvanced(!!(px.head_snippet && !px.tag_id));
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const remove = async (id) => {
    if (!await window.appConfirm("Bu pixel'i silmek istediğinize emin misiniz?")) return;
    await axios.delete(`${API}/marketing-pixels/${id}`, auth);
    toast.success("Silindi");
    await load();
  };

  const toggle = async (px) => {
    await axios.post(`${API}/marketing-pixels`, { ...px, is_active: !px.is_active }, auth);
    await load();
  };

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6" data-testid="marketing-pixels-page">
      <div>
        <h1 className="text-2xl font-semibold flex items-center gap-2"><Code size={20} /> Pazarlama Pixel & Etiket Yönetimi</h1>
        <p className="text-sm text-gray-500 mt-1">
          Sadece tag ID'nizi yapıştırıp aktif edin — her sayfada otomatik çalışır.
        </p>
      </div>

      {/* Form */}
      <section className="bg-white rounded-lg border border-gray-200 p-5 space-y-3">
        <h2 className="font-semibold flex items-center gap-2">
          {editing ? "Pixel Güncelle" : <><Plus size={16} /> Yeni Pixel Ekle</>}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-gray-600 mb-1">Sağlayıcı</label>
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}
              className="w-full border px-3 py-2 text-sm rounded bg-white" data-testid="pixel-provider">
              {providers.map((p) => (<option key={p.key} value={p.key}>{p.name}</option>))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Etiket ID / Pixel ID</label>
            <input value={form.tag_id} onChange={(e) => setForm({ ...form, tag_id: e.target.value })}
              placeholder={PROVIDER_HINTS[form.provider] || ""}
              className="w-full border px-3 py-2 text-sm rounded" data-testid="pixel-tag-id" />
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Ad (etiket)</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="ör. Ana GA4"
              className="w-full border px-3 py-2 text-sm rounded" data-testid="pixel-name" />
          </div>
        </div>

        <div className="flex items-center justify-between pt-2">
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              data-testid="pixel-active-toggle" />
            Aktif
          </label>
          <button onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-blue-600 hover:underline" data-testid="pixel-advanced-toggle">
            {showAdvanced ? "Gelişmiş modu gizle" : "Gelişmiş (özel HTML/JS)"}
          </button>
        </div>

        {showAdvanced && (
          <div className="space-y-2">
            <label className="block text-xs text-gray-600">&lt;head&gt; içine eklenecek kod (script/meta/noscript)</label>
            <textarea rows={6} value={form.head_snippet}
              onChange={(e) => setForm({ ...form, head_snippet: e.target.value })}
              className="w-full border px-3 py-2 text-xs font-mono rounded"
              placeholder="<script>...</script>"
              data-testid="pixel-head-snippet" />
            <label className="block text-xs text-gray-600">&lt;body&gt; sonuna eklenecek kod (opsiyonel)</label>
            <textarea rows={3} value={form.body_snippet}
              onChange={(e) => setForm({ ...form, body_snippet: e.target.value })}
              className="w-full border px-3 py-2 text-xs font-mono rounded"
              data-testid="pixel-body-snippet" />
          </div>
        )}

        <div className="flex items-center gap-2 pt-2">
          <button onClick={save} disabled={saving}
            className="inline-flex items-center gap-1 bg-black text-white px-4 py-2 rounded text-sm disabled:opacity-60"
            data-testid="pixel-save-btn">
            <Save size={14} /> {saving ? "Kaydediliyor..." : editing ? "Güncelle" : "Ekle"}
          </button>
          {editing && (
            <button onClick={() => { setEditing(null); setForm({ provider: "ga4", name: "", tag_id: "", head_snippet: "", body_snippet: "", is_active: true }); setShowAdvanced(false); }}
              className="text-sm text-gray-500 hover:text-black">İptal</button>
          )}
        </div>
      </section>

      {/* Liste */}
      <section className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        <div className="bg-gray-50 px-4 py-2 text-xs uppercase font-semibold">Eklenmiş Pixel'ler ({items.length})</div>
        {items.length === 0 ? (
          <div className="p-6 text-sm text-gray-500">Henüz pixel eklenmedi.</div>
        ) : (
          <ul className="divide-y">
            {items.map((px) => (
              <li key={px.id} className="p-4 flex items-start justify-between gap-3 hover:bg-gray-50">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-sm">{px.name}</span>
                    <span className="text-[10px] uppercase bg-gray-100 px-1.5 py-0.5 rounded">{px.provider}</span>
                    {px.is_active ? (
                      <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded">Aktif</span>
                    ) : (
                      <span className="text-[10px] bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">Pasif</span>
                    )}
                  </div>
                  {px.tag_id && <div className="text-xs text-gray-500 font-mono mt-1">{px.tag_id}</div>}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <button onClick={() => toggle(px)}
                    className="text-xs px-2 py-1 rounded border hover:bg-gray-100"
                    data-testid={`pixel-toggle-${px.id}`}>
                    {px.is_active ? "Pasifleştir" : "Aktif Et"}
                  </button>
                  <button onClick={() => edit(px)}
                    className="text-xs px-2 py-1 rounded border hover:bg-blue-50"
                    data-testid={`pixel-edit-${px.id}`}>
                    Düzenle
                  </button>
                  <button onClick={() => remove(px.id)}
                    className="text-red-600 hover:bg-red-50 p-1.5 rounded"
                    data-testid={`pixel-delete-${px.id}`}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
