import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RotateCcw, Package, ExternalLink, Check, X, RefreshCw, FileText, CreditCard } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL;

// Tüm durumların etiket + rengi (rozet için)
const STATUS_LABELS = {
  created: "Oluşturuldu", approved: "Onaylandı", in_transit: "İade Kargoda",
  received: "Teslim Alındı", returned: "Teslim Alındı", refunded: "Bedeli Ödendi",
  rejected: "Reddedildi", cancelled: "İptal",
};
const STATUS_CLS = {
  created: "bg-rose-50 text-rose-700 border-rose-200",
  approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  in_transit: "bg-pink-50 text-pink-700 border-pink-200",
  received: "bg-red-50 text-red-700 border-red-200",
  returned: "bg-red-50 text-red-700 border-red-200",
  refunded: "bg-green-100 text-green-800 border-green-300",
  rejected: "bg-gray-100 text-gray-600 border-gray-300",
  cancelled: "bg-gray-100 text-gray-500 border-gray-300",
};
// Manuel lojistik durum dropdown'u (onay/ret/ödeme AYRI butonlarla, RBAC'lı)
const LOGISTIC_OPTS = [
  { value: "created", label: "Oluşturuldu" },
  { value: "in_transit", label: "İade Kargoda" },
  { value: "returned", label: "Teslim Alındı" },
  { value: "cancelled", label: "İptal" },
];
const FILTER_OPTS = [
  { value: "", label: "Tüm Durumlar" },
  ...Object.entries(STATUS_LABELS).filter(([k]) => k !== "received").map(([value, label]) => ({ value, label })),
];

const fmtTL = (v) => Number(v || 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " TL";

export default function SiteReturns({ embedded = false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");
  const [perms, setPerms] = useState([]);
  const [busyId, setBusyId] = useState("");

  const [approveM, setApproveM] = useState(null); // {row, fault, preview, finalAmount, note, edited, loading}
  const [rejectM, setRejectM] = useState(null);    // {row, reason, reship, loading}

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });
  const can = (key) => perms.includes("*") || perms.includes(key);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const url = `${API}/orders/returns/admin/list${filter ? `?status=${filter}` : ""}`;
      const res = await axios.get(url, auth());
      setRows(res.data?.returns || []);
    } catch (e) {
      toast.error("İade talepleri yüklenemedi");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const loadPerms = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/admin/me/permissions`, auth());
      setPerms(res.data?.permissions || []);
    } catch (e) {
      setPerms([]);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { loadPerms(); }, [loadPerms]);

  const fmt = (d) => (d ? new Date(d).toLocaleString("tr-TR") : "");

  const changeStatus = async (id, status) => {
    try {
      await axios.post(`${API}/orders/returns/${id}/status`, { status }, auth());
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, status } : r)));
      toast.success("İade durumu güncellendi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Güncellenemedi");
    }
  };

  // ---- Onay akışı (tutar önizleme + kusur + düzenlenebilir tutar) ----
  const fetchPreview = async (id, fault) => {
    const res = await axios.get(`${API}/orders/returns/${id}/refund-preview?fault=${fault}`, auth());
    return res.data?.breakdown || null;
  };
  const openApprove = async (row) => {
    try {
      setBusyId(row.id);
      const pv = await fetchPreview(row.id, "store");
      setApproveM({ row, fault: "store", preview: pv, finalAmount: pv?.auto_refund ?? 0, note: "", edited: false, loading: false });
    } catch (e) {
      toast.error(e.response?.data?.detail || "Önizleme alınamadı");
    } finally {
      setBusyId("");
    }
  };
  const changeFault = async (fault) => {
    if (!approveM) return;
    try {
      setApproveM((m) => ({ ...m, loading: true }));
      const pv = await fetchPreview(approveM.row.id, fault);
      setApproveM((m) => ({ ...m, fault, preview: pv, loading: false, finalAmount: m.edited ? m.finalAmount : (pv?.auto_refund ?? 0) }));
    } catch (e) {
      toast.error("Önizleme alınamadı");
      setApproveM((m) => ({ ...m, loading: false }));
    }
  };
  const submitApprove = async () => {
    if (!approveM) return;
    try {
      setApproveM((m) => ({ ...m, loading: true }));
      const body = { fault: approveM.fault, note: approveM.note };
      if (approveM.edited) body.refund_amount = Number(approveM.finalAmount);
      const res = await axios.post(`${API}/orders/returns/${approveM.row.id}/approve`, body, auth());
      setRows((rs) => rs.map((r) => (r.id === approveM.row.id ? { ...r, status: "approved", refund_amount: res.data?.refund_amount } : r)));
      toast.success(`İade onaylandı · İade tutarı: ${fmtTL(res.data?.refund_amount)}`);
      setApproveM(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Onaylanamadı");
      setApproveM((m) => ({ ...m, loading: false }));
    }
  };

  // ---- Ret akışı (sebep + geri gönderim) ----
  const submitReject = async () => {
    if (!rejectM) return;
    if (!rejectM.reason.trim()) { toast.error("Ret sebebi zorunludur"); return; }
    try {
      setRejectM((m) => ({ ...m, loading: true }));
      const res = await axios.post(`${API}/orders/returns/${rejectM.row.id}/reject`,
        { reason: rejectM.reason.trim(), reship: !!rejectM.reship }, auth());
      setRows((rs) => rs.map((r) => (r.id === rejectM.row.id ? { ...r, status: "rejected" } : r)));
      toast.success(res.data?.reship_code ? `Reddedildi · Geri gönderim: ${res.data.reship_code}` : "İade reddedildi");
      setRejectM(null);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Reddedilemedi");
      setRejectM((m) => ({ ...m, loading: false }));
    }
  };

  const doReissue = async (row) => {
    if (!window.confirm("Yeni 3 günlük iade barkodu üretilsin mi? (14 gün içinde)")) return;
    try {
      setBusyId(row.id);
      const res = await axios.post(`${API}/orders/returns/${row.id}/reissue-barcode`, {}, auth());
      toast.success(`Yeni barkod: ${res.data?.return_code}`);
      load();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Barkod üretilemedi");
    } finally { setBusyId(""); }
  };

  const doGiderPusulasi = async (row) => {
    try {
      setBusyId(row.id);
      const res = await axios.post(`${API}/orders/returns/${row.id}/gider-pusulasi`, {}, auth());
      toast.success(`Gider pusulası: ${res.data?.gider_pusulasi?.display_number}`);
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, has_gider_pusulasi: true } : r)));
    } catch (e) {
      toast.error(e.response?.data?.detail || "Gider pusulası oluşturulamadı");
    } finally { setBusyId(""); }
  };

  const doRefundPay = async (row) => {
    if (!window.confirm(`İade bedeli ödendi olarak işaretlensin mi?${row.refund_amount ? ` (${fmtTL(row.refund_amount)})` : ""}`)) return;
    try {
      setBusyId(row.id);
      await axios.post(`${API}/orders/returns/${row.id}/refund-pay`, {}, auth());
      setRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, status: "refunded" } : r)));
      toast.success("İade bedeli ödendi olarak işaretlendi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "İşaretlenemedi");
    } finally { setBusyId(""); }
  };

  const btn = "inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition-colors disabled:opacity-50";

  return (
    <div data-testid="admin-site-returns">
      <div className="flex items-center justify-between mb-6 gap-4 flex-wrap">
        {!embedded && (
          <div className="flex items-center gap-2">
            <RotateCcw size={22} className="text-rose-600" />
            <h1 className="text-2xl font-bold">İade Talepleri (Site)</h1>
          </div>
        )}
        <select value={filter} onChange={(e) => setFilter(e.target.value)} className="border px-3 py-2 rounded text-sm">
          {FILTER_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {loading ? (
        <div className="p-10 text-center text-gray-400">Yükleniyor…</div>
      ) : rows.length === 0 ? (
        <div className="p-10 text-center text-gray-400 border rounded-xl bg-white">
          <Package className="mx-auto mb-2 opacity-40" size={28} /> Henüz iade talebi yok.
        </div>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => {
            const closed = ["refunded", "rejected", "cancelled"].includes(r.status);
            const isBusy = busyId === r.id;
            return (
              <div key={r.id} className="bg-white border rounded-xl p-4 shadow-sm">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900">{r.order_number}</span>
                      <span className={`text-[10px] uppercase tracking-wide border px-2 py-0.5 rounded-full ${STATUS_CLS[r.status] || STATUS_CLS.created}`}>
                        {STATUS_LABELS[r.status] || r.status}
                      </span>
                      {r.refund_amount != null && (r.status === "approved" || r.status === "refunded") && (
                        <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
                          İade: {fmtTL(r.refund_amount)}
                        </span>
                      )}
                      {r.has_gider_pusulasi && (
                        <span className="text-[10px] text-purple-700 bg-purple-50 border border-purple-200 px-2 py-0.5 rounded-full">GP ✓</span>
                      )}
                      {!r.mng_ok && <span className="text-[10px] text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full">Etiket bekliyor</span>}
                    </div>
                    <p className="text-sm text-gray-600 mt-1">{r.customer_name} · {r.customer_phone} · {r.customer_email}</p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Kod: <span className="font-mono font-medium text-gray-800">{r.return_code}</span> · {r.cargo_provider_name}
                    </p>
                    <p className="text-[11px] text-gray-400 mt-0.5">Oluşturma: {fmt(r.created_at)} · Geçerlilik: {fmt(r.valid_until)}</p>
                    <div className="mt-2 text-xs text-gray-700">
                      {(r.items || []).map((it, i) => (
                        <span key={i} className="inline-block bg-gray-50 border border-gray-100 rounded px-2 py-0.5 mr-1 mb-1">
                          {it.quantity}× {it.name}{it.size ? ` (${it.size}${it.color ? `/${it.color}` : ""})` : ""}
                        </span>
                      ))}
                    </div>
                    {r.reason && <p className="text-xs text-gray-500 mt-1 italic">Neden: {r.reason}</p>}
                    {r.reject_reason && <p className="text-xs text-rose-600 mt-1">Ret sebebi: {r.reject_reason}</p>}
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <img src={`${BACKEND}${r.barcode_url}`} alt={r.return_code} className="h-14 border border-gray-100 rounded bg-white" />
                    <a href={`${BACKEND}${r.barcode_url}`} target="_blank" rel="noopener noreferrer"
                      className="text-[11px] text-blue-600 hover:text-blue-800 inline-flex items-center gap-1">
                      Barkodu aç <ExternalLink size={11} />
                    </a>
                    <select value={["approved","refunded","rejected"].includes(r.status) ? "" : r.status}
                      onChange={(e) => e.target.value && changeStatus(r.id, e.target.value)}
                      className="border px-2 py-1.5 rounded text-xs" title="Lojistik durum">
                      <option value="">Durum…</option>
                      {LOGISTIC_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                  </div>
                </div>

                {/* Aksiyon çubuğu — RBAC'a göre gösterilir */}
                {!closed && (
                  <div className="flex flex-wrap items-center gap-2 mt-3 pt-3 border-t border-gray-100">
                    {r.status === "created" && can("returns.approve") && (
                      <button disabled={isBusy} onClick={() => openApprove(r)}
                        className={`${btn} border-emerald-300 text-emerald-700 hover:bg-emerald-50`}>
                        <Check size={13} /> Onayla
                      </button>
                    )}
                    {r.status === "created" && can("returns.reject") && (
                      <button disabled={isBusy} onClick={() => setRejectM({ row: r, reason: "", reship: false, loading: false })}
                        className={`${btn} border-rose-300 text-rose-700 hover:bg-rose-50`}>
                        <X size={13} /> Reddet
                      </button>
                    )}
                    {can("returns.cargo_rebook") && (
                      <button disabled={isBusy} onClick={() => doReissue(r)}
                        className={`${btn} border-gray-300 text-gray-700 hover:bg-gray-50`}>
                        <RefreshCw size={13} /> Yeni Barkod
                      </button>
                    )}
                    {can("returns.expense_note") && (
                      <button disabled={isBusy} onClick={() => doGiderPusulasi(r)}
                        className={`${btn} border-purple-300 text-purple-700 hover:bg-purple-50`}>
                        <FileText size={13} /> Gider Pusulası
                      </button>
                    )}
                    {["approved", "in_transit", "received", "returned"].includes(r.status) && can("returns.refund_pay") && (
                      <button disabled={isBusy} onClick={() => doRefundPay(r)}
                        className={`${btn} border-green-400 bg-green-600 text-white hover:bg-green-700`}>
                        <CreditCard size={13} /> İade Ödemesi Yap
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* ---- Onay Modalı ---- */}
      {approveM && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setApproveM(null)}>
          <div className="bg-white rounded-2xl max-w-md w-full p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-1">İadeyi Onayla</h3>
            <p className="text-xs text-gray-500 mb-3">Sipariş {approveM.row.order_number}</p>

            <div className="mb-3">
              <p className="text-xs font-bold text-gray-500 uppercase mb-1">Kusur</p>
              <div className="flex gap-2">
                {[["store", "Mağaza kusuru (kargo bizden)"], ["customer", "Müşteri kusuru (kargo müşteriden)"]].map(([v, l]) => (
                  <button key={v} onClick={() => changeFault(v)} disabled={approveM.loading}
                    className={`flex-1 px-3 py-2 rounded-lg text-xs border transition-colors ${approveM.fault === v ? "border-emerald-500 bg-emerald-50 text-emerald-700 font-semibold" : "border-gray-200 text-gray-600"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>

            {approveM.preview && (
              <div className="bg-gray-50 rounded-lg p-3 text-sm space-y-1 mb-3">
                <div className="flex justify-between"><span className="text-gray-600">İade edilen (net)</span><span className="font-mono">{fmtTL(approveM.preview.returned_net)}</span></div>
                {approveM.preview.campaign_deduction > 0 && (
                  <div className="flex justify-between text-orange-600"><span>Kargo kampanya mahsubu</span><span className="font-mono">−{fmtTL(approveM.preview.campaign_deduction)}</span></div>
                )}
                {approveM.preview.return_cargo_fee > 0 && (
                  <div className="flex justify-between text-orange-600"><span>İade kargo bedeli</span><span className="font-mono">−{fmtTL(approveM.preview.return_cargo_fee)}</span></div>
                )}
                {approveM.preview.campaign_note && <p className="text-[11px] text-gray-400 pt-1">{approveM.preview.campaign_note}</p>}
                <div className="flex justify-between border-t pt-1 mt-1 font-bold"><span>Otomatik iade tutarı</span><span className="font-mono">{fmtTL(approveM.preview.auto_refund)}</span></div>
              </div>
            )}

            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">İade Tutarı (düzenlenebilir)</label>
            <input type="number" step="0.01" value={approveM.finalAmount}
              onChange={(e) => setApproveM((m) => ({ ...m, finalAmount: e.target.value, edited: true }))}
              className="w-full px-3 py-2 border rounded-lg text-sm font-mono mb-3" />

            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Not (opsiyonel)</label>
            <input value={approveM.note} onChange={(e) => setApproveM((m) => ({ ...m, note: e.target.value }))}
              className="w-full px-3 py-2 border rounded-lg text-sm mb-4" placeholder="Örn. düzeltme gerekçesi" />

            <div className="flex gap-2 justify-end">
              <button onClick={() => setApproveM(null)} className="px-4 py-2 rounded-lg text-sm border">Vazgeç</button>
              <button onClick={submitApprove} disabled={approveM.loading}
                className="px-4 py-2 rounded-lg text-sm bg-emerald-600 text-white font-bold hover:bg-emerald-700 disabled:opacity-50">
                {approveM.loading ? "…" : "Onayla ve Kaydet"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ---- Ret Modalı ---- */}
      {rejectM && (
        <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={() => setRejectM(null)}>
          <div className="bg-white rounded-2xl max-w-md w-full p-5 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold mb-1">İadeyi Reddet</h3>
            <p className="text-xs text-gray-500 mb-3">Sipariş {rejectM.row.order_number}</p>

            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Ret Sebebi <span className="text-rose-500">*</span></label>
            <textarea value={rejectM.reason} onChange={(e) => setRejectM((m) => ({ ...m, reason: e.target.value }))}
              rows={3} className="w-full px-3 py-2 border rounded-lg text-sm mb-3" placeholder="Müşteriye iletilecek ret sebebi" />

            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer mb-4">
              <input type="checkbox" checked={rejectM.reship} onChange={(e) => setRejectM((m) => ({ ...m, reship: e.target.checked }))} />
              Ürünü müşteriye geri gönder (yeni kargo barkodu üret)
            </label>

            <div className="flex gap-2 justify-end">
              <button onClick={() => setRejectM(null)} className="px-4 py-2 rounded-lg text-sm border">Vazgeç</button>
              <button onClick={submitReject} disabled={rejectM.loading}
                className="px-4 py-2 rounded-lg text-sm bg-rose-600 text-white font-bold hover:bg-rose-700 disabled:opacity-50">
                {rejectM.loading ? "…" : "Reddet"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
