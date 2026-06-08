import { useState, useEffect, useRef, useCallback } from "react";
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

// 4 pusula/sayfa: A4 dikey (297mm) / 4 = 74.25mm bant
const GP_PER_PAGE = 4;
const GP_SLIP_H_MM = 74.25;
const GP_SLIP_W_MM = 210;

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
  const [gpOverlay, setGpOverlay] = useState(() => localStorage.getItem("gp_overlay") === "1");
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
            Numara kağıda basılmaz (matbuda zaten var); takip için satırda ve önizlemede görünür. Her çıktı 1 ilerler.
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

const gpTh = { border: "0.2mm solid #555", padding: "0.4mm 1mm", textAlign: "left", fontWeight: 700, background: "#f0f0f0" };
const gpTd = { border: "0.2mm solid #555", padding: "0.4mm 1mm" };

// Tek pusula: matbu forma bindirme (yalnız veri) veya tam form (boş kağıt / önizleme)
function GiderPusulasiSlip({ data, overlay, offX = 0, offY = 0, guides = false }) {
  if (!data) return null;
  const co = data.company || {};
  const c = data.customer || {};
  const t = data.totals || {};
  const items = data.items || [];
  const dt = data.date ? new Date(data.date) : null;
  const dateStr = dt ? dt.toLocaleDateString("tr-TR") : "";
  const timeStr = dt ? dt.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "";
  const neg = (v) => (v ? -Math.abs(v) : 0);
  const tutar = t.net || 0;
  const matrah = t.net_without_vat || 0;
  const kdv = t.vat_amount || 0;
  const words = sayiToWords(Math.round(tutar));
  const coName = co.company_name || "FACETTE DIŞ TİC. A.Ş.";
  const coAddr = [co.address, co.city].filter(Boolean).join(" ");
  const coVd = co.tax_office || "Halkalı";
  const coVkn = co.tax_number || "7810816779";

  const slipStyle = {
    width: GP_SLIP_W_MM + "mm",
    height: GP_SLIP_H_MM + "mm",
    boxSizing: "border-box",
    position: "relative",
    overflow: "hidden",
    fontFamily: "Arial, sans-serif",
    fontSize: "2.4mm",
    lineHeight: 1.15,
    color: "#000",
    background: "#fff",
    padding: "3mm 5mm",
    border: guides ? "0.3mm dashed #c084fc" : "none",
  };
  const inner = { transform: `translate(${offX}mm, ${offY}mm)`, height: "100%", position: "relative" };

  // ---- Matbu bindirme: yalnız değişken veri, mutlak konum (hizalama mm offset ile) ----
  if (overlay) {
    const F = ({ x, y, w, a = "left", b = false, children }) => (
      <div style={{ position: "absolute", left: x + "mm", top: y + "mm", width: w ? w + "mm" : undefined, textAlign: a, fontWeight: b ? 700 : 400, whiteSpace: "nowrap", overflow: "hidden" }}>{children}</div>
    );
    return (
      <div style={slipStyle}>
        <div style={inner}>
          <F x={26} y={9} b>{c.name || ""}</F>
          <F x={26} y={13}>{c.address || ""}</F>
          <F x={26} y={19}>{[c.district, c.city, "Türkiye"].filter(Boolean).join("/")}</F>
          <F x={30} y={32}>{data.order_number || ""}</F>
          <F x={30} y={35}>{dateStr}</F>
          <F x={68} y={35}>{timeStr}</F>
          {items.slice(0, 4).map((it, i) => (
            <F key={i} x={30} y={50 + i * 3.2} w={90}>{(it.name || "").slice(0, 40)}</F>
          ))}
          {items.slice(0, 4).map((it, i) => (
            <F key={"a" + i} x={150} y={50 + i * 3.2} w={24} a="right">{fmt2(neg(it.net_price))}</F>
          ))}
          <F x={118} y={50} w={28} a="right" b>{fmt2(tutar)}</F>
          <F x={118} y={61} w={28} a="right">{fmt2(matrah)}</F>
          <F x={118} y={64} w={28} a="right">{fmt2(kdv)}</F>
          <F x={118} y={67} w={28} a="right" b>{fmt2(tutar)}</F>
          <F x={26} y={67} w={80}>{words}</F>
        </div>
      </div>
    );
  }

  // ---- Tam form (boş kağıt / önizleme) ----
  return (
    <div style={slipStyle}>
      <div style={inner}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <div style={{ fontWeight: 700 }}>{coName}</div>
            <div>{coAddr}</div>
            <div>V.D.: {coVd} &nbsp; VKN: {coVkn}</div>
            <div>iletisim@facette.com.tr</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div>İL KODU: 34</div>
            <div style={{ fontWeight: 700 }}>SERİ A</div>
            <div style={{ fontWeight: 700 }}>GİDER PUSULASI</div>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.5mm" }}>
          <div style={{ maxWidth: "120mm" }}>
            <div style={{ fontWeight: 700 }}>{c.name || "-"}</div>
            <div>{c.address || ""}</div>
            <div>{[c.district, c.city, "Türkiye"].filter(Boolean).join("/")}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div>Sipariş: {data.order_number || "-"}</div>
            <div>{dateStr} {timeStr}</div>
            <div>{data.claim_type === "RETURN" ? "İade" : "İptal"}</div>
          </div>
        </div>

        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "1.5mm" }}>
          <thead>
            <tr>
              <th style={gpTh}>Açıklama</th>
              <th style={{ ...gpTh, textAlign: "center", width: "12mm" }}>Adet</th>
              <th style={{ ...gpTh, textAlign: "right", width: "28mm" }}>Tutar</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i}>
                <td style={gpTd}>{it.name}</td>
                <td style={{ ...gpTd, textAlign: "center" }}>{it.quantity}</td>
                <td style={{ ...gpTd, textAlign: "right" }}>{fmt2(neg(it.net_price))}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1.5mm" }}>
          <div style={{ maxWidth: "115mm" }}>
            <div>Yalnız: <span style={{ fontWeight: 700 }}>{words} TL</span></div>
            <div style={{ marginTop: "2.5mm" }}>Adı Soyadı: {c.name || ""}</div>
            <div style={{ marginTop: "2.5mm" }}>İmza:</div>
          </div>
          <div style={{ textAlign: "right", minWidth: "48mm" }}>
            <div>Tutar: <b>{fmt2(tutar)}</b></div>
            <div>Vergi Matrahı: {fmt2(matrah)}</div>
            <div>KDV: {fmt2(kdv)}</div>
            <div style={{ fontWeight: 700 }}>Net Tutar: {fmt2(tutar)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

// A4 dikey: sayfa başına 4 pusula. Ekranda gizli, sadece yazdırmada görünür.
function GpPrintLayer({ slips, overlay, offX, offY, guides }) {
  const pages = [];
  for (let i = 0; i < (slips || []).length; i += GP_PER_PAGE) pages.push(slips.slice(i, i + GP_PER_PAGE));
  return (
    <div className="gp-print">
      <style>{`
        .gp-print { display: none; }
        @media print {
          body { margin: 0 !important; }
          .gp-print { display: block !important; }
          .gp-page { width: ${GP_SLIP_W_MM}mm; height: 297mm; page-break-after: always; }
          .gp-page:last-child { page-break-after: auto; }
          .gp-slip-wrap { width: ${GP_SLIP_W_MM}mm; height: ${GP_SLIP_H_MM}mm; }
        }
      `}</style>
      {pages.map((pg, pi) => (
        <div className="gp-page" key={pi}>
          {pg.map((gp, si) => (
            <div className="gp-slip-wrap" key={si}>
              <GiderPusulasiSlip data={gp} overlay={overlay} offX={offX} offY={offY} guides={guides} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
