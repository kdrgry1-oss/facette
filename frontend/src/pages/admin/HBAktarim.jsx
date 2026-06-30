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
  Circle, Plug, Copy, Trash2, X, Loader2, Sliders, ListChecks,
  Coins, Send, Upload, PackageSearch, Truck, AlertTriangle, Eye,
} from "lucide-react";

const HB_IMG_MAX = 10;
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
        <TabBtn active={tab === "ozellik"} onClick={() => setTab("ozellik")} icon={Sliders}>
          Özellik & Değer
        </TabBtn>
        <TabBtn active={tab === "alan"} onClick={() => setTab("alan")} icon={Coins}>
          Alan & Fiyat
        </TabBtn>
        <TabBtn active={tab === "gonderim"} onClick={() => setTab("gonderim")} icon={Send}>
          Gönderim
        </TabBtn>
      </div>

      {tab === "kimlik" && <KimlikTab cfg={cfg} auth={auth} onSaved={loadCfg} />}
      {tab === "kategori" && <KategoriTab auth={auth} configured={cfg?.configured} />}
      {tab === "ozellik" && <OzellikTab auth={auth} configured={cfg?.configured} />}
      {tab === "alan" && <AlanFiyatTab auth={auth} configured={cfg?.configured} />}
      {tab === "gonderim" && <GonderimTab auth={auth} configured={cfg?.configured} cfg={cfg} />}
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

/* ====================== ÖZELLİK & DEĞER EŞLEŞTİRME ====================== */
function OzellikTab({ auth, configured }) {
  const [cats, setCats] = useState([]);
  const [sel, setSel] = useState("");
  const [attrs, setAttrs] = useState({ base_attributes: [], attributes: [] });
  const [cfgMap, setCfgMap] = useState({});
  const [sourceFields, setSourceFields] = useState([]);
  const [loading, setLoading] = useState(false);

  const loadCats = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/hb-aktarim/mappings/used-hb-categories`, auth);
      setCats(r.data?.categories || []);
    } catch { /* sessiz */ }
  }, [auth]);

  useEffect(() => {
    loadCats();
    axios.get(`${API}/hb-aktarim/source-fields`, auth)
      .then((r) => setSourceFields(r.data?.fields || []))
      .catch(() => {});
  }, [loadCats, auth]);

  const loadCategory = useCallback(async (hbId) => {
    if (!hbId) { setAttrs({ base_attributes: [], attributes: [] }); setCfgMap({}); return; }
    setLoading(true);
    try {
      const [a, m] = await Promise.all([
        axios.get(`${API}/hb-aktarim/categories/${hbId}/attributes`, auth),
        axios.get(`${API}/hb-aktarim/mappings/attributes/${hbId}`, auth),
      ]);
      setAttrs({
        base_attributes: a.data?.base_attributes || [],
        attributes: a.data?.attributes || [],
      });
      setCfgMap(m.data?.attributes || {});
    } catch { toast.error("Özellikler yüklenemedi"); }
    finally { setLoading(false); }
  }, [auth]);

  useEffect(() => { loadCategory(sel); }, [sel, loadCategory]);

  const onAttrSaved = (attrId, cfg) =>
    setCfgMap((m) => ({ ...m, [attrId]: cfg }));

  if (!configured) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800">
        Önce <b>Kimlik</b> sekmesini doldur, sonra <b>Kategori Eşleştirme</b>'den en az bir
        kategori eşle. Burada o HB kategorisinin özelliklerini eşleştireceksin.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-gray-600">HB Kategorisi:</label>
        <select value={sel} onChange={(e) => setSel(e.target.value)}
          className="border border-gray-300 rounded-md px-3 py-2 text-sm min-w-[280px]">
          <option value="">— eşleşmiş bir HB kategorisi seç —</option>
          {cats.map((c) => (
            <option key={c.hb_category_id} value={c.hb_category_id}>
              {(c.hb_category_name || c.hb_category_id)} · {c.system_count} sistem kat. ·
              {" "}{c.configured_attrs} alan ayarlı
            </option>
          ))}
        </select>
        {cats.length === 0 && (
          <span className="text-sm text-gray-400">Önce Kategori Eşleştirme yap.</span>
        )}
      </div>

      {loading && (
        <div className="text-center text-gray-400 py-8">
          <Loader2 size={18} className="animate-spin inline" /> Yükleniyor…
        </div>
      )}

      {!loading && sel && (
        <>
          <AttrGroup title="Temel Alanlar (HB sabit)" items={attrs.base_attributes}
            hbCatId={sel} sourceFields={sourceFields} cfgMap={cfgMap} auth={auth} onSaved={onAttrSaved} />
          <AttrGroup title="Kategori Özellikleri" items={attrs.attributes}
            hbCatId={sel} sourceFields={sourceFields} cfgMap={cfgMap} auth={auth} onSaved={onAttrSaved} />
        </>
      )}
    </div>
  );
}

function AttrGroup({ title, items, hbCatId, sourceFields, cfgMap, auth, onSaved }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-4 py-2 text-xs font-semibold uppercase text-gray-500 flex items-center gap-1.5">
        <ListChecks size={14} /> {title} <span className="text-gray-400">({items.length})</span>
      </div>
      <div className="divide-y divide-gray-100">
        {items.map((a) => (
          <AttrRow key={a.id} attr={a} hbCatId={hbCatId} sourceFields={sourceFields}
            initial={cfgMap[a.id]} auth={auth} onSaved={onSaved} />
        ))}
      </div>
    </div>
  );
}

function AttrRow({ attr, hbCatId, sourceFields, initial, auth, onSaved }) {
  const [source, setSource] = useState(initial?.source || "ignore");
  const [field, setField] = useState(initial?.field || "");
  const [fixed, setFixed] = useState(initial?.fixed ?? "");
  const [valueMap, setValueMap] = useState(initial?.value_map || {});
  const [hbValues, setHbValues] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  const loadHbValues = useCallback(async (force = false) => {
    if (!force && (hbValues || !attr.selectable)) return;
    try {
      const r = await axios.get(
        `${API}/hb-aktarim/categories/${hbCatId}/attributes/${encodeURIComponent(attr.id)}/values`, auth);
      setHbValues(r.data?.values || []);
    } catch { setHbValues([]); }
  }, [hbValues, attr.selectable, attr.id, hbCatId, auth]);

  useEffect(() => {
    if (attr.selectable && (source === "fixed" || source === "valuemap")) loadHbValues();
  }, [source, attr.selectable, loadHbValues]);

  const mark = (fn) => (v) => { fn(v); setDirty(true); };

  const save = async () => {
    setSaving(true);
    try {
      const body = { source, field: field || null, fixed, value_map: valueMap };
      const r = await axios.post(
        `${API}/hb-aktarim/mappings/attributes/${hbCatId}/${encodeURIComponent(attr.id)}`, body, auth);
      toast.success(`"${attr.name}" kaydedildi`);
      setDirty(false);
      onSaved && onSaved(attr.id, r.data?.config);
    } catch { toast.error("Kaydedilemedi"); }
    finally { setSaving(false); }
  };


  return (
    <div className="px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-[180px]">
          <span className="text-sm font-medium text-gray-800">{attr.name}</span>
          <div className="flex gap-1 mt-0.5">
            {attr.mandatory && <Badge color="red">zorunlu</Badge>}
            {attr.multiValue && <Badge color="blue">çoklu</Badge>}
            {attr.selectable && <Badge color="gray">değer listesi</Badge>}
            <span className="text-[10px] text-gray-400">#{attr.id}</span>
          </div>
        </div>

        <select value={source} onChange={(e) => mark(setSource)(e.target.value)}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-sm">
          <option value="ignore">— Gönderme —</option>
          <option value="field">Ürün alanı</option>
          <option value="fixed">Sabit değer</option>
          {attr.selectable && <option value="valuemap">Değer eşleştirme</option>}
        </select>

        {source === "field" && (
          <select value={field} onChange={(e) => mark(setField)(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[200px]">
            <option value="">— ürün alanı seç —</option>
            {sourceFields.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}{f.system ? " (sistem)" : ""}{f.sample ? ` · örn: ${f.sample}` : ""}
              </option>
            ))}
          </select>
        )}

        {source === "fixed" && (
          <div className="flex items-center gap-2">
            <input value={fixed ?? ""} onChange={(e) => mark(setFixed)(e.target.value)}
              placeholder="sabit değer gir"
              className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[180px]" />
            {attr.selectable && hbValues && hbValues.length > 0 && (
              <select value="" onChange={(e) => { if (e.target.value) mark(setFixed)(e.target.value); }}
                className="border border-gray-300 rounded-md px-2 py-1.5 text-sm">
                <option value="">↳ listeden seç</option>
                {hbValues.map((v) => (<option key={v.id} value={v.name}>{v.name}</option>))}
              </select>
            )}
          </div>
        )}

        {source === "valuemap" && (
          <span className="text-xs text-gray-500 inline-flex items-center gap-1">
            <ListChecks size={13} className="text-orange-600" />
            {hbValues == null ? "HB değerleri yükleniyor…"
              : `${hbValues.length} HB değeri · aşağıdan eşle`}
          </span>
        )}

        <button onClick={save} disabled={saving}
          className={`ml-auto inline-flex items-center gap-1 text-sm px-3 py-1.5 rounded-md ${
            dirty ? "bg-orange-600 text-white hover:bg-orange-700" : "bg-gray-100 text-gray-500"
          } disabled:opacity-50`}>
          {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />} Kaydet
        </button>
      </div>

      {source === "valuemap" && (
        <ValueMapEditor hbCatId={hbCatId} attr={attr} field={field}
          setField={(v) => mark(setField)(v)} sourceFields={sourceFields}
          hbValues={hbValues} onReloadHb={() => loadHbValues(true)}
          valueMap={valueMap}
          onChange={(m) => { setValueMap(m); setDirty(true); }}
          auth={auth} />
      )}
    </div>
  );
}

function Badge({ color, children }) {
  const map = {
    red: "bg-red-100 text-red-700", blue: "bg-blue-100 text-blue-700",
    gray: "bg-gray-100 text-gray-600",
  };
  return <span className={`text-[10px] px-1.5 py-0.5 rounded ${map[color] || map.gray}`}>{children}</span>;
}

function ValueMapEditor({ hbCatId, attr, field, setField, sourceFields, hbValues, onReloadHb, valueMap, onChange, auth }) {
  const [sysVals, setSysVals] = useState(null);

  useEffect(() => {
    if (!field) { setSysVals(null); return; }
    let on = true;
    setSysVals(null);
    axios.get(`${API}/hb-aktarim/source-fields/values?field=${encodeURIComponent(field)}`, auth)
      .then((r) => { if (on) setSysVals(r.data?.values || []); })
      .catch(() => { if (on) setSysVals([]); });
    return () => { on = false; };
  }, [field, auth]);

  const setVal = (sv, hbId) => onChange({ ...valueMap, [sv]: hbId });
  const hbEmpty = Array.isArray(hbValues) && hbValues.length === 0;

  return (
    <div className="mt-3 border border-orange-200 rounded-md bg-orange-50/40 p-3">
      {/* Kaynak alan seçimi + HB karşılık özeti */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <span className="text-xs text-gray-600">Kaynak ürün alanı:</span>
        <select value={field || ""} onChange={(e) => setField(e.target.value)}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[200px]">
          <option value="">— seç (ör. Varyant · Renk) —</option>
          {sourceFields.map((f) => (
            <option key={f.key} value={f.key}>{f.label}{f.system ? " (sistem)" : ""}</option>
          ))}
        </select>
        <span className="text-xs text-gray-400">
          → HB "{attr.name}": {hbValues == null ? "yükleniyor…" : `${hbValues.length} değer`}
        </span>
        {hbEmpty && (
          <button onClick={onReloadHb}
            className="text-xs inline-flex items-center gap-1 px-2 py-1 border border-orange-300 rounded text-orange-700 hover:bg-orange-50">
            <RefreshCw size={12} /> HB değerlerini yenile
          </button>
        )}
      </div>

      {!field && (
        <div className="text-xs text-gray-400">
          Eşlemek için önce yukarıdan bir kaynak ürün alanı seç; ardından senin değerlerin
          Hepsiburada karşılıklarıyla eşlenecek.
        </div>
      )}
      {field && sysVals === null && <div className="text-xs text-gray-400">değerler yükleniyor…</div>}
      {field && sysVals && sysVals.length === 0 && (
        <div className="text-xs text-gray-400">Bu alan için üründe değer bulunamadı.</div>
      )}
      {hbEmpty && field && (
        <div className="text-xs text-amber-700 mb-1">
          Hepsiburada değer listesi boş geldi — "HB değerlerini yenile"yi dene.
        </div>
      )}

      {field && sysVals && sysVals.length > 0 && (
        <div className="max-h-72 overflow-auto divide-y divide-orange-100">
          {sysVals.map((sv) => (
            <div key={sv} className="flex items-center gap-3 py-1.5">
              <span className="text-sm text-gray-700 w-1/2 truncate" title={sv}>{sv}</span>
              <select value={valueMap[sv] || ""} onChange={(e) => setVal(sv, e.target.value)}
                className="flex-1 border border-gray-300 rounded px-2 py-1 text-sm">
                <option value="">— HB değeri —</option>
                {(hbValues || []).map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}
      <p className="text-[11px] text-gray-400 mt-2">
        Eşleştirmeyi kalıcı yapmak için satırın sağındaki <b>Kaydet</b>'e bas.
      </p>
    </div>
  );
}

/* ====================== ALAN & FİYAT (global config) ====================== */
function HbWarn({ children }) {
  return (
    <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-sm text-amber-800 flex gap-2">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" /> <div>{children}</div>
    </div>
  );
}
function HbLoading() {
  return (
    <div className="text-center text-gray-400 py-8">
      <Loader2 size={18} className="animate-spin inline" /> Yükleniyor…
    </div>
  );
}

function AlanFiyatTab({ auth, configured }) {
  const [cfg, setCfg] = useState(null);
  const [baseFields, setBaseFields] = useState([]);
  const [cargoList, setCargoList] = useState([]);
  const [sourceFields, setSourceFields] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    axios.get(`${API}/hb-aktarim/config/fields`, auth)
      .then((r) => {
        setCfg(r.data?.config || {});
        setBaseFields(r.data?.hb_base_fields || []);
        setCargoList(r.data?.cargo_companies || []);
      })
      .catch(() => toast.error("Konfigürasyon yüklenemedi"));
    axios.get(`${API}/hb-aktarim/source-fields`, auth)
      .then((r) => setSourceFields(r.data?.fields || []))
      .catch(() => {});
  }, [auth]);

  const setBase = (key, patch) =>
    setCfg((c) => ({ ...c, base: { ...(c.base || {}), [key]: { ...((c.base || {})[key] || {}), ...patch } } }));
  const setPrice = (patch) => setCfg((c) => ({ ...c, price: { ...(c.price || {}), ...patch } }));
  const setStock = (patch) => setCfg((c) => ({ ...c, stock: { ...(c.stock || {}), ...patch } }));
  const setListing = (patch) => setCfg((c) => ({ ...c, listing: { ...(c.listing || {}), ...patch } }));
  const toggleCargo = (name) =>
    setCfg((c) => {
      const cur = (c.listing && c.listing.cargo) || [];
      const next = cur.includes(name) ? cur.filter((x) => x !== name) : [...cur, name];
      return { ...c, listing: { ...(c.listing || {}), cargo: next } };
    });

  const save = async () => {
    setSaving(true);
    try {
      await axios.post(`${API}/hb-aktarim/config/fields`, cfg, auth);
      toast.success("Alan & fiyat ayarları kaydedildi");
    } catch { toast.error("Kaydedilemedi"); }
    finally { setSaving(false); }
  };

  if (!configured) return <HbWarn>Önce <b>Kimlik</b> sekmesini doldur.</HbWarn>;
  if (!cfg) return <HbLoading />;

  const opts = sourceFields.map((f) => (
    <option key={f.key} value={f.key}>{f.label}{f.system ? " (sistem)" : ""}{f.sample ? ` · örn: ${f.sample}` : ""}</option>
  ));

  return (
    <div className="space-y-6">
      <Section title="Temel Alanlar" desc="Hepsiburada zorunlu alanlarının kaynağı (ürün alanı veya sabit değer).">
        <div className="space-y-2">
          {baseFields.map((key) => {
            const fc = (cfg.base || {})[key] || {};
            return (
              <div key={key} className="flex flex-wrap items-center gap-2">
                <span className="w-36 text-sm font-medium text-gray-700">{key}</span>
                <select value={fc.source || "field"} onChange={(e) => setBase(key, { source: e.target.value })}
                  className="border border-gray-300 rounded-md px-2 py-1.5 text-sm">
                  <option value="field">Ürün alanı</option>
                  <option value="fixed">Sabit değer</option>
                </select>
                {fc.source === "fixed" ? (
                  <input value={fc.fixed ?? ""} onChange={(e) => setBase(key, { fixed: e.target.value })}
                    placeholder="sabit değer"
                    className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[220px]" />
                ) : (
                  <select value={fc.field || ""} onChange={(e) => setBase(key, { field: e.target.value })}
                    className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[260px]">
                    <option value="">— ürün alanı seç —</option>{opts}
                  </select>
                )}
              </div>
            );
          })}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <span className="w-36 text-sm font-medium text-gray-700">Görseller</span>
            <select value={cfg.images_field || "images"} onChange={(e) => setCfg((c) => ({ ...c, images_field: e.target.value }))}
              className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[260px]">
              <option value="images">images</option>{opts}
            </select>
            <span className="text-xs text-gray-400">Image1…Image{HB_IMG_MAX} olarak gönderilir</span>
          </div>
        </div>
      </Section>

      <Section title="Fiyat" desc="Fiyat kaynağı + kâr marjı (%). HB'ye sayı olarak gider.">
        <div className="flex flex-wrap items-center gap-3">
          <select value={(cfg.price || {}).field || "price"} onChange={(e) => setPrice({ field: e.target.value })}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[220px]">
            <option value="price">Satış Fiyatı</option>
            <option value="sale_price">İndirimli Fiyat</option>
            <option value="market_price">Piyasa Fiyatı</option>
            {opts}
          </select>
          <label className="text-sm text-gray-600">Marj %</label>
          <input type="number" value={(cfg.price || {}).margin_pct ?? 0}
            onChange={(e) => setPrice({ margin_pct: Number(e.target.value) })}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm w-24" />
          <label className="text-sm text-gray-600">Yuvarla</label>
          <input type="number" value={(cfg.price || {}).round ?? 2}
            onChange={(e) => setPrice({ round: Number(e.target.value) })}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm w-20" />
        </div>
      </Section>

      <Section title="Stok" desc="Stok adedi kaynağı (genelde variant.stock).">
        <select value={(cfg.stock || {}).field || "variant.stock"} onChange={(e) => setStock({ field: e.target.value })}
          className="border border-gray-300 rounded-md px-2 py-1.5 text-sm min-w-[260px]">
          <option value="variant.stock">Varyant · Stok</option>
          <option value="stock">Stok</option>
          {opts}
        </select>
      </Section>

      <Section title="Kargo & Termin" desc="Listeleme için varsayılan kargo firmaları ve termin.">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <label className="text-sm text-gray-600">Termin (gün)</label>
          <input type="number" value={(cfg.listing || {}).dispatch_time ?? 1}
            onChange={(e) => setListing({ dispatch_time: Number(e.target.value) })}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm w-24" />
          <label className="text-sm text-gray-600 ml-2">Maks. adet/sipariş</label>
          <input type="number" value={(cfg.listing || {}).max_qty ?? ""}
            onChange={(e) => setListing({ max_qty: e.target.value === "" ? null : Number(e.target.value) })}
            placeholder="—" className="border border-gray-300 rounded-md px-2 py-1.5 text-sm w-24" />
        </div>
        <div className="flex flex-wrap gap-2">
          {cargoList.map((name) => {
            const on = ((cfg.listing || {}).cargo || []).includes(name);
            return (
              <button key={name} onClick={() => toggleCargo(name)}
                className={`text-xs px-2.5 py-1.5 rounded-md border flex items-center gap-1 ${
                  on ? "bg-orange-600 text-white border-orange-600" : "bg-white text-gray-600 border-gray-300"
                }`}>
                <Truck size={12} /> {name}
              </button>
            );
          })}
        </div>
      </Section>

      <button onClick={save} disabled={saving}
        className="inline-flex items-center gap-1.5 bg-orange-600 text-white text-sm px-4 py-2 rounded-md hover:bg-orange-700 disabled:opacity-50">
        {saving ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} />} Kaydet
      </button>
    </div>
  );
}

function Section({ title, desc, children }) {
  return (
    <div className="border border-gray-200 rounded-lg p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-gray-800">{title}</h3>
        {desc && <p className="text-xs text-gray-400 mt-0.5">{desc}</p>}
      </div>
      {children}
    </div>
  );
}

/* ====================== GÖNDERİM (preview / send / status / fiyat-stok / sipariş) ====================== */
function GonderimTab({ auth, configured, cfg }) {
  const [busy, setBusy] = useState("");
  const [preview, setPreview] = useState(null);
  const [sendRes, setSendRes] = useState(null);
  const [trackId, setTrackId] = useState("");
  const [status, setStatus] = useState(null);
  const [psPrev, setPsPrev] = useState(null);
  const [psRes, setPsRes] = useState(null);
  const [obegin, setObegin] = useState("");
  const [oend, setOend] = useState("");
  const [orders, setOrders] = useState(null);

  const env = (cfg?.env || cfg?.mode || "sandbox").toLowerCase();
  const isProd = ["prod", "production", "live", "canli", "canlı"].includes(env);
  const envText = isProd ? "CANLI (prod)" : "SANDBOX (test)";

  const run = async (key, fn) => { setBusy(key); try { await fn(); } finally { setBusy(""); } };

  const doPreview = () => run("prev", async () => {
    try {
      const r = await axios.post(`${API}/hb-aktarim/publish/preview?limit=25`, {}, auth);
      setPreview(r.data); toast.success(`${r.data.items_built} kalem kuruldu`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Önizleme başarısız"); }
  });

  const doSend = () => {
    if (!window.confirm(`${envText} ortamına ürünler gönderilecek (katalog). Emin misin?`)) return;
    run("send", async () => {
      try {
        const r = await axios.post(`${API}/hb-aktarim/publish/send`, {}, auth);
        setSendRes(r.data); toast.success(`${r.data.sent} kalem gönderildi`);
      } catch (e) { toast.error(e?.response?.data?.detail || "Gönderim başarısız"); }
    });
  };

  const doStatus = () => run("st", async () => {
    if (!trackId.trim()) return;
    try {
      const r = await axios.get(`${API}/hb-aktarim/publish/status/${encodeURIComponent(trackId.trim())}`, auth);
      setStatus(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Statü alınamadı"); }
  });

  const doPsPreview = () => run("psp", async () => {
    try {
      const r = await axios.post(`${API}/hb-aktarim/listing/price-stock/preview?limit=25`, {}, auth);
      setPsPrev(r.data); toast.success(`${r.data.count} satır`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Önizleme başarısız"); }
  });

  const doPsSend = () => {
    if (!window.confirm(`${envText} ortamına fiyat/stok gönderilecek. Emin misin?`)) return;
    run("pss", async () => {
      try {
        const r = await axios.post(`${API}/hb-aktarim/listing/price-stock/send`, {}, auth);
        setPsRes(r.data); toast.success(`Fiyat:${r.data.sent_price} Stok:${r.data.sent_stock}`);
      } catch (e) { toast.error(e?.response?.data?.detail || "Gönderim başarısız"); }
    });
  };

  const doOrders = () => run("ord", async () => {
    try {
      const qs = new URLSearchParams();
      if (obegin) qs.set("begin_date", obegin);
      if (oend) qs.set("end_date", oend);
      const r = await axios.get(`${API}/hb-aktarim/orders?${qs.toString()}`, auth);
      setOrders(r.data?.orders); toast.success("Siparişler çekildi");
    } catch (e) { toast.error(e?.response?.data?.detail || "Sipariş çekilemedi"); }
  });

  if (!configured) return <HbWarn>Önce <b>Kimlik</b> sekmesini doldur ve kategori/özellik eşleştirmesini tamamla.</HbWarn>;

  return (
    <div className="space-y-6">
      <div className={`text-xs px-3 py-2 rounded-md inline-flex items-center gap-2 ${
        isProd ? "bg-red-50 text-red-700 border border-red-200" : "bg-emerald-50 text-emerald-700 border border-emerald-200"
      }`}>
        <Plug size={13} /> Aktif ortam: <b>{envText}</b>
        {isProd && <span>— gönderimler gerçek mağazana yazar!</span>}
      </div>

      <Section title="1) Ürün Gönderimi (katalog)" desc="Önce dry-run önizleme; sorun yoksa Hepsiburada'ya gönder.">
        <div className="flex flex-wrap gap-2 mb-3">
          <ActBtn onClick={doPreview} busy={busy === "prev"} icon={Eye} ghost>Önizleme (dry-run)</ActBtn>
          <ActBtn onClick={doSend} busy={busy === "send"} icon={Send}>Hepsiburada'ya Gönder</ActBtn>
        </div>
        {preview && (
          <div className="text-sm space-y-2">
            <div className="flex flex-wrap gap-4 text-gray-700">
              <span>Kapsam: <b>{preview.products_in_scope}</b> ürün</span>
              <span>Kurulan kalem: <b>{preview.items_built}</b></span>
              <span className={preview.warnings_count ? "text-amber-700" : "text-emerald-700"}>
                Uyarı: <b>{preview.warnings_count}</b>
              </span>
            </div>
            {preview.warnings?.length > 0 && (
              <div className="bg-amber-50 border border-amber-200 rounded p-2 max-h-48 overflow-auto">
                {preview.warnings.map((w, i) => (
                  <div key={i} className="text-xs text-amber-800">
                    <b>{w.merchantSku}</b> ({w.product}) → eksik zorunlu: {w.missing_mandatory?.join(", ")}
                  </div>
                ))}
              </div>
            )}
            <JsonBox label="Örnek payload (ilk 5 ürün)" data={preview.sample} />
          </div>
        )}
        {sendRes && (
          <div className="mt-3 text-sm bg-gray-50 border border-gray-200 rounded p-3">
            <div>Gönderilen kalem: <b>{sendRes.sent}</b> · ortam: <b>{sendRes.env}</b></div>
            {(sendRes.created !== undefined || sendRes.updated !== undefined) && (
              <div className="text-xs text-gray-600 mt-0.5">
                Yeni ürün (katalog girişi): <b>{sendRes.created ?? 0}</b> ·
                {" "}Var olan ürün (özellik güncelleme): <b>{sendRes.updated ?? 0}</b>
              </div>
            )}
            {sendRes.tracking_ids?.map((t, i) => (
              <div key={`c${i}`} className="text-xs text-gray-600 mt-1">
                [yeni] batch {t.batch}: {t.count} kalem · trackingId: <code>{String(t.trackingId)}</code>
              </div>
            ))}
            {sendRes.update_tracking_ids?.map((t, i) => (
              <div key={`u${i}`} className="text-xs text-blue-700 mt-1">
                [güncelleme] batch {t.batch}: {t.count} kalem · trackingId: <code>{String(t.trackingId)}</code>
              </div>
            ))}
            {sendRes.errors?.length > 0 && (
              <div className="text-xs text-red-600 mt-1">Hatalar (yeni ürün): {sendRes.errors.length}</div>
            )}
            {sendRes.update_errors?.length > 0 && (
              <div className="text-xs text-red-600 mt-1">Hatalar (özellik güncelleme): {sendRes.update_errors.length}</div>
            )}
          </div>
        )}
      </Section>

      <Section title="2) İçe Aktarım Durumu" desc="Gönderim trackingId ile import sonucunu sorgula.">
        <div className="flex flex-wrap gap-2">
          <input value={trackId} onChange={(e) => setTrackId(e.target.value)} placeholder="trackingId"
            className="border border-gray-300 rounded-md px-3 py-2 text-sm min-w-[280px]" />
          <ActBtn onClick={doStatus} busy={busy === "st"} icon={Search} ghost>Durum sorgula</ActBtn>
        </div>
        {status && <JsonBox label="Statü" data={status} />}
      </Section>

      <Section title="3) Fiyat / Stok" desc="Listeleme fiyat & stok güncellemesi.">
        <div className="flex flex-wrap gap-2 mb-3">
          <ActBtn onClick={doPsPreview} busy={busy === "psp"} icon={Eye} ghost>Önizleme</ActBtn>
          <ActBtn onClick={doPsSend} busy={busy === "pss"} icon={Upload}>Fiyat/Stok Gönder</ActBtn>
        </div>
        {psPrev && (
          <div className="text-sm">
            <div className="text-gray-700 mb-1">Satır: <b>{psPrev.count}</b></div>
            <div className="border border-gray-200 rounded max-h-56 overflow-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 text-gray-500"><tr>
                  <th className="text-left px-2 py-1">merchantSku</th>
                  <th className="text-right px-2 py-1">fiyat</th>
                  <th className="text-right px-2 py-1">stok</th>
                  <th className="text-left px-2 py-1">ürün</th>
                </tr></thead>
                <tbody>
                  {psPrev.sample?.map((r, i) => (
                    <tr key={i} className="border-t border-gray-100">
                      <td className="px-2 py-1">{r.merchantSku}</td>
                      <td className="px-2 py-1 text-right">{r.price}</td>
                      <td className="px-2 py-1 text-right">{r.stock}</td>
                      <td className="px-2 py-1 truncate">{r.product}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {psRes && (
          <div className="mt-2 text-sm text-gray-700">
            Gönderilen → fiyat: <b>{psRes.sent_price}</b>, stok: <b>{psRes.sent_stock}</b> · ortam: <b>{psRes.env}</b>
          </div>
        )}
      </Section>

      <Section title="4) Sipariş Çek (salt-okunur)" desc="Tarih aralığıyla HB siparişlerini çek.">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <input type="date" value={obegin} onChange={(e) => setObegin(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm" />
          <span className="text-gray-400">→</span>
          <input type="date" value={oend} onChange={(e) => setOend(e.target.value)}
            className="border border-gray-300 rounded-md px-2 py-1.5 text-sm" />
          <ActBtn onClick={doOrders} busy={busy === "ord"} icon={PackageSearch} ghost>Çek</ActBtn>
        </div>
        {orders && <JsonBox label="Siparişler" data={orders} />}
      </Section>
    </div>
  );
}

function ActBtn({ onClick, busy, icon: Icon, ghost, children }) {
  return (
    <button onClick={onClick} disabled={busy}
      className={`inline-flex items-center gap-1.5 text-sm px-3.5 py-2 rounded-md disabled:opacity-50 ${
        ghost ? "border border-orange-300 text-orange-700 hover:bg-orange-50"
              : "bg-orange-600 text-white hover:bg-orange-700"
      }`}>
      {busy ? <Loader2 size={14} className="animate-spin" /> : <Icon size={14} />} {children}
    </button>
  );
}

function JsonBox({ label, data }) {
  return (
    <details className="mt-2">
      <summary className="text-xs text-gray-500 cursor-pointer select-none">{label} (aç/kapat)</summary>
      <pre className="mt-1 text-[11px] bg-gray-900 text-gray-100 rounded p-3 max-h-72 overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}
