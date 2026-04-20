import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Store, Key, Save, PlugZap, AlertCircle, CheckCircle2, RefreshCw, Link2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

/**
 * Hepsiburada Kategori & Ürün Eşleştirme sayfası.
 *
 * HB gerçek yetkilendirmesi: Merchant ID + Kullanıcı Adı (username) + Şifre (password) → Basic Auth.
 * Eşleştirme tablosu: local kategoriler (db.categories) → HB kategori ID'leri.
 */
export default function HepsiburadaEslestir() {
  const [settings, setSettings] = useState({ merchant_id: "", username: "", password: "", mode: "sandbox", is_active: false });
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const [categories, setCategories] = useState([]);
  const [mappings, setMappings] = useState({}); // {local_id: {hb_id, hb_name}}
  const [search, setSearch] = useState("");

  const loadSettings = async () => {
    try {
      const { data } = await axios.get(`${API}/integrations/hepsiburada/settings`, { headers: authHeaders() });
      setSettings({
        merchant_id: data.merchant_id || "",
        username: data.username || "",
        password: data.password === "********" ? "" : (data.password || ""),
        mode: data.mode || "sandbox",
        is_active: !!data.is_active,
        _has_password: data.password === "********",
      });
    } catch (_) {}
  };

  const loadCategories = async () => {
    try {
      const { data } = await axios.get(`${API}/categories`, { headers: authHeaders() });
      const rows = Array.isArray(data) ? data : data?.categories || [];
      setCategories(rows);
      // Build mappings from existing field
      const m = {};
      rows.forEach((c) => {
        if (c.hepsiburada_category_id) {
          m[c.id] = { hb_id: c.hepsiburada_category_id, hb_name: c.hepsiburada_category_name || "" };
        }
      });
      setMappings(m);
    } catch (_) {}
  };

  useEffect(() => { loadSettings(); loadCategories(); }, []);

  const handleSave = async () => {
    if (!settings.merchant_id || !settings.username) {
      return toast.warning("Merchant ID ve Kullanıcı Adı zorunlu");
    }
    setSaving(true);
    try {
      await axios.post(`${API}/integrations/hepsiburada/settings`, settings, { headers: authHeaders() });
      toast.success("Hepsiburada ayarları kaydedildi");
      loadSettings();
    } catch (e) { toast.error("Kaydedilemedi"); }
    finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const { data } = await axios.post(`${API}/integrations/hepsiburada/test-connection`, {}, { headers: authHeaders() });
      setTestResult(data);
      if (data.success) toast.success(data.message); else toast.error(data.message);
    } catch (e) {
      setTestResult({ success: false, message: "Test hatası: " + (e.message || "bilinmeyen") });
    } finally { setTesting(false); }
  };

  const saveMapping = async (localId, hbId, hbName) => {
    try {
      await axios.put(
        `${API}/categories/${localId}`,
        { hepsiburada_category_id: hbId || "", hepsiburada_category_name: hbName || "" },
        { headers: authHeaders() }
      );
      toast.success("Eşleştirme kaydedildi");
      setMappings({ ...mappings, [localId]: { hb_id: hbId, hb_name: hbName } });
    } catch (e) { toast.error("Kaydedilemedi"); }
  };

  const filtered = categories.filter(
    (c) => !search || c.name?.toLowerCase().includes(search.toLowerCase()) || (mappings[c.id]?.hb_id || "").includes(search)
  );
  const mappedCount = Object.keys(mappings).filter((k) => mappings[k]?.hb_id).length;

  return (
    <div className="space-y-6" data-testid="hepsiburada-eslestir-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-orange-500 to-red-600 text-white flex items-center justify-center text-sm font-bold">H</div>
          Hepsiburada Eşleştirme
        </h1>
        <p className="text-sm text-gray-500 mt-1">Hepsiburada API bağlantısını yapılandırın ve kategorilerinizi HB kategori ID'lerine eşleştirin.</p>
      </div>

      {/* Credentials */}
      <div className="bg-white rounded-xl border p-5">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Key size={16} /> API Kimlik Bilgileri</h3>
        <p className="text-xs text-gray-500 mb-4">
          Hepsiburada Merchant Panel &rarr; Entegrasyonlar &rarr; API Bilgileri &rarr; <em>Listings API</em> kullanıcı adı ve şifresini girin.
          HB <strong>Basic Auth</strong> (Username + Password) kullanır — API Key/Secret yoktur.
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-600">Merchant ID *</label>
            <input value={settings.merchant_id} onChange={(e) => setSettings({ ...settings, merchant_id: e.target.value })}
              data-testid="hb-merchant-id" placeholder="örn: 54321abc"
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">API Kullanıcı Adı *</label>
            <input value={settings.username} onChange={(e) => setSettings({ ...settings, username: e.target.value })}
              data-testid="hb-username" placeholder="hbseller_api_user"
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">API Şifre {settings._has_password && <span className="text-green-600 ml-1">(kayıtlı)</span>}</label>
            <input type="password" value={settings.password} onChange={(e) => setSettings({ ...settings, password: e.target.value })}
              data-testid="hb-password" placeholder={settings._has_password ? "Değiştirmek için yeni şifre girin" : "•••••••"}
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">Ortam</label>
            <select value={settings.mode} onChange={(e) => setSettings({ ...settings, mode: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
              <option value="sandbox">Sandbox (SIT Test)</option>
              <option value="production">Production (Canlı)</option>
            </select>
          </div>
        </div>
        <label className="flex items-center gap-2 mt-4 text-sm">
          <input type="checkbox" checked={settings.is_active} onChange={(e) => setSettings({ ...settings, is_active: e.target.checked })} />
          Entegrasyon aktif olsun
        </label>
        <div className="flex gap-2 mt-4">
          <button onClick={handleSave} disabled={saving} data-testid="hb-save-settings"
            className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg text-sm font-medium disabled:opacity-50">
            <Save size={14} /> {saving ? "Kaydediliyor..." : "Kaydet"}
          </button>
          <button onClick={handleTest} disabled={testing} data-testid="hb-test-connection"
            className="inline-flex items-center gap-2 px-4 py-2 border rounded-lg text-sm font-medium disabled:opacity-50">
            <PlugZap size={14} /> {testing ? "Test ediliyor..." : "Bağlantıyı Test Et"}
          </button>
        </div>
        {testResult && (
          <div className={`mt-3 p-3 rounded-lg text-sm flex items-start gap-2 ${testResult.success ? "bg-green-50 text-green-800 border border-green-200" : "bg-red-50 text-red-800 border border-red-200"}`}>
            {testResult.success ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
            <span>{testResult.message}</span>
          </div>
        )}
      </div>

      {/* Category Mapping */}
      <div className="bg-white rounded-xl border">
        <div className="flex items-center justify-between p-5 border-b flex-wrap gap-3">
          <div>
            <h3 className="font-semibold flex items-center gap-2"><Link2 size={16} /> Kategori Eşleştirme</h3>
            <p className="text-xs text-gray-500 mt-0.5">Yerel kategorilerinizi Hepsiburada kategori ID'lerine bağlayın.</p>
          </div>
          <div className="flex gap-2 items-center">
            <span className="text-xs text-gray-500">Eşleşti: <strong className="text-black">{mappedCount}</strong> / {categories.length}</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Kategori ara..."
              className="px-3 py-1.5 border rounded-lg text-sm" data-testid="hb-cat-search" />
            <button onClick={loadCategories} className="p-1.5 border rounded hover:bg-gray-50"><RefreshCw size={14} /></button>
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="text-left p-3 w-10">#</th>
              <th className="text-left p-3">Yerel Kategori</th>
              <th className="text-left p-3">HB Kategori ID</th>
              <th className="text-left p-3">HB Kategori Adı</th>
              <th className="text-right p-3">İşlem</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={5} className="p-6 text-center text-gray-400">Kategori bulunamadı.</td></tr>
            ) : filtered.map((c, i) => {
              const m = mappings[c.id] || { hb_id: "", hb_name: "" };
              return (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 text-gray-400">{i + 1}</td>
                  <td className="p-3 font-medium">{c.name}</td>
                  <td className="p-3">
                    <input value={m.hb_id} onChange={(e) => setMappings({ ...mappings, [c.id]: { ...m, hb_id: e.target.value } })}
                      data-testid={`hb-cat-id-${c.id}`} placeholder="örn: 18021982"
                      className="px-2 py-1 border rounded text-sm w-40 font-mono" />
                  </td>
                  <td className="p-3">
                    <input value={m.hb_name} onChange={(e) => setMappings({ ...mappings, [c.id]: { ...m, hb_name: e.target.value } })}
                      placeholder="Kadın > Giyim > Elbise"
                      className="px-2 py-1 border rounded text-sm w-full" />
                  </td>
                  <td className="p-3 text-right">
                    <button onClick={() => saveMapping(c.id, m.hb_id, m.hb_name)} data-testid={`hb-save-mapping-${c.id}`}
                      className="px-3 py-1 bg-black text-white text-xs rounded hover:bg-gray-800">Kaydet</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
