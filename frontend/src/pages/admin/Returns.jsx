import { useState, useEffect } from "react";
import { RefreshCw, Search, RotateCcw, XCircle, Eye, Package, DollarSign, AlertTriangle, FileText, CheckCircle } from "lucide-react";
import axios from "axios";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminReturns() {
  const [claims, setClaims] = useState([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [typeFilter, setTypeFilter] = useState("");
  const [search, setSearch] = useState("");
  const [stats, setStats] = useState({ total_returns: 0, total_cancels: 0, total_refund: 0 });
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedClaim, setSelectedClaim] = useState(null);
  const [daysBack, setDaysBack] = useState(90);

  // Issue states
  const [issueModalOpen, setIssueModalOpen] = useState(false);
  const [issueReasons, setIssueReasons] = useState([]);
  const [actionItem, setActionItem] = useState(null);
  const [issueReasonId, setIssueReasonId] = useState("");
  const [issueDesc, setIssueDesc] = useState("");
  const [actionLoading, setActionLoading] = useState(false);

  useEffect(() => {
    fetchClaims();
    fetchIssueReasons();
  }, [page, typeFilter]);

  const fetchClaims = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      let url = `${API}/trendyol/claims?page=${page}&limit=20`;
      if (typeFilter) url += `&claim_type=${typeFilter}`;
      if (search) url += `&search=${search}`;
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
      setClaims(res.data?.claims || []);
      setTotal(res.data?.total || 0);
      setStats(res.data?.stats || { total_returns: 0, total_cancels: 0, total_refund: 0 });
    } catch (err) {
      console.error(err);
      toast.error("İade kayıtları yüklenemedi");
    } finally {
      setLoading(false);
    }
  };

  const fetchIssueReasons = async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/trendyol/claims/issue-reasons`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setIssueReasons(res.data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/trendyol/claims/sync?days_back=${daysBack}`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 120000
      });
      toast.success(res.data?.message || "Senkronizasyon tamamlandı");
      fetchClaims();
    } catch (err) {
      console.error(err);
      toast.error(err.response?.data?.detail || "Senkronizasyon başarısız");
    } finally {
      setSyncing(false);
    }
  };

  const handleSearch = () => {
    setPage(1);
    fetchClaims();
  };

  const openDetail = async (claim) => {
    try {
      const token = localStorage.getItem("token");
      const res = await axios.get(`${API}/trendyol/claims/${claim.claim_id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setSelectedClaim(res.data);
      setDetailOpen(true);
    } catch (err) {
      setSelectedClaim(claim);
      setDetailOpen(true);
    }
  };

  const approveClaim = async (item) => {
    if (!window.confirm("Bu iade kalemini onaylamak istediğinize emin misiniz?")) return;
    
    setActionLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(`${API}/trendyol/claims/${selectedClaim.claim_id}/approve`, {
        claim_item_ids: [item.claim_item_id]
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(res.data?.message || "İade onaylandı");
      setDetailOpen(false);
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Onaylama başarısız");
    } finally {
      setActionLoading(false);
    }
  };

  const openIssueModal = (item) => {
    setActionItem(item);
    setIssueReasonId("");
    setIssueDesc("");
    setIssueModalOpen(true);
  };

  const submitIssue = async () => {
    if (!issueReasonId) return toast.error("Lütfen bir itiraz sebebi seçin");
    
    setActionLoading(true);
    try {
      const token = localStorage.getItem("token");
      const res = await axios.post(`${API}/trendyol/claims/${selectedClaim.claim_id}/issue`, {
        claim_item_ids: [actionItem.claim_item_id],
        issue_reason_id: parseInt(issueReasonId),
        description: issueDesc
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success(res.data?.message || "İtiraz talebi oluşturuldu");
      setIssueModalOpen(false);
      setDetailOpen(false);
      fetchClaims();
    } catch (err) {
      toast.error(err.response?.data?.detail || "İtiraz oluşturma başarısız");
    } finally {
      setActionLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleString("tr-TR");
    } catch {
      return dateStr;
    }
  };

  const totalPages = Math.ceil(total / 20);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold">İade ve İptaller</h1>
          <p className="text-gray-500 text-sm mt-1">Trendyol iade ve iptal talepleri</p>
        </div>
        <div className="flex gap-2 items-center">
          <input 
            type="number" 
            value={daysBack}
            onChange={(e) => setDaysBack(e.target.value)}
            className="w-20 border rounded px-2 py-2 text-sm"
            title="Geriye Dönük Gün"
            min="1"
            max="365"
          />
          <span className="text-sm text-gray-500 font-medium whitespace-nowrap hidden sm:block">Gün</span>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg hover:bg-gray-800 disabled:opacity-50"
          >
            <RefreshCw size={18} className={syncing ? "animate-spin" : ""} />
            {syncing ? "Eşitleniyor..." : "Son Siparişleri Çek"}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
        <div className="bg-white p-6 rounded-xl border flex items-center gap-4">
          <div className="w-12 h-12 bg-orange-100 rounded-full flex items-center justify-center text-orange-600">
            <RotateCcw size={24} />
          </div>
          <div>
            <p className="text-gray-500 text-sm font-medium">Toplam İade</p>
            <p className="text-2xl font-bold">{stats.total_returns || 0}</p>
          </div>
        </div>
        <div className="bg-white p-6 rounded-xl border flex items-center gap-4">
          <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center text-red-600">
            <XCircle size={24} />
          </div>
          <div>
            <p className="text-gray-500 text-sm font-medium">Toplam İptal</p>
            <p className="text-2xl font-bold">{stats.total_cancels || 0}</p>
          </div>
        </div>
        <div className="bg-white p-6 rounded-xl border flex items-center gap-4">
          <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">
            <DollarSign size={24} />
          </div>
          <div>
            <p className="text-gray-500 text-sm font-medium">İade/İptal Tutarı</p>
            <p className="text-2xl font-bold">{(stats.total_refund || 0).toLocaleString("tr-TR", { minimumFractionDigits: 2 })} ₺</p>
          </div>
        </div>
      </div>

      {/* Search and Filter */}
      <div className="bg-white rounded-xl border shadow-sm">
        <div className="p-4 border-b flex flex-wrap gap-4 justify-between">
          <div className="flex gap-2">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1"
            >
              <option value="">Tüm Talepler</option>
              <option value="RETURN">İadeler</option>
              <option value="CANCEL">İptaller</option>
            </select>
          </div>
          <div className="relative border rounded-lg overflow-hidden flex-1 max-w-sm">
            <input
              type="text"
              placeholder="Sipariş / Claim No Ara..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-3 py-2 text-sm focus:outline-none"
            />
            <Search size={16} className="absolute left-3 top-2.5 text-gray-400" />
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-6 py-4 font-medium">Sipariş / Claim No</th>
                <th className="text-left px-6 py-4 font-medium">Durum / Tür</th>
                <th className="text-left px-6 py-4 font-medium">Müşteri</th>
                <th className="text-left px-6 py-4 font-medium hidden md:table-cell">Tarih</th>
                <th className="text-right px-6 py-4 font-medium">Tutar</th>
                <th className="text-center px-6 py-4 font-medium">İşlem</th>
              </tr>
            </thead>
            <tbody className="divide-y text-gray-700">
              {loading ? (
                <tr><td colSpan="6" className="px-6 py-8 text-center text-gray-500">Yükleniyor...</td></tr>
              ) : claims.length === 0 ? (
                <tr><td colSpan="6" className="px-6 py-8 text-center text-gray-500">Kayıt bulunamadı.</td></tr>
              ) : (
                claims.map((claim) => (
                  <tr key={claim._id} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <div className="font-semibold">{claim.order_number}</div>
                      <div className="text-xs text-gray-400 mt-1">{claim.claim_id}</div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {claim.claim_type === "RETURN" ? (
                          <span className="inline-flex py-1 px-2 rounded-md bg-orange-100 text-orange-700 text-xs font-medium">İade</span>
                        ) : (
                          <span className="inline-flex py-1 px-2 rounded-md bg-red-100 text-red-700 text-xs font-medium">İptal</span>
                        )}
                        <span className="text-xs text-gray-500">{claim.claim_status || claim.claim_reason}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 truncate max-w-[150px]">{claim.customer_name || "-"}</td>
                    <td className="px-6 py-4 hidden md:table-cell text-xs">{formatDate(claim.created_date)}</td>
                    <td className="px-6 py-4 text-right font-medium text-red-600">
                      {claim.refund_amount ? claim.refund_amount.toFixed(2) + " ₺" : "-"}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button 
                        onClick={() => {
                          setSelectedClaim(claim);
                          setDetailOpen(true);
                        }}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                        title="Detay Görüntüle"
                      >
                        <Eye size={18} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2 mt-4">
          <button
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
            className="px-3 py-1.5 border rounded text-sm disabled:opacity-50 hover:bg-gray-50"
          >
            ← Önceki
          </button>
          <span className="px-3 py-1.5 text-sm text-gray-600">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
            className="px-3 py-1.5 border rounded text-sm disabled:opacity-50 hover:bg-gray-50"
          >
            Sonraki →
          </button>
        </div>
      )}

      {/* Detail Modal */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto w-full">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedClaim?.claim_type === "RETURN" ? (
                <RotateCcw size={20} className="text-orange-600" />
              ) : (
                <XCircle size={20} className="text-red-600" />
              )}
              Sipariş #{selectedClaim?.order_number}
              <span className="text-xs text-gray-400 ml-2">Claim: {selectedClaim?.claim_id?.substring(0, 8)}...</span>
            </DialogTitle>
          </DialogHeader>

          {selectedClaim && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 p-4 bg-gray-50 rounded-lg">
                <div>
                  <p className="text-xs text-gray-500">Tür</p>
                  <p className="font-semibold">
                    {selectedClaim.claim_type === "RETURN" ? "İade" : "İptal"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Durum</p>
                  <p className="font-semibold">{selectedClaim.claim_status}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Müşteri</p>
                  <p className="font-semibold">{selectedClaim.customer_name || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Tarih</p>
                  <p className="font-semibold">{formatDate(selectedClaim.created_date)}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Sebep</p>
                  <p className="font-semibold">{selectedClaim.claim_reason || "-"}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">İade Tutarı</p>
                  <p className="font-semibold text-red-600">{selectedClaim.refund_amount?.toFixed(2)} ₺</p>
                </div>
                <div>
                  <p className="text-xs text-gray-500">Kargo Takip</p>
                  <p className="font-semibold">{selectedClaim.cargo_tracking_number || "-"}</p>
                </div>
                <div className="col-span-2 lg:col-span-4 border-t pt-3 mt-1 flex justify-between items-center">
                  <div>
                    <p className="text-xs text-gray-500">Fatura Numarası</p>
                    <p className="font-semibold text-lg">{selectedClaim.invoice_number || <span className="text-gray-400 text-sm">Bulunamadı</span>}</p>
                  </div>
                  {selectedClaim.invoice_link && (
                    <a 
                      href={selectedClaim.invoice_link} 
                      target="_blank" 
                      rel="noopener noreferrer"
                      className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-600 rounded hover:bg-blue-100 text-sm font-medium"
                    >
                      <FileText size={16} />
                      Faturayı Gör
                    </a>
                  )}
                </div>
              </div>

              {/* Items */}
              <div>
                <h4 className="font-semibold mb-2">Ürün Kalemleri</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm border whitespace-nowrap lg:whitespace-normal">
                    <thead className="bg-gray-100">
                      <tr>
                        <th className="text-left px-3 py-2 border-b">Ürün</th>
                        <th className="text-left px-3 py-2 border-b hidden sm:table-cell">Barkod</th>
                        <th className="text-right px-3 py-2 border-b">Birim Fiyat</th>
                        <th className="text-right px-3 py-2 border-b text-orange-600">İndirim</th>
                        <th className="text-right px-3 py-2 border-b">Net Tutar</th>
                        <th className="text-center px-3 py-2 border-b">İşlem</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedClaim.items?.map((item, i) => (
                        <tr key={i} className="hover:bg-gray-50">
                          <td className="px-3 py-2 border-b">
                            <div className="max-w-[200px] truncate" title={item.productName || "-"}>
                              {item.productName || "-"}
                            </div>
                            <div className="sm:hidden text-xs text-gray-500 font-mono mt-1">{item.barcode}</div>
                          </td>
                          <td className="px-3 py-2 border-b font-mono text-xs hidden sm:table-cell">{item.barcode || "-"}</td>
                          <td className="px-3 py-2 border-b text-right text-gray-500 line-through text-xs">{(item.unit_price || item.price)?.toFixed(2)} ₺</td>
                          <td className="px-3 py-2 border-b text-right text-orange-600 text-xs">{(item.discount_amount || 0)?.toFixed(2)} ₺</td>
                          <td className="px-3 py-2 border-b text-right font-medium">{item.price?.toFixed(2)} ₺</td>
                          <td className="px-3 py-2 border-b text-center">
                            {/* Actions only valid if waiting or specific statuses. Generally we allow trying. */}
                            {item.claim_item_id && selectedClaim.claim_type === "RETURN" ? (
                              ["Approved", "Rejected", "Completed", "Onaylandı", "İtiraz Edildi", "Unresolved"].includes(selectedClaim.claim_status) && selectedClaim.claim_status !== "Created" ? (
                                <span className="text-gray-400 text-xs italic">{selectedClaim.claim_status}</span>
                              ) : (
                                <div className="flex items-center justify-center gap-2">
                                  <button 
                                    onClick={() => approveClaim(item)}
                                    disabled={actionLoading}
                                    className="flex items-center gap-1 bg-green-500 text-white px-2 py-1 rounded text-xs hover:bg-green-600 disabled:opacity-50"
                                  >
                                    <CheckCircle size={14} /> Onayla
                                  </button>
                                  <button 
                                    onClick={() => openIssueModal(item)}
                                    disabled={actionLoading}
                                    className="flex items-center gap-1 bg-red-500 text-white px-2 py-1 rounded text-xs hover:bg-red-600 disabled:opacity-50"
                                  >
                                    <AlertTriangle size={14} /> İtiraz
                                  </button>
                                </div>
                              )
                            ) : (
                              <span className="text-xs text-gray-400">İşlem Yok</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Issue Modal */}
      <Dialog open={issueModalOpen} onOpenChange={setIssueModalOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>İadeye İtiraz Et</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <p className="text-sm text-gray-600">
              Aşağıdaki ürün için itiraz oluşturulacaktır:<br/>
              <strong>{actionItem?.productName}</strong>
            </p>

            <div>
              <label className="block text-sm font-medium mb-1">İtiraz Sebebi</label>
              <select
                value={issueReasonId}
                onChange={(e) => setIssueReasonId(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1"
              >
                <option value="">Sebep Seçin...</option>
                {issueReasons.map(r => (
                  <option key={r.id} value={r.id}>{r.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Açıklama (İsteğe bağlı)</label>
              <textarea
                value={issueDesc}
                onChange={(e) => setIssueDesc(e.target.value)}
                className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 h-24"
                placeholder="İtirazınız ile ilgili Trendyol ekiplerine iletilmek üzere açıklama girebilirsiniz."
              ></textarea>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button 
                onClick={() => setIssueModalOpen(false)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50 text-sm font-medium"
              >
                İptal
              </button>
              <button 
                onClick={submitIssue}
                disabled={actionLoading || !issueReasonId}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 text-sm font-medium"
              >
                {actionLoading ? "İşleniyor..." : "İtirazı Gönder"}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
