import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { RefreshCw, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronUp, Clock } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

const STATUS_MAP = {
  success: { label: "Başarılı", color: "text-green-700 bg-green-50 border-green-200", icon: <CheckCircle2 size={14} className="text-green-500" /> },
  partial: { label: "Kısmi Başarı", color: "text-orange-700 bg-orange-50 border-orange-200", icon: <AlertTriangle size={14} className="text-orange-500" /> },
  failed:  { label: "Başarısız", color: "text-red-700 bg-red-50 border-red-200", icon: <XCircle size={14} className="text-red-500" /> },
  error:   { label: "API Hatası", color: "text-red-700 bg-red-50 border-red-200", icon: <XCircle size={14} className="text-red-500" /> },
};

function fmt(dt) {
  if (!dt) return "-";
  return new Date(dt).toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export default function TrendyolLogs() {
  const [logs, setLogs]     = useState([]);
  const [total, setTotal]   = useState(0);
  const [page, setPage]     = useState(1);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/integrations/trendyol/sync-logs?page=${page}&limit=20`, {
        headers: authHeaders(),
      });
      setLogs(res.data?.logs || []);
      setTotal(res.data?.total || 0);
    } catch (err) {
      console.error("Log fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => { fetchLogs(); }, [fetchLogs]);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold">Trendyol Aktarım Logları</h1>
          <p className="text-sm text-gray-500 mt-0.5">Her aktarım denemesinin detaylı kaydı</p>
        </div>
        <button
          onClick={fetchLogs}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 border rounded hover:bg-gray-50 text-sm"
        >
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          Yenile
        </button>
      </div>

      {/* Log List */}
      <div className="space-y-3">
        {loading && logs.length === 0 ? (
          <div className="bg-white rounded-lg border p-16 text-center">
            <RefreshCw size={28} className="animate-spin text-gray-300 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">Loglar yükleniyor...</p>
          </div>
        ) : logs.length === 0 ? (
          <div className="bg-white rounded-lg border p-16 text-center">
            <Clock size={36} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-400 text-sm">Henüz hiç aktarım denemesi kaydedilmedi.</p>
            <p className="text-gray-300 text-xs mt-1">İlk aktarımdan sonra loglar burada görünecek.</p>
          </div>
        ) : (
          logs.map((log) => {
            const s = STATUS_MAP[log.status] || STATUS_MAP.error;
            const isExpanded = expanded === log.id;
            return (
              <div key={log.id} className="bg-white rounded-lg border shadow-sm overflow-hidden">
                {/* Row header */}
                <div
                  className="flex items-center gap-4 px-5 py-4 cursor-pointer select-none hover:bg-gray-50 transition-colors"
                  onClick={() => setExpanded(isExpanded ? null : log.id)}
                >
                  {/* Status badge */}
                  <span className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-bold ${s.color}`}>
                    {s.icon} {s.label}
                  </span>

                  {/* Date */}
                  <span className="text-sm text-gray-500 font-mono">{fmt(log.started_at)}</span>

                  {/* Stats */}
                  <div className="flex gap-4 text-xs text-gray-500 ml-auto">
                    <span><strong className="text-gray-800">{log.products_attempted ?? "-"}</strong> denendi</span>
                    <span><strong className="text-green-600">{log.products_sent ?? "-"}</strong> gönderildi</span>
                    <span><strong className={log.errors?.length ? "text-red-600" : "text-gray-400"}>{log.errors?.length ?? 0}</strong> hata</span>
                    {log.batch_request_id && (
                      <span className="font-mono text-gray-400">Batch: {log.batch_request_id}</span>
                    )}
                  </div>

                  {/* Expand toggle */}
                  {isExpanded ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="border-t bg-gray-50 px-5 py-4">
                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">
                      Aktarım Mesajı
                    </p>
                    <p className="text-sm text-gray-700 mb-4 bg-white border rounded px-3 py-2">{log.message || "-"}</p>

                    {log.errors && log.errors.length > 0 ? (
                      <>
                        <p className="text-xs font-bold text-red-500 uppercase tracking-wider mb-2">
                          Hata Listesi ({log.errors.length})
                        </p>
                        <div className="space-y-1.5 max-h-64 overflow-y-auto">
                          {log.errors.map((err, i) => (
                            <div key={i} className="flex items-start gap-2 bg-red-50 border border-red-100 rounded px-3 py-2 text-xs text-red-700">
                              <XCircle size={13} className="mt-0.5 flex-shrink-0 text-red-400" />
                              <span>{err}</span>
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <div className="flex items-center gap-2 text-green-600 text-sm">
                        <CheckCircle2 size={16} />
                        Bu aktarımda hiç hata oluşmadı.
                      </div>
                    )}

                    {log.finished_at && (
                      <p className="text-[10px] text-gray-400 mt-3">
                        Tamamlandı: {fmt(log.finished_at)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-6">
          {[...Array(Math.ceil(total / 20))].map((_, i) => (
            <button
              key={i}
              onClick={() => setPage(i + 1)}
              className={`w-8 h-8 rounded text-sm font-medium transition-colors ${page === i + 1 ? "bg-black text-white" : "bg-white border hover:bg-gray-50"}`}
            >
              {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
