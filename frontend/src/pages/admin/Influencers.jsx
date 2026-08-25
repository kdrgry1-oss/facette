/**
 * Influencer CRM & ROI — iki sekme:
 *   1) Influencerlar  → kayıtlı influencer kartları (arama + ekle/düzenle + ROI detay)
 *   2) Ürün Gönderimleri → tüm gönderim geçmişi (kim, ne, ne zaman, paylaşıldı mı) +
 *      "Yeni Gönderim" (influencer seç → ürün seç → stok düş → kargo).
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Plus, TrendingUp, CheckCircle, Trash2, X,
  Instagram, DollarSign, Truck, Share2, Search, Pencil, Calendar, Package,
  ClipboardList, ExternalLink, History, Filter, Download,
  ChevronRight, ChevronDown, Barcode,
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
          Gönderi Takibi
        </TabBtn>
        <TabBtn active={tab === "shipments"} onClick={() => setTab("shipments")} icon={<Package size={15} />} testid="tab-shipments">
          Takvim
        </TabBtn>
        <TabBtn active={tab === "influencers"} onClick={() => setTab("influencers")} icon={<Instagram size={15} />} testid="tab-influencers">
          Kayıtlı Influencerlar
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

// TikTok orijinal glyph (lucide'de marka ikonu yok — inline SVG, currentColor ile renk alır).
function TikTokIcon({ size = 12, className = "" }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" className={className} aria-hidden="true">
      <path d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.09v12.4a2.59 2.59 0 1 1-2.59-2.59c.27 0 .53.04.77.12V9.79a5.7 5.7 0 0 0-.77-.05 5.69 5.69 0 1 0 5.69 5.69V8.9a7.32 7.32 0 0 0 4.3 1.38V7.19a4.28 4.28 0 0 1-3.25-1.37z" />
    </svg>
  );
}

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
          <TikTokIcon size={size} /> {cleanHandle(tiktok)} <ExternalLink size={size - 3} />
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
    if (!window.confirm("Bu gönderi kaydı silinsin mi?")) return;
    try { await axios.delete(`${API}/influencer-pr/${id}`, auth()); toast.success("Silindi"); load(); }
    catch { toast.error("Silinemedi"); }
  };

  // Inline düzenleme (Paylaşma Tarihi / Not / İletişim Tarihi) — kısmi PUT, sonra tazele.
  const patchEntry = async (id, patch) => {
    try { await axios.put(`${API}/influencer-pr/${id}`, patch, auth()); load(); }
    catch { toast.error("Kaydedilemedi"); }
  };
  // Kalem-bazlı "Paylaştı" — yalnız o ürün kaleminin shared'ı (diğer kalemler etkilenmez).
  const patchItemShared = async (id, index, shared) => {
    try { await axios.put(`${API}/influencer-pr/${id}/item-shared`, { index, shared }, auth()); load(); }
    catch { toast.error("Kaydedilemedi"); }
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
      a.href = url; a.download = "gonderi-takibi.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Excel oluşturulamadı"); }
  };

  // Kamyon: PR'daki ürünleri KARGOYA VER — mevcut influencer kargo akışını kullanır
  // (kampanya oluştur → ürünleri işle [STOK DÜŞER] → MNG barkod + takip). PR kaydına işlenir.
  const shipPR = async (e) => {
    if (!e.influencer_id) return toast.error("Kargo için PR kaydı bir kayıtlı influencer'a bağlı olmalı");
    if (!(e.products && e.products.length)) return toast.error("Önce ürün ekleyin (ürünü ara → beden seç)");
    if (e.cargo_barcode) return toast(`Zaten kargolandı · barkod ${e.cargo_barcode}`);
    if (!window.confirm("Bu ürünler kargoya verilsin mi? STOK DÜŞÜLECEK ve MNG barkodu oluşturulacak.")) return;
    const t = toast.loading("Kargo oluşturuluyor…");
    try {
      // İdempotent backend ucu: kampanya → stok düşümü → MNG barkod + takip; gönderim
      // tarihi/durumu PR kaydına işler. Tekrar tıklamada çift stok düşümü YAPMAZ.
      const r = await axios.post(`${API}/influencer-pr/${e.id}/ship`, {}, auth());
      toast.success(`Kargo oluşturuldu · barkod ${r.data?.cargo_barcode || "—"} · stok düşüldü`, { id: t });
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Kargo oluşturulamadı", { id: t });
    }
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
          <table className="w-full text-sm min-w-[920px]">
            <thead className="bg-gray-50 text-[10px] uppercase tracking-wide text-gray-500 text-left">
              <tr>
                {["Influencer", "İletişim", "Ürün", "Beden", "Gönderim Tarihi",
                  "Gönderim Durumu", "Paylaştı", "Not", "İşlemler"].map((h, i) => (
                  <th key={i} className="px-2 py-2 font-semibold whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <PRRow key={e.id} e={e}
                       onEdit={() => { setEditTarget(e); setShowForm(true); }}
                       onDelete={() => del(e.id)}
                       onShip={() => shipPR(e)}
                       onPatch={patchEntry}
                       onItemShared={patchItemShared}
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

// Ürün kalemi thumbnail'ı + hover büyük önizleme (yeni npm YOK — createPortal + fixed div).
// Görsel yoksa/kırıksa nötr gri placeholder (kırık görsel gösterilmez).
function PRThumb({ src, name }) {
  const [err, setErr] = useState(false);
  const [pv, setPv] = useState(null); // {top,left}
  const show = !!src && !err;
  const onEnter = (ev) => {
    if (!show) return;
    const r = ev.currentTarget.getBoundingClientRect();
    // Sağda yer yoksa sola aç (kırpılmasın).
    const openLeft = r.right + 220 > window.innerWidth;
    setPv({ top: Math.max(8, Math.min(r.top - 80, window.innerHeight - 224)), left: openLeft ? r.left - 212 : r.right + 8 });
  };
  return (
    <span className="relative shrink-0" onMouseEnter={onEnter} onMouseLeave={() => setPv(null)}>
      {show ? (
        <img src={src} alt={name || ""} loading="lazy" onError={() => setErr(true)}
          className="w-7 h-7 rounded object-cover bg-gray-100 border border-gray-200" data-testid="pr-thumb" />
      ) : (
        <span className="w-7 h-7 rounded bg-gray-100 border border-gray-200 block" aria-hidden data-testid="pr-thumb-empty" />
      )}
      {pv && show && createPortal(
        <div style={{ position: "fixed", top: pv.top, left: pv.left, zIndex: 90 }}
          className="pointer-events-none border border-gray-200 rounded-lg shadow-2xl bg-white p-1" data-testid="pr-thumb-preview">
          <img src={src} alt={name || ""} className="w-[200px] h-[200px] object-cover rounded" />
        </div>, document.body)}
    </span>
  );
}

// Gönderi Takibi satırı (Excel düzeni): görünür sütunlar + çoklu ürün kalemleri +
// detaya-basınca (expand) profil alanları + inline düzenlenebilir Paylaşma Tarihi/Not/İletişim Tarihi.
function PRRow({ e, onEdit, onDelete, onHistory, onShip, onPatch, onItemShared }) {
  const [open, setOpen] = useState(false);
  const st = prStatusMeta(e.status);
  const td = "px-2 py-2 align-top";
  const items = Array.isArray(e.products) && e.products.length ? e.products : null;
  const canShip = (items && e.influencer_id);
  const barcoded = !!e.cargo_barcode;
  const platform = e.platform || (e.instagram ? "İnstagram" : e.tiktok ? "Tiktok" : "—");
  const uname = e.handle || e.instagram || e.tiktok || "—";

  // İnline kaydet: dokunulmadıysa PUT etme.
  const saveField = (key, val) => { if ((e[key] || "") !== (val || "")) onPatch(e.id, { [key]: val }); };

  return (
    <>
      <tr className="border-t hover:bg-gray-50/60" data-testid={`pr-row-${e.id}`}>
        {/* Influencer + expand */}
        <td className={`${td} whitespace-nowrap`}>
          <button onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 font-medium text-gray-900 hover:underline" data-testid={`pr-expand-${e.id}`}>
            {open ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
            {e.influencer_name || "—"}
          </button>
        </td>
        {/* İletişim (platform) */}
        <td className={`${td} whitespace-nowrap`}>
          <span className="text-gray-900">{platform}</span>
          <div className="mt-0.5"><SocialLinks instagram={e.instagram} tiktok={e.tiktok} /></div>
        </td>
        {/* Ürün (çoklu kalem) — solda thumbnail; ürün adı TEK SATIR ve TAM (kırpma YOK).
            Sütun içeriğe göre genişler; yer için Not + tarih inputları daraltıldı. */}
        <td className={td}>
          {items ? (
            <div className="space-y-1">
              {items.map((p, i) => (
                <div key={i} className="flex items-center gap-1.5 h-7">
                  <PRThumb src={p.image} name={p.name || p.barcode} />
                  <span className="text-gray-900 whitespace-nowrap" title={p.name || p.barcode}>{p.name || p.barcode}</span>
                  {(p.barkod || barcoded) && <span title={`Barkod: ${p.barkod || e.cargo_barcode}`} className="inline-flex items-center text-green-700 bg-green-50 rounded px-1 py-0.5 text-[9px] shrink-0"><Barcode size={10} className="mr-0.5" />Barkod</span>}
                </div>
              ))}
            </div>
          ) : <span className="whitespace-nowrap" title={e.urun || ""}>{e.urun || "—"}</span>}
        </td>
        {/* Beden (çoklu kalem) — ürün satırlarıyla HİZALI (h-7) */}
        <td className={td}>
          {items ? <div className="space-y-1">{items.map((p, i) => <div key={i} className="h-7 flex items-center text-gray-900">{p.size || "—"}</div>)}</div> : (e.beden || "—")}
        </td>
        {/* Gönderim Tarihi (çoklu kalem) — hizalı */}
        <td className={`${td} whitespace-nowrap text-gray-900`}>
          {items ? <div className="space-y-1">{items.map((p, i) => <div key={i} className="h-7 flex items-center">{p.gonderim_tarihi ? fmtDate(p.gonderim_tarihi) : (e.shipped_at ? fmtDate(e.shipped_at) : "—")}</div>)}</div>
                 : (e.shipped_at ? fmtDate(e.shipped_at) : "—")}
        </td>
        {/* Gönderim Durumu — sipariş listesi gibi rozet + inline değiştir */}
        <td className={`${td} whitespace-nowrap`}>
          <select value={e.status || "beklemede"} onChange={(ev) => onPatch(e.id, { status: ev.target.value })}
                  className={`text-[11px] rounded-full px-2 py-1 border-0 focus:outline-none cursor-pointer ${st.c}`} data-testid={`pr-status-cell-${e.id}`}>
            {PR_STATUS.map((s) => <option key={s.v} value={s.v}>{s.l}</option>)}
          </select>
        </td>
        {/* Paylaştı — KALEM BAZLI (her ürün AYRI); Beden/Gönderim Tarihi ile hizalı (h-7) */}
        <td className={td}>
          {items ? (
            <div className="space-y-1">
              {items.map((p, i) => (
                <label key={i} className="h-7 flex items-center gap-1 cursor-pointer">
                  <input type="checkbox" checked={!!p.shared}
                         onChange={(ev) => onItemShared(e.id, i, ev.target.checked)}
                         className="w-4 h-4 accent-black" data-testid={`pr-item-shared-${e.id}-${i}`} />
                  <span className="text-[10px] text-gray-600">{p.shared ? "Evet" : "Hayır"}</span>
                </label>
              ))}
            </div>
          ) : <span className="text-[11px] text-gray-400">—</span>}
        </td>
        {/* Not — inline text (düzenlenebilir) */}
        <td className={td}>
          <input type="text" defaultValue={e.note || ""} onBlur={(ev) => saveField("note", ev.target.value)} placeholder="Not…"
                 className="border rounded px-1.5 py-1 text-xs w-[92px] focus:outline-none focus:border-black" data-testid={`pr-note-${e.id}`} />
        </td>
        {/* İşlemler: Barkod Çıkart / Düzenle / Sil (+ Geçmiş) */}
        <td className={`${td} whitespace-nowrap`}>
          <div className="flex items-center gap-1">
            {canShip && (
              barcoded
                ? <span className="inline-flex items-center text-green-700 bg-green-50 rounded px-1 py-1" title={`Barkod çıkarıldı · ${e.cargo_barcode}`}><Barcode size={14} /></span>
                : <button onClick={onShip} title="Barkod Çıkart — stok düşer + MNG kargo barkodu oluşur"
                          className="inline-flex items-center text-indigo-600 hover:text-indigo-800 border border-indigo-200 rounded px-1.5 py-1"
                          data-testid={`pr-ship-${e.id}`}><Barcode size={15} /></button>
            )}
            {e.influencer_id && (
              <button onClick={onHistory} title="Geçmiş" className="text-gray-400 hover:text-black p-1" data-testid={`pr-history-${e.id}`}><History size={14} /></button>
            )}
            <button onClick={onEdit} title="Düzenle" className="text-gray-400 hover:text-black p-1" data-testid={`pr-edit-${e.id}`}><Pencil size={13} /></button>
            <button onClick={onDelete} title="Sil" className="text-gray-400 hover:text-red-600 p-1" data-testid={`pr-del-${e.id}`}><Trash2 size={13} /></button>
          </div>
        </td>
      </tr>
      {open && (
        <tr className="bg-gray-50/70 border-t" data-testid={`pr-detail-${e.id}`}>
          <td colSpan={9} className="px-4 py-3">
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-xs">
              <div><span className="text-gray-400">Kullanıcı Adı: </span><span className="font-medium text-gray-900">{uname}</span></div>
              <div><span className="text-gray-400">Influencer Türü: </span><span className="font-medium text-gray-900">{e.influencer_turu || "—"}</span></div>
              <div><span className="text-gray-400">İş Birliği Türü: </span><span className="font-medium text-gray-900">{e.anlasma_sekli || "—"}</span></div>
              <div><span className="text-gray-400">Telefon: </span><span className="font-medium text-gray-900">{e.phone || "—"}</span></div>
              <div><span className="text-gray-400">İletişim (kanal): </span><span className="font-medium text-gray-900">{e.contact || "—"}</span></div>
              <div><span className="text-gray-400">Teklif: </span><span className="text-gray-900">{e.offer || "—"}</span></div>
              <div><span className="text-gray-400">Cevap: </span><span className="text-gray-900">{e.response || "—"}</span></div>
              <div><span className="text-gray-400">Follow-up: </span><span className="text-gray-900">{e.follow_up || "—"}</span></div>
              {e.adres && <div className="w-full"><span className="text-gray-400">Adres: </span><span className="text-gray-900">{e.adres}</span></div>}
              {e.cargo_barcode && <div className="w-full"><span className="text-gray-400">Kargo barkodu: </span><span className="font-mono text-gray-800">{e.cargo_barcode}</span>{e.cargo_tracking_no ? <span className="text-gray-400"> · Takip: {e.cargo_tracking_no}</span> : null}</div>}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function PRFormModal({ initial, onClose, onSaved }) {
  const [infList, setInfList] = useState([]);
  const [products, setProducts] = useState(Array.isArray(initial?.products) ? initial.products : []);
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
    urun: initial?.urun || "",
    beden: initial?.beden || "",
    anlasma_sekli: initial?.anlasma_sekli || "",
    phone: initial?.phone || "",
    adres: initial?.adres || "",
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
    const sa = inf?.shipping_address || {};
    const adr = [sa.adres, sa.ilce, sa.il].filter(Boolean).join(", ");
    // Kadir: SADECE kimlik/iletişim otomatik dolsun (isim/insta/tiktok/telefon/adres).
    // Tür/anlaşma/beden/teklif/cevap/durum vb. her kayıtta DEĞİŞEBİLİR → otomatik doldurulmaz.
    setForm((f) => ({
      ...f, influencer_id: id,
      influencer_name: inf?.name || f.influencer_name,
      instagram: inf?.instagram || f.instagram,
      tiktok: inf?.tiktok || f.tiktok,
      phone: inf?.phone || f.phone,
      adres: adr || f.adres,
    }));
  };

  const save = async () => {
    if (!form.influencer_name.trim() && !form.influencer_id) return toast.error("Influencer seçin veya adını yazın");
    setSaving(true);
    try {
      const body = { ...form, products, beden: "", urun: "", date: form.date ? `${form.date}T00:00:00` : new Date().toISOString() };
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
        <Field label="Telefon"><input className="inp" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="05..." /></Field>
        <Field label="Anlaşma Şekli">
          <select className="inp" value={form.anlasma_sekli} onChange={(e) => set("anlasma_sekli", e.target.value)} data-testid="pr-anlasma">
            <option value="">— Seçin —</option>
            {ANLASMA_SEKLI.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Ürün & Beden (ürünü ara → bedenini seç; birden çok eklenebilir)" full>
          <ProductPicker picked={products} setPicked={setProducts} />
        </Field>
        <Field label="Adres" full><input className="inp" value={form.adres} onChange={(e) => set("adres", e.target.value)} placeholder="Kargo adresi" /></Field>
        <Field label="Gönderim Durumu">
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

  const removeInf = async (inf) => {
    if (!window.confirm(`"${inf.name}" kaydı silinsin mi? (Geri alınamaz)`)) return;
    try {
      await axios.delete(`${API}/influencers/${inf.id}`, auth());
      toast.success("Influencer silindi");
      load(q);
    } catch {
      toast.error("Silinemedi");
    }
  };

  const exportRegistry = async () => {
    try {
      const r = await axios.get(`${API}/influencer-registry/export`, { ...auth(), params: q.trim() ? { q: q.trim() } : {}, responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = "kayitli-influencerlar.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Excel oluşturulamadı"); }
  };

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
        <div className="flex items-center gap-2">
          <button onClick={exportRegistry} data-testid="registry-export-btn"
            className="inline-flex items-center gap-2 border px-3 py-2 rounded-lg text-sm hover:bg-gray-50">
            <Download size={15} /> Excel'e Aktar
          </button>
          <button
            onClick={() => { setEditTarget(null); setShowForm(true); }}
            data-testid="new-influencer-btn"
            className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
          >
            <Plus size={16} /> Yeni Influencer
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : list.length === 0 ? (
        <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">
          {q.trim() ? "Aramayla eşleşen influencer yok." : 'Henüz influencer eklenmedi. "Yeni Influencer" ile başlayın.'}
        </div>
      ) : (
        <div className="border rounded-xl overflow-x-auto bg-white">
          <table className="w-full text-sm min-w-[1100px]">
            <thead>
              <tr className="bg-gray-50 text-gray-600 text-left text-xs uppercase tracking-wide">
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">İsim Soyisim</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Kullanıcı Adı</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Platform</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Influencer Türü</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Telefon</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Adres</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">İş Birliği Türü</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Beden Üst</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Beden Alt</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap">Not</th>
                <th className="px-3 py-2.5 font-semibold whitespace-nowrap text-right">İşlemler</th>
              </tr>
            </thead>
            <tbody>
              {list.map((inf) => {
                const uname = inf.handle || inf.instagram || inf.tiktok || "—";
                const adres = inf.adres || (inf.shipping_address && inf.shipping_address.adres) || "—";
                return (
                  <tr key={inf.id} data-testid={`influencer-row-${inf.id}`} className="border-t hover:bg-gray-50/60">
                    <td className="px-3 py-2.5 whitespace-nowrap">
                      <button onClick={() => setSelected(inf.id)} className="font-medium text-gray-900 hover:underline text-left" title="Detay">
                        {inf.name}
                      </button>
                      {inf.is_active === false && <span className="ml-2 text-[10px] bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded">pasif</span>}
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{uname}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.platform || "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.influencer_turu || influencerTuru(inf.follower_count)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.phone || "—"}</td>
                    <td className="px-3 py-2.5 max-w-[220px] truncate text-gray-900" title={adres}>{adres}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.anlasma_sekli || "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.beden_ust || "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-gray-900">{inf.beden_alt || "—"}</td>
                    <td className="px-3 py-2.5 max-w-[240px] truncate text-gray-900" title={inf.notes || ""}>{inf.notes || "—"}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap text-right">
                      <div className="inline-flex items-center gap-1.5">
                        <button
                          onClick={() => { setEditTarget(inf); setShowForm(true); }}
                          title="Düzenle" data-testid={`influencer-edit-${inf.id}`}
                          className="text-gray-400 hover:text-black p-1"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => removeInf(inf)}
                          title="Sil" data-testid={`influencer-del-${inf.id}`}
                          className="text-gray-400 hover:text-red-600 p-1"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
/* ===== GÖNDERİM TAKVİMİ (Ürün Gönderimleri sekmesi) — veri: influencer_pr ===== */
const CAL_AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];
const CAL_GUN = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const _pad2 = (n) => String(n).padStart(2, "0");
const _ymd = (dt) => `${dt.getFullYear()}-${_pad2(dt.getMonth() + 1)}-${_pad2(dt.getDate())}`;
const _startOfWeek = (dt) => { const d = new Date(dt); const wd = (d.getDay() + 6) % 7; d.setDate(d.getDate() - wd); d.setHours(0, 0, 0, 0); return d; };
// Kaydın takvim tarihi: kalem gonderim_tarihi → shipped_at → (eski) date → created_at.
// İletişim tarihi (date) alanı UI'dan kalktı; tarihsiz kayıtlar created_at'e düşer.
const _prEvDate = (e) => {
  const items = Array.isArray(e.products) ? e.products : [];
  const g = items.map((p) => p && p.gonderim_tarihi).find(Boolean);
  return String(g || e.shipped_at || e.date || e.created_at || "").slice(0, 10);
};

function CalEventCard({ e, onOpen }) {
  const st = prStatusMeta(e.status);
  const uname = e.handle || e.instagram || e.tiktok || "";
  const items = Array.isArray(e.products) ? e.products : [];
  return (
    <button onClick={() => onOpen && onOpen(e)} data-testid={`cal-event-${e.id}`}
      className="w-full text-left border rounded-lg p-2 hover:border-black transition-colors bg-white">
      <div className="flex items-center gap-1.5">
        <span className="font-medium text-gray-900 text-xs truncate">{e.influencer_name || "—"}</span>
        {uname && <span className="text-[10px] text-gray-500 truncate">{uname}</span>}
        <span className={`ml-auto text-[9px] px-1.5 py-0.5 rounded-full shrink-0 ${st.c}`}>{st.l}</span>
      </div>
      {items.length > 0 && (
        <div className="flex items-center gap-1 mt-1.5 flex-wrap">
          {items.slice(0, 4).map((p, i) => (
            p.image
              ? <img key={i} src={p.image} alt={p.name || ""} title={`${p.name || ""}${p.size ? " · " + p.size : ""}`} className="w-6 h-6 rounded object-cover border border-gray-200" />
              : <span key={i} className="w-6 h-6 rounded bg-gray-100 border border-gray-200" title={p.name || ""} />
          ))}
          {items.length > 4 && <span className="text-[10px] text-gray-500">+{items.length - 4}</span>}
        </div>
      )}
    </button>
  );
}

function ShipmentCalendar({ entries }) {
  const [view, setView] = useState("aylik"); // gunluk | haftalik | aylik | yillik
  const [anchor, setAnchor] = useState(() => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; });
  const [dayModal, setDayModal] = useState(null); // {key, list}
  const [detail, setDetail] = useState(null);      // tek etkinlik detayı

  const byDay = useMemo(() => {
    const m = {};
    for (const e of entries || []) {
      const k = _prEvDate(e);
      if (!k) continue;
      (m[k] = m[k] || []).push(e);
    }
    return m;
  }, [entries]);
  const byMonth = useMemo(() => {
    const m = {};
    for (const e of entries || []) { const k = _prEvDate(e).slice(0, 7); if (k) (m[k] = m[k] || []).push(e); }
    return m;
  }, [entries]);

  const shift = (dir) => {
    const d = new Date(anchor);
    if (view === "gunluk") d.setDate(d.getDate() + dir);
    else if (view === "haftalik") d.setDate(d.getDate() + dir * 7);
    else if (view === "aylik") d.setMonth(d.getMonth() + dir);
    else d.setFullYear(d.getFullYear() + dir);
    setAnchor(d);
  };
  const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); setAnchor(d); };

  const title = view === "gunluk" ? `${anchor.getDate()} ${CAL_AY[anchor.getMonth()]} ${anchor.getFullYear()}`
    : view === "haftalik" ? (() => { const s = _startOfWeek(anchor); const e = new Date(s); e.setDate(s.getDate() + 6); return `${s.getDate()} ${CAL_AY[s.getMonth()]} – ${e.getDate()} ${CAL_AY[e.getMonth()]} ${e.getFullYear()}`; })()
    : view === "aylik" ? `${CAL_AY[anchor.getMonth()]} ${anchor.getFullYear()}`
    : `${anchor.getFullYear()}`;

  const todayKey = _ymd(new Date());

  // AY ızgarası hücreleri
  const monthCells = useMemo(() => {
    const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
    const lead = (first.getDay() + 6) % 7; // Pzt=0
    const start = new Date(first); start.setDate(first.getDate() - lead);
    return Array.from({ length: 42 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  }, [anchor]);

  const weekCells = useMemo(() => {
    const s = _startOfWeek(anchor);
    return Array.from({ length: 7 }, (_, i) => { const d = new Date(s); d.setDate(s.getDate() + i); return d; });
  }, [anchor]);

  const openDay = (key) => { const list = byDay[key] || []; setDayModal({ key, list }); };

  return (
    <div data-testid="shipment-calendar">
      {/* Başlık + görünüm toggle + navigasyon */}
      <div className="flex items-center gap-2 mb-4 flex-wrap">
        <div className="inline-flex rounded-lg border overflow-hidden text-xs">
          {[["gunluk", "Günlük"], ["haftalik", "Haftalık"], ["aylik", "Aylık"], ["yillik", "Yıllık"]].map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} data-testid={`cal-view-${k}`}
              className={`px-3 py-1.5 font-medium ${view === k ? "bg-black text-white" : "bg-white text-gray-700 hover:bg-gray-50"}`}>{l}</button>
          ))}
        </div>
        <div className="flex items-center gap-1 ml-auto">
          <button onClick={() => shift(-1)} className="p-1.5 border rounded-lg hover:bg-gray-50" title="Önceki" data-testid="cal-prev"><ChevronRight size={16} className="rotate-180" /></button>
          <div className="text-sm font-semibold text-gray-900 min-w-[150px] text-center">{title}</div>
          <button onClick={() => shift(1)} className="p-1.5 border rounded-lg hover:bg-gray-50" title="Sonraki" data-testid="cal-next"><ChevronRight size={16} /></button>
          <button onClick={today} className="px-3 py-1.5 border rounded-lg text-xs font-medium hover:bg-gray-50" data-testid="cal-today">Bugün</button>
        </div>
      </div>

      {/* AYLIK */}
      {view === "aylik" && (
        <div className="border rounded-xl overflow-hidden">
          <div className="grid grid-cols-7 bg-gray-50 text-[11px] font-semibold text-gray-500">
            {CAL_GUN.map((g) => <div key={g} className="px-2 py-2 text-center">{g}</div>)}
          </div>
          <div className="grid grid-cols-7">
            {monthCells.map((d, i) => {
              const key = _ymd(d);
              const inMonth = d.getMonth() === anchor.getMonth();
              const list = byDay[key] || [];
              return (
                <button key={i} onClick={() => list.length && openDay(key)} data-testid={`cal-day-${key}`}
                  className={`relative min-h-[74px] border-t border-l p-1.5 pt-7 text-left ${inMonth ? "bg-white" : "bg-gray-50/60"} ${list.length ? "hover:bg-amber-50 cursor-pointer" : "cursor-default"}`}>
                  {/* Gün no — HER hücrede SABİT sol-üst (absolute); içerik/rozet konumunu ETKİLEMEZ.
                      Bugün kırmızı daire aynı 20px kutuda → diğer numaralarla BİREBİR aynı konum. */}
                  <span className={`absolute top-1 left-1 text-[11px] w-5 h-5 inline-flex items-center justify-center rounded-full ${key === todayKey ? "bg-red-600 text-white font-semibold" : inMonth ? "text-gray-900" : "text-gray-400"}`}>{d.getDate()}</span>
                  {/* İşlem-sayısı rozeti — SABİT sağ-üst (absolute) */}
                  {list.length > 0 && (
                    <span className="absolute top-1 right-1 text-[9px] leading-none bg-black text-white rounded-full min-w-[18px] h-[18px] inline-flex items-center justify-center px-1">{list.length}</span>
                  )}
                  {/* İçerik — numaranın ALTINDA (pt-7 sabit boşluk), numarayı İTMEZ */}
                  {list.length > 0 && (
                    <div className="space-y-0.5">
                      {list.slice(0, 2).map((e) => <div key={e.id} className="text-[10px] leading-4 text-gray-900 truncate">{e.influencer_name || "—"}</div>)}
                      {list.length > 2 && <div className="text-[9px] leading-4 text-gray-500">+{list.length - 2} daha</div>}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* HAFTALIK */}
      {view === "haftalik" && (
        <div className="grid grid-cols-1 sm:grid-cols-7 gap-2">
          {weekCells.map((d, i) => {
            const key = _ymd(d);
            const list = byDay[key] || [];
            return (
              <div key={i} className="border rounded-lg p-2 min-h-[120px]">
                <div className={`text-[11px] font-semibold mb-2 ${key === todayKey ? "text-red-600" : "text-gray-500"}`}>{CAL_GUN[i]} · {d.getDate()} {CAL_AY[d.getMonth()].slice(0, 3)}</div>
                <div className="space-y-1.5">
                  {list.length === 0 ? <div className="text-[10px] text-gray-300">—</div>
                    : list.map((e) => <CalEventCard key={e.id} e={e} onOpen={setDetail} />)}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* GÜNLÜK */}
      {view === "gunluk" && (() => {
        const key = _ymd(anchor);
        const list = byDay[key] || [];
        return (
          <div className="space-y-2">
            {list.length === 0 ? <div className="border border-dashed rounded-xl py-16 text-center text-gray-500">Bu gün gönderim yok.</div>
              : list.map((e) => <CalEventCard key={e.id} e={e} onOpen={setDetail} />)}
          </div>
        );
      })()}

      {/* YILLIK */}
      {view === "yillik" && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {CAL_AY.map((ay, mi) => {
            const key = `${anchor.getFullYear()}-${_pad2(mi + 1)}`;
            const cnt = (byMonth[key] || []).length;
            const isNowMonth = key === todayKey.slice(0, 7);   // içinde bulunduğumuz ay → kırmızı
            return (
              <button key={mi} onClick={() => { const d = new Date(anchor.getFullYear(), mi, 1); setAnchor(d); setView("aylik"); }}
                data-testid={`cal-month-${mi + 1}`}
                className={`border rounded-lg p-4 text-left hover:border-black transition-colors ${isNowMonth ? "ring-2 ring-red-500 border-red-500" : ""} ${cnt ? "bg-white" : "bg-gray-50/60"}`}>
                <div className={`text-sm font-semibold ${isNowMonth ? "text-red-600" : "text-gray-900"}`}>{ay}</div>
                <div className="text-xs text-gray-500 mt-1">{cnt ? `${cnt} gönderim` : "—"}</div>
              </button>
            );
          })}
        </div>
      )}

      {/* Gün detay modalı */}
      {dayModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" onClick={() => setDayModal(null)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative bg-white rounded-xl w-full max-w-lg max-h-[80vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()} data-testid="cal-day-modal">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div className="text-sm font-semibold text-gray-900">{dayModal.key} — {dayModal.list.length} gönderim</div>
              <button onClick={() => setDayModal(null)} className="text-gray-400 hover:text-black"><X size={18} /></button>
            </div>
            <div className="p-3 space-y-2 overflow-y-auto">
              {dayModal.list.map((e) => <CalDetail key={e.id} e={e} />)}
            </div>
          </div>
        </div>
      )}
      {detail && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/40" />
          <div className="relative bg-white rounded-xl w-full max-w-md shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div className="text-sm font-semibold text-gray-900">Gönderim Detayı</div>
              <button onClick={() => setDetail(null)} className="text-gray-400 hover:text-black"><X size={18} /></button>
            </div>
            <div className="p-3"><CalDetail e={detail} /></div>
          </div>
        </div>
      )}
    </div>
  );
}

function CalDetail({ e }) {
  const st = prStatusMeta(e.status);
  const uname = e.handle || e.instagram || e.tiktok || "";
  const items = Array.isArray(e.products) ? e.products : [];
  return (
    <div className="border rounded-lg p-3">
      <div className="flex items-center gap-2">
        <span className="font-medium text-gray-900">{e.influencer_name || "—"}</span>
        {uname && <span className="text-xs text-gray-500">{uname}</span>}
        <span className={`ml-auto text-[10px] px-2 py-0.5 rounded-full ${st.c}`}>{st.l}</span>
      </div>
      <div className="text-[11px] text-gray-500 mt-0.5">Tarih: {_prEvDate(e) || "—"}</div>
      <div className="mt-2 space-y-1.5">
        {items.length === 0 ? <div className="text-xs text-gray-400">Ürün yok</div>
          : items.map((p, i) => (
            <div key={i} className="flex items-center gap-2">
              {p.image ? <img src={p.image} alt={p.name || ""} className="w-8 h-8 rounded object-cover border border-gray-200" />
                : <span className="w-8 h-8 rounded bg-gray-100 border border-gray-200" />}
              <span className="text-xs text-gray-900 truncate">{p.name || p.barcode}</span>
              {p.size && <span className="text-[11px] text-gray-600 ml-auto">Beden: {p.size}</span>}
            </div>
          ))}
      </div>
    </div>
  );
}

function ShipmentsTab() {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/influencer-pr`, { ...auth() });
      setEntries(r.data?.entries || []);
    } catch {
      toast.error("Gönderimler yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const exportCalendar = async () => {
    try {
      const r = await axios.get(`${API}/influencer-pr/calendar-export`, { ...auth(), responseType: "blob" });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url; a.download = "gonderim-takvimi.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Excel oluşturulamadı"); }
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
        <div className="text-sm text-gray-500">Gönderim takvimi — kime ne zaman ne gönderildiği (Gönderi Takibi kayıtları).</div>
        <div className="flex items-center gap-2">
          <button onClick={exportCalendar} data-testid="calendar-export-btn"
            className="inline-flex items-center gap-2 border px-3 py-2 rounded-lg text-sm hover:bg-gray-50">
            <Download size={15} /> Excel'e Aktar
          </button>
          <button
            onClick={() => setShowCreate(true)}
            data-testid="new-shipment-btn"
            className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-800"
          >
            <Plus size={16} /> Yeni Gönderim
          </button>
        </div>
      </div>

      {loading ? (
        <div className="text-gray-400 text-sm py-12 text-center">Yükleniyor...</div>
      ) : (
        <ShipmentCalendar entries={entries} />
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
// Excel "Kayıtlı Influencer" seçenekleri (dropdown). Serbest-metin alanlar kişi tarafından dolar.
const ANLASMA_SEKLI = ["Barter", "PR", "Ücretli İş Birliği"];       // İş Birliği Türü
const PLATFORM_OPTS = ["İnstagram", "Tiktok"];                       // Platform
const INF_TURU_BASE = ["Mikro", "Makro", "Nano/UGC", "Mid-Tier"];   // Influencer Türü
const BEDEN_OPTS = ["XXS", "XS", "S", "M", "L", "XL"];              // Beden Üst / Alt
const influencerTuru = (fc) => {
  const n = parseInt(String(fc ?? "").replace(/[^\d]/g, ""), 10) || 0;
  return n >= 100000 ? "Makro" : n >= 10000 ? "Micro" : "Nano";
};

// TR 81 il — adresten İl/İlçe best-effort çıkarımı için (MNG kargo barkodu İl/İlçe ister).
const TR_ILLER = ["Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya", "Artvin", "Aydın", "Balıkesir", "Bilecik", "Bingöl", "Bitlis", "Bolu", "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır", "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep", "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Isparta", "Mersin", "İstanbul", "İzmir", "Kars", "Kastamonu", "Kayseri", "Kırklareli", "Kırşehir", "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Kahramanmaraş", "Mardin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Rize", "Sakarya", "Samsun", "Siirt", "Sinop", "Sivas", "Tekirdağ", "Tokat", "Trabzon", "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray", "Bayburt", "Karaman", "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan", "Iğdır", "Yalova", "Karabük", "Kilis", "Osmaniye", "Düzce"];
const _trNorm = (s) => String(s || "").toLocaleLowerCase("tr")
  .replace(/i̇/g, "i").replace(/ı/g, "i").replace(/ş/g, "s").replace(/ğ/g, "g")
  .replace(/ü/g, "u").replace(/ö/g, "o").replace(/ç/g, "c").trim();

// Adresten İl/İlçe çıkar (best-effort). "…Kadıköy/İstanbul" veya adreste geçen il adı.
function parseIlIlce(adres) {
  const s = String(adres || "").trim();
  if (!s) return { il: "", ilce: "" };
  let il = "", ilce = "";
  const m = s.match(/([A-Za-zÇĞİÖŞÜçğıöşü.\s]+?)\s*\/\s*([A-Za-zÇĞİÖŞÜçğıöşü.\s]+?)\s*$/);
  if (m) {
    const cand = m[2].trim();
    const prov = TR_ILLER.find((p) => _trNorm(p) === _trNorm(cand) || _trNorm(cand).endsWith(_trNorm(p)));
    if (prov) { il = prov; ilce = m[1].trim().split(/\s+/).slice(-1)[0]; }
  }
  if (!il) {
    const ns = _trNorm(s); let best = -1;
    for (const p of TR_ILLER) { const pos = ns.lastIndexOf(_trNorm(p)); if (pos > best) { best = pos; il = p; } }
    if (best < 0) il = "";
  }
  if (il && !ilce) {
    const re = new RegExp("([A-Za-zÇĞİÖŞÜçğıöşü.]+)\\s*[\\/, ]\\s*" + il.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    const mm = s.match(re);
    if (mm) ilce = mm[1].trim();
  }
  ilce = String(ilce || "").replace(/[.,]/g, "").trim();
  return { il, ilce };
}

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
    influencer_turu: initial?.influencer_turu || "",
    beden_alt: initial?.beden_alt || "", beden_ust: initial?.beden_ust || "",
    notes: initial?.notes || "",
    address_full_name: addr.full_name || "", address_phone: addr.phone || "",
    il: addr.il || "", ilce: addr.ilce || "", adres: initial?.adres || addr.adres || "",
  });
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  // Influencer Türü seçenekleri: Excel tabanı + backend'in eklediği özel tipler (tekilleştirilmiş).
  const [turuTypes, setTuruTypes] = useState(INF_TURU_BASE);
  const mergeTuru = (extra) => {
    const seen = new Set();
    return [...INF_TURU_BASE, ...(extra || [])].filter((t) => {
      const k = String(t).toLowerCase();
      if (!t || seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  };
  useEffect(() => {
    axios.get(`${API}/influencer-types`, auth())
      .then((r) => setTuruTypes(mergeTuru(r.data?.types)))
      .catch(() => setTuruTypes(INF_TURU_BASE));
  }, []);
  const addTuruType = async () => {
    const name = window.prompt("Yeni influencer türü:");
    if (!name || !name.trim()) return;
    try {
      const r = await axios.post(`${API}/influencer-types`, { name: name.trim() }, auth());
      setTuruTypes(r.data?.types || turuTypes);
      set("influencer_turu", name.trim());
    } catch { toast.error("Tip eklenemedi"); }
  };

  const save = async () => {
    if (!form.name.trim()) return toast.error("İsim gerekli");
    setSaving(true);
    const body = {
      // handle formdan KALKTI → Instagram (yoksa TikTok) handle olarak kullanılır (ekranlar bozulmasın).
      name: form.name, platform: form.platform, handle: form.handle || form.instagram || form.tiktok || "",
      instagram: form.instagram, tiktok: form.tiktok, birthday: form.birthday || null,
      phone: form.phone, email: form.email,
      follower_count: parseInt(String(form.follower_count).replace(/[^\d]/g, ""), 10) || 0,
      coupon_code: form.coupon_code, aff_id: form.aff_id,
      commission_rate: Number(form.commission_rate) || 0,
      anlasma_sekli: form.anlasma_sekli,
      influencer_turu: form.influencer_turu || influencerTuru(form.follower_count),
      beden_alt: form.beden_alt, beden_ust: form.beden_ust,
      notes: form.notes,
      adres: form.adres,   // Excel "Adres" (serbest metin) — üst düzey alan (liste sütunu)
      shipping_address: {
        // Alıcı Adı alanı KALKTI → her zaman influencer'ın İsim Soyisim'i.
        full_name: form.name, phone: form.phone,   // alıcı telefonu = influencer ana telefonu (ayrı alan yok)
        il: form.il, ilce: form.ilce, adres: form.adres,   // kargo akışı için de yaz (senkron)
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
        <Field label="İsim Soyisim *"><input data-testid="inf-name" className="inp" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Ad Soyad" /></Field>
        <Field label="Platform">
          <select data-testid="inf-platform" className="inp" value={form.platform} onChange={(e) => set("platform", e.target.value)}>
            <option value="">— Seçin —</option>
            {PLATFORM_OPTS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Field>
        <Field label="Instagram (@)"><input data-testid="inf-handle" className="inp" value={form.instagram} onChange={(e) => set("instagram", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="TikTok (@) (opsiyonel)"><input className="inp" value={form.tiktok} onChange={(e) => set("tiktok", e.target.value)} placeholder="@kullanici" /></Field>
        <Field label="Doğum Günü"><input type="date" className="inp" value={form.birthday} onChange={(e) => set("birthday", e.target.value)} /></Field>
        <Field label="Telefon"><input className="inp" value={form.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
        <Field label="İş Birliği Türü">
          <select className="inp" value={form.anlasma_sekli} onChange={(e) => set("anlasma_sekli", e.target.value)} data-testid="inf-anlasma">
            <option value="">— Seçin —</option>
            {ANLASMA_SEKLI.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </Field>
        <Field label="Influencer Türü">
          <div className="flex gap-1">
            <select className="inp flex-1" value={form.influencer_turu} onChange={(e) => set("influencer_turu", e.target.value)} data-testid="inf-turu">
              <option value="">— Seçin —</option>
              {turuTypes.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <button type="button" onClick={addTuruType} title="Yeni tip ekle" className="px-3 border rounded-lg hover:bg-gray-50">+</button>
          </div>
        </Field>
        <Field label="Beden Üst">
          <select className="inp" value={form.beden_ust} onChange={(e) => set("beden_ust", e.target.value)} data-testid="inf-beden-ust">
            <option value="">— Seçin —</option>
            {BEDEN_OPTS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </Field>
        <Field label="Beden Alt">
          <select className="inp" value={form.beden_alt} onChange={(e) => set("beden_alt", e.target.value)} data-testid="inf-beden-alt">
            <option value="">— Seçin —</option>
            {BEDEN_OPTS.map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
        </Field>
        <Field label="Adres" full>
          <textarea data-testid="inf-adres" className="inp h-16" value={form.adres}
            onChange={(e) => {
              const v = e.target.value;
              const g = parseIlIlce(v);   // adresten İl/İlçe çıkar (best-effort, yalnız boş alanları doldur)
              setForm((f) => ({ ...f, adres: v, il: f.il || g.il, ilce: f.ilce || g.ilce }));
            }}
            placeholder="Kargo/teslim adresi (ör. … Mah. … Sok. No:2 Kadıköy/İstanbul)" />
        </Field>
      </div>
      <p className="text-xs font-semibold text-gray-500 mt-4 mb-2">Kargo Detayı (MNG barkodu için İl/İlçe — Adres'ten otomatik dolar, düzenlenebilir; alıcı adı=İsim Soyisim, telefon=Telefon)</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="İl"><input className="inp" value={form.il} onChange={(e) => set("il", e.target.value)} data-testid="inf-il" /></Field>
        <Field label="İlçe"><input className="inp" value={form.ilce} onChange={(e) => set("ilce", e.target.value)} data-testid="inf-ilce" /></Field>
      </div>
      <Field label="Not" full>
        <textarea data-testid="inf-not" className="inp h-20" value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Bu influencer'a özel notlar…" />
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
        {inf.tiktok && <span className="flex items-center gap-1"><TikTokIcon size={12} /> {inf.tiktok}</span>}
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
        <div className="flex items-center gap-2">
          <button
            onClick={async () => {
              try {
                const r = await axios.get(`${API}/influencer-pr/export`, { ...auth(), params: { influencer_id: influencerId }, responseType: "blob" });
                const url = URL.createObjectURL(r.data);
                const a = document.createElement("a");
                a.href = url; a.download = "influencer-pr-rapor.xlsx"; a.click();
                URL.revokeObjectURL(url);
              } catch { toast.error("Rapor oluşturulamadı"); }
            }}
            className="inline-flex items-center gap-1 text-sm border px-3 py-1.5 rounded-lg hover:bg-gray-50" title="Bu influencer'ın PR işlemlerini Excel indir">
            <Download size={14} /> PR Rapor
          </button>
          <button onClick={() => setShowCampaign(true)} data-testid="new-campaign-btn" className="inline-flex items-center gap-1 text-sm border px-3 py-1.5 rounded-lg hover:bg-gray-50">
            <Plus size={14} /> Yeni Gönderim
          </button>
        </div>
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
