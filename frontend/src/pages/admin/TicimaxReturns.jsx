import { useState, useEffect, useCallback, Fragment } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, Search, ChevronDown, ChevronUp, CreditCard, Banknote, Truck, Package } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

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
const STATUS_CLS = {
  pending: "bg-gray-100 text-gray-600 border-gray-300",
  awaiting_payment: "bg-amber-50 text-amber-700 border-amber-200",
  payment_notified: "bg-amber-50 text-amber-700 border-amber-200",
  confirmed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  preparing: "bg-blue-50 text-blue-700 border-blue-200",
  processing: "bg-indigo-50 text-indigo-700 border-indigo-200",
  ready_to_ship: "bg-sky-50 text-sky-700 border-sky-200",
  shipped: "bg-violet-50 text-violet-700 border-violet-200",
  in_transit: "bg-violet-50 text-violet-700 border-violet-200",
  out_for_delivery: "bg-fuchsia-50 text-fuchsia-700 border-fuchsia-200",
  delivered: "bg-green-100 text-green-800 border-green-300",
  undelivered: "bg-orange-50 text-orange-700 border-orange-200",
  return_requested: "bg-rose-50 text-rose-700 border-rose-200",
  return_approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  return_rejected: "bg-gray-100 text-gray-600 border-gray-300",
  return_in_transit: "bg-pink-50 text-pink-700 border-pink-200",
  returned: "bg-red-50 text-red-700 border-red-200",
  partial_refunded: "bg-rose-50 text-rose-700 border-rose-200",
  refunded: "bg-green-100 text-green-800 border-green-300",
  cancelled: "bg-gray-100 text-gray-500 border-gray-300",
};

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

export default function TicimaxReturns({ embedded = false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pulling, setPulling] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [paymentFilter, setPaymentFilter] = useState("");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [statusCounts, setStatusCounts] = useState({});
  const [paymentCounts, setPaymentCounts] = useState({});
  const [totalReturns, setTotalReturns] = useState(0);
  const [busyId, setBusyId] = useState("");
  const [expandedId, setExpandedId] = useState(null);

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

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
      const res = await axios.get(`${API}/admin/ticimax/return-orders?${params}`, auth());
      setRows(res.data.orders || []);
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

  // Ticimax'tan siparişleri çek (iade olanlar orders'a düşer, sonra listeyi yenile)
  const pullFromTicimax = async () => {
    setPulling(true);
    toast.info("Ticimax'tan siparişler çekiliyor — bu işlem birkaç dakika sürebilir…");
    try {
      const res = await axios.post(
        `${API}/integrations/ticimax/orders/import?days=365&pages=20&limit=100`,
        {},
        auth()
      );
      if (res.data?.success === false) {
        // Backend gerçek WS hatasını message + error_detail ile döndürür
        toast.error(res.data.message || "Ticimax'tan sipariş çekilemedi.");
      } else {
        toast.success(res.data.message || "Ticimax siparişleri çekildi");
      }
      await load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Ticimax'tan çekme başarısız. WS yetki kodu / Sipariş Servisi iznini kontrol edin.");
    } finally {
      setPulling(false);
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
      toast.success(`Durum güncellendi: ${STATUS_LABEL[newStatus] || newStatus}`);
    } catch (e) {
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, status: prev } : r)));
      toast.error(e.response?.data?.detail || "Durum güncellenemedi");
    } finally {
      setBusyId("");
    }
  };

  return (
    <div className={embedded ? "" : "p-4"}>
      {/* Üst bar: çek butonu + özet */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="text-sm text-gray-600">
          İade / kısmi iade durumundaki siparişler.
          {totalReturns > 0 && <span className="ml-1 font-medium text-gray-800">Toplam {totalReturns} iade siparişi.</span>}
        </div>
        <button
          onClick={pullFromTicimax}
          disabled={pulling}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-orange-500 text-white text-sm font-medium hover:bg-orange-600 disabled:opacity-60"
        >
          <RefreshCw size={15} className={pulling ? "animate-spin" : ""} />
          {pulling ? "Çekiliyor…" : "Siparişleri Çek"}
        </button>
      </div>

      {/* Durum rozetleri */}
      {Object.keys(statusCounts).length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {STATUS_OPTS.filter((s) => statusCounts[s.value]).map((s) => (
            <span key={s.value} className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border ${STATUS_CLS[s.value]}`}>
              {s.label}: <b>{statusCounts[s.value]}</b>
            </span>
          ))}
        </div>
      )}

      {/* Filtreler */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative">
          <Search size={15} className="absolute left-2.5 top-2.5 text-gray-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Sipariş no / müşteri / telefon…"
            className="pl-8 pr-3 py-2 text-sm border rounded-lg w-64 focus:outline-none focus:ring-1 focus:ring-orange-400"
          />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="py-2 px-3 text-sm border rounded-lg">
          <option value="">Tüm İade Durumları</option>
          {STATUS_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select value={paymentFilter} onChange={(e) => setPaymentFilter(e.target.value)} className="py-2 px-3 text-sm border rounded-lg">
          {PAYMENT_OPTS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </div>

      {/* Liste */}
      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Yükleniyor…</div>
      ) : rows.length === 0 ? (
        <div className="text-center py-16 border rounded-xl text-gray-400">
          <Package className="mx-auto mb-2 opacity-40" size={28} />
          Ticimax iade siparişi bulunamadı.
          <div className="text-xs mt-1">Yukarıdaki "Ticimax'tan Çek" ile siparişleri içeri aktarın.</div>
        </div>
      ) : (
        <div className="border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600 text-left text-xs uppercase">
              <tr>
                <th className="px-3 py-2.5 font-medium">Sipariş</th>
                <th className="px-3 py-2.5 font-medium">Müşteri</th>
                <th className="px-3 py-2.5 font-medium">Ödeme Tipi</th>
                <th className="px-3 py-2.5 font-medium">Tutar</th>
                <th className="px-3 py-2.5 font-medium">Tarih</th>
                <th className="px-3 py-2.5 font-medium">Durum</th>
                <th className="px-3 py-2.5 font-medium w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((r) => (
                <Fragment key={r.id}>
                  <tr className="hover:bg-gray-50">
                    <td className="px-3 py-2.5">
                      <div className="font-medium text-gray-900">{r.order_number}</div>
                      {r.item_count > 0 && <div className="text-xs text-gray-400">{r.item_count} ürün</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-gray-800">{r.customer_name}</div>
                      {r.phone && <div className="text-xs text-gray-400">{r.phone}</div>}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-gray-100 text-gray-700 text-xs border border-gray-200">
                        {payIcon(r.payment_method)} {r.payment_label}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{fmtTL(r.total)}</td>
                    <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{fmtDate(r.created_at)}</td>
                    <td className="px-3 py-2.5">
                      <select
                        value={r.status}
                        disabled={busyId === r.id}
                        onChange={(e) => changeStatus(r, e.target.value)}
                        className={`text-xs border rounded-md px-2 py-1 font-medium focus:outline-none focus:ring-1 focus:ring-orange-400 ${STATUS_CLS[r.status] || "bg-gray-50 text-gray-700 border-gray-200"}`}
                      >
                        {STATUS_OPTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    </td>
                    <td className="px-3 py-2.5">
                      <button onClick={() => setExpandedId(expandedId === r.id ? null : r.id)} className="text-gray-400 hover:text-gray-700">
                        {expandedId === r.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </button>
                    </td>
                  </tr>
                  {expandedId === r.id && (
                    <tr className="bg-gray-50/60">
                      <td colSpan={7} className="px-4 py-3">
                        {/* Müşteri + sipariş özeti */}
                        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-1 text-xs text-gray-600 mb-3">
                          <span>Müşteri: <b className="text-gray-800">{r.customer_name}</b></span>
                          {r.phone && <span>Telefon: <b className="text-gray-800">{r.phone}</b></span>}
                          {r.email && <span>E-posta: <b className="text-gray-800">{r.email}</b></span>}
                          {(r.address || r.city || r.district) && (
                            <span className="lg:col-span-3">Adres: <b className="text-gray-800">{[r.address, r.district, r.city].filter(Boolean).join(", ")}</b></span>
                          )}
                          <span>Durum: <b className="text-gray-800">{STATUS_LABEL[r.status] || r.status}</b></span>
                          <span>Ödeme: <b className="text-gray-800">{r.payment_label}</b></span>
                          {r.payment_method_raw && <span>Ham ödeme: <b className="text-gray-800">{r.payment_method_raw}</b></span>}
                          <span>Sipariş tutarı: <b className="text-gray-800">{fmtTL(r.total)}</b></span>
                          {r.paid_amount > 0 && <span>Ödenen: <b className="text-gray-800">{fmtTL(r.paid_amount)}</b></span>}
                          {r.invoice_number && <span>Fatura: <b className="text-gray-800">{r.invoice_number}</b></span>}
                          {r.ticimax_order_id && <span>Kaynak No: <b className="text-gray-800">{r.ticimax_order_id}</b></span>}
                          {r.coupon_code && <span>Kupon: <b className="text-gray-800">{r.coupon_code}</b></span>}
                        </div>

                        {/* Ürün kalemleri: ne almış / kaç adet / birim ve satır tutarı */}
                        <div className="text-[11px] font-semibold text-gray-500 mb-1">Ürünler ({r.item_count} adet)</div>
                        {(r.items || []).length > 0 ? (
                          <div className="space-y-1">
                            {r.items.map((it, i) => (
                              <div key={i} className="flex items-center gap-3 text-xs text-gray-700 bg-white border rounded-md px-2.5 py-1.5">
                                <span className="flex-1 truncate">{it.name || "—"}</span>
                                {it.size && <span className="text-gray-500">Beden: {it.size}</span>}
                                {it.color && <span className="text-gray-500">Renk: {it.color}</span>}
                                {it.barcode && <span className="text-gray-400">#{it.barcode}</span>}
                                <span className="text-gray-500 whitespace-nowrap">{it.qty} ad. × {fmtTL(it.price)}</span>
                                <span className="font-medium whitespace-nowrap">{fmtTL((Number(it.qty) || 1) * (Number(it.price) || 0))}</span>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="text-xs text-gray-400">Ürün kalemi yok.</div>
                        )}

                        {/* Tutar dökümü */}
                        {(r.subtotal > 0 || r.shipping_cost > 0 || r.discount > 0) && (
                          <div className="mt-2 text-xs text-gray-600 flex flex-wrap gap-x-6 gap-y-1 justify-end">
                            {r.subtotal > 0 && <span>Ara toplam: <b className="text-gray-800">{fmtTL(r.subtotal)}</b></span>}
                            {r.shipping_cost > 0 && <span>Kargo: <b className="text-gray-800">{fmtTL(r.shipping_cost)}</b></span>}
                            {r.discount > 0 && <span>İndirim: <b className="text-gray-800">−{fmtTL(r.discount)}</b></span>}
                            <span>Genel toplam: <b className="text-gray-900">{fmtTL(r.total)}</b></span>
                          </div>
                        )}

                        {/* İade/iptal durumu açıklaması */}
                        {(r.status === "partial_refunded" || r.status === "returned" || r.status === "refunded" || r.status === "cancelled") && (
                          <div className="mt-2 text-[11px] text-gray-500 bg-white border rounded-md px-2.5 py-1.5">
                            {r.status === "cancelled" ? "Sipariş iptal edildi."
                              : r.status === "partial_refunded" ? "Kısmi iade yapıldı. (Kaynak sistem kalem bazında ayrım vermiyor; iade edilen tutar yukarıdaki ödenen/tutar bilgisine yansır.)"
                              : "Sipariş iade sürecinde / iade tamamlandı."}
                          </div>
                        )}
                        {r.notes && <div className="mt-2 text-[11px] text-gray-500">Not: {r.notes}</div>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
