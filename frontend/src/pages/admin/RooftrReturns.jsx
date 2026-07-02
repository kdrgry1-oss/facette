import { useState, useEffect, useCallback, Fragment } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, Search, ChevronDown, ChevronUp, CreditCard, Banknote, Truck, Package, Download, CheckCircle, XCircle, FileText } from "lucide-react";
import MultiSelect from "../../components/admin/MultiSelect";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL;

// TÜM sipariş durumları — order_statuses.py kataloğuyla birebir (iade sayfasında da hepsi seçilebilir)
const STATUS_OPTS = [
  { value: "pending", label: "Onay Bekliyor" },
  { value: "awaiting_payment", label: "Ödeme Bekleniyor (Havale/EFT)" },
  { value: "payment_notified", label: "Ödeme Bildirimi Alındı" },
  { value: "confirmed", label: "Onaylandı" },
  { value: "preparing", label: "Hazırlanıyor" },
  { value: "processing", label: "İşleme Alındı" },
  { value: "ready_to_ship", label: "Kargoya Hazır" },
  { value: "shipped", label: "Kargoya Verildi" },
  { value: "in_transit", label: "Taşınıyor" },
  { value: "out_for_delivery", label: "Dağıtımda" },
  { value: "delivered", label: "Teslim Edildi" },
  { value: "undelivered", label: "Teslim Edilemedi" },
  { value: "return_requested", label: "İade Talebi Alındı" },
  { value: "return_approved", label: "İade Onaylandı" },
  { value: "return_rejected", label: "İade Reddedildi" },
  { value: "return_in_transit", label: "İade Kargoda" },
  { value: "returned", label: "İade Tamamlandı" },
  { value: "partial_refunded", label: "Kısmi İade Yapıldı" },
  { value: "refunded", label: "İade Bedeli Ödendi" },
  { value: "cancelled", label: "İptal Edildi" },
];
const STATUS_LABEL = Object.fromEntries(STATUS_OPTS.map((s) => [s.value, s.label]));
const STATUS_CLS = {}; // durum renkleri kaldırıldı — tüm durumlar nötr görünür

// 6 AŞAMALI operasyonel iade akışı — "Tüm İadeler" yok, "Kısmi İade" ayrı sekme DEĞİL.
// Her hane bir/birkaç order status'üne map'lenir; 5. hane refunded + partial_refunded'ı birlikte gösterir.
// "Kısmi İade Yapıldı" durum açılır menüsünde elle seçilebilir kalır. Sayaçlar status_counts'tan gelir.
const ALL_RETURN_STATUSES = ["return_requested", "return_in_transit", "returned", "return_approved", "refunded", "partial_refunded", "return_rejected"];
const RETURN_TABS = [
  { key: "",                          label: "Tüm İadeler",       statuses: ALL_RETURN_STATUSES },
  { key: "return_requested",          label: "Talep Oluşturulan", statuses: ["return_requested"] },
  { key: "return_in_transit",         label: "İade Kargoda",      statuses: ["return_in_transit"] },
  { key: "returned,return_requested", label: "Aksiyon Bekleyen",  statuses: ["returned", "return_requested"] },
  { key: "return_approved",           label: "Onaylananlar",      statuses: ["return_approved"] },
  { key: "refunded,partial_refunded", label: "İade Ödemeleri",    statuses: ["refunded", "partial_refunded"] },
  { key: "return_rejected",           label: "Reddedilenler",     statuses: ["return_rejected"] },
];

const PAYMENT_OPTS = [
  { value: "", label: "Tüm Ödeme Tipleri" },
  { value: "bank_transfer", label: "Havale / EFT" },
  { value: "credit_card", label: "Kredi Kartı" },
  { value: "cash_on_delivery", label: "Kapıda Ödeme" },
];
const payIcon = (m) =>
  m === "bank_transfer" ? <Banknote size={13} /> :
  m === "cash_on_delivery" ? <Truck size={13} /> :
  <CreditCard size={13} />;

const fmtTL = (v) => Number(v || 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " TL";
const fmtDate = (s) => {
  if (!s) return "—";
  try { return new Date(s).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" }); }
  catch { return String(s).slice(0, 10); }
};

export default function RooftrReturns({ embedded = false, gpStart = "085490", onGiderCreated }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pulling, setPulling] = useState(false);
  const [redating, setRedating] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [statusCounts, setStatusCounts] = useState({});
  const [paymentCounts, setPaymentCounts] = useState({});
  const [totalReturns, setTotalReturns] = useState(0);
  const [busyId, setBusyId] = useState("");
  const [exporting, setExporting] = useState(false);
  const [expandedId, setExpandedId] = useState(null);
  const [perms, setPerms] = useState([]);
  const [wf, setWf] = useState(null); // iade işlem akışı modal'ı
  const [selItems, setSelItems] = useState({}); // açılır detayda tiklenen kalemler: { "orderId::index": true }
  const [cargoSel, setCargoSel] = useState({}); // kargo satırı tiklendi mi: { orderId: true }
  const [freeShipFee, setFreeShipFee] = useState(0); // ücretsiz-kargo mahsup tutarı (ayarlardan)
  // Tek kaynak: durum listesi Ayarlar → Sipariş Durumları'ndan beslenir (görünürlük + özel durumlar dahil).
  const [statusOpts, setStatusOpts] = useState(STATUS_OPTS);        // dropdown (yalnız "görünür" olanlar)
  const [statusLabelMap, setStatusLabelMap] = useState(STATUS_LABEL); // tüm etiketler (pasif olanlar da)
  const toggleItem = (rid, i) => setSelItems((s) => { const k = `${rid}::${i}`; const n = { ...s }; if (n[k]) delete n[k]; else n[k] = true; return n; });
  const toggleCargo = (rid) => setCargoSel((s) => { const n = { ...s }; if (n[rid]) delete n[rid]; else n[rid] = true; return n; });
  const selCount = (rid) => Object.keys(selItems).filter((k) => k.startsWith(`${rid}::`)).length;

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
  // Durum kataloğunu tek kaynaktan çek (Ayarlar). Hata olursa hardcoded fallback kalır.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/settings/order-statuses`, auth());
        const all = r.data?.statuses || [];
        if (all.length) {
          setStatusLabelMap(Object.fromEntries(all.map((s) => [s.key, s.label])));
          setStatusOpts(all.filter((s) => s.active).map((s) => ({ value: s.key, label: s.label })));
        }
      } catch { /* hardcoded fallback */ }
    })();
  }, []);
  const lbl = (s) => statusLabelMap[s] || STATUS_LABEL[s] || s;

  // Arama debounce (350ms)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      if (paymentFilter) params.append("payment", paymentFilter);
      if (debounced) params.append("search", debounced);
      const res = await axios.get(`${API}/admin/rooftr/return-orders?${params}`, auth());
      setRows(res.data.orders || []);
      setFreeShipFee(Number(res.data.free_ship_fee) || 0);
      setStatusCounts(res.data.status_counts || {});
      setPaymentCounts(res.data.payment_counts || {});
      setTotalReturns(res.data.total_returns || 0);
    } catch (e) {
      console.error(e);
      toast.error(e.response?.data?.detail || "İade siparişleri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, paymentFilter, debounced]);

  useEffect(() => { load(); }, [load]);

  // Rooftr'dan siparişleri çek (iade olanlar orders'a düşer, sonra listeyi yenile)
  const pullFromRooftr = async () => {
    setPulling(true);
    toast.info("Rooftr'dan siparişler çekiliyor — bu işlem birkaç dakika sürebilir…");
    try {
      const res = await axios.post(
        `${API}/integrations/rooftr/orders/import?days=365&pages=20&limit=100`,
        {},
        auth()
      );
      if (res.data?.success === false) {
        // Backend gerçek WS hatasını message + error_detail ile döndürür
        toast.error(res.data.message || "Rooftr'dan sipariş çekilemedi.");
      } else {
        toast.success(res.data.message || "Rooftr siparişleri çekildi");
      }
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Rooftr'dan çekme başarısız. WS yetki kodu / Sipariş Servisi iznini kontrol edin.");
    } finally {
      setPulling(false);
    }
  };

  // Tüm siparişlerin TARİHİ'ni Rooftr'daki gerçek SiparisTarihi'ne çek.
  // Zaman aşımına takılmamak için backend'i parça parça (5 sayfa) döngüyle çağırır.
  const refreshDates = async () => {
    if (redating || pulling) return;
    setRedating(true);
    let page = 1, totalFixed = 0;
    try {
      for (let guard = 0; guard < 60; guard++) {
        const res = await axios.post(
          `${API}/admin/rooftr/orders/refresh-dates?page=${page}&per_pages=5`,
          {},
          auth()
        );
        const d = res.data || {};
        if (d.success === false) {
          toast.error(d.message || "Tarih güncelleme başarısız.", { id: "redate" });
          break;
        }
        totalFixed += d.fixed || 0;
        toast.info(`Tarihler güncelleniyor… ${totalFixed} sipariş düzeltildi`, { id: "redate" });
        if (!d.has_more) {
          toast.success(`Tamamlandı — ${totalFixed} siparişin tarihi gerçek tarihine çekildi.`, { id: "redate" });
          break;
        }
        page = d.next_page || page + 5;
      }
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || e.response?.data?.message || "Tarih güncelleme başarısız.", { id: "redate" });
    } finally {
      setRedating(false);
    }
  };

  // İade siparişlerini Excel'e aktar (görseldeki kolon düzeni — backend openpyxl üretir)
  const exportExcel = async () => {
    setExporting(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.append("status", statusFilter);
      if (paymentFilter) params.append("payment", paymentFilter);
      if (debounced) params.append("search", debounced);
      const res = await fetch(`${API}/admin/rooftr/return-orders/export?${params.toString()}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "iade-siparisleri.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Excel indirildi");
    } catch (e) {
      toast.error("Excel aktarımı başarısız");
    } finally {
      setExporting(false);
    }
  };

  // Sipariş durumunu değiştir (mevcut endpoint — bildirim de buradan gider)
  const changeStatus = async (row, newStatus) => {
    if (newStatus === row.status) return;
    setBusyId(row.id);
    const prev = row.status;
    setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, status: newStatus } : r)));
    try {
      await axios.put(`${API}/orders/${row.id}/status?status=${encodeURIComponent(newStatus)}`, {}, auth());
      toast.success(`Durum güncellendi: ${lbl(newStatus)}`);
    } catch (e) {
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, status: prev } : r)));
      toast.error(e.response?.data?.detail || "Durum güncellenemedi");
    } finally {
      setBusyId("");
    }
  };

  // Yetkiler (RBAC) — butonları yetkiye göre göster
  useEffect(() => {
    axios.get(`${API}/admin/me/permissions`, auth())
      .then((r) => setPerms(r.data?.permissions || []))
      .catch(() => {});
  }, []);
  const can = (k) => perms.includes("*") || perms.includes(k);

  // İade işlem akışı: Rooftr siparişini köprüle (customer_returns üret) → tutar önizleme → modal
  const openWorkflow = async (row, mode = "approve") => {
    try {
      setBusyId(row.id);
      const br = await axios.post(`${API}/admin/rooftr/returns/${row.id}/open`, {}, auth());
      const returnId = br.data?.return_id;
      if (!returnId) throw new Error("bridge");
      // Açılır detayda seçili kalem(ler) varsa iade tutarını onların NET toplamından hesapla.
      // ÖNEMLİ: TÜM kalemler seçiliyse bu TAM İADE'dir → override GÖNDERME; backend ödenen
      // tutarı (kargo DAHİL gerçek genel toplam) baz alır. Override sadece GERÇEK kısmi
      // seçimde (bazı kalemler, bazıları değil) gönderilir — yoksa kargo iki kez düşer.
      const itemCount = (row.items || []).length;
      const selIdx = (row.items || []).map((_, i) => i).filter((i) => selItems[`${row.id}::${i}`]);
      const isPartialSelection = selIdx.length > 0 && selIdx.length < itemCount;
      const selAmount = isPartialSelection ? Math.round(selIdx.reduce(
        (a, i) => a + (Number(row.items[i].qty) || 1) * (Number(row.items[i].price) || 0), 0
      ) * 100) / 100 : 0;
      const returnedNet = selAmount > 0 ? selAmount : null;
      // Kısmi onayda seçilen kalemler backend'e KİMLİKLERİYLE gönderilir (approve kaydına
      // yazılır) ki gider pusulası sonradan kesilse bile onaylanan kalemlere düzenlensin.
      const selIdents = isPartialSelection
        ? selIdx.map((i) => row.items[i]).filter(Boolean)
            .map((it) => ({ barcode: it.barcode || "", name: it.name || "", size: it.size || "", color: it.color || "" }))
        : [];
      // Kargo: liste ekranındaki "Kargoyu müşteriden kes" işaretliyse kargo bedeli iade
      // tutarından mahsup edilir (kusur müşteride); işaretli değilse kargo da tam iade edilir
      // (mağaza üstlenir). Elle "kusur" seçimi yok — bu checkbox tek karar noktasıdır.
      const fault = cargoSel[row.id] ? "customer" : "store";
      let preview = null;
      try {
        const q = `fault=${fault}${returnedNet != null ? `&returned_net=${returnedNet}` : ""}`;
        const pv = await axios.get(`${API}/orders/returns/${returnId}/refund-preview?${q}`, auth());
        preview = pv.data?.breakdown || null;
      } catch { /* önizleme alınamazsa modal yine açılır */ }
      setWf({
        row, returnId, status: br.data?.status || "created", fault,
        preview, returnedNet,
        selIdx: isPartialSelection ? selIdx : [], selIdents,
        finalAmount: preview ? preview.auto_refund : (returnedNet ?? 0),
        edited: false, note: "",
        loading: false, rejectReason: "", reship: false,
        showReject: mode === "reject",
      });
    } catch (e) {
      toast.error(e.response?.data?.detail || "İade işlem akışı açılamadı");
    } finally { setBusyId(""); }
  };
  const wfApprove = async () => {
    if (!wf) return;
    setWf((m) => ({ ...m, loading: true }));
    try {
      const body = { fault: wf.fault, note: wf.note };
      if (wf.returnedNet != null) body.returned_net = wf.returnedNet;
      if (wf.edited) body.refund_amount = Number(wf.finalAmount);
      if (wf.selIdx?.length) {
        body.item_indexes = wf.selIdx;
        body.selected_items = wf.selIdents || [];
      }
      const res = await axios.post(`${API}/orders/returns/${wf.returnId}/approve`, body, auth());
      toast.success(`İade onaylandı · ${fmtTL(res.data?.refund_amount)}`);
      setWf((m) => ({ ...m, status: "approved", loading: false }));
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Onaylanamadı"); setWf((m) => ({ ...m, loading: false })); }
  };
  const wfReject = async () => {
    if (!wf) return;
    if (!wf.rejectReason.trim()) { toast.error("Ret sebebi zorunludur"); return; }
    setWf((m) => ({ ...m, loading: true }));
    try {
      const res = await axios.post(`${API}/orders/returns/${wf.returnId}/reject`,
        { reason: wf.rejectReason.trim(), reship: !!wf.reship }, auth());
      toast.success(res.data?.reship_code ? `Reddedildi · Geri gönderim: ${res.data.reship_code}` : "İade reddedildi");
      setWf(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Reddedilemedi"); setWf((m) => ({ ...m, loading: false })); }
  };
  // wfGider / wfPay kaldırıldı: modaldaki "Gider Pusulası" ve "İade Bedeli Öde"
  // butonları kaldırıldı. Gider pusulası satırdaki belge ikonundan (handleSiteGider),
  // "İade Bedeli Ödendi" işaretlemesi ise Durum açılır menüsünden yapılır.



  // Satır-içi gider pusulası (Trendyol ile ORTAK seri): siparişi köprüle → gider pusulası
  // (tracking_no = ortak başlangıç no gpStart) → parent yazdırma modalını aç + sayacı +1 ilerlet.
  const handleSiteGider = async (r) => {
    try {
      setBusyId(r.id);
      const br = await axios.post(`${API}/admin/rooftr/returns/${r.id}/open`, {}, auth());
      const returnId = br.data?.return_id;
      if (!returnId) throw new Error("bridge");
      const trackingNo = String(gpStart || "").trim();
      // Kısmi gider pusulası: açılır detayda seçili kalem index'leri (hiç seçim yoksa tüm sipariş)
      const selIdx = Object.keys(selItems)
        .filter((k) => k.startsWith(`${r.id}::`) && selItems[k])
        .map((k) => parseInt(k.split("::")[1], 10))
        .filter((n) => !Number.isNaN(n));
      const includeCargo = !!cargoSel[r.id];
      const body = { tracking_no: trackingNo };
      if (selIdx.length) {
        body.item_indexes = selIdx;
        // Index kaymasına dayanıklı kimlik eşlemesi: customer_returns kaydı (idempotent
        // bridge) ekrandaki listeden farklıysa backend barcode/ad+beden+renk ile eşler.
        body.selected_items = selIdx
          .map((i) => (r.items || [])[i])
          .filter(Boolean)
          .map((it) => ({ barcode: it.barcode || "", name: it.name || "", size: it.size || "", color: it.color || "" }));
      }
      if (includeCargo) body.include_cargo = true;
      const res = await axios.post(`${API}/orders/returns/${returnId}/gider-pusulasi`, body, auth());
      const gp = res.data?.gider_pusulasi;
      toast.success(`Gider pusulası: ${gp?.display_number || trackingNo}`);
      if (gp && onGiderCreated) onGiderCreated({ ...gp, assigned_no: trackingNo });
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gider pusulası oluşturulamadı");
    } finally { setBusyId(""); }
  };

  const wfCanAct = can("returns.approve") || can("returns.reject") || can("returns.expense_note") || can("returns.refund_pay");

  // Bu iade daha önce karara bağlandı mı? (modal'da Onayla/Reddet'i soluklaştırmak için)
  const wfDecided = wf
    ? ((wf.status === "approved" || ["return_approved", "refunded", "partial_refunded"].includes(wf.row.status))
        ? "approved"
        : (wf.row.status === "return_rejected" ? "rejected" : null))
    : null;

  return (
    <div className={embedded ? "" : "p-4"}>
      {/* Üst bar: çek butonu + özet */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="text-sm text-gray-600">
          İade / kısmi iade durumundaki siparişler.
          {totalReturns > 0 && <span className="ml-1 font-medium text-gray-800">Toplam {totalReturns} iade siparişi.</span>}
        </div>
        <button
          onClick={pullFromRooftr}
          disabled={pulling}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-600 text-white text-sm font-bold hover:bg-orange-700 disabled:opacity-60"
        >
          <RefreshCw size={15} className={pulling ? "animate-spin" : ""} />
          {pulling ? "Çekiliyor…" : "Siparişleri Çek"}
        </button>
        <button
          onClick={refreshDates}
          disabled={redating || pulling}
          title="Tüm siparişlerin tarihini Rooftr'daki gerçek sipariş tarihine günceller"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-600 text-white text-sm font-bold hover:bg-slate-700 disabled:opacity-60"
        >
          <RefreshCw size={15} className={redating ? "animate-spin" : ""} />
          {redating ? "Tarihler düzeltiliyor…" : "Tarihleri Düzelt"}
        </button>
        <button
          onClick={exportExcel}
          disabled={exporting}
          title="İade siparişlerini (mevcut filtreyle) Excel olarak indir"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-bold hover:bg-green-700 disabled:opacity-60"
        >
          <Download size={15} />
          {exporting ? "Hazırlanıyor…" : "Excel'e Aktar"}
        </button>
      </div>

      {/* İade durum sekmeleri — Trendyol sekmeleriyle birebir görsel dil (oval/pill) */}
      <div className="flex flex-wrap gap-2 mb-4 border-b border-gray-200 pb-2">
        {RETURN_TABS.map((t) => {
          const n = (t.statuses || [t.key]).reduce((a, s) => a + (statusCounts[s] || 0), 0);
          const active = statusFilter === t.key;
          return (
            <button
              key={t.key || "all"}
              onClick={() => setStatusFilter(t.key)}
              className={`whitespace-nowrap px-3 py-1.5 rounded-full text-sm border transition-colors ${
                active
                  ? "bg-gray-900 text-white border-gray-900"
                  : "bg-white text-gray-600 border-gray-200 hover:border-gray-400"
              }`}
            >
              {t.label}
              <span className={`ml-1.5 text-xs ${active ? "text-gray-300" : "text-gray-400"}`}>{n}</span>
            </button>
          );
        })}
      </div>

      {/* Filtreler */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-2.5 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Sipariş no / müşteri / telefon…"
            className="pl-8 pr-3 py-2 text-sm border rounded-lg w-64 focus:outline-none focus:ring-1 focus:ring-gray-300"
          />
        </div>
        <MultiSelect className="w-44" placeholder="Tüm Ödeme Tipleri" value={paymentFilter} onChange={setPaymentFilter}
          options={PAYMENT_OPTS.filter((p) => p.value)} />
      </div>

      {/* Liste */}
      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Yükleniyor…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 border rounded-xl text-gray-400">
          <Package className="mx-auto mb-2 opacity-40" size={28} />
          Rooftr iade siparişi bulunamadı.
          <div className="text-xs mt-1">Yukarıdaki "Siparişleri Çek" ile siparişleri içeri aktarın.</div>
        </div>
      ) : (
        <div className="border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b text-gray-500 text-left text-xs uppercase">
              <tr>
                <th className="px-3 py-2.5 font-bold">Sipariş No</th>
                <th className="px-3 py-2.5 font-bold">İade No</th>
                <th className="px-3 py-2.5 font-bold">Müşteri</th>
                <th className="px-3 py-2.5 font-bold">Sebep</th>
                <th className="px-3 py-2.5 font-bold">Ödeme</th>
                <th className="px-3 py-2.5 font-bold">Kargo</th>
                <th className="px-3 py-2.5 font-bold text-right whitespace-nowrap">Tutar<span className="block text-[9px] font-normal normal-case text-gray-400">Brüt / İskonto / Net</span></th>
                <th className="px-3 py-2.5 font-bold whitespace-nowrap">Sipariş Tarihi</th>
                <th className="px-3 py-2.5 font-bold whitespace-nowrap">İade Onay/Ret</th>
                <th className="px-3 py-2.5 font-bold whitespace-nowrap">İade Ödeme</th>
                <th className="px-3 py-2.5 font-bold">Durum</th>
                <th className="px-3 py-2.5 font-bold text-right w-8">İşlemler</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <Fragment key={r.id}>
                  <tr className="hover:bg-gray-50">
                    <td className="px-3 py-2.5">
                      <div className="font-mono text-sm font-bold text-blue-600">{r.order_number}</div>
                      {r.item_count > 0 && <div className="text-xs text-gray-400">{r.item_count} ürün</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      {r.iade_no
                        ? <div className="font-mono text-xs font-semibold text-gray-800 truncate max-w-[120px]" title={r.iade_no}>{r.iade_no}</div>
                        : <span className="text-gray-400">—</span>}
                      {r.gonderi_no && <div className="font-mono text-[10px] text-gray-400 truncate max-w-[120px]" title={`Gönderi No: ${r.gonderi_no}`}>Gönderi: {r.gonderi_no}</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-gray-800">{r.customer_name}</div>
                      {r.phone && <div className="text-xs text-gray-400">{r.phone}</div>}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-gray-600 max-w-[140px] truncate" title={r.reason || ""}>{r.reason || "—"}</td>
                    <td className="px-3 py-2.5">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs border ${r.payment_method === "credit_card" ? "bg-blue-100 text-blue-700 border-blue-200" : r.payment_method === "bank_transfer" ? "bg-purple-100 text-purple-700 border-purple-200" : "bg-gray-100 text-gray-700 border-gray-200"}`}>
                        {payIcon(r.payment_method)} {r.payment_label}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs">
                      {(r.return_cargo_provider || r.cargo_provider_name || r.return_code) ? (
                        <div className="flex flex-col">
                          <span className="font-medium text-orange-600 text-[11px]">{r.return_cargo_provider || r.cargo_provider_name || "Kargo"}</span>
                          {r.return_code && <span className="font-mono text-[10px] text-gray-500 truncate max-w-[110px]" title={r.return_code}>{r.return_code}</span>}
                        </div>
                      ) : <span className="text-gray-400">—</span>}
                    </td>
                    <td className="px-3 py-2.5 text-right font-mono whitespace-nowrap">
                      {Number(r.discount) > 0 && <div className="text-gray-500 line-through text-xs leading-tight">{fmtTL(r.subtotal || r.total)}</div>}
                      {Number(r.discount) > 0 && <div className="text-orange-600 text-xs font-bold leading-tight">-{fmtTL(r.discount)}</div>}
                      <div className="font-bold text-gray-900 leading-tight">{fmtTL(r.total)}</div>
                    </td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{r.return_approved_at ? fmtDate(r.return_approved_at) : "—"}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{r.refund_paid_at ? fmtDate(r.refund_paid_at) : "—"}</td>
                    <td className="px-3 py-2.5">
                      <select
                        value={r.status}
                        disabled={busyId === r.id}
                        onChange={(e) => changeStatus(r, e.target.value)}
                        className={`text-xs border rounded-md px-2 py-1 font-medium focus:outline-none focus:ring-1 focus:ring-gray-300 ${STATUS_CLS[r.status] || "bg-gray-50 text-gray-700 border-gray-200"}`}
                      >
                        {(statusOpts.some((o) => o.value === r.status) ? statusOpts : [{ value: r.status, label: lbl(r.status) }, ...statusOpts]).map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-1">
                        {r.gider_pusulasi_no && (
                          <span className="text-[11px] font-mono font-bold text-purple-700 px-1" title="Gider Pusulası Takip No">
                            #{r.gider_pusulasi_no}
                          </span>
                        )}
                        {can("returns.expense_note") && (
                          <button onClick={() => handleSiteGider(r)} disabled={busyId === r.id}
                            className={`p-1.5 rounded-lg disabled:opacity-50 ${r.has_gider_pusulasi ? "bg-purple-100 text-purple-700 hover:bg-purple-200" : "bg-gray-100 text-gray-600 hover:bg-gray-200"}`} title="Gider Pusulası">
                            <FileText size={14} />
                          </button>
                        )}
                        <button onClick={() => setExpandedId(expandedId === r.id ? null : r.id)} className="text-gray-400 hover:text-gray-700 px-1" title="Detay">
                          {expandedId === r.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === r.id && (
                    <tr className="bg-gray-50/60">
                      <td colSpan={12} className="px-4 py-3">
                        {/* Müşteri + sipariş özeti */}
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1 text-xs text-gray-900 mb-3">
                          <span>Müşteri: <b className="text-gray-900">{r.customer_name}</b></span>
                          {(r.address || r.city || r.district) && (
                            <span className="lg:col-span-3">Adres: <b className="text-gray-900">{[r.address, r.district, r.city].filter(Boolean).join(", ")}</b></span>
                          )}
                          <span>Durum: <b className="text-gray-900">{lbl(r.status)}</b></span>
                          <span>Sipariş tutarı: <b className="text-gray-900">{fmtTL(r.total)}</b></span>
                          <span>Fatura: <b className="text-gray-900">{r.invoice_number || "—"}</b></span>
                          <span>İade Onay Tarihi: <b className="text-gray-900">{r.return_approved_at ? fmtDate(r.return_approved_at) : "—"}</b></span>
                          <span>İade Ödeme Tarihi: <b className="text-gray-900">{r.refund_paid_at ? fmtDate(r.refund_paid_at) : "—"}</b></span>
                          {r.coupon_code && <span>Kupon: <b className="text-gray-900">{r.coupon_code}</b></span>}
                        </div>

                        {/* İade talep edilen ürünler — tiklenebilir (kısmi işlem için kalem seçimi) */}
                        <div className="flex items-center justify-between mb-1">
                          <div className="text-[11px] font-semibold text-gray-700">İade talep edilen ürünler ({r.item_count} adet)</div>
                          {selCount(r.id) > 0 && <div className="text-[11px] font-semibold text-orange-600">{selCount(r.id)} kalem seçili</div>}
                        </div>
                        {(r.items || []).length > 0 ? (
                          <div className="space-y-1">
                            {r.items.map((it, i) => {
                              const sel = !!selItems[`${r.id}::${i}`];
                              return (
                                <label key={i} className={`flex items-center gap-3 text-xs text-gray-900 border rounded-md px-2.5 py-1.5 cursor-pointer ${sel ? "bg-orange-50 border-orange-300" : "bg-white"}`}>
                                  <input type="checkbox" checked={sel} onChange={() => toggleItem(r.id, i)} className="shrink-0" />
                                  <span className="truncate max-w-[260px]">{it.name || "—"}</span>
                                  <span className="whitespace-nowrap">{it.qty} ad. × {fmtTL(it.price)}</span>
                                  <span className="font-semibold whitespace-nowrap">{fmtTL((Number(it.qty) || 1) * (Number(it.price) || 0))}</span>
                                  {it.barcode && <span className="text-gray-700">#{it.barcode}</span>}
                                  {it.size && <span className="text-gray-700">Beden: {it.size}</span>}
                                  {it.color && <span className="text-gray-700">Renk: {it.color}</span>}
                                  <span className="flex-1" />
                                </label>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="text-xs text-gray-400">Ürün kalemi yok.</div>
                        )}

                        {/* Kargo bedeli — tek anlam: "kargoyu müşteriden KES (mahsup)".
                            Kusur müşterideyse (bana uymadı vb.) işaretle → iade tutarından düşülür.
                            Tam iadede de tiklenebilir: işaretliyse net = ödenen − kargo. */}
                        {(() => {
                          const paid = Number(r.shipping_cost) > 0;
                          const amt = paid ? Number(r.shipping_cost) : Number(freeShipFee) || 0;
                          if (amt <= 0) return null;
                          const sel = !!cargoSel[r.id];
                          return (
                            <label className={`mt-1 flex items-center gap-3 text-xs border rounded-md px-2.5 py-1.5 cursor-pointer ${sel ? "bg-amber-50 border-amber-300 text-gray-900" : "bg-white text-gray-900"}`}>
                              <input type="checkbox" checked={sel} onChange={() => toggleCargo(r.id)} className="shrink-0" />
                              <span className="font-medium whitespace-nowrap">Kargoyu müşteriden kes</span>
                              <span className="text-gray-500 whitespace-nowrap">{paid ? "(faturadaki kargo — mahsup)" : "(ücretsiz kargo iptali — mahsup)"}</span>
                              <span className="flex-1" />
                              <span className={`font-semibold whitespace-nowrap ${sel ? "text-amber-700" : "text-gray-400"}`}>−{fmtTL(amt)}</span>
                            </label>
                          );
                        })()}

                        {/* İade kargo süreci: gelen iade barkodu/kodu + reddedilenlerde geri gönderim */}
                        {(r.return_code || r.return_barcode_url || r.cargo_tracking_number || r.reship_code || r.return_cargo_provider) && (
                          <div className="mt-2 text-[11px] text-gray-900 bg-white border rounded-md px-2.5 py-1.5 flex flex-wrap gap-x-5 gap-y-1 items-center">
                            {r.return_cargo_provider && <span>İade kargo: <b className="text-gray-900">{r.return_cargo_provider}</b></span>}
                            {r.return_code && <span>İade kodu: <b className="text-gray-900 font-mono">{r.return_code}</b></span>}
                            {r.return_barcode_url && (
                              <a href={r.return_barcode_url.startsWith("http") ? r.return_barcode_url : `${BACKEND}${r.return_barcode_url}`}
                                target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline">Kargo barkodu</a>
                            )}
                            {r.cargo_tracking_number && <span>Takip no: <b className="text-gray-900 font-mono">{r.cargo_tracking_number}</b></span>}
                            {r.reship_code && <span className="text-blue-700">Geri gönderim: <b className="font-mono">{r.reship_code}</b>{r.reshipped_at ? ` · ${fmtDate(r.reshipped_at)}` : ""}</span>}
                          </div>
                        )}

                        {/* Tutar dökümü */}
                        {(r.subtotal > 0 || r.shipping_cost > 0 || r.discount > 0) && (
                          <div className="mt-2 text-xs text-gray-900 flex flex-wrap gap-x-6 gap-y-1 justify-start">
                            {r.subtotal > 0 && <span>Ara toplam: <b className="text-gray-900">{fmtTL(r.subtotal)}</b></span>}
                            {r.shipping_cost > 0 && <span>Kargo: <b className="text-gray-900">{fmtTL(r.shipping_cost)}</b></span>}
                            {r.discount > 0 && <span>İndirim: <b className="text-gray-900">−{fmtTL(r.discount)}</b></span>}
                            <span>Genel toplam: <b className="text-gray-900">{fmtTL(r.total)}</b></span>
                          </div>
                        )}
                        {/* Taksit farkı: gerçekten tahsil edilen (iyzico paidPrice) genel toplamdan
                            yüksekse — tam iadede ONAY EKRANINDA bu tutar baz alınır, burada da
                            gösteriyoruz ki admin onaya girmeden önce gerçek iade tutarını görsün. */}
                        {r.vade_farki > 0 && (
                          <div className="mt-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1.5 inline-flex flex-wrap items-center gap-x-4 gap-y-0.5">
                            <span>Taksit farkı (+{r.installment} taksit): <b>+{fmtTL(r.vade_farki)}</b></span>
                            <span>Gerçek tahsilat — iade onayında baz alınacak tutar: <b>{fmtTL(r.charged_total)}</b></span>
                          </div>
                        )}

                        {/* İade/iptal durumu açıklaması */}
                        {(r.status === "partial_refunded" || r.status === "cancelled") && (
                          <div className="mt-2 text-[11px] text-gray-900 bg-white border rounded-md px-2.5 py-1.5">
                            {r.status === "cancelled" ? "Sipariş iptal edildi."
                              : "Kısmi iade yapıldı. (Kaynak sistem kalem bazında ayrım vermiyor; iade edilen tutar yukarıdaki tutar bilgisine yansır.)"}
                          </div>
                        )}
                        {wfCanAct && (
                          <div className="mt-3">
                            <div className="flex flex-wrap gap-2">
                              {can("returns.approve") && (
                                <button
                                  onClick={() => openWorkflow(r, "approve")}
                                  disabled={busyId === r.id}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-60"
                                >
                                  <CheckCircle size={14} /> İade Onay{selCount(r.id) > 0 ? ` (${selCount(r.id)} kalem)` : ""}
                                </button>
                              )}
                              {can("returns.reject") && (
                                <button
                                  onClick={() => openWorkflow(r, "reject")}
                                  disabled={busyId === r.id}
                                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 disabled:opacity-60"
                                >
                                  <XCircle size={14} /> İade Reddet
                                </button>
                              )}
                            </div>
                            <div className="text-[11px] text-gray-700 mt-1">
                              Onay/ret penceresi açılır: tutar + gider pusulası + iade ödemesi; müşteriye SMS/mail gider. Kalem seçiliyse iade tutarı seçili kalemlerden ön-dolar.
                            </div>
                          </div>
                        )}
                        {r.notes && <div className="mt-2 text-[11px] text-gray-700">Not: {r.notes}</div>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* İade işlem akışı modal'ı (köprülenmiş customer_returns üzerinden) */}
      {wf && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={() => !wf.loading && setWf(null)}>
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <div>
                <div className="font-semibold text-gray-900">İade İşlemleri</div>
                <div className="text-xs text-gray-500">Sipariş {wf.row.order_number} · {wf.row.customer_name}</div>
              </div>
              <button onClick={() => setWf(null)} disabled={wf.loading} className="text-gray-400 hover:text-gray-700 text-sm">Kapat ✕</button>
            </div>
            <div className="p-5 space-y-4">
              <div className="text-xs text-gray-500">
                Mevcut iade durumu: <b className="text-gray-800">{lbl(wf.row.status)}</b>
              </div>

              {wf.preview ? (
                <div className="border rounded-xl p-3 text-sm">
                  <div className="text-xs text-gray-500 mb-2">
                    Kargo: {wf.fault === "customer" ? <b className="text-amber-700">müşteriden kesildi</b> : <b className="text-gray-700">mağazadan (tam iade)</b>}
                  </div>
                  <div className="space-y-1 text-xs text-gray-600">
                    {wf.preview.vade_farki > 0 && <div className="flex justify-between text-emerald-700"><span>Taksit farkı dahil ({wf.preview.installment} taksit)</span><b>+ {fmtTL(wf.preview.vade_farki)}</b></div>}
                    <div className="flex justify-between"><span>İade edilen ürün tutarı</span><b>{fmtTL(wf.preview.returned_net)}</b></div>
                    {wf.preview.campaign_deduction > 0 && <div className="flex justify-between text-amber-700"><span>Kargo bedeli (müşteriden tahsil)</span><b>− {fmtTL(wf.preview.campaign_deduction)}</b></div>}
                    {wf.preview.return_cargo_fee > 0 && <div className="flex justify-between text-amber-700"><span>İade kargo bedeli</span><b>− {fmtTL(wf.preview.return_cargo_fee)}</b></div>}
                    <div className="flex justify-between pt-1 border-t mt-1 text-gray-900"><span>Otomatik iade tutarı</span><b>{fmtTL(wf.preview.auto_refund)}</b></div>
                  </div>
                  {wf.preview.campaign_note && <div className="text-[11px] text-amber-600 mt-1">{wf.preview.campaign_note}</div>}
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-xs text-gray-500">İade tutarı:</span>
                    <input type="number" value={wf.finalAmount}
                      onChange={(e) => setWf((m) => ({ ...m, finalAmount: e.target.value, edited: true }))}
                      className="w-32 text-sm border rounded-md px-2 py-1" />
                    <span className="text-xs text-gray-400">TL {wf.edited && "(elle)"}</span>
                  </div>
                </div>
              ) : (
                <div className="text-xs text-gray-400">Tutar önizlemesi alınamadı. Onayda tutarı elle girebilirsin.</div>
              )}

              <div className="flex flex-wrap items-center gap-2">
                {wfDecided ? (
                  <>
                    <button disabled title="Bu iade karara bağlanmış"
                      className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-not-allowed ${wfDecided === "approved" ? "bg-emerald-600 text-white opacity-80" : "bg-gray-200 text-gray-400 opacity-60"}`}>
                      {wfDecided === "approved" && <CheckCircle size={14} />} {wfDecided === "approved" ? "Onaylandı" : "Onayla"}
                    </button>
                    <button disabled title="Bu iade karara bağlanmış"
                      className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold cursor-not-allowed ${wfDecided === "rejected" ? "bg-rose-600 text-white opacity-80" : "bg-gray-200 text-gray-400 opacity-60"}`}>
                      {wfDecided === "rejected" && <XCircle size={14} />} {wfDecided === "rejected" ? "Reddedildi" : "Reddet"}
                    </button>
                    <span className="text-[11px] text-gray-500">Bu iade {wfDecided === "approved" ? "onaylanmış" : "reddedilmiş"}; tekrar işlem yapılamaz.</span>
                  </>
                ) : (
                  <>
                    {can("returns.approve") && (
                      <button onClick={wfApprove} disabled={wf.loading}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-semibold hover:bg-emerald-700 disabled:opacity-50">Onayla</button>
                    )}
                    {can("returns.reject") && (
                      <button onClick={() => setWf((m) => ({ ...m, showReject: !m.showReject }))} disabled={wf.loading}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 disabled:opacity-50">Reddet</button>
                    )}
                  </>
                )}
              </div>

              {wf.showReject && !wfDecided && (
                <div className="border rounded-xl p-3 bg-rose-50/40">
                  <label className="text-xs text-gray-600">Ret sebebi (müşteriye SMS/mail ile gider)</label>
                  <textarea value={wf.rejectReason} onChange={(e) => setWf((m) => ({ ...m, rejectReason: e.target.value }))}
                    rows={2} className="w-full mt-1 text-sm border rounded-md px-2 py-1" placeholder="Örn. ürün kullanılmış / etiketi yok…" />
                  <label className="flex items-center gap-2 mt-2 text-xs text-gray-600">
                    <input type="checkbox" checked={wf.reship} onChange={(e) => setWf((m) => ({ ...m, reship: e.target.checked }))} />
                    Ürünü müşteriye geri gönder (yeni kargo barkodu üret)
                  </label>
                  <button onClick={wfReject} disabled={wf.loading}
                    className="mt-2 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-semibold hover:bg-rose-700 disabled:opacity-50">Reddi Onayla</button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
