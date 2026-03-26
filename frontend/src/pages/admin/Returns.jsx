import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, Search, Check, X, FileText, Printer, ChevronDown, ChevronUp, AlertCircle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function formatCurrency(val) {
  return new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY" }).format(val || 0);
}

function formatDate(d) {
  if (!d) return "-";
  try { return new Date(d).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return d; }
}

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
  const autoRefreshRef = useRef(null);
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
    if (!window.confirm("Bu iadeyi onaylamak istediğinize emin misiniz?")) return;
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
    const desc = window.prompt("İtiraz açıklaması:");
    if (desc === null) return;
    try {
      const token = localStorage.getItem("token");
      const claimItemIds = (claim.items || []).map(i => i.claim_item_id).filter(Boolean);
      await axios.post(`${API}/integrations/trendyol/claims/${claim.claim_id}/issue`,
        { claim_item_ids: claimItemIds, issue_reason_id: 1, description: desc || "İtiraz" },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      toast.success("İtiraz oluşturuldu");
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "İtiraz hatası");
    }
  };

  const handleGiderPusulasi = async (claimId) => {
    setGpLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(`${API}/integrations/trendyol/claims/${claimId}/gider-pusulasi`, {},
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setGpData(res.data.gider_pusulasi);
      setGpModalOpen(true);
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Gider pusulası oluşturulamadı");
    } finally {
      setGpLoading(false);
    }
  };

  const handleBulkPrint = async () => {
    if (selectedIds.size === 0) { toast.error("Yazdırılacak satır seçin"); return; }
    setGpLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(`${API}/integrations/trendyol/claims/bulk-gider-pusulasi`,
        { claim_ids: [...selectedIds] },
        { headers: { Authorization: `Bearer ${token}` } }
      );
      setBulkPrintData(res.data.gider_pusulalari);
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
      {/* Bulk Print Hidden Area */}
      {bulkPrintData && (
        <div className="hidden print:block">
          {bulkPrintData.map((gp, idx) => (
            <div key={idx} className="page-break-after p-8" style={{ pageBreakAfter: "always" }}>
              <GiderPusulasiContent data={gp} />
            </div>
          ))}
        </div>
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
                <tr><td colSpan={11} className="text-center py-12 text-gray-400">Yükleniyor...</td></tr>
              ) : claims.length === 0 ? (
                <tr><td colSpan={11} className="text-center py-12 text-gray-400">İade kaydı bulunamadı</td></tr>
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
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="gp-modal">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold flex items-center gap-2">
              <FileText size={20} />
              Gider Pusulası {gpData?.display_number}
            </DialogTitle>
          </DialogHeader>
          {gpData && (
            <div>
              <div id="gider-pusulasi-print">
                <GiderPusulasiContent data={gpData} />
              </div>
              <div className="flex justify-end gap-3 mt-4 print:hidden">
                <button onClick={() => setGpModalOpen(false)}
                  className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-200">Kapat</button>
                <button onClick={() => { 
                    const printWindow = window.open('', '_blank');
                    const el = document.getElementById('gider-pusulasi-print');
                    printWindow.document.write(`<html><head><title>Gider Pusulası ${gpData.display_number}</title>
                      <style>body{font-family:Arial,sans-serif;margin:20px;font-size:12px}
                      table{width:100%;border-collapse:collapse}td,th{border:1px solid #333;padding:6px;text-align:left}
                      th{background:#f5f5f5}h2,h3{margin:8px 0}.right{text-align:right}.center{text-align:center}
                      .header{display:flex;justify-content:space-between;margin-bottom:16px}
                      .bold{font-weight:bold}.border{border:1px solid #333;padding:12px;margin:8px 0}</style></head>
                      <body>${el.innerHTML}</body></html>`);
                    printWindow.document.close();
                    printWindow.print();
                  }}
                  className="px-6 py-2 bg-purple-600 text-white rounded-lg text-sm font-bold hover:bg-purple-700">
                  <Printer size={16} className="inline mr-2" />Yazdır
                </button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GiderPusulasiContent({ data }) {
  if (!data) return null;
  const company = data.company || {};
  const customer = data.customer || {};
  const totals = data.totals || {};

  return (
    <div className="text-xs leading-relaxed" style={{ fontFamily: "Arial, sans-serif" }}>
      <div className="text-center mb-4">
        <h2 className="text-base font-bold uppercase tracking-wide">GİDER PUSULASI</h2>
        <p className="text-gray-600 mt-1">Türk Vergi Usul Kanunu Madde 234</p>
      </div>

      <div className="flex justify-between mb-4">
        <div className="border border-gray-400 p-3 rounded flex-1 mr-2">
          <p className="font-bold text-sm mb-1">Düzenleyen (Alıcı)</p>
          <p className="font-bold">{company.company_name || "-"}</p>
          <p>{company.address || "-"}</p>
          <p>{company.city || "-"}</p>
          <p>VD: {company.tax_office || "-"}</p>
          <p>VKN: {company.tax_number || "-"}</p>
        </div>
        <div className="border border-gray-400 p-3 rounded w-48">
          <p className="font-bold text-sm mb-1">Belge Bilgisi</p>
          <p><strong>No:</strong> {data.display_number}</p>
          <p><strong>Tarih:</strong> {formatDate(data.date)}</p>
          <p><strong>Sipariş:</strong> {data.order_number}</p>
          <p><strong>Tür:</strong> {data.claim_type === "RETURN" ? "İade" : "İptal"}</p>
        </div>
      </div>

      <div className="border border-gray-400 p-3 rounded mb-4">
        <p className="font-bold text-sm mb-1">Satıcı / Müşteri (Ödeme Yapılan)</p>
        <p className="font-bold">{customer.name || "-"}</p>
        <p>{customer.address || ""} {customer.city || ""}</p>
        {data.claim_reason && <p className="mt-1"><strong>İade Sebebi:</strong> {data.claim_reason}</p>}
      </div>

      <table className="w-full border-collapse mb-4" style={{ border: "1px solid #666" }}>
        <thead>
          <tr style={{ backgroundColor: "#f0f0f0" }}>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-center w-8">#</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-left">Ürün Adı</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-left">Barkod</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-center">Adet</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-right">Birim Fiyat</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-right">İskonto</th>
            <th style={{ border: "1px solid #666", padding: "6px" }} className="text-right">Net Tutar</th>
          </tr>
        </thead>
        <tbody>
          {(data.items || []).map((item, idx) => (
            <tr key={idx}>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="text-center">{idx + 1}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }}>{item.name}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="font-mono text-xs">{item.barcode}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="text-center">{item.quantity}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="text-right">{formatCurrency(item.unit_price)}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="text-right">{item.discount > 0 ? formatCurrency(item.discount) : "-"}</td>
              <td style={{ border: "1px solid #666", padding: "6px" }} className="text-right font-bold">{formatCurrency(item.net_price)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex justify-end">
        <div className="border border-gray-400 rounded p-3 w-64">
          {totals.discount > 0 && (
            <>
              <div className="flex justify-between mb-1"><span>Brüt Tutar:</span><span>{formatCurrency(totals.gross)}</span></div>
              <div className="flex justify-between mb-1 text-orange-600"><span>İskonto:</span><span>-{formatCurrency(totals.discount)}</span></div>
            </>
          )}
          <div className="flex justify-between mb-1"><span>KDV Matrahı:</span><span>{formatCurrency(totals.net_without_vat)}</span></div>
          <div className="flex justify-between mb-1"><span>KDV (%{totals.vat_rate}):</span><span>{formatCurrency(totals.vat_amount)}</span></div>
          <div className="flex justify-between font-bold text-sm border-t pt-1 mt-1">
            <span>Genel Toplam:</span><span>{formatCurrency(totals.net)}</span>
          </div>
        </div>
      </div>

      <div className="mt-8 flex justify-between">
        <div className="text-center w-48">
          <div className="border-b border-gray-400 mb-1 h-16"></div>
          <p className="font-bold">Düzenleyen</p>
          <p>{company.company_name || ""}</p>
        </div>
        <div className="text-center w-48">
          <div className="border-b border-gray-400 mb-1 h-16"></div>
          <p className="font-bold">Teslim Eden / Satıcı</p>
          <p>{customer.name || ""}</p>
        </div>
      </div>
    </div>
  );
}
