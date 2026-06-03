/**
 * =============================================================================
 * CapiLogs.jsx — CAPI (Server-Side Conversions API) Gönderim Logları
 * =============================================================================
 *   • Son N gönderim listesi (provider, event, status, error)
 *   • Filtre: provider, event_name, sadece başarısızlar
 *   • Kuyruk: bekleyen + ölü event'ler, tekrar deneme / silme butonları
 *   • 30 gün öncesi logları temizle
 * =============================================================================
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Activity, RefreshCw, Trash2, CheckCircle2, XCircle, AlertCircle, Filter } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const EVENT_OPTIONS = [
  { value: "", label: "Tüm event'ler" },
  { value: "view_item", label: "View Item" },
  { value: "view_item_list", label: "View Item List" },
  { value: "add_to_cart", label: "Add to Cart" },
  { value: "remove_from_cart", label: "Remove from Cart" },
  { value: "begin_checkout", label: "Begin Checkout" },
  { value: "add_payment_info", label: "Add Payment Info" },
  { value: "purchase", label: "Purchase" },
  { value: "refund", label: "Refund" },
  { value: "lead", label: "Lead" },
  { value: "search", label: "Search" },
  { value: "test_connection", label: "Test Connection" },
];

const PROVIDER_OPTIONS = [
  { value: "", label: "Tüm sağlayıcılar" },
  { value: "meta", label: "Meta" }, { value: "tiktok", label: "TikTok" },
  { value: "google_ads", label: "Google Ads" }, { value: "ga4", label: "GA4" },
  { value: "pinterest", label: "Pinterest" }, { value: "snapchat", label: "Snapchat" },
];

export default function CapiLogs() {
  const [tab, setTab] = useState("logs");          // logs | queue
  const [logs, setLogs] = useState([]);
  const [queue, setQueue] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ provider: "", event_name: "", ok: "" });
  const [queueFilter, setQueueFilter] = useState("");  // "" | "true" (dead) | "false" (pending)
  const [expandedRow, setExpandedRow] = useState(null);

  const token = localStorage.getItem("token");
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const loadLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("limit", "100");
      if (filters.provider) params.append("provider", filters.provider);
      if (filters.event_name) params.append("event_name", filters.event_name);
      if (filters.ok !== "") params.append("ok", filters.ok);
      const res = await axios.get(`${API}/marketing-pixels/capi/logs?${params}`, auth);
      setLogs(res.data?.items || []);
      setTotal(res.data?.total || 0);
    } catch (e) {
      toast.error("Loglar yüklenemedi: " + (e?.response?.data?.detail || e.message));
    } finally { setLoading(false); }
  };

  const loadQueue = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      params.append("limit", "100");
      if (queueFilter !== "") params.append("dead", queueFilter);
      const res = await axios.get(`${API}/marketing-pixels/capi/queue?${params}`, auth);
      setQueue(res.data?.items || []);
    } catch (e) {
      toast.error("Kuyruk yüklenemedi: " + (e?.response?.data?.detail || e.message));
    } finally { setLoading(false); }
  };

  useEffect(() => {
    if (tab === "logs") loadLogs(); else loadQueue();
    // eslint-disable-next-line
  }, [tab, filters, queueFilter]);

  const retryOne = async (qid) => {
    try {
      await axios.post(`${API}/marketing-pixels/capi/queue/${qid}/retry`, {}, auth);
      toast.success("Yeniden deneme için kuyruğa alındı");
      await loadQueue();
    } catch (e) { toast.error(e.message); }
  };

  const deleteOne = async (qid) => {
    if (!await window.appConfirm("Bu kuyruk öğesini silmek istediğinize emin misiniz?")) return;
    try {
      await axios.delete(`${API}/marketing-pixels/capi/queue/${qid}`, auth);
      toast.success("Silindi");
      await loadQueue();
    } catch (e) { toast.error(e.message); }
  };

  const runAll = async () => {
    setLoading(true);
    try {
      const res = await axios.post(`${API}/marketing-pixels/capi/queue/run-now`, {}, auth);
      toast.success(`İşlem: ${res.data?.ok || 0} başarılı, ${res.data?.failed || 0} hatalı`);
      await loadQueue();
    } catch (e) { toast.error(e.message); }
    finally { setLoading(false); }
  };

  const clearOldLogs = async () => {
    if (!await window.appConfirm("30 günden eski tüm logları silmek istediğinize emin misiniz?")) return;
    try {
      const res = await axios.delete(`${API}/marketing-pixels/capi/logs/clear-old?days=30`, auth);
      toast.success(`${res.data?.deleted} log silindi`);
      await loadLogs();
    } catch (e) { toast.error(e.message); }
  };

  const fmtTime = (iso) => {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString("tr-TR"); } catch { return iso; }
  };

  return (
    <div className="max-w-7xl mx-auto p-6 space-y-5" data-testid="capi-logs-page">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Activity size={20} /> CAPI Loglar & Kuyruk
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Server-side reklam platformlarına (Meta, Google, TikTok, Pinterest, Snapchat) gönderilen tüm event'lerin durumu.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={tab === "logs" ? loadLogs : loadQueue} disabled={loading}
            className="inline-flex items-center gap-1 bg-white border px-3 py-1.5 rounded text-xs hover:bg-gray-50"
            data-testid="capi-refresh">
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> Yenile
          </button>
          {tab === "logs" && (
            <button onClick={clearOldLogs}
              className="inline-flex items-center gap-1 bg-red-50 text-red-700 border border-red-200 px-3 py-1.5 rounded text-xs hover:bg-red-100"
              data-testid="capi-clear-old">
              <Trash2 size={12} /> 30+ gün
            </button>
          )}
          {tab === "queue" && (
            <button onClick={runAll} disabled={loading}
              className="inline-flex items-center gap-1 bg-black text-white px-3 py-1.5 rounded text-xs disabled:opacity-60"
              data-testid="capi-run-all">
              <RefreshCw size={12} /> Tümünü Şimdi Dene
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b">
        <button onClick={() => setTab("logs")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "logs" ? "border-black text-black" : "border-transparent text-gray-500 hover:text-black"}`}
          data-testid="tab-logs">
          📜 Loglar ({total})
        </button>
        <button onClick={() => setTab("queue")}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${tab === "queue" ? "border-black text-black" : "border-transparent text-gray-500 hover:text-black"}`}
          data-testid="tab-queue">
          ⏳ Kuyruk ({queue.length})
        </button>
      </div>

      {/* Filtreler */}
      {tab === "logs" ? (
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <Filter size={14} className="text-gray-500" />
          <select value={filters.provider} onChange={(e) => setFilters({ ...filters, provider: e.target.value })}
            className="border px-2 py-1 rounded text-xs" data-testid="filter-provider">
            {PROVIDER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={filters.event_name} onChange={(e) => setFilters({ ...filters, event_name: e.target.value })}
            className="border px-2 py-1 rounded text-xs" data-testid="filter-event">
            {EVENT_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <select value={filters.ok} onChange={(e) => setFilters({ ...filters, ok: e.target.value })}
            className="border px-2 py-1 rounded text-xs" data-testid="filter-ok">
            <option value="">Tüm durumlar</option>
            <option value="true">✓ Başarılı</option>
            <option value="false">✗ Hatalı</option>
          </select>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm">
          <Filter size={14} className="text-gray-500" />
          <select value={queueFilter} onChange={(e) => setQueueFilter(e.target.value)}
            className="border px-2 py-1 rounded text-xs">
            <option value="">Tümü</option>
            <option value="false">⏳ Aktif bekleyen</option>
            <option value="true">💀 Ölü (max retry)</option>
          </select>
        </div>
      )}

      {/* İçerik tablosu */}
      <div className="bg-white border rounded-lg overflow-hidden">
        {tab === "logs" ? (
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-600 uppercase">
              <tr>
                <th className="text-left px-3 py-2">Zaman</th>
                <th className="text-left px-3 py-2">Provider</th>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-left px-3 py-2">ID</th>
                <th className="text-center px-3 py-2">Durum</th>
                <th className="text-left px-3 py-2">Mesaj</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-gray-400" data-testid="empty-logs">
                  Henüz log yok. Bir storefront sayfasını ziyaret ederek event tetikleyin.
                </td></tr>
              )}
              {logs.map((l) => (
                <tr key={l.id} className={`border-t hover:bg-gray-50 ${l.is_test ? "bg-amber-50" : ""}`}>
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{fmtTime(l.created_at)}</td>
                  <td className="px-3 py-2"><span className="text-[10px] uppercase bg-gray-100 px-1.5 py-0.5 rounded font-bold">{l.provider}</span></td>
                  <td className="px-3 py-2 font-mono">{l.event_name}</td>
                  <td className="px-3 py-2 font-mono text-gray-400 text-[10px]">{(l.event_id || "").slice(0, 12)}…</td>
                  <td className="px-3 py-2 text-center">
                    {l.ok ? <CheckCircle2 size={16} className="text-green-600 inline" /> : <XCircle size={16} className="text-red-600 inline" />}
                    {l.from_retry && <span className="ml-1 text-[9px] bg-blue-100 text-blue-700 px-1 rounded">RETRY</span>}
                    {l.is_test && <span className="ml-1 text-[9px] bg-amber-200 text-amber-900 px-1 rounded">TEST</span>}
                  </td>
                  <td className="px-3 py-2 text-gray-500 max-w-md truncate cursor-pointer"
                      onClick={() => setExpandedRow(expandedRow === l.id ? null : l.id)}>
                    {expandedRow === l.id ? (
                      <pre className="text-[10px] whitespace-pre-wrap break-all bg-gray-100 p-2 rounded">
                        {JSON.stringify(l.error || l.response, null, 2).slice(0, 1500)}
                      </pre>
                    ) : (
                      <span>{JSON.stringify(l.error || l.response || "").slice(0, 100)}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full text-xs">
            <thead className="bg-gray-50 text-gray-600 uppercase">
              <tr>
                <th className="text-left px-3 py-2">Sıradaki Deneme</th>
                <th className="text-left px-3 py-2">Provider</th>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-center px-3 py-2">Deneme</th>
                <th className="text-left px-3 py-2">Son Hata</th>
                <th className="text-right px-3 py-2">İşlem</th>
              </tr>
            </thead>
            <tbody>
              {queue.length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-gray-400" data-testid="empty-queue">
                  Kuyruk boş — tüm CAPI event'leri başarıyla gönderildi.
                </td></tr>
              )}
              {queue.map((q) => (
                <tr key={q.id} className={`border-t hover:bg-gray-50 ${q.dead ? "bg-red-50" : ""}`}>
                  <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{fmtTime(q.next_try_at)}</td>
                  <td className="px-3 py-2"><span className="text-[10px] uppercase bg-gray-100 px-1.5 py-0.5 rounded font-bold">{q.provider}</span></td>
                  <td className="px-3 py-2 font-mono">{q.event_name}</td>
                  <td className="px-3 py-2 text-center">
                    <span className={q.dead ? "bg-red-100 text-red-700 px-1.5 rounded text-[10px] font-bold" : ""}>
                      {q.attempts}{q.dead && " 💀"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-500 max-w-md truncate">
                    {JSON.stringify(q.last_error || "").slice(0, 100)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button onClick={() => retryOne(q.id)}
                      className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border hover:bg-blue-50 mr-1"
                      data-testid={`retry-${q.id}`}>
                      <RefreshCw size={11} /> Dene
                    </button>
                    <button onClick={() => deleteOne(q.id)}
                      className="text-red-600 hover:bg-red-50 p-1.5 rounded"
                      data-testid={`delete-${q.id}`}>
                      <Trash2 size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="text-xs text-gray-500 flex items-center gap-1">
        <AlertCircle size={12} />
        Arkaplanda her 30 dk'da bir kuyruk otomatik denenir; max 5 deneme (1/5/15/60/240 dk üstel backoff).
      </div>
    </div>
  );
}
