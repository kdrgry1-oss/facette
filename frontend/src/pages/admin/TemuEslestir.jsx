import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Key, Save, PlugZap, AlertCircle, CheckCircle2, RefreshCw, Link2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

/**
 * Temu Kategori & Ürün Eşleştirme sayfası.
 * Temu yetkilendirmesi: Shop ID + App Key + App Secret.
 */
export default function TemuEslestir() {
  const [settings, setSettings] = useState({ merchant_id: "", api_key: "", api_secret: "", mode: "sandbox", is_active: false });
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const [categories, setCategories] = useState([]);
  const [mappings, setMappings] = useState({});
  const [search, setSearch] = useState("");

  const loadSettings = async () => {
    try {
      const { data } = await axios.get(`${API}/integrations/temu/settings`, { headers: authHeaders() });
      setSettings({
        merchant_id: data.merchant_id || "",
        api_key: data.api_key || "",
        api_secret: data.api_secret === "********" ? "" : (data.api_secret || ""),
        mode: data.mode || "sandbox",
        is_active: !!data.is_active,
        _has_secret: data.api_secret === "********",
      });
    } catch (_) {}
  };

  const loadCategories = async () => {
    try {
      const { data } = await axios.get(`${API}/categories`, { headers: authHeaders() });
      const rows = Array.isArray(data) ? data : data?.categories || [];
      setCategories(rows);
      const m = {};
      rows.forEach((c) => {
        if (c.temu_category_id) {
          m[c.id] = { temu_id: c.temu_category_id, temu_name: c.temu_category_name || "" };
        }
      });
      setMappings(m);
    } catch (_) {}
  };

  useEffect(() => { loadSettings(); loadCategories(); }, []);

  const handleSave = async () => {
    if (!settings.merchant_id || !settings.api_key) {
      return toast.warning("Shop ID ve App Key zorunlu");
    }
    setSaving(true);
    try {
      await axios.post(`${API}/integrations/temu/settings`, settings, { headers: authHeaders() });
      toast.success("Temu ayarları kaydedildi");
      loadSettings();
    } catch (e) { toast.error("Kaydedilemedi"); }
    finally { setSaving(false); }
  };

  const handleTest = async () => {
    setTesting(true); setTestResult(null);
    try {
      const { data } = await axios.post(`${API}/integrations/temu/test-connection`, {}, { headers: authHeaders() });
      setTestResult(data);
      if (data.success) toast.success(data.message); else toast.error(data.message);
    } catch (e) { setTestResult({ success: false, message: e.message }); }
    finally { setTesting(false); }
  };

  const saveMapping = async (localId, temuId, temuName) => {
    try {
      await axios.put(
        `${API}/categories/${localId}`,
        { temu_category_id: temuId || "", temu_category_name: temuName || "" },
        { headers: authHeaders() }
      );
      toast.success("Eşleştirme kaydedildi");
      setMappings({ ...mappings, [localId]: { temu_id: temuId, temu_name: temuName } });
    } catch (e) { toast.error("Kaydedilemedi"); }
  };

  const filtered = categories.filter(
    (c) => !search || c.name?.toLowerCase().includes(search.toLowerCase()) || (mappings[c.id]?.temu_id || "").includes(search)
  );
  const mappedCount = Object.keys(mappings).filter((k) => mappings[k]?.temu_id).length;

  return (
    <div className="space-y-6" data-testid="temu-eslestir-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-amber-500 to-orange-600 text-white flex items-center justify-center text-sm font-bold">T</div>
          Temu Eşleştirme
        </h1>
        <p className="text-sm text-gray-500 mt-1">Temu Seller Central üzerinden alınan App Key/Secret ile bağlantıyı yapılandırın ve kategorileri eşleştirin.</p>
      </div>

      <div className="bg-white rounded-xl border p-5">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><Key size={16} /> API Kimlik Bilgileri</h3>
        <p className="text-xs text-gray-500 mb-4">
          Temu Seller Central &rarr; Developer &rarr; App &rarr; <em>App Key / App Secret</em>.
          Shop ID, mağaza kimliğinizdir.
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-gray-600">Shop ID *</label>
            <input value={settings.merchant_id} onChange={(e) => setSettings({ ...settings, merchant_id: e.target.value })}
              data-testid="temu-shop-id" placeholder="örn: 110000123456"
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">App Key *</label>
            <input value={settings.api_key} onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
              data-testid="temu-app-key" placeholder="temu_app_xxxxx"
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">App Secret {settings._has_secret && <span className="text-green-600 ml-1">(kayıtlı)</span>}</label>
            <input type="password" value={settings.api_secret} onChange={(e) => setSettings({ ...settings, api_secret: e.target.value })}
              data-testid="temu-app-secret" placeholder={settings._has_secret ? "Değiştirmek için yeni giri" : "•••••••"}
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">Ortam</label>
            <select value={settings.mode} onChange={(e) => setSettings({ ...settings, mode: e.target.value })}
              className="w-full mt-1 px-3 py-2 border rounded-lg text-sm">
              <option value="sandbox">Sandbox</option>
              <option value="production">Production</option>
            </select>
          </div>
        </div>
        <label className="flex items-center gap-2 mt-4 text-sm">
          <input type="checkbox" checked={settings.is_active} onChange={(e) => setSettings({ ...settings, is_active: e.target.checked })} />
          Entegrasyon aktif olsun
        </label>
        <div className="flex gap-2 mt-4">
          <button onClick={handleSave} disabled={saving} data-testid="temu-save-settings"
            className="inline-flex items-center gap-2 px-4 py-2 bg-black text-white rounded-lg text-sm font-medium disabled:opacity-50">
            <Save size={14} /> {saving ? "Kaydediliyor..." : "Kaydet"}
          </button>
          <button onClick={handleTest} disabled={testing} data-testid="temu-test-connection"
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

      <div className="bg-white rounded-xl border">
        <div className="flex items-center justify-between p-5 border-b flex-wrap gap-3">
          <div>
            <h3 className="font-semibold flex items-center gap-2"><Link2 size={16} /> Kategori Eşleştirme</h3>
            <p className="text-xs text-gray-500 mt-0.5">Yerel kategorilerinizi Temu kategori ID'lerine bağlayın.</p>
          </div>
          <div className="flex gap-2 items-center">
            <span className="text-xs text-gray-500">Eşleşti: <strong className="text-black">{mappedCount}</strong> / {categories.length}</span>
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Kategori ara..."
              className="px-3 py-1.5 border rounded-lg text-sm" data-testid="temu-cat-search" />
            <button onClick={loadCategories} className="p-1.5 border rounded hover:bg-gray-50"><RefreshCw size={14} /></button>
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="text-left p-3 w-10">#</th>
              <th className="text-left p-3">Yerel Kategori</th>
              <th className="text-left p-3">Temu Kategori ID</th>
              <th className="text-left p-3">Temu Kategori Adı</th>
              <th className="text-right p-3">İşlem</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr><td colSpan={5} className="p-6 text-center text-gray-400">Kategori bulunamadı.</td></tr>
            ) : filtered.map((c, i) => {
              const m = mappings[c.id] || { temu_id: "", temu_name: "" };
              return (
                <tr key={c.id} className="border-t hover:bg-gray-50">
                  <td className="p-3 text-gray-400">{i + 1}</td>
                  <td className="p-3 font-medium">{c.name}</td>
                  <td className="p-3">
                    <input value={m.temu_id} onChange={(e) => setMappings({ ...mappings, [c.id]: { ...m, temu_id: e.target.value } })}
                      data-testid={`temu-cat-id-${c.id}`} placeholder="örn: 30847"
                      className="px-2 py-1 border rounded text-sm w-40 font-mono" />
                  </td>
                  <td className="p-3">
                    <input value={m.temu_name} onChange={(e) => setMappings({ ...mappings, [c.id]: { ...m, temu_name: e.target.value } })}
                      placeholder="Women > Dresses"
                      className="px-2 py-1 border rounded text-sm w-full" />
                  </td>
                  <td className="p-3 text-right">
                    <button onClick={() => saveMapping(c.id, m.temu_id, m.temu_name)} data-testid={`temu-save-mapping-${c.id}`}
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
