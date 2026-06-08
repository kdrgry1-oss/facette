import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, Search, Check, X, FileText, Printer, ChevronDown, ChevronUp, AlertCircle, CreditCard, Truck } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function formatCurrency(val) {
  return new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(val || 0);
}

function formatDate(d) {
  if (!d) return "-";
  try { return new Date(d).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return d; }
}

// Gider pusulası takip numarası: 6 haneli, başında sıfırla (085490)
function pad6(n) {
  const v = parseInt(String(n).replace(/\D/g, ""), 10);
  return isNaN(v) ? "" : String(v).padStart(6, "0");
}

// Tutarı sadece tamsayı kısmını TR yazıya çevirir (kuruşsuz): 1862 -> "Binsekizyüzaltmışiki"
function sayiToWords(num) {
  num = Math.abs(Math.floor(Number(num) || 0));
  if (num === 0) return "Sıfır";
  const birler = ["", "Bir", "İki", "Üç", "Dört", "Beş", "Altı", "Yedi", "Sekiz", "Dokuz"];
  const onlar = ["", "On", "Yirmi", "Otuz", "Kırk", "Elli", "Altmış", "Yetmiş", "Seksen", "Doksan"];
  const basamak = ["", "Bin", "Milyon", "Milyar", "Trilyon"];
  const uclu = (n) => {
    let s = "";
    const y = Math.floor(n / 100), o = Math.floor((n % 100) / 10), b = n % 10;
    if (y > 0) s += (y === 1 ? "" : birler[y]) + "Yüz";
    if (o > 0) s += onlar[o];
    if (b > 0) s += birler[b];
    return s;
  };
  const parts = [];
  let i = 0;
  while (num > 0) {
    const grp = num % 1000;
    if (grp > 0) {
      let g = uclu(grp);
      if (i === 1 && grp === 1) g = ""; // "Bin", "BirBin" değil
      parts.unshift(g + basamak[i]);
    }
    num = Math.floor(num / 1000);
    i++;
  }
  const joined = parts.join("");
  return joined.charAt(0) + joined.slice(1).toLocaleLowerCase("tr-TR");
}

// A4 yatay: sayfada aynı pusula 4 kopya (4 sütun), her sütun 74.25mm
const GP_COPIES = 4;            // bir A4 yatay sayfada aynı pusula 4 kopya (4 sütun)
const GP_SLIP_W_MM = 74.25;     // sütun genişliği (297mm / 4)
const GP_SLIP_H_MM = 210;       // sütun yüksekliği (A4 yatay)
const GP_PAGE_W_MM = 297;       // A4 yatay genişlik
const GP_PAGE_H_MM = 210;       // A4 yatay yükseklik

function ActionBadge({ action }) {
  if (action === "approved") return <span className="px-2 py-0.5 bg-green-100 text-green-700 text-xs font-bold rounded-full">Onaylandı</span>;
  if (action === "issued") return <span className="px-2 py-0.5 bg-red-100 text-red-700 text-xs font-bold rounded-full">İtiraz Edildi</span>;
  return <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-xs font-bold rounded-full">Bekliyor</span>;
}

export default function Returns() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState({});
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [expandedId, setExpandedId] = useState(null);
  const [gpModalOpen, setGpModalOpen] = useState(false);
  const [gpData, setGpData] = useState(null);
  const [gpLoading, setGpLoading] = useState(false);
  const [bulkPrintData, setBulkPrintData] = useState(null);
  // Gider pusulası: takip no (085490'dan), matbu bindirme modu ve hizalama (mm)
  const [gpStart, setGpStart] = useState(() => localStorage.getItem("gp_next_no") || "085490");
  const [gpOverlay, setGpOverlay] = useState(() => localStorage.getItem("gp_overlay") !== "0");
  const [gpOffX, setGpOffX] = useState(() => parseFloat(localStorage.getItem("gp_off_x")) || 0);
  const [gpOffY, setGpOffY] = useState(() => parseFloat(localStorage.getItem("gp_off_y")) || 0);
  const [gpGuides, setGpGuides] = useState(false);
  const autoRefreshRef = useRef(null);

  // A2 - Ret sebebi modal state
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectTargetClaim, setRejectTargetClaim] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [rejectReasonId, setRejectReasonId] = useState(1);

  // Iyzico kısmi iade modal state
  const [refundModalOpen, setRefundModalOpen] = useState(false);
  const [refundClaim, setRefundClaim] = useState(null);
  const [refundAmount, setRefundAmount] = useState(0);
  const [refundShipping, setRefundShipping] = useState(0);
  const [refundReason, setRefundReason] = useState("Müşteri iadesi");
  const [refundLoading, setRefundLoading] = useState(false);

  const limit = 20;

  const fetchClaims = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const params = new URLSearchParams({ page, limit, search });
      if (typeFilter) params.append("claim_type", typeFilter);
      const res = await axios.get(`${API}/integrations/trendyol/claims?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setClaims(res.data.claims || []);
      setTotal(res.data.total || 0);
      setStats(res.data.stats || {});
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [page, search, typeFilter]);

  useEffect(() => { fetchClaims(); }, [fetchClaims]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const syncAndRefresh = async () => {
      try {
        const token = localStorage.getItem("token");
        await axios.get(`${API}/integrations/trendyol/claims/sync`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        await fetchClaims();
      } catch (e) { /* silent */ }
    };
    autoRefreshRef.current = setInterval(syncAndRefresh, 5 * 60 * 1000);
    return () => clearInterval(autoRefreshRef.current);
  }, [fetchClaims]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/integrations/trendyol/claims/sync`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(res.data.message || "Senkronizasyon tamamlandı");
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Senkronizasyon hatası");
    } finally {
      setSyncing(false);
    }
  };

  const handleApprove = async (claim) => {
    if (!await window.appConfirm("Bu iadeyi onaylamak istediğinize emin misiniz?")) return;
    try {
      const token = localStorage.getItem("token");
      const claimItemIds = (claim.items || []).map(i => i.claim_item_id).filter(Boolean);
      if (!claimItemIds.length) { toast.error("Onaylanacak kalem bulunamadı"); return; }
      await axios.post(`${API}/integrations/trendyol/claims/${claim.claim_id}/approve`,
        { claim_item_ids: claimItemIds },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("İade onaylandı");
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Onay hatası");
    }
  };

  const handleIssue = async (claim) => {
    // A2 - open reject reason modal instead of prompt
    setRejectTargetClaim(claim);
    setRejectReason("");
    setRejectReasonId(1);
    setRejectModalOpen(true);
  };

  const submitReject = async () => {
    if (!rejectTargetClaim) return;
    if (!rejectReason.trim()) { toast.error("Ret sebebi boş olamaz"); return; }
    try {
      const token = localStorage.getItem("token");
      const claimItemIds = (rejectTargetClaim.items || []).map(i => i.claim_item_id).filter(Boolean);
      await axios.post(`${API}/integrations/trendyol/claims/${rejectTargetClaim.claim_id}/issue`,
        { claim_item_ids: claimItemIds, issue_reason_id: Number(rejectReasonId) || 1, description: rejectReason.trim() },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("İtiraz oluşturuldu");
      setRejectModalOpen(false);
      setRejectTargetClaim(null);
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "İtiraz hatası");
    }
  };

  const openRefundModal = (claim) => {
    const totalGross = (claim.items || []).reduce((s, i) => s + (i.gross_price || i.price || 0), 0);
    const totalDiscount = (claim.items || []).reduce((s, i) => s + (i.discount_amount || 0), 0);
    const totalNet = Math.max(0, totalGross - totalDiscount);
    setRefundClaim(claim);
    setRefundAmount(Number(totalNet.toFixed(2)));
    setRefundShipping(0);
    setRefundReason(claim.claim_reason || "Müşteri iadesi");
    setRefundModalOpen(true);
  };

  const submitRefund = async () => {
    if (!refundClaim) return;
    const orderId = refundClaim.order_id || refundClaim.local_order_id;
    if (!orderId) {
      toast.error("Sipariş bağlantısı (order_id) bulunamadı — yerel siparişte iyzico ödemesi yapılmamış olabilir.");
      return;
    }
    if (refundAmount <= 0) { toast.error("İade tutarı 0'dan büyük olmalı"); return; }
    if (refundShipping < 0) { toast.error("Kargo kesintisi negatif olamaz"); return; }
    if (refundShipping >= refundAmount) {
      toast.error("Kargo kesintisi iade tutarından büyük veya eşit olamaz");
      return;
    }
    setRefundLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(`${API}/integrations/iyzico/refund`,
        {
          order_id: orderId,
          amount: Number(refundAmount),
          shipping_deduction: Number(refundShipping),
          reason: refundReason || "Kısmi iade",
        },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.data.success) {
        toast.success(`İade başarılı: ${formatCurrency(res.data.net_refund)} müşteriye iade edildi`);
        setRefundModalOpen(false);
        setRefundClaim(null);
        fetchClaims();
      } else {
        toast.error(res.data.message || "Iyzico iadesi başarısız");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || "İade hatası");
    } finally {
      setRefundLoading(false);
    }
  };

  const advanceGpNo = (count) => {
    const base = parseInt(pad6(gpStart) || "0", 10);
    const next = pad6(base + (count || 1));
    setGpStart(next);
    localStorage.setItem("gp_next_no", next);
  };

  const handleGiderPusulasi = async (claimId) => {
    setGpLoading(true);
    try {
      const token = localStorage.getItem("token");
      const trackingNo = pad6(gpStart);
      const res = await axios.post(`${API}/integrations/trendyol/claims/${claimId}/gider-pusulasi`,
        { tracking_no: trackingNo },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setGpData({ ...res.data.gider_pusulasi, assigned_no: trackingNo });
      setGpModalOpen(true);
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gider pusulası oluşturulamadı");
    } finally {
      setGpLoading(false);
    }
  };

  // Modaldan tek pusula yazdır: aynı 4'lü A4 mekanizmasını kullanır
  const printSingleGp = () => {
    if (!gpData) return;
    setBulkPrintData([gpData]);
    setTimeout(() => { window.print(); advanceGpNo(1); }, 300);
  };

  const handleBulkPrint = async () => {
    if (selectedIds.size === 0) { toast.error("Yazdırılacak satır seçin"); return; }
    setGpLoading(true);
    try {
      const token = localStorage.getItem("token");
      const startNo = pad6(gpStart);
      const res = await axios.post(`${API}/integrations/trendyol/claims/bulk-gider-pusulasi`,
        { claim_ids: [...selectedIds], start_no: startNo },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      const list = res.data.gider_pusulalari || [];
      const base = parseInt(startNo || "0", 10);
      const withNo = list.map((gp, i) => ({ ...gp, assigned_no: pad6(base + i) }));
      setBulkPrintData(withNo);
      const nextNo = res.data.next_no || pad6(base + withNo.length);
      setGpStart(nextNo); localStorage.setItem("gp_next_no", nextNo);
      setTimeout(() => window.print(), 500);
      fetchClaims();
    } catch (err) {
      toast.error("Toplu yazdırma hatası");
    } finally {
      setGpLoading(false);
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === claims.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(claims.map(c => c.claim_id)));
    }
  };

  const totalPages = Math.ceil(total / limit);

  return (
    <div data-testid="admin-returns">
      {/* Gider Pusulası Yazdırma Katmanı: A4 dikey, sayfa başına 4 pusula */}
      {bulkPrintData && (
        <GpPrintLayer slips={bulkPrintData} overlay={gpOverlay} offX={gpOffX} offY={gpOffY} guides={gpGuides} />
      )}

      <div className="print:hidden">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">İadeler & İptaller</h1>
            <p className="text-xs text-gray-500 mt-1">Her 5 dakikada otomatik güncellenir</p>
          </div>
          <div className="flex items-center gap-3">
            {selectedIds.size > 0 && (
              <button onClick={handleBulkPrint} disabled={gpLoading}
                data-testid="bulk-print-btn"
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-bold hover:bg-purple-700 transition-colors disabled:opacity-50">
                <Printer size={16} />
                Toplu Yazdır ({selectedIds.size})
              </button>
            )}
            <button onClick={handleSync} disabled={syncing}
              data-testid="sync-claims-btn"
              className="flex items-center gap-2 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-bold hover:bg-orange-700 transition-colors disabled:opacity-50">
              <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Güncelleniyor..." : "Güncelle"}
            </button>
          </div>
        </div>

        {/* Gider Pusulası Ayarları */}
        <div className="flex flex-wrap items-end gap-4 mb-6 p-3 bg-purple-50 border border-purple-200 rounded-xl">
          <div>
            <label className="block text-[11px] font-bold text-purple-800 uppercase mb-1">Gider Pusulası Başlangıç No</label>
            <input value={gpStart}
              onChange={(e) => setGpStart(e.target.value)}
              onBlur={(e) => { const v = pad6(e.target.value); setGpStart(v); localStorage.setItem("gp_next_no", v); }}
              data-testid="gp-start-no"
              className="w-32 px-3 py-1.5 border border-purple-300 rounded-lg text-sm font-mono"
              placeholder="085490" />
          </div>
          <label className="flex items-center gap-2 text-sm text-purple-800 cursor-pointer pb-1.5">
            <input type="checkbox" checked={gpOverlay}
              onChange={(e) => { setGpOverlay(e.target.checked); localStorage.setItem("gp_overlay", e.target.checked ? "1" : "0"); }} />
            Matbu forma bindir (yalnız veri)
          </label>
          {gpOverlay && (
            <>
              <div>
                <label className="block text-[11px] font-bold text-purple-800 uppercase mb-1">Yatay (mm)</label>
                <input type="number" step="0.5" value={gpOffX}
                  onChange={(e) => { const v = parseFloat(e.target.value) || 0; setGpOffX(v); localStorage.setItem("gp_off_x", v); }}
                  className="w-20 px-2 py-1.5 border border-purple-300 rounded-lg text-sm" />
              </div>
              <div>
                <label className="block text-[11px] font-bold text-purple-800 uppercase mb-1">Dikey (mm)</label>
                <input type="number" step="0.5" value={gpOffY}
                  onChange={(e) => { const v = parseFloat(e.target.value) || 0; setGpOffY(v); localStorage.setItem("gp_off_y", v); }}
                  className="w-20 px-2 py-1.5 border border-purple-300 rounded-lg text-sm" />
              </div>
              <label className="flex items-center gap-2 text-sm text-purple-800 cursor-pointer pb-1.5">
                <input type="checkbox" checked={gpGuides} onChange={(e) => setGpGuides(e.target.checked)} />
                Hizalama çerçevesi
              </label>
            </>
          )}
          <p className="text-[11px] text-purple-600 ml-auto max-w-xs pb-1">
            A4 yatay, aynı pusula 4 kopya. Numara kağıda basılmaz (matbuda var); takip için satırda/önizlemede görünür. Her iade çıktısı no'yu 1 ilerletir.
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-white p-4 rounded-xl border shadow-sm">
            <p className="text-xs text-gray-500 font-bold uppercase">Toplam İade</p>
            <p className="text-2xl font-bold text-red-600 mt-1">{stats.total_returns || 0}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border shadow-sm">
            <p className="text-xs text-gray-500 font-bold uppercase">Toplam İptal</p>
            <p className="text-2xl font-bold text-yellow-600 mt-1">{stats.total_cancels || 0}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border shadow-sm">
            <p className="text-xs text-gray-500 font-bold uppercase">Toplam İade Tutarı</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{formatCurrency(stats.total_refund)}</p>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3 mb-4">
          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
            <input type="text" placeholder="Sipariş no, müşteri adı..."
              value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}
              className="w-full pl-9 pr-4 py-2 bg-white border rounded-lg text-sm" />
          </div>
          <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }}
            className="border rounded-lg px-3 py-2 text-sm bg-white">
            <option value="">Tümü</option>
            <option value="RETURN">İadeler</option>
            <option value="CANCEL">İptaller</option>
          </select>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-3 w-10">
                  <input type="checkbox" checked={claims.length > 0 && selectedIds.size === claims.length}
                    onChange={toggleSelectAll} className="rounded" data-testid="select-all-checkbox" />
                </th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Sipariş No</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Müşteri</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Tür</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Sebep</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Ödeme</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Kargo</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase">Brüt</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase">İskonto</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase">Net (Fatura)</th>
                <th className="text-left px-3 py-3 text-xs font-bold text-gray-500 uppercase">Tarih</th>
                <th className="text-center px-3 py-3 text-xs font-bold text-gray-500 uppercase">Durum</th>
                <th className="text-right px-3 py-3 text-xs font-bold text-gray-500 uppercase">İşlemler</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {loading ? (
                <tr><td colSpan={13} className="text-center py-12 text-gray-400">Yükleniyor...</td></tr>
              ) : claims.length === 0 ? (
                <tr><td colSpan={13} className="text-center py-12 text-gray-400">İade kaydı bulunamadı</td></tr>
              ) : claims.map(claim => {
                const totalGross = (claim.items || []).reduce((s, i) => s + (i.unit_price || 0), 0);
                const totalDiscount = (claim.items || []).reduce((s, i) => s + (i.discount_amount || 0), 0);
                const totalNet = (claim.items || []).reduce((s, i) => s + (i.price || 0), 0);
                const isExpanded = expandedId === claim.claim_id;
                const isActioned = !!claim.panel_action;

                return (
                  <tr key={claim.claim_id} className={`${selectedIds.has(claim.claim_id) ? "bg-blue-50" : "hover:bg-gray-50"} transition-colors`}>
                    <td className="px-3 py-3">
                      <input type="checkbox" checked={selectedIds.has(claim.claim_id)}
                        onChange={() => toggleSelect(claim.claim_id)} className="rounded"
                        data-testid={`select-claim-${claim.claim_id}`} />
                    </td>
                    <td className="px-3 py-3">
                      <button onClick={() => setExpandedId(isExpanded ? null : claim.claim_id)}
                        className="flex items-center gap-1 font-mono text-sm font-bold text-blue-600 hover:text-blue-800">
                        {claim.order_number}
                        {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                      </button>
                      {isExpanded && (
                        <div className="mt-2 p-3 bg-gray-50 rounded-lg text-xs space-y-1">
                          <p><strong>Claim ID:</strong> {claim.claim_id}</p>
                          {(claim.items || []).map((item, ii) => (
                            <div key={ii} className="flex justify-between border-t pt-1 mt-1">
                              <span>{item.productName}</span>
                              <span className="font-mono">{formatCurrency(item.price)}</span>
                            </div>
                          ))}
                          {claim.invoice_number && <p><strong>Fatura No:</strong> {claim.invoice_number}</p>}
                        </div>
                      )}
                    </td>
                    <td className="px-3 py-3 text-gray-700">{claim.customer_name || "-"}</td>
                    <td className="px-3 py-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        claim.claim_type === "RETURN" ? "bg-red-100 text-red-700" : "bg-yellow-100 text-yellow-700"
                      }`}>
                        {claim.claim_type === "RETURN" ? "İade" : "İptal"}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-xs text-gray-600 max-w-[140px] truncate">{claim.claim_reason || "-"}</td>
                    <td className="px-3 py-3 text-xs">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        (claim.payment_type || 'credit_card') === 'credit_card' ? 'bg-blue-100 text-blue-700' :
                        claim.payment_type === 'transfer' ? 'bg-purple-100 text-purple-700' : 'bg-gray-100 text-gray-700'
                      }`}>
                        {claim.payment_type === 'transfer' ? 'Havale' : claim.payment_type === 'cod' ? 'Kapıda' : 'Kredi Kartı'}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-xs">
                      {claim.cargo_tracking_number ? (
                        <div className="flex flex-col">
                          <span className="font-medium text-orange-600 text-[11px]">{claim.cargo_provider_name || 'Trendyol'}</span>
                          <span className="font-mono text-[10px] text-gray-500 truncate max-w-[110px]" title={claim.cargo_tracking_number}>{claim.cargo_tracking_number}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right font-mono text-gray-500 line-through text-xs">{totalDiscount > 0 ? formatCurrency(totalGross) : ""}</td>
                    <td className="px-3 py-3 text-right font-mono text-orange-600 text-xs font-bold">{totalDiscount > 0 ? `-${formatCurrency(totalDiscount)}` : "-"}</td>
                    <td className="px-3 py-3 text-right font-mono font-bold">{formatCurrency(totalNet)}</td>
                    <td className="px-3 py-3 text-xs text-gray-500">{formatDate(claim.created_date)}</td>
                    <td className="px-3 py-3 text-center"><ActionBadge action={claim.panel_action} /></td>
                    <td className="px-3 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {!isActioned ? (
                          <>
                            <button onClick={() => handleApprove(claim)}
                              data-testid={`approve-${claim.claim_id}`}
                              className="p-1.5 bg-green-100 text-green-700 rounded-lg hover:bg-green-200 transition-colors" title="Onayla">
                              <Check size={14} />
                            </button>
                            <button onClick={() => handleIssue(claim)}
                              data-testid={`issue-${claim.claim_id}`}
                              className="p-1.5 bg-red-100 text-red-700 rounded-lg hover:bg-red-200 transition-colors" title="İtiraz">
                              <X size={14} />
                            </button>
                          </>
                        ) : (
                          <span className="text-xs text-gray-400 italic px-1">
                            {claim.panel_action === "approved" ? "Onaylandı" : "İtiraz"}
                          </span>
                        )}
                        {claim.gider_pusulasi_no && (
                          <span className="text-[11px] font-mono font-bold text-purple-700 px-1" title="Gider Pusulası Takip No">
                            #{claim.gider_pusulasi_no}
                          </span>
                        )}
                        <button onClick={() => handleGiderPusulasi(claim.claim_id)}
                          disabled={gpLoading}
                          data-testid={`gp-${claim.claim_id}`}
                          className={`p-1.5 rounded-lg transition-colors ${
                            claim.has_gider_pusulasi
                              ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                              : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                          }`} title="Gider Pusulası">
                          <FileText size={14} />
                        </button>
                        {claim.claim_type === "RETURN" && (
                          <button onClick={() => openRefundModal(claim)}
                            data-testid={`refund-btn-${claim.claim_id}`}
                            className={`p-1.5 rounded-lg transition-colors ${
                              (claim.refunds || []).length > 0
                                ? "bg-blue-100 text-blue-700 hover:bg-blue-200"
                                : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                            }`}
                            title={(claim.refunds || []).length > 0 ? "Kısmi iade yapıldı" : "Iyzico Kısmi İade"}>
                            <CreditCard size={14} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4">
            <p className="text-sm text-gray-500">Toplam {total} kayıt, Sayfa {page}/{totalPages}</p>
            <div className="flex gap-2">
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50">Önceki</button>
              <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50">Sonraki</button>
            </div>
          </div>
        )}
      </div>

      {/* Gider Pusulası Modal */}
      <Dialog open={gpModalOpen} onOpenChange={setGpModalOpen}>
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto print:hidden" data-testid="gp-modal">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold flex items-center gap-2">
              <FileText size={20} />
              Gider Pusulası — Takip No {gpData?.assigned_no || gpData?.display_number}
            </DialogTitle>
          </DialogHeader>
          {gpData && (
            <div className="print:hidden">
              <p className="text-xs text-gray-500 mb-2">
                Bu pusula <span className="font-mono font-bold text-purple-700">#{gpData.assigned_no || gpData.display_number}</span> numaralı matbu forma basılacak. Numara kağıda yazılmaz; yalnız veriler basılır.
              </p>
              <div className="border rounded-lg overflow-hidden bg-white mx-auto" style={{ width: `${GP_SLIP_W_MM}mm`, maxWidth: "100%" }}>
                <GiderPusulasiSlip data={gpData} overlay={false} offX={0} offY={0} guides preview />
              </div>
              <div className="flex justify-end gap-3 mt-4">
                <button onClick={() => setGpModalOpen(false)}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">Kapat</button>
                <button onClick={printSingleGp}
                  data-testid="gp-print-btn"
                  className="px-6 py-2 bg-purple-600 text-white rounded-lg text-sm font-bold hover:bg-purple-700">
                  <Printer size={16} className="inline mr-2" />Yazdır
                </button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* A2 - Reject/Issue Reason Modal */}
      <Dialog open={rejectModalOpen} onOpenChange={(o) => { setRejectModalOpen(o); if (!o) setRejectTargetClaim(null); }}>
        <DialogContent data-testid="reject-reason-modal">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <X size={18} className="text-red-600" />
              İade Reddet / İtiraz
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            {rejectTargetClaim && (
              <div className="bg-gray-50 border rounded-lg p-3 text-sm">
                <p className="font-bold text-gray-900">Sipariş: {rejectTargetClaim.order_number}</p>
                <p className="text-xs text-gray-500 mt-1">{rejectTargetClaim.customer_name || "-"} · {rejectTargetClaim.claim_reason || ""}</p>
              </div>
            )}
            <div>
              <label className="block text-sm font-medium mb-1">İtiraz Sebep Kodu</label>
              <select
                value={rejectReasonId}
                onChange={(e) => setRejectReasonId(e.target.value)}
                data-testid="reject-reason-id"
                className="w-full border px-3 py-2 rounded text-sm bg-white"
              >
                <option value="1">1 - Ürün eksiksiz/hasarsız</option>
                <option value="2">2 - Ürün kullanılmış</option>
                <option value="3">3 - İade süresi aşıldı</option>
                <option value="4">4 - Ürün orijinalinden farklı</option>
                <option value="99">99 - Diğer</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">
                Ret Sebebi Açıklaması <span className="text-red-500">*</span>
              </label>
              <textarea
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="Müşteriye iletilecek itiraz nedenini detaylı yazın..."
                className="w-full border rounded-lg p-3 text-sm min-h-[120px]"
                data-testid="reject-reason-text"
                required
              />
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t">
              <button onClick={() => setRejectModalOpen(false)} className="px-4 py-2 border rounded hover:bg-gray-50 text-sm">
                İptal
              </button>
              <button
                onClick={submitReject}
                disabled={!rejectReason.trim()}
                data-testid="submit-reject-btn"
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 text-sm font-bold"
              >
                <X size={14} className="inline mr-1" /> Reddet ve Gönder
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Iyzico Kısmi İade Modal */}
      <Dialog open={refundModalOpen} onOpenChange={(o) => { setRefundModalOpen(o); if (!o) setRefundClaim(null); }}>
        <DialogContent data-testid="iyzico-refund-modal" className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CreditCard size={18} className="text-blue-600" />
              Iyzico Kısmi İade
            </DialogTitle>
            <DialogDescription className="text-xs text-gray-500 mt-1">
              Sipariş tutarından iade yapın. Kargo bedeli kesintisi opsiyoneldir.
            </DialogDescription>
          </DialogHeader>
          {refundClaim && (
            <div className="space-y-4 py-2">
              <div className="bg-blue-50 border border-blue-200 rounded p-3 text-xs">
                <div className="flex justify-between mb-1">
                  <span className="text-gray-600">Sipariş No:</span>
                  <span className="font-mono font-bold">{refundClaim.order_number || refundClaim.order_id}</span>
                </div>
                <div className="flex justify-between mb-1">
                  <span className="text-gray-600">Müşteri:</span>
                  <span>{refundClaim.customer_name || "-"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600">Sipariş Tutarı:</span>
                  <span className="font-bold">{formatCurrency(refundClaim.order_total || 0)}</span>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  İade Edilecek Ürün Tutarı (KDV Dahil) <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={refundAmount}
                  onChange={(e) => setRefundAmount(parseFloat(e.target.value) || 0)}
                  data-testid="refund-amount-input"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                />
                <p className="text-xs text-gray-500 mt-1">İade edilecek ürünlerin toplam tutarı</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1 flex items-center gap-1">
                  <Truck size={14} /> Kargo Bedeli Kesintisi
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={refundShipping}
                  onChange={(e) => setRefundShipping(parseFloat(e.target.value) || 0)}
                  data-testid="refund-shipping-input"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
                />
                <p className="text-xs text-gray-500 mt-1">İade tutarından düşülerek müşteriden alınacak kargo bedeli</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">İade Sebebi</label>
                <input
                  type="text"
                  value={refundReason}
                  onChange={(e) => setRefundReason(e.target.value)}
                  data-testid="refund-reason-input"
                  className="w-full px-3 py-2 border border-gray-300 rounded text-sm"
                  placeholder="Örn: Müşteri talebiyle iade"
                />
              </div>

              <div className="bg-gray-50 border border-gray-200 rounded p-3">
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-600">İade Tutarı:</span>
                  <span className="font-mono">{formatCurrency(refundAmount)}</span>
                </div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-600">Kargo Kesintisi:</span>
                  <span className="font-mono text-red-600">-{formatCurrency(refundShipping)}</span>
                </div>
                <div className="flex justify-between text-sm font-bold border-t border-gray-300 pt-1 mt-1">
                  <span>Müşteriye İade Edilecek:</span>
                  <span data-testid="refund-net-amount" className="font-mono text-blue-700">
                    {formatCurrency(Math.max(0, refundAmount - refundShipping))}
                  </span>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t">
                <button
                  onClick={() => setRefundModalOpen(false)}
                  disabled={refundLoading}
                  className="px-4 py-2 border rounded hover:bg-gray-50 text-sm disabled:opacity-50"
                >
                  İptal
                </button>
                <button
                  onClick={submitRefund}
                  disabled={refundLoading || refundAmount <= 0 || refundShipping >= refundAmount}
                  data-testid="submit-refund-btn"
                  className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm font-bold flex items-center gap-2"
                >
                  {refundLoading ? <RefreshCw size={14} className="animate-spin" /> : <CreditCard size={14} />}
                  {refundLoading ? "İade Yapılıyor..." : "Iyzico'ya İade Et"}
                </button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function fmt2(v) {
  return new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v || 0);
}

// Tek matbu form (sütun): 74.25mm x 210mm. overlay=true -> yalnız işaretli alan verisi basılır
// (matbu için). overlay=false -> gri referans form + siyah veri (boş kağıt / hizalama testi).
function GiderPusulasiSlip({ data, overlay, offX = 0, offY = 0, guides = false }) {
  if (!data) return null;
  const c = data.customer || {};
  const tot = data.totals || {};
  const items = data.items || [];
  const dt = data.date ? new Date(data.date) : null;
  const dateStr = dt ? dt.toLocaleDateString("tr-TR") : "";
  const timeStr = dt ? dt.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  const neg = (v) => -Math.abs(v || 0);
  const net = tot.net || 0;
  const matrah = tot.net_without_vat || 0;
  const kdv = tot.vat_amount || 0;
  const indirim = tot.discount || 0;
  const words = sayiToWords(Math.round(net));
  const cityLine = [c.district, c.city, c.country || "Türkiye"].filter(Boolean).join("/");

  const wrap = {
    position: "relative", width: GP_SLIP_W_MM + "mm", height: GP_SLIP_H_MM + "mm",
    boxSizing: "border-box", overflow: "hidden", fontFamily: "Arial, sans-serif",
    color: "#000", background: "#fff", borderRight: guides ? "0.3mm dashed #c084fc" : "none",
  };

  // --- GRİ REFERANS (yalnız overlay kapalıyken / önizlemede; KAĞIDA BASILMAZ) ---
  const G = "#9aa0a6";
  const Gt = (x, y, s, txt, extra = {}) => (
    <div style={{ position: "absolute", left: x + "mm", top: y + "mm", fontSize: s + "mm", color: G, whiteSpace: "nowrap", ...extra }}>{txt}</div>
  );
  const reference = !overlay && (
    <div style={{ position: "absolute", inset: 0 }}>
      {Gt(5, 4, 1.7, "No: 3  34307 Küçükçekmece/İST.")}
      {Gt(5, 7.5, 1.7, "Halkalı V.D.: 781 081 6779")}
      {Gt(5, 11, 1.7, "Ticaret Sicil No: 203113-5")}
      {Gt(5, 14.5, 1.7, "iletisim@facette.com.tr")}
      <div style={{ position: "absolute", left: "52mm", top: "4mm", width: "13mm", height: "13mm", border: "0.3mm solid " + G, borderRadius: "50%", textAlign: "center", fontSize: "1.4mm", color: G, lineHeight: "13mm" }}>T.C.</div>
      {Gt(48, 27, 1.9, "İL KODU: 34", { fontWeight: 700 })}
      {Gt(52, 34, 2.0, "SERİ A", { fontWeight: 700 })}
      {Gt(5, 188, 1.6, "Yalnız _______________________")}
      {Gt(5, 193, 1.5, "____ den yukarıda belirtilen Mal/İş")}
      {Gt(5, 196.5, 1.5, "bedelini aldım.")}
      {Gt(5, 202, 1.6, "Adı Soyadı ________________")}
      {Gt(5, 206, 1.6, "Adresi ___________   İMZA")}
      <div style={{ position: "absolute", left: "2.4mm", top: "150mm", transform: "rotate(-90deg)", transformOrigin: "left top", fontSize: "1.7mm", color: "#cc2222" }}>SIRA NO   No {data.assigned_no || ""}</div>
    </div>
  );

  // --- SİYAH VERİ: sıkışık akışkan blok (KAĞIDA BASILAN TEK ALAN) ---
  const row = (label, val, bold) => (
    <div style={{ display: "flex", justifyContent: "space-between", gap: "2mm", fontWeight: bold ? 700 : 400 }}>
      <span>{label}</span><span>{val}</span>
    </div>
  );
  const black = (
    <div style={{ position: "absolute", left: "6mm", top: "41mm", width: "63mm", transform: `translate(${offX}mm, ${offY}mm)`, fontSize: "2.0mm", lineHeight: 1.12, color: "#000" }}>
      <div style={{ fontWeight: 700 }}>{c.name || ""}</div>
      {c.address ? <div>{c.address}</div> : null}
      <div>{cityLine}</div>
      <div style={{ height: "1.2mm" }} />
      <div>Sipariş: {data.order_number || ""}</div>
      <div>{dateStr}{timeStr ? "  " + timeStr : ""}</div>
      <div style={{ height: "0.8mm" }} />
      <div>Satış Fatura No: {data.sales_invoice_no || "-"}</div>
      <div>Kargo Firma: {data.cargo_company || "-"}</div>
      <div>Satış Sorumlusu: {data.sales_rep || "-"}</div>
      <div style={{ height: "1mm" }} />
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "1.9mm" }}>
        <thead>
          <tr style={{ borderBottom: "0.2mm solid #999" }}>
            <th style={{ textAlign: "left", fontWeight: 700, padding: "0.2mm 0" }}>Açıklama</th>
            <th style={{ textAlign: "right", fontWeight: 700, width: "8mm" }}>Ad.</th>
            <th style={{ textAlign: "right", fontWeight: 700, width: "17mm" }}>Tutar</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => (
            <tr key={i}>
              <td style={{ padding: "0.3mm 0" }}>{(it.name || "").slice(0, 26)}</td>
              <td style={{ textAlign: "right" }}>{it.quantity}</td>
              <td style={{ textAlign: "right" }}>{fmt2(neg(it.net_price))}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ height: "1.2mm" }} />
      {row("Tutar (V.D.)", fmt2(net), true)}
      {row("Toplam Satır İsk (VD)", fmt2(indirim))}
      {row("Toplam Dip İsk (/D)", fmt2(0))}
      {row("Vergi Matrahı", fmt2(matrah))}
      {row("Kdv", fmt2(kdv))}
      {row("Net Tutar", fmt2(net), true)}
      <div style={{ height: "0.8mm" }} />
      <div>Yalnız: {words} TL</div>
    </div>
  );

  return <div style={wrap}>{reference}{black}</div>;
}

// A4 YATAY: her iade = 1 sayfa, aynı pusula 4 kopya (4 sütun). Ekranda gizli, yazdırmada görünür.
function GpPrintLayer({ slips, overlay, offX, offY, guides }) {
  if (typeof document === "undefined") return null;
  return createPortal(
    <div className="gp-print">
      <style>{`
        .gp-print { display: none; }
        @media print {
          @page { size: A4 landscape; margin: 0; }
          html, body { margin: 0 !important; padding: 0 !important; background: #fff !important; }
          /* Yazdırmada SADECE gider pusulası katmanı; admin arayüzü/başlık/kenar çubuğu/modal gizlenir */
          body > *:not(.gp-print) { display: none !important; }
          .gp-print { display: block !important; background: #fff; }
          .gp-page { width: ${GP_PAGE_W_MM}mm; height: ${GP_PAGE_H_MM}mm; display: flex; flex-direction: row; page-break-after: always; overflow: hidden; background: #fff; }
          .gp-page:last-child { page-break-after: auto; }
          .gp-col { width: ${GP_SLIP_W_MM}mm; height: ${GP_SLIP_H_MM}mm; }
        }
      `}</style>
      {(slips || []).map((gp, pi) => (
        <div className="gp-page" key={pi}>
          {Array.from({ length: GP_COPIES }).map((_, ci) => (
            <div className="gp-col" key={ci}>
              <GiderPusulasiSlip data={gp} overlay={overlay} offX={offX} offY={offY} guides={guides} />
            </div>
          ))}
        </div>
      ))}
    </div>,
    document.body
  );
}
