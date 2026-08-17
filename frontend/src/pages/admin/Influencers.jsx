/**
 * Influencer CRM & ROI — iki sekme:
 *   1) Influencerlar  → kayıtlı influencer kartları (arama + ekle/düzenle + ROI detay)
 *   2) Ürün Gönderimleri → tüm gönderim geçmişi (kim, ne, ne zaman, paylaşıldı mı) +
 *      "Yeni Gönderim" (influencer seç → ürün seç → stok düş → kargo).
 */
import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Plus, TrendingUp, CheckCircle, Trash2, X,
  Instagram, DollarSign, Truck, Share2, Search, Pencil, Calendar, Music2, Package,
  ClipboardList, ExternalLink, History, Filter, Download,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
const money = (n) => `${(Number(n) || 0).toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} TL`;
const fmtDate = (s) => {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d.getTime())) return String(s).slice(0, 10);
    return d.toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch { return String(s).slice(0, 10); }
};

/* Kampanya/gönderim aksiyonları — hem detay modalı hem gönderim geçmişi aynı davranışı kullanır. */
function makeCampaignActions(reload) {
  return {
    createCargo: async (cid) => {
      try {
        const r = await axios.post(`${API}/influencer-campaigns/${cid}/cargo`, {}, auth());
        toast.success(`Kargo barkodu: ${r.data.cargo_barcode}`);
        reload();
      } catch (e) { toast.error(e.response?.data?.detail || "Kargo oluşturulamadı"); }
    },
    toggleShared: async (c) => {
      try { await axios.put(`${API}/influencer-campaigns/${c.id}`, { shared: !c.shared }, auth()); reload(); }
      catch { toast.error("Güncellenemedi"); }
    },
    markSent: async (cid) => {
      try {
        await axios.put(`${API}/influencer-campaigns/${cid}`, { sent_at: new Date().toISOString(), status: "shipped" }, auth());
        toast.success("Gönderildi olarak işaretlendi"); reload();
      } catch { toast.error("Güncellenemedi"); }
    },
    saveContentUrl: async (cid, url) => {
      try { await axios.put(`${API}/influencer-campaigns/${cid}`, { content_url: url }, auth()); toast.success("İçerik linki kaydedildi"); reload(); }
      catch { toast.error("Kaydedilemedi"); }
    },
    uncommitStock: async (cid) => {
      if (!window.confirm("Bu gönderimin ürünleri stoğa GERİ yüklensin mi?")) return;
      try { await axios.post(`${API}/influencer-campaigns/${cid}/uncommit-products`, {}, auth()); toast.success("Stok geri yüklendi"); reload(); }
      catch (e) { toast.error(e.response?.data?.detail || "Geri alınamadı"); }
    },
    delCampaign: async (cid) => {
      if (!window.confirm("Gönderim silinsin mi? (Düşülen stok varsa otomatik geri yüklenir)")) return;
      await axios.delete(`${API}/influencer-campaigns/${cid}`, auth()); reload();
    },
  };
}

export default function Influencers() {
  const [tab, setTab] = useState("pr"); // 'pr' | 'influencers' | 'shipments'

  return (
    <div className="p-6 w-full" data-testid="influencers-page">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Instagram className="text-pink-600" size={24} /> Influencer / İş Birlikleri
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          PR takip, influencer kayıtları, seeding gönderimleri, kargo otomasyonu ve ROI takibi.
        </p>
      </div>

      {/* Sekmeler */}
      <div className="flex gap-2 border-b mb-5">
        <TabBtn active={tab === "pr"} onClick={() => setTab("pr")} icon={<ClipboardList size={15} />} testid="tab-pr">
          PR Takip
        </TabBtn>
        <TabBtn active={tab === "influencers"} onClick={() => setTab("influencers")} icon={<Instagram size={15} />} testid="tab-influencers">
          Kayıtlı Influencerlar
        </TabBtn>
        <TabBtn active={tab === "shipments"} onClick={() => setTab("shipments")} icon={<Package size={15} />} testid="tab-shipments">
          Ürün Gönderimleri
        </TabBtn>
      </div>

      {tab === "pr" ? <PRTrackTab /> : tab === "influencers" ? <InfluencerListTab /> : <ShipmentsTab />}
    </div>
  );
}

/* ======================= SEKME 0: PR TAKİP =======================
 * Kadir: haftalık PR listesi — her işlem TEK TEK "sipariş gibi" ayrı kart, alt alta.
 * Tarih filtresi + günlük/haftalık/aylık/yıllık sayaç. TikTok/Insta otomatik linkli.
 * Yan panel: bir influencerla geçmiş (ne gönderdik + PR işlemleri). STOK HAREKETİ YOK. */

const PR_STATUS = [
  { v: "beklemede", l: "Beklemede", c: "bg-gray-100 text-gray-600" },
  { v: "iletildi", l: "İletildi", c: "bg-blue-50 text-blue-700" },
  { v: "cevap_bekleniyor", l: "Cevap Bekleniyor", c: "bg-amber-50 text-amber-700" },
  { v: "olumlu", l: "Olumlu", c: "bg-green-50 text-green-700" },
  { v: "olumsuz", l: "Olumsuz", c: "bg-red-50 text-red-700" },
  { v: "gonderildi", l: "Gönderildi", c: "bg-indigo-50 text-indigo-700" },
  { v: "yayinlandi", l: "Yayınlandı", c: "bg-emerald-50 text-emerald-700" },
  { v: "iptal", l: "İptal", c: "bg-gray-100 text-gray-400 line-through" },
];
const prStatusMeta = (v) => PR_STATUS.find((s) => s.v === v) || PR_STATUS[0];

// Kullanıcı adını (@x veya x) tam profil linkine çevirir.
const cleanHandle = (h) => String(h || "").trim().replace(/^@+/, "").replace(/\s+/g, "");
const socialUrl = (kind, h) => {
  const u = cleanHandle(h);
  if (!u) return null;
  if (/^https?:\/\//i.test(h)) return h;
  return kind === "tiktok" ? `https://www.tiktok.com/@${u}` : `https://instagram.com/${u}`;
};

function SocialLinks({ instagram, tiktok, size = 12 }) {
  const ig = socialUrl("instagram", instagram);
  const tk = socialUrl("tiktok", tiktok);
  if (!ig && !tk) return null;
  return (
    <span className="flex items-center gap-2">
      {ig && (
        <a href={ig} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
           className="inline-flex items-center gap-1 text-pink-600 hover:underline">
          <Instagram size={size} /> {cleanHandle(instagram)} <ExternalLink size={size - 3} />
        </a>
      )}
      {tk && (
        <a href={tk} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
           className="inline-flex items-center gap-1 text-gray-800 hover:underline">
          <Music2 size={size} /> {cleanHandle(tiktok)} <ExternalLink size={size - 3} />
        </a>
      )}
    </span>
  );
}

function periodStart(kind) {
  const now = new Date();
  const d = new Date(now);
  if (kind === "today") { d.setHours(0, 0, 0, 0); return d.toISOString().slice(0, 10); }
  if (kind === "week") { const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); return d.toISOString().slice(0, 10); }
  if (kind === "month") return new Date(now.getFullYear(), now.getMonth(), 1).toISOString().slice(0, 10);
  if (kind === "year") return new Date(now.getFullYear(), 0, 1).toISOString().slice(0, 10);
  return "";
}

function PRTrackTab() {
  const [entries, setEntries] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [statusF, setStatusF] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [historyFor, setHistoryFor] = useState(null); // {id, name}

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (q.trim()) params.q = q.trim();
      if (start) params.start_date = start;
      if (end) params.end_date = `${end}T23:59:59.999999`;
      if (statusF) params.status = statusF;
      const r = await axios.get(`${API}/influencer-pr`, { ...auth(), params });
      setEntries(r.data?.entries || []);
      setSummary(r.data?.summary || {});
    } catch {
      toast.error("PR kayıtları yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [q, start, end, statusF]);

  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const del = async (id) => {
    if (!window.confirm("Bu PR kaydı silinsin mi?")) return;
    try { await axios.delete(`${API}/influencer-pr/${id}`, auth()); toast.success("Silindi"); load(); }
    catch { toast.error("Silinemedi"); }
  };

  const quick = (kind) => { setStart(periodStart(kind)); setEnd(""); };

  // Excel'e aktar — ekrandaki AYNI filtreyle (durum/tarih/arama). Auth header gerektiği
  // için blob olarak çekip indiriyoruz (window.open header taşımaz).
  const exportXlsx = async () => {
    try {
      const params = {};
      if (q.trim()) params.q = q.trim();
      if (start) params.start_date = start;
      if (end) params.end_date = `${end}T23:59:59.999999`;
      if (statusF) params.status = statusF;
      const r = await axios.get(`${API}/influencer-pr/export`, { ...auth(), params, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = "pr-listesi.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Excel oluşturulamadı"); }
  };

  return (
    <div data-testid="pr-track-tab">
      {/* Dönem sayaçları */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat icon={<Calendar size={16} />} label="Bugün" value={summary.today ?? 0} color="blue" />
        <Stat icon={<Calendar size={16} />} label="Bu Hafta" value={summary.week ?? 0} color="green" />
        <Stat icon={<Calendar size={16} />} label="Bu Ay" value={summary.month ?? 0} color="blue" />
        <Stat icon={<Calendar size={16} />} label="Bu Yıl" value={summary.year ?? 0} color="green" />
      </div>

      {/* Filtre çubuğu */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="pr-search"
                 placeholder="Influencer, @kullanıcı, not, teklif ara…"
                 className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-black" />
        </div>
        <div className="flex items-center gap-1 text-xs">
          <Filter size={14} className="text-gray-400" />
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="border rounded-lg px-2 py-1.5" data-testid="pr-start" />
          <span className="text-gray-400">–</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="border rounded-lg px-2 py-1.5" data-testid="pr-end" />
        </div>
        <div className="flex gap-1 text-xs">
          {[["today", "Bugün"], ["week", "Hafta"], ["month", "Ay"], ["year", "Yıl"]].map(([k, l]) => (
            <button key={k} onClick={() => quick(k)} className="px-2 py-1.5 border rounded-lg hover:bg-gray-50">{l}</button>
          ))}
          {(start || end) && <button onClick={() => { setStart(""); setEnd(""); }} className="px-2 py-1.5 border rounded-lg text-gray-500 hover:bg-gray-50">Temizle</button>}
        </div>
        <select value={statusF} onChange={(e) => setStatusF(e.target.value)} className="border rounded-lg px-2 py-1.5 text-xs" data-testid="pr-status-filter">
          <option value="">Tüm durumlar</option>
          {PR_STATUS.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
        </select>
        <button onClick={exportXlsx} data-testid="pr-export-btn"
                className="inline-flex items-center gap-2 border px-3 py-2 rounded-lg text-sm hover:bg-gray-50 ml-auto">
          <Download size={15} /> Excel'e Aktar
        </button>
        <button onClick={() => { setEditTarget(null); setShowForm(true); }} data-testid="new-pr-btn"
                className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800">
          <Plus size={16} /> Yeni PR Kaydı
        </button>
      </div>

      {/* İşlem listesi — alt alta, her biri "sipariş gibi" */}
      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : entries.length === 0 ? (
        <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">
          Kayıt yok. "Yeni PR Kaydı" ile ekleyin.
        </div>
      ) : (
        <div className="overflow-x-auto border rounded-xl bg-white" data-testid="pr-list">
          <table className="w-full text-sm whitespace-nowrap">
            <thead className="bg-gray-50 text-[10px] uppercase tracking-wide text-gray-500 text-left">
              <tr>
                {["İsim Soyisim", "Kullanıcı Adı", "Telefon", "Adres", "Ürün", "Beden",
                  "Anlaşma", "Durum", "Tarih", "İletişim", "Teklif", "Cevap", "Follow-up", "Not", ""].map((h, i) => (
                  <th key={i} className="px-3 py-2 font-semibold">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <PRRow key={e.id} e={e}
                       onEdit={() => { setEditTarget(e); setShowForm(true); }}
                       onDelete={() => del(e.id)}
                       onHistory={() => e.influencer_id && setHistoryFor({ id: e.influencer_id, name: e.influencer_name })} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <PRFormModal initial={editTarget} onClose={() => setShowForm(false)}
                     onSaved={() => { setShowForm(false); load(); }} />
      )}
      {historyFor && (
        <HistoryPanel influencerId={historyFor.id} influencerName={historyFor.name}
                      onClose={() => setHistoryFor(null)} />
      )}
    </div>
  );
}

// Basılı PR listesi gibi TABLO satırı (kart yerine) — Kadir: sayfaya yayılan geniş tablo.
function PRRow({ e, onEdit, onDelete, onHistory }) {
  const st = prStatusMeta(e.status);
  const td = "px-3 py-2 align-top";
  return (
    <tr className="border-t hover:bg-gray-50" data-testid={`pr-row-${e.id}`}>
      <td className={`${td} font-medium`}>
        {e.influencer_name || "—"}
        {e.influencer_turu && <span className="ml-1 text-[10px] text-purple-600">({e.influencer_turu})</span>}
      </td>
      <td className={td}><SocialLinks instagram={e.instagram} tiktok={e.tiktok} /></td>
      <td className={`${td} text-gray-600`}>{e.phone || "—"}</td>
      <td className={`${td} whitespace-normal max-w-[220px] text-gray-600`}>{e.adres || "—"}</td>
      <td className={`${td} whitespace-normal max-w-[220px]`}>{e.urun || "—"}</td>
      <td className={td}>{e.beden || "—"}</td>
      <td className={td}>{e.anlasma_sekli || "—"}</td>
      <td className={td}><span className={`text-[10px] px-2 py-0.5 rounded-full ${st.c}`}>{st.l}</span></td>
      <td className={`${td} text-gray-500`}>{fmtDate(e.date)}</td>
      <td className={td}>{e.contact || "—"}</td>
      <td className={td}>{e.offer || "—"}</td>
      <td className={td}>{e.response || "—"}</td>
      <td className={td}>{e.follow_up || "—"}</td>
      <td className={`${td} whitespace-normal max-w-[200px] text-gray-600`}>{e.note || "—"}</td>
      <td className={`${td} whitespace-nowrap`}>
        <div className="flex items-center gap-1">
          {e.influencer_id && (
            <button onClick={onHistory} title="Geçmiş" className="text-gray-400 hover:text-black p-1" data-testid={`pr-history-${e.id}`}><History size={14} /></button>
          )}
          <button onClick={onEdit} title="Düzenle" className="text-gray-400 hover:text-black p-1"><Pencil size={13} /></button>
          <button onClick={onDelete} title="Sil" className="text-gray-400 hover:text-red-600 p-1"><Trash2 size={13} /></button>
        </div>
      </td>
    </tr>
  );
}

function PRFormModal({ initial, onClose, onSaved }) {
  const [infList, setInfList] = useState([]);
  const [form, setForm] = useState({
    influencer_id: initial?.influencer_id || "",
    influencer_name: initial?.influencer_name || "",
    influencer_type: initial?.influencer_type || "",
    date: (initial?.date || new Date().toISOString()).slice(0, 10),
    contact: initial?.contact || "",
    offer: initial?.offer || "",
    response: initial?.response || "",
    status: initial?.status || "beklemede",
    follow_up: initial?.follow_up || "",
    note: initial?.note || "",
    instagram: initial?.instagram || "",
    tiktok: initial?.tiktok || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    (async () => {
      try { const r = await axios.get(`${API}/influencers`, auth()); setInfList(r.data?.influencers || []); }
      catch { /* sessiz */ }
    })();
  }, []);

  // Kayıtlı influencer seçilince isim/tür/insta/tiktok otomatik dolsun (kullanıcı sonra düzenleyebilir).
  const pickInfluencer = (id) => {
    const inf = infList.find((i) => i.id === id);
    setForm((f) => ({
      ...f, influencer_id: id,
      influencer_name: inf?.name || f.influencer_name,
      influencer_type: inf?.platform || f.influencer_type,
      instagram: inf?.instagram || f.instagram,
      tiktok: inf?.tiktok || f.tiktok,
    }));
  };

  const save = async () => {
    if (!form.influencer_name.trim() && !form.influencer_id) return toast.error("Influencer seçin veya adını yazın");
    setSaving(true);
    try {
      const body = { ...form, date: form.date ? `${form.date}T00:00:00` : new Date().toISOString() };
      if (initial?.id) await axios.put(`${API}/influencer-pr/${initial.id}`, body, auth());
      else await axios.post(`${API}/influencer-pr`, body, auth());
      toast.success("Kaydedildi");
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally { setSaving(false); }
  };

  return (
    <Modal title={initial?.id ? "PR Kaydı Düzenle" : "Yeni PR Kaydı"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Kayıtlı influencer (opsiyonel — seçince alanlar dolar)" full>
          <select className="inp" value={form.influencer_id} onChange={(e) => pickInfluencer(e.target.value)} data-testid="pr-inf-select">
            <option value="">— Bağlama / serbest yaz —</option>
            {infList.map((i) => (
              <option key={i.id} value={i.id}>{i.name}{i.instagram ? ` (${i.instagram})` : ""}</option>
            ))}
          </select>
        </Field>
        <Field label="Influencer adı *"><input className="inp" value={form.influencer_name} onChange={(e) => set("influencer_name", e.target.value)} placeholder="İsim" /></Field>
        <Field label="Influencer Türü"><input className="inp" value={form.influencer_type} onChange={(e) => set("influencer_type", e.target.value)} placeholder="Örn. Moda / Mikro / Nano" /></Field>
        <Field label="Instagram (@)"><input className="inp" value={form.instagram} onChange={(e) => set("instagram", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="TikTok (@)"><input className="inp" value={form.tiktok} onChange={(e) => set("tiktok", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="Tarih"><input type="date" className="inp" value={form.date} onChange={(e) => set("date", e.target.value)} /></Field>
        <Field label="Durum">
          <select className="inp" value={form.status} onChange={(e) => set("status", e.target.value)} data-testid="pr-status">
            {PR_STATUS.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
        </Field>
        <Field label="İletişim (nasıl/kanal)"><input className="inp" value={form.contact} onChange={(e) => set("contact", e.target.value)} placeholder="DM / e-posta / telefon" /></Field>
        <Field label="Teklif"><input className="inp" value={form.offer} onChange={(e) => set("offer", e.target.value)} placeholder="Ne teklif edildi" /></Field>
        <Field label="Cevap"><input className="inp" value={form.response} onChange={(e) => set("response", e.target.value)} placeholder="Ne cevap geldi" /></Field>
        <Field label="Follow-up"><input className="inp" value={form.follow_up} onChange={(e) => set("follow_up", e.target.value)} placeholder="Tekrar iletişim / hatırlatma" /></Field>
        <Field label="Not" full><textarea className="inp h-20" value={form.note} onChange={(e) => set("note", e.target.value)} /></Field>
      </div>
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">İptal</button>
        <button onClick={save} disabled={saving} data-testid="pr-save" className="px-4 py-2 text-sm bg-black text-white rounded-lg disabled:opacity-50">
          {saving ? "..." : "Kaydet"}
        </button>
      </div>
    </Modal>
  );
}

function HistoryPanel({ influencerId, influencerName, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    (async () => {
      try { const r = await axios.get(`${API}/influencers/${influencerId}/history`, auth()); setData(r.data); }
      catch { toast.error("Geçmiş yüklenemedi"); }
    })();
  }, [influencerId]);

  return (
    <div className="fixed inset-0 z-[60] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative bg-white w-full max-w-md h-full overflow-y-auto p-5 shadow-xl" onClick={(e) => e.stopPropagation()} data-testid="pr-history-panel">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-bold text-lg flex items-center gap-2"><History size={18} /> {influencerName || "Geçmiş"}</h2>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        {!data ? (
          <div className="py-10 text-center text-gray-400 text-sm">Yükleniyor...</div>
        ) : (
          <>
            <div className="text-xs mb-3"><SocialLinks instagram={data.influencer?.instagram} tiktok={data.influencer?.tiktok} /></div>

            <h3 className="font-semibold text-sm mb-2 flex items-center gap-1"><Package size={14} /> Gönderdiklerimiz ({(data.campaigns || []).length})</h3>
            <div className="space-y-2 mb-5">
              {(data.campaigns || []).length === 0 && <p className="text-xs text-gray-400">Henüz ürün gönderimi yok.</p>}
              {(data.campaigns || []).map((c) => (
                <div key={c.id} className="border rounded-lg p-2.5 text-xs">
                  <div className="flex justify-between"><span className="font-medium">{c.title || "Gönderim"}</span><span className="text-gray-400">{fmtDate(c.created_at)}</span></div>
                  {(c.products || []).length > 0 && (
                    <div className="text-gray-500 mt-1">{(c.products || []).map((p) => `${p.name || p.barcode}${p.qty ? ` ×${p.qty}` : ""}`).join(", ")}</div>
                  )}
                  {c.status && <Badge>{c.status}</Badge>}
                </div>
              ))}
            </div>

            <h3 className="font-semibold text-sm mb-2 flex items-center gap-1"><ClipboardList size={14} /> PR işlemleri ({(data.pr_entries || []).length})</h3>
            <div className="space-y-2">
              {(data.pr_entries || []).length === 0 && <p className="text-xs text-gray-400">Henüz PR işlemi yok.</p>}
              {(data.pr_entries || []).map((e) => (
                <div key={e.id} className="border rounded-lg p-2.5 text-xs">
                  <div className="flex justify-between items-center">
                    <span className={`px-2 py-0.5 rounded-full ${prStatusMeta(e.status).c}`}>{prStatusMeta(e.status).l}</span>
                    <span className="text-gray-400">{fmtDate(e.date)}</span>
                  </div>
                  {e.offer && <div className="mt-1"><span className="text-gray-400">Teklif:</span> {e.offer}</div>}
                  {e.response && <div><span className="text-gray-400">Cevap:</span> {e.response}</div>}
                  {e.note && <div className="text-gray-500 mt-0.5">{e.note}</div>}
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TabBtn({ active, onClick, icon, children, testid }) {
  return (
    <button
      onClick={onClick}
      data-testid={testid}
      className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
        active ? "border-black text-black" : "border-transparent text-gray-500 hover:text-gray-800"
      }`}
    >
      {icon} {children}
    </button>
  );
}

/* ======================= SEKME 1: KAYITLI INFLUENCERLAR ======================= */
function InfluencerListTab() {
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editTarget, setEditTarget] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async (search) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/influencers`, {
        ...auth(), params: (search || "").trim() ? { q: search.trim() } : {},
      });
      setList(r.data?.influencers || []);
    } catch {
      toast.error("Influencerlar yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(""); }, [load]);
  useEffect(() => { const t = setTimeout(() => load(q), 350); return () => clearTimeout(t); }, [q, load]);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="influencer-search"
            placeholder="İsim, @kullanıcı, Instagram, TikTok, telefon, kupon ara…"
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-black"
          />
        </div>
        <button
          onClick={() => { setEditTarget(null); setShowForm(true); }}
          data-testid="new-influencer-btn"
          className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
        >
          <Plus size={16} /> Yeni Influencer
        </button>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : list.length === 0 ? (
        <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">
          {q.trim() ? "Aramayla eşleşen influencer yok." : 'Henüz influencer eklenmedi. "Yeni Influencer" ile başlayın.'}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {list.map((inf) => (
            <div
              key={inf.id}
              data-testid={`influencer-card-${inf.id}`}
              className="relative bg-white border rounded-xl p-4 hover:border-black transition-colors"
            >
              <button
                onClick={(e) => { e.stopPropagation(); setEditTarget(inf); setShowForm(true); }}
                title="Düzenle"
                className="absolute top-3 right-3 text-gray-400 hover:text-black"
                data-testid={`influencer-edit-${inf.id}`}
              >
                <Pencil size={14} />
              </button>
              <button onClick={() => setSelected(inf.id)} className="text-left w-full">
                <div className="flex items-center gap-2 pr-6">
                  <span className="font-semibold">{inf.name}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full ${inf.is_active ? "bg-green-50 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {inf.platform}
                  </span>
                </div>
                <div className="flex flex-col gap-0.5 mt-1 text-xs text-gray-500">
                  {inf.instagram && <span className="flex items-center gap-1"><Instagram size={11} /> {inf.instagram}</span>}
                  {inf.tiktok && <span className="flex items-center gap-1"><Music2 size={11} /> {inf.tiktok}</span>}
                  {!inf.instagram && !inf.tiktok && <span>{inf.handle || "—"}</span>}
                  {inf.birthday && <span className="flex items-center gap-1"><Calendar size={11} /> {fmtDate(inf.birthday)}</span>}
                </div>
                <div className="flex flex-wrap gap-2 mt-3 text-[11px]">
                  {inf.coupon_code && <span className="bg-amber-50 text-amber-700 px-2 py-0.5 rounded">Kupon: {inf.coupon_code}</span>}
                  {inf.aff_id && <span className="bg-blue-50 text-blue-700 px-2 py-0.5 rounded">aff: {inf.aff_id}</span>}
                  <span className="bg-gray-50 text-gray-600 px-2 py-0.5 rounded">{(inf.follower_count || 0).toLocaleString("tr-TR")} takipçi</span>
                  <span className="bg-purple-50 text-purple-700 px-2 py-0.5 rounded" title="Takipçiye göre: Nano/Micro/Makro">{inf.influencer_turu || influencerTuru(inf.follower_count)}</span>
                  {inf.anlasma_sekli && <span className="bg-teal-50 text-teal-700 px-2 py-0.5 rounded">{inf.anlasma_sekli}</span>}
                  {(inf.beden_alt || inf.beden_ust) && <span className="bg-gray-50 text-gray-600 px-2 py-0.5 rounded">Beden {inf.beden_alt || "—"}/{inf.beden_ust || "—"}</span>}
                </div>
              </button>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <InfluencerFormModal
          initial={editTarget}
          onClose={() => { setShowForm(false); setEditTarget(null); }}
          onSaved={() => { setShowForm(false); setEditTarget(null); load(q); }}
        />
      )}
      {selected && <DetailModal influencerId={selected} onClose={() => { setSelected(null); load(q); }} />}
    </div>
  );
}

/* ======================= SEKME 2: ÜRÜN GÖNDERİMLERİ (GEÇMİŞ) ======================= */
function ShipmentsTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all"); // all | shared | pending
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (q.trim()) params.q = q.trim();
      if (filter === "shared") params.shared = true;
      if (filter === "pending") params.shared = false;
      const r = await axios.get(`${API}/influencer-campaigns`, { ...auth(), params });
      setRows(r.data?.campaigns || []);
    } catch {
      toast.error("Gönderimler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [q, filter]);

  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t); }, [load]);

  const act = makeCampaignActions(load);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="shipment-search"
            placeholder="Influencer, gönderim başlığı veya ürün ara…"
            className="w-full border rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-black"
          />
        </div>
        <button
          onClick={() => setShowCreate(true)}
          data-testid="new-shipment-btn"
          className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
        >
          <Plus size={16} /> Yeni Gönderim
        </button>
      </div>

      {/* Filtre */}
      <div className="flex gap-1.5 mb-4">
        {[["all", "Tümü"], ["pending", "Paylaşım Bekleyen"], ["shared", "Paylaşıldı"]].map(([k, lbl]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`text-xs px-3 py-1.5 rounded-full border ${filter === k ? "bg-black text-white border-black" : "bg-white text-gray-600 hover:bg-gray-50"}`}>
            {lbl}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : rows.length === 0 ? (
        <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">
          {q.trim() || filter !== "all"
            ? "Eşleşen gönderim yok."
            : 'Henüz ürün gönderimi yok. "Yeni Gönderim" ile influencer seçip ürün yollayın.'}
        </div>
      ) : (
        <div className="space-y-2">
          {rows.map((c) => <CampaignCard key={c.id} c={c} act={act} showInfluencer />)}
        </div>
      )}

      {showCreate && (
        <CampaignModal
          onClose={() => setShowCreate(false)}
          onCreated={() => { setShowCreate(false); load(); }}
        />
      )}
    </div>
  );
}

/* ======================= INFLUENCER EKLE/DÜZENLE ======================= */
// Kadir: influencer anlaşma şekilleri + türü (takipçiden türetilir).
const ANLASMA_SEKLI = ["Barter", "İş birliği", "PR", "Aylık ücretli", "Açıkta"];
const influencerTuru = (fc) => {
  const n = parseInt(String(fc ?? "").replace(/[^\d]/g, ""), 10) || 0;
  return n >= 100000 ? "Makro" : n >= 10000 ? "Micro" : "Nano";
};

function InfluencerFormModal({ initial, onClose, onSaved }) {
  const isEdit = !!initial;
  const addr = initial?.shipping_address || {};
  const [form, setForm] = useState({
    name: initial?.name || "", platform: initial?.platform || "instagram",
    handle: initial?.handle || "", instagram: initial?.instagram || "", tiktok: initial?.tiktok || "",
    birthday: (initial?.birthday || "").slice(0, 10),
    phone: initial?.phone || "", email: initial?.email || "",
    follower_count: initial?.follower_count || 0,
    coupon_code: initial?.coupon_code || "", aff_id: initial?.aff_id || "",
    commission_rate: initial?.commission_rate || 0,
    anlasma_sekli: initial?.anlasma_sekli || "",
    beden_alt: initial?.beden_alt || "", beden_ust: initial?.beden_ust || "",
    notes: initial?.notes || "",
    address_full_name: addr.full_name || "", address_phone: addr.phone || "",
    il: addr.il || "", ilce: addr.ilce || "", adres: addr.adres || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.name.trim()) return toast.error("İsim gerekli");
    setSaving(true);
    const body = {
      name: form.name, platform: form.platform, handle: form.handle,
      instagram: form.instagram, tiktok: form.tiktok, birthday: form.birthday || null,
      phone: form.phone, email: form.email,
      follower_count: parseInt(String(form.follower_count).replace(/[^\d]/g, ""), 10) || 0,
      coupon_code: form.coupon_code, aff_id: form.aff_id,
      commission_rate: Number(form.commission_rate) || 0,
      anlasma_sekli: form.anlasma_sekli, beden_alt: form.beden_alt, beden_ust: form.beden_ust,
      notes: form.notes,
      shipping_address: {
        full_name: form.address_full_name || form.name, phone: form.address_phone || form.phone,
        il: form.il, ilce: form.ilce, adres: form.adres,
      },
    };
    try {
      if (isEdit) {
        await axios.put(`${API}/influencers/${initial.id}`, body, auth());
        toast.success("Influencer güncellendi");
      } else {
        await axios.post(`${API}/influencers`, body, auth());
        toast.success("Influencer eklendi");
      }
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title={isEdit ? "Influencer Düzenle" : "Yeni Influencer"} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="İsim *"><input data-testid="inf-name" className="inp" value={form.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Birincil Platform">
          <select className="inp" value={form.platform} onChange={(e) => set("platform", e.target.value)}>
            <option value="instagram">Instagram</option>
            <option value="tiktok">TikTok</option>
            <option value="youtube">YouTube</option>
            <option value="x">X</option>
          </select>
        </Field>
        <Field label="Instagram (@)"><input className="inp" value={form.instagram} onChange={(e) => set("instagram", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="TikTok (@)"><input className="inp" value={form.tiktok} onChange={(e) => set("tiktok", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="Doğum Günü"><input type="date" className="inp" value={form.birthday} onChange={(e) => set("birthday", e.target.value)} /></Field>
        <Field label="Takipçi"><input type="text" inputMode="numeric" className="inp" value={form.follower_count} onChange={(e) => set("follower_count", e.target.value)} placeholder="Örn. 125.500" /></Field>
        <Field label="Telefon"><input className="inp" value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="E-posta"><input className="inp" value={form.email} onChange={(e) => set("email", e.target.value)} /></Field>
        <Field label="Kupon Kodu"><input data-testid="inf-coupon" className="inp uppercase" value={form.coupon_code} onChange={(e) => set("coupon_code", e.target.value)} placeholder="MELIS10" /></Field>
        <Field label="aff_id (takip linki)"><input className="inp" value={form.aff_id} onChange={(e) => set("aff_id", e.target.value)} placeholder="melis" /></Field>
        <Field label="Komisyon %"><input type="number" className="inp" value={form.commission_rate} onChange={(e) => set("commission_rate", e.target.value)} /></Field>
        <Field label="Anlaşma Şekli">
          <select className="inp" value={form.anlasma_sekli} onChange={(e) => set("anlasma_sekli", e.target.value)} data-testid="inf-anlasma">
            <option value="">— Seçin —</option>
            {ANLASMA_SEKLI.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Influencer Türü (takipçiden otomatik)">
          <input className="inp bg-gray-50 text-gray-500" value={influencerTuru(form.follower_count)} readOnly
                 title="Nano <10.000 · Micro 10.000–100.000 · Makro 100.000+" />
        </Field>
        <Field label="Beden — Alt"><input className="inp" value={form.beden_alt} onChange={(e) => set("beden_alt", e.target.value)} placeholder="Örn. S / 36" /></Field>
        <Field label="Beden — Üst"><input className="inp" value={form.beden_ust} onChange={(e) => set("beden_ust", e.target.value)} placeholder="Örn. M / 38" /></Field>
      </div>
      <p className="text-xs font-semibold text-gray-500 mt-4 mb-2">Kargo Adresi (seeding için)</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Alıcı Adı (boşsa isim)"><input className="inp" value={form.address_full_name} onChange={(e) => set("address_full_name", e.target.value)} /></Field>
        <Field label="Alıcı Telefon (boşsa telefon)"><input className="inp" value={form.address_phone} onChange={(e) => set("address_phone", e.target.value)} /></Field>
        <Field label="İl"><input className="inp" value={form.il} onChange={(e) => set("il", e.target.value)} /></Field>
        <Field label="İlçe"><input className="inp" value={form.ilce} onChange={(e) => set("ilce", e.target.value)} /></Field>
        <Field label="Adres" full><input className="inp" value={form.adres} onChange={(e) => set("adres", e.target.value)} /></Field>
      </div>
      <Field label="Not / Genel Direktif" full>
        <textarea className="inp h-20" value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Bu influencer'a özel notlar…" />
      </Field>
      <div className="flex justify-end gap-2 mt-5">
        <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">İptal</button>
        <button onClick={save} disabled={saving} data-testid="inf-save" className="px-4 py-2 text-sm bg-black text-white rounded-lg disabled:opacity-50">
          {saving ? "Kaydediliyor..." : "Kaydet"}
        </button>
      </div>
    </Modal>
  );
}

/* ======================= INFLUENCER DETAY (ROI + o kişinin gönderimleri) ======================= */
function DetailModal({ influencerId, onClose }) {
  const [inf, setInf] = useState(null);
  const [roi, setRoi] = useState(null);
  const [showCampaign, setShowCampaign] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, r] = await Promise.all([
        axios.get(`${API}/influencers/${influencerId}`, auth()),
        axios.get(`${API}/influencers/${influencerId}/roi`, auth()),
      ]);
      setInf(d.data);
      setRoi(r.data);
    } catch {
      toast.error("Detay yüklenemedi");
    }
  }, [influencerId]);

  useEffect(() => { load(); }, [load]);

  const act = makeCampaignActions(load);

  if (!inf) return <Modal title="Yükleniyor..." onClose={onClose}><div className="py-8 text-center text-gray-400">...</div></Modal>;

  return (
    <Modal title={`${inf.name} · ${inf.platform}`} wide onClose={onClose}>
      {/* Kimlik satırı */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600 mb-4">
        {inf.instagram && <span className="flex items-center gap-1"><Instagram size={12} /> {inf.instagram}</span>}
        {inf.tiktok && <span className="flex items-center gap-1"><Music2 size={12} /> {inf.tiktok}</span>}
        {inf.phone && <span>☎ {inf.phone}</span>}
        {inf.birthday && <span className="flex items-center gap-1"><Calendar size={12} /> {fmtDate(inf.birthday)}</span>}
        {inf.coupon_code && <span className="text-amber-700">Kupon: {inf.coupon_code}</span>}
      </div>
      {inf.notes && <p className="text-xs bg-stone-50 border rounded-lg p-2 mb-4 whitespace-pre-wrap">{inf.notes}</p>}

      {/* ROI */}
      {roi && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5" data-testid="inf-roi">
          <Stat icon={<DollarSign size={16} />} label="Toplam Maliyet" value={money(roi.cost.total_cost)} color="red" />
          <Stat icon={<TrendingUp size={16} />} label="Ciro" value={money(roi.revenue.revenue)} color="green" />
          <Stat icon={<DollarSign size={16} />} label="Net Kâr" value={money(roi.net_profit)} color={roi.net_profit >= 0 ? "green" : "red"} />
          <Stat icon={<TrendingUp size={16} />} label="ROAS" value={roi.roas != null ? `${roi.roas}x` : "—"} color="blue" />
        </div>
      )}
      {roi && (
        <p className="text-xs text-gray-500 mb-4">
          {roi.revenue.successful_orders} başarılı sipariş · {roi.cost.campaign_count} gönderim · {roi.cost.shared_count} paylaşım · Komisyon: {money(roi.revenue.commission_due)}
        </p>
      )}

      {/* Gönderimler */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-sm">Bu influencer'a gönderimler</h3>
        <button onClick={() => setShowCampaign(true)} data-testid="new-campaign-btn" className="inline-flex items-center gap-1 text-sm border px-3 py-1.5 rounded-lg hover:bg-gray-50">
          <Plus size={14} /> Yeni Gönderim
        </button>
      </div>
      <div className="space-y-2">
        {(inf.campaigns || []).length === 0 && <p className="text-xs text-gray-400 py-3">Henüz gönderim yok. Her ürün gönderimi için ayrı kart açın.</p>}
        {(inf.campaigns || []).map((c) => <CampaignCard key={c.id} c={c} act={act} />)}
      </div>

      {showCampaign && (
        <CampaignModal influencerId={influencerId} onClose={() => setShowCampaign(false)} onCreated={() => { setShowCampaign(false); load(); }} />
      )}
    </Modal>
  );
}

/* ======================= TEK GÖNDERİM KARTI (paylaşılan) ======================= */
function CampaignCard({ c, act, showInfluencer }) {
  return (
    <div className="border rounded-lg p-3" data-testid={`campaign-${c.id}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          {showInfluencer && (
            <div className="text-[11px] text-pink-700 font-medium flex items-center gap-1 truncate">
              <Instagram size={11} /> {c.influencer_name || "—"}{c.influencer_handle ? ` · ${c.influencer_handle}` : ""}
            </div>
          )}
          <span className="font-medium text-sm">{c.title}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge>{c.status}</Badge>
          <Badge tone="cargo">{c.cargo_status}</Badge>
        </div>
      </div>
      <div className="flex flex-wrap gap-3 mt-2 text-[11px] text-gray-500">
        <span>Ücret: {money(c.fee_paid)}</span>
        <span>Ürün: {money(c.product_cost)}</span>
        <span>Kargo: {money(c.cargo_cost)}</span>
        {c.sent_at && <span className="text-gray-700 font-medium">Gönderim: {fmtDate(c.sent_at)}</span>}
        {c.cargo_barcode && <span className="text-blue-600">Barkod: {c.cargo_barcode}</span>}
        {c.cargo_tracking_no && <span className="text-blue-600">Takip: {c.cargo_tracking_no}</span>}
      </div>
      {c.directives && (
        <p className="text-[11px] text-gray-500 mt-2 bg-stone-50 border rounded p-2 whitespace-pre-wrap">
          <b className="text-gray-600">Direktif:</b> {c.directives}
        </p>
      )}
      {(c.sent_products || []).length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 mt-2" data-testid={`sent-products-${c.id}`}>
          {(c.sent_products || []).map((p, pi) => (
            <span key={pi} className="text-[10px] bg-stone-100 border rounded px-1.5 py-0.5">
              {p.name}{p.size ? ` (${p.size})` : ""} ×{p.qty || 1}
            </span>
          ))}
          {c.stock_deducted ? (
            <span className="text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 rounded px-1.5 py-0.5">stok düşüldü ✓</span>
          ) : (
            <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 rounded px-1.5 py-0.5">stok düşülmedi</span>
          )}
        </div>
      )}
      {/* Paylaşıldı tik'i + içerik linki */}
      <div className="flex items-center flex-wrap gap-3 mt-3">
        <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none" data-testid={`shared-toggle-${c.id}`}>
          <input type="checkbox" checked={!!c.shared} onChange={() => act.toggleShared(c)} className="w-4 h-4 accent-green-600" />
          <span className={c.shared ? "text-green-700 font-medium flex items-center gap-1" : "text-gray-600"}>
            {c.shared ? <><CheckCircle size={12} /> Paylaşıldı{c.shared_at ? ` · ${fmtDate(c.shared_at)}` : ""}</> : "Paylaşıldı mı?"}
          </span>
        </label>
        {c.shared && (
          <input
            defaultValue={c.content_url || ""}
            onBlur={(e) => { const v = e.target.value.trim(); if (v !== (c.content_url || "")) act.saveContentUrl(c.id, v); }}
            placeholder="İçerik linki (yapıştır)…"
            className="text-xs border rounded px-2 py-1 flex-1 min-w-[180px]"
          />
        )}
      </div>
      <div className="flex gap-2 mt-3 flex-wrap">
        {!c.sent_at && (
          <button onClick={() => act.markSent(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded hover:bg-gray-50">
            <Share2 size={12} /> Gönderildi İşaretle
          </button>
        )}
        <button onClick={() => act.createCargo(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded hover:bg-gray-50">
          <Truck size={12} /> Kargo Oluştur
        </button>
        {c.stock_deducted && (
          <button onClick={() => act.uncommitStock(c.id)} title="Yanlış seçim/vazgeçme: ürünleri stoğa geri yükler"
            className="text-xs inline-flex items-center gap-1 border border-amber-300 text-amber-700 px-2 py-1 rounded hover:bg-amber-50">
            Stok Geri Al
          </button>
        )}
        <button onClick={() => act.delCampaign(c.id)} className="text-xs inline-flex items-center gap-1 border px-2 py-1 rounded text-red-600 hover:bg-red-50 ml-auto">
          <Trash2 size={12} /> Sil
        </button>
      </div>
    </div>
  );
}

/* Gönderilecek ürün seçici: ürün ara → beden/varyant seç → adet → listeye ekle. */
function ProductPicker({ picked, setPicked }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (q.trim().length < 2) { setResults([]); return; }
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const { data } = await axios.get(`${API}/products`, {
          ...auth(), params: { search: q.trim(), limit: 8, admin_view: 1 },
        });
        setResults(data.products || data || []);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [q]);

  const addVariant = (p, v) => {
    const bc = v?.barcode || p.barcode;
    if (!bc) { toast.error("Bu varyantın barkodu yok"); return; }
    if (picked.some((x) => x.barcode === bc)) { toast.error("Zaten listede"); return; }
    setPicked([...picked, { barcode: bc, name: p.name, size: v?.size || "", stock: v ? v.stock : p.stock, qty: 1 }]);
    setQ(""); setResults([]);
  };

  return (
    <div>
      <input className="inp" value={q} onChange={(e) => setQ(e.target.value)}
        placeholder="Ürün ara (en az 2 harf)..." data-testid="seeding-product-search" />
      {searching && <p className="text-[11px] text-gray-400 mt-1">Aranıyor…</p>}
      {results.length > 0 && (
        <div className="border rounded-lg mt-1 max-h-52 overflow-y-auto divide-y">
          {results.map((p) => (
            <div key={p.id} className="p-2">
              <p className="text-xs font-medium">{p.name}</p>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {(p.variants || []).length > 0 ? (p.variants || []).map((v) => (
                  <button key={v.barcode || v.id} type="button" onClick={() => addVariant(p, v)}
                    disabled={Number(v.stock) <= 0}
                    className="text-[11px] border rounded px-2 py-0.5 hover:bg-gray-50 disabled:opacity-40 disabled:line-through">
                    {v.size || "STD"} · stok {v.stock ?? "?"}
                  </button>
                )) : (
                  <button type="button" onClick={() => addVariant(p, null)}
                    className="text-[11px] border rounded px-2 py-0.5 hover:bg-gray-50">
                    Ekle · stok {p.stock ?? "?"}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
      {picked.length > 0 && (
        <div className="mt-2 space-y-1.5" data-testid="seeding-picked-list">
          {picked.map((it, i) => (
            <div key={it.barcode} className="flex items-center gap-2 bg-gray-50 border rounded px-2 py-1.5 text-xs">
              <span className="flex-1 truncate">{it.name} {it.size && <b>({it.size})</b>}</span>
              <input type="number" min={1} max={it.stock || 99} value={it.qty}
                onChange={(e) => {
                  const qv = Math.max(1, Math.min(Number(e.target.value) || 1, it.stock || 99));
                  setPicked(picked.map((x, xi) => (xi === i ? { ...x, qty: qv } : x)));
                }}
                className="w-14 border rounded px-1.5 py-0.5 text-center" />
              <button type="button" onClick={() => setPicked(picked.filter((_, xi) => xi !== i))}
                className="text-red-500 hover:text-red-700"><Trash2 size={12} /></button>
            </div>
          ))}
          <p className="text-[10px] text-gray-400">Kaydedince bu ürünler gönderime işlenir ve STOKTAN DÜŞÜLÜR.</p>
        </div>
      )}
    </div>
  );
}

/* Yeni gönderim. influencerId verilirse (detaydan) o kişiye; verilmezse (geçmiş sekmesi)
   önce influencer seçtirilir. */
function CampaignModal({ influencerId, onClose, onCreated }) {
  const preset = !!influencerId;
  const [infList, setInfList] = useState([]);
  const [chosenInf, setChosenInf] = useState(influencerId || "");
  const [form, setForm] = useState({ title: "", fee_paid: 0, product_cost: 0, cargo_cost: 0, directives: "" });
  const [picked, setPicked] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  // Geçmiş sekmesinden açıldıysa influencer listesini yükle (seçim için).
  useEffect(() => {
    if (preset) return;
    (async () => {
      try {
        const r = await axios.get(`${API}/influencers`, auth());
        setInfList(r.data?.influencers || []);
      } catch { /* sessiz */ }
    })();
  }, [preset]);

  const save = async () => {
    const infId = influencerId || chosenInf;
    if (!infId) return toast.error("Önce influencer seçin");
    if (!form.title.trim()) return toast.error("Başlık gerekli");
    setSaving(true);
    try {
      const r = await axios.post(`${API}/influencers/${infId}/campaigns`, {
        title: form.title, fee_paid: Number(form.fee_paid) || 0,
        product_cost: Number(form.product_cost) || 0, cargo_cost: Number(form.cargo_cost) || 0,
        directives: form.directives,
      }, auth());
      const cid = r.data?.campaign?.id;
      if (cid && picked.length > 0) {
        await axios.post(`${API}/influencer-campaigns/${cid}/commit-products`, {
          products: picked.map((p) => ({ barcode: p.barcode, qty: p.qty })),
          auto_cost: !(Number(form.product_cost) > 0),
        }, auth());
        toast.success(`Gönderim oluşturuldu — ${picked.length} ürün stoktan düşüldü`);
      } else {
        toast.success("Gönderim oluşturuldu");
      }
      onCreated();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Oluşturulamadı");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Yeni Ürün Gönderimi" onClose={onClose}>
      {!preset && (
        <Field label="Influencer *" full>
          {infList.length === 0 ? (
            <p className="text-xs text-amber-600 py-1">Önce "Kayıtlı Influencerlar" sekmesinden influencer ekleyin.</p>
          ) : (
            <select className="inp" value={chosenInf} onChange={(e) => setChosenInf(e.target.value)} data-testid="ship-inf-select">
              <option value="">— Influencer seçin —</option>
              {infList.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}{i.instagram ? ` (${i.instagram})` : i.handle ? ` (${i.handle})` : ""}
                </option>
              ))}
            </select>
          )}
        </Field>
      )}
      <div className="grid grid-cols-2 gap-3 mt-1">
        <Field label="Başlık *" full><input data-testid="camp-title" className="inp" value={form.title} onChange={(e) => set("title", e.target.value)} placeholder="Örn. Temmuz gönderimi" /></Field>
        <Field label="Ödenen Ücret"><input type="number" className="inp" value={form.fee_paid} onChange={(e) => set("fee_paid", e.target.value)} /></Field>
        <Field label="Ürün Maliyeti (boşsa seçilen ürünlerden otomatik)"><input type="number" className="inp" value={form.product_cost} onChange={(e) => set("product_cost", e.target.value)} /></Field>
        <Field label="Kargo Maliyeti"><input type="number" className="inp" value={form.cargo_cost} onChange={(e) => set("cargo_cost", e.target.value)} /></Field>
      </div>
      <Field label="Gönderilecek Ürünler (beden seçin — kaydetmede stoktan düşer)" full>
        <ProductPicker picked={picked} setPicked={setPicked} />
      </Field>
      <Field label="İçerik Talimatları / Direktif (boşsa 9:16 dikey format standardı otomatik eklenir)" full>
        <textarea className="inp h-24" value={form.directives} onChange={(e) => set("directives", e.target.value)} placeholder="Boş bırakırsanız zorunlu içerik standartları (9:16 dikey format, @facette mention) otomatik eklenir." />
      </Field>
      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-4 py-2 text-sm border rounded-lg">İptal</button>
        <button onClick={save} disabled={saving} data-testid="camp-save" className="px-4 py-2 text-sm bg-black text-white rounded-lg disabled:opacity-50">
          {saving ? "..." : "Gönderim Oluştur"}
        </button>
      </div>
    </Modal>
  );
}

/* ---- küçük yardımcı bileşenler ---- */
function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-start justify-center overflow-y-auto py-10 px-4" onClick={onClose}>
      <div className={`bg-white rounded-xl w-full ${wide ? "max-w-3xl" : "max-w-xl"} p-6`} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-bold text-lg">{title}</h2>
          <button onClick={onClose}><X size={20} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Field({ label, children, full }) {
  return (
    <div className={full ? "col-span-2" : ""}>
      <label className="block text-xs text-gray-500 mb-1">{label}</label>
      {children}
    </div>
  );
}
function Stat({ icon, label, value, color }) {
  const c = { red: "bg-red-50 text-red-700", green: "bg-green-50 text-green-700", blue: "bg-blue-50 text-blue-700" }[color] || "bg-gray-50 text-gray-700";
  return (
    <div className={`rounded-lg p-3 ${c}`}>
      <div className="flex items-center gap-1 text-[11px] opacity-80">{icon} {label}</div>
      <div className="text-lg font-bold mt-0.5">{value}</div>
    </div>
  );
}
function Badge({ children, tone }) {
  const c = tone === "cargo" ? "bg-blue-50 text-blue-600" : "bg-gray-100 text-gray-600";
  return <span className={`text-[10px] px-2 py-0.5 rounded-full ${c}`}>{children}</span>;
}
