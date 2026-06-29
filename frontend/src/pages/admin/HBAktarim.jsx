/**
 * HBAktarim.jsx — "Özel HB Aktarım" (Ayarlar)
 *
 * Clean-room Hepsiburada aktarım modülü. Tüm HB tarafı (kategori/özellik/değer)
 * backend'de HB API dökümanından gelir; bu sayfa o uçları tüketir.
 * Sistemden alınan tek veri kimliktir ("FACETTE'ten kopyala").
 *
 * Sekmeler (bu sürüm): Kimlik · Kategori Eşleştirme
 *   (Sıradaki: Özellik & Değer Eşleştirme · Alan & Fiyat Kaynağı)
 *
 * Backend: /api/hb-aktarim/*
 */
import { useEffect, useMemo, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  KeyRound, FolderTree, RefreshCw, Save, Search, CheckCircle2,
  Circle, Plug, Copy, Trash2, X, Loader2,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function HBAktarim() {
  const token = useMemo(() => localStorage.getItem("token"), []);
  const auth = useMemo(() => ({ headers: { Authorization: `Bearer ${token}` } }), [token]);
  const [tab, setTab] = useState("kimlik");
  const [cfg, setCfg] = useState(null);

  const loadCfg = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/hb-aktarim/credentials`, auth);
      setCfg(r.data);
    } catch { /* sessiz */ }
  }, [auth]);

  useEffect(() => { loadCfg(); }, [loadCfg]);

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-semibold text-gray-900 flex items-center gap-2">
            <Plug size={20} className="text-orange-600" /> Özel HB Aktarım
          </h1>
          <p className="text-sm text-gray-500 mt-0.5">
            Hepsiburada ürün & sipariş entegrasyonu — kategori, özellik ve değer eşleştirme.
          </p>
        </div>
        {cfg && (
          <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
            cfg.is_live ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
          }`}>
            {cfg.is_live ? "CANLI" : "SANDBOX"}
          </span>
        )}
      </div>

      <div className="flex gap-1 border-b border-gray-200 mb-5">
        <TabBtn active={tab === "kimlik"} onClick={() => setTab("kimlik")} icon={KeyRound}>
          Kimlik
        </TabBtn>
        <TabBtn active={tab === "kategori"} onClick={() => setTab("kategori")} icon={FolderTree}>
          Kategori Eşleştirme
        </TabBtn>
        <span className="px-3 py-2 text-sm text-gray-300 cursor-not-allowed" title="Sıradaki sürüm">
          Özellik & Değer
        </span>
        <span className="px-3 py-2 text-sm text-gray-300 cursor-not-allowed" title="Sıradaki sürüm">
          Alan & Fiyat
        </span>
      </div>

      {tab === "kimlik" && <KimlikTab cfg={cfg} auth={auth} onSaved={loadCfg} />}
      {tab === "kategori" && <KategoriTab auth={auth} configured={cfg?.configured} />}
    </div>
  );
}

function TabBtn({ active, onClick, icon: Icon, children }) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 text-sm font-medium flex items-center gap-1.5 border-b-2 -mb-px transition ${
        active
          ? "border-orange-600 text-orange-700"
          : "border-transparent text-gray-500 hover:text-gray-800"
      }`}
    >
      {Icon && <Icon size={15} />} {children}
    </button>
  );
}

/* ====================== KİMLİK ====================== */
function KimlikTab({ cfg, auth, onSaved }) {
  const [form, setForm] = useState({
    merchant_id: "", dev_username: "", secret_key: "",
    oms_username: "", oms_password: "", env: "sandbox",
  });
  const [saving, setSaving] = useState(false);
  const [copying, setCopying] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState(null);

  useEffect(() => {
    if (!cfg) return;
    setForm((f) => ({
      ...f,
      merchant_id: cfg.merchant_id || "",
      dev_username: cfg.dev_username || "",
      oms_username: cfg.oms_username || "",
      env: cfg.is_live ? "prod" : "sandbox",
      secret_key: "", oms_password: "",
    }));
  }, [cfg]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const copyFromFacette = async () => {
    setCopying(true);
    try {
      const r = await axios.post(`${API}/hb-aktarim/credentials/copy-from-facette`, {}, auth);
      const c = r.data?.copied || {};
      const got = Object.entries(c).filter(([, v]) => v).map(([k]) => k);
      toast.success(`FACETTE'ten kopyalandı: ${got.join(", ") || "—"}`);
      onSaved && onSaved();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "FACETTE'te HB kimliği bulunamadı");
    } finally { setCopying(false); }
  };

  const save = async () => {
    if (!form.merchant_id.trim()) { toast.info("Merchant ID gerekli"); return; }
    setSaving(true);
    try {
      const body = {
        merchant_id: form.merchant_id.trim(),
        dev_username: form.dev_username.trim(),
        oms_username: form.oms_username.trim(),
        env: form.env,
      };
      if (form.secret_key.trim()) body.secret_key = form.secret_key.trim();
      if (form.oms_password.trim()) body.oms_password = form.oms_password.trim();
      await axios.post(`${API}/hb-aktarim/credentials`, body, auth);
      toast.success("Kimlik kaydedildi");
      setTest(null);
      onSaved && onSaved();
    } catch { toast.error("Kaydedilemedi"); }
    finally { setSaving(false); }
  };

  const runTest = async () => {
    setTesting(true); setTest(null);
    try {
      const r = await axios.get(`${API}/hb-aktarim/test`, auth);
      setTest(r.data);
      if (r.data?.ok) toast.success("Bağlantı başarılı");
      else toast.error("Bağlantı başarısız");
    } catch (e) {
      setTest({ ok: false, error: e?.response?.data?.detail || "Test çağrısı hata verdi" });
    } finally { setTesting(false); }
  };

  return (
    <div className="space-y-5">
      <div className="bg-orange-50 border border-orange-200 rounded-lg p-3 flex items-start justify-between gap-3">
        <p className="text-sm text-orange-800">
          Hepsiburada üç kimlik ister: <b>Merchant ID</b>, <b>Secret Key</b> ve
          <b> Developer Username</b> (User-Agent). FACETTE'te kayıtlı HB kimliğini buraya tek tıkla taşıyabilirsin.
        </p>
        <button
          onClick={copyFromFacette}
          disabled={copying}
          className="shrink-0 inline-flex items-center gap-1.5 text-sm px-3 py-1.5 bg-white border border-orange-300 rounded-md text-orange-700 hover:bg-orange-100 disabled:opacity-50"
        >
          {copying ? <Loader2 size={15} className="animate-spin" /> : <Copy size={15} />}
          FACETTE'ten kopyala
        </button>
      </div>

      <div className="grid md:grid-cols-2 gap-4 bg-white border border-gray-200 rounded-lg p-5">
        <Field label="Merchant ID" value={form.merchant_id} onChange={set("merchant_id")}
          placeholder="6fc6d90d-..." />
        <Field label="Developer Username (User-Agent)" value={form.dev_username}
          onChange={set("dev_username")} placeholder="entegrasyon kullanıcı adı" />
        <Field label="Secret Key" type="password" value={form.secret_key} onChange={set("secret_key")}
          placeholder={cfg?.secret_key_set ? "•••• kayıtlı — değiştirmek için yaz" : "secret key"} />
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Ortam</label>
          <select value={form.env} onChange={set("env")}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm">
            <option value="sandbox">Sandbox (test)</option>
            <option value="prod">Canlı (production)</option>
          </select>
        </div>
        <Field label="OMS Username (opsiyonel)" value={form.oms_username} onChange={set("oms_username")}
          placeholder="sipariş ayrı kimlik isterse" />
        <Field label="OMS Password (opsiyonel)" type="password" value={form.oms_password}
          onChange={set("oms_password")}
          placeholder={cfg?.oms_password_set ? "•••• kayıtlı" : "sipariş ayrı kimlik isterse"} />
      </div>

      <div className="flex items-center gap-2">
        <button onClick={save} disabled={saving}
          className="inline-flex items-center gap-1.5 text-sm px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700 disabled:opacity-50">
          {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Kaydet
        </button>
        <button onClick={runTest} disabled={testing}
          className="inline-flex items-center gap-1.5 text-sm px-4 py-2 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
          {testing ? <Loader2 size={15} className="animate-spin" /> : <Plug size={15} />} Bağlantıyı Test Et
        </button>
        {test && (
          <span className={`text-sm font-medium ${test.ok ? "text-green-700" : "text-red-700"}`}>
            {test.ok
              ? `✓ Bağlantı OK (${test.env}, örnek kategori: ${test.sample_count})`
              : `✗ ${test.error || "Başarısız"}`}
          </span>
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, type = "text", placeholder }) {
  return (
    <div>
      <label className="block text-xs font-medium text-gray-600 mb-1">{label}</label>
      <input type={type} value={value} onChange={onChange} placeholder={placeholder}
        className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-1 focus:ring-orange-500 focus:border-orange-500" />
    </div>
  );
}

/* ====================== KATEGORİ EŞLEŞTİRME ====================== */
function KategoriTab({ auth, configured }) {
  const [data, setData] = useState({ items: [], total: 0, matched: 0, unmatched: 0 });
  const [search, setSearch] = useState("");
  const [onlyUnmatched, setOnlyUnmatched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [pickerFor, setPickerFor] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/hb-aktarim/mappings/categories?search=${encodeURIComponent(search)}&only_unmatched=${onlyUnmatched}`,
        auth,
      );
      setData(r.data);
    } catch { toast.error("Kategori listesi yüklenemedi"); }
    finally { setLoading(false); }
  }, [auth, search, onlyUnmatched]);

  useEffect(() => {
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [load]);

  const refreshHbTree = async () => {
    setRefreshing(true);
    try {
      const r = await axios.post(`${API}/hb-aktarim/categories/refresh`, {}, auth);
      toast.success(`HB kategori ağacı güncellendi (${r.data?.total} leaf)`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "HB ağacı çekilemedi (kimlik?)");
    } finally { setRefreshing(false); }
  };

  const onPicked = async (row, hb) => {
    try {
      await axios.post(`${API}/hb-aktarim/mappings/categories/${row.system_category_id}`,
        { hb_category_id: hb.hb_id, hb_category_name: hb.label }, auth);
      toast.success("Eşleştirildi");
      setPickerFor(null);
      load();
    } catch { toast.error("Kaydedilemedi"); }
  };

  const clearRow = async (row) => {
    try {
      await axios.delete(`${API}/hb-aktarim/mappings/categories/${row.system_category_id}`, auth);
      toast.success("Eşleştirme silindi");
      load();
    } catch { toast.error("Silinemedi"); }
  };

  if (!configured) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
        Önce <b>Kimlik</b> sekmesinden Hepsiburada bilgilerini kaydet ve bağlantıyı test et.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="absolute left-2.5 top-2.5 text-gray-400" />
          <input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Sistem kategorisi ara..."
            className="w-full border border-gray-300 rounded-md pl-8 pr-3 py-2 text-sm"
          />
        </div>
        <label className="flex items-center gap-1.5 text-sm text-gray-600">
          <input type="checkbox" checked={onlyUnmatched}
            onChange={(e) => setOnlyUnmatched(e.target.checked)} />
          Sadece eşleşmeyenler
        </label>
        <span className="text-sm text-gray-500">
          {data.matched}/{data.total} eşleşti
        </span>
        <button onClick={refreshHbTree} disabled={refreshing}
          className="inline-flex items-center gap-1.5 text-sm px-3 py-2 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50">
          {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          HB ağacını yenile
        </button>
      </div>

      <div className="border border-gray-200 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Sistem Kategorisi</th>
              <th className="text-left px-4 py-2 font-medium">Hepsiburada Kategorisi (leaf)</th>
              <th className="px-4 py-2 w-24"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading && (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-gray-400">
                <Loader2 size={18} className="animate-spin inline" /> Yükleniyor…
              </td></tr>
            )}
            {!loading && data.items.length === 0 && (
              <tr><td colSpan={3} className="px-4 py-8 text-center text-gray-400">Kayıt yok.</td></tr>
            )}
            {!loading && data.items.map((row) => (
              <tr key={row.system_category_id} className="hover:bg-gray-50 align-top">
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    {row.hb_category_id
                      ? <CheckCircle2 size={15} className="text-green-600 shrink-0" />
                      : <Circle size={15} className="text-gray-300 shrink-0" />}
                    <span className="text-gray-800">{row.system_category_path}</span>
                  </div>
                </td>
                <td className="px-4 py-2.5">
                  {pickerFor === row.system_category_id ? (
                    <HbCategoryPicker auth={auth}
                      onPick={(hb) => onPicked(row, hb)}
                      onClose={() => setPickerFor(null)} />
                  ) : row.hb_category_id ? (
                    <button onClick={() => setPickerFor(row.system_category_id)}
                      className="text-left text-gray-700 hover:text-orange-700">
                      {row.hb_category_name || row.hb_category_id}
                      <span className="text-xs text-gray-400 ml-1">#{row.hb_category_id}</span>
                    </button>
                  ) : (
                    <button onClick={() => setPickerFor(row.system_category_id)}
                      className="text-orange-600 hover:text-orange-700 text-sm">
                      + HB kategori seç
                    </button>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right">
                  {row.hb_category_id && (
                    <button onClick={() => clearRow(row)}
                      className="text-gray-400 hover:text-red-600" title="Eşleştirmeyi sil">
                      <Trash2 size={15} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HbCategoryPicker({ auth, onPick, onClose }) {
  const [q, setQ] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = setTimeout(async () => {
      if (!q.trim()) { setRows([]); return; }
      setLoading(true);
      try {
        const r = await axios.get(
          `${API}/hb-aktarim/categories?search=${encodeURIComponent(q)}&limit=30`, auth);
        const items = (r.data?.categories || []).map((c) => ({
          hb_id: c.hb_id,
          label: (Array.isArray(c.paths) && c.paths.length
            ? c.paths.join(" > ") + " > " + c.name : c.name) || String(c.hb_id),
        }));
        setRows(items);
      } catch { /* sessiz */ }
      finally { setLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [q, auth]);

  return (
    <div className="border border-orange-300 rounded-md p-2 bg-orange-50/40">
      <div className="flex items-center gap-2 mb-2">
        <Search size={14} className="text-gray-400" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="HB leaf kategori ara..."
          className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm" />
        <button onClick={onClose} className="text-gray-400 hover:text-gray-700"><X size={15} /></button>
      </div>
      {loading && <div className="text-xs text-gray-400 px-1 py-1">Aranıyor…</div>}
      {!loading && q.trim() && rows.length === 0 && (
        <div className="text-xs text-gray-400 px-1 py-1">Sonuç yok.</div>
      )}
      <div className="max-h-52 overflow-auto">
        {rows.map((c) => (
          <button key={c.hb_id} onClick={() => onPick(c)}
            className="block w-full text-left text-sm px-2 py-1.5 rounded hover:bg-orange-100">
            {c.label}
            <span className="text-xs text-gray-400 ml-1">#{c.hb_id}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
