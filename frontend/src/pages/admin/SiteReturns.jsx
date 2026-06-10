import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RotateCcw, Package, ExternalLink } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const BACKEND = process.env.REACT_APP_BACKEND_URL;

const STATUS_OPTS = [
  { value: "created", label: "Oluşturuldu" },
  { value: "in_transit", label: "İade Kargoda" },
  { value: "returned", label: "İade Teslim Alındı" },
  { value: "refunded", label: "Bedeli İade Edildi" },
  { value: "rejected", label: "Reddedildi" },
  { value: "cancelled", label: "İptal" },
];

const STATUS_CLS = {
  created: "bg-rose-50 text-rose-700 border-rose-200",
  in_transit: "bg-pink-50 text-pink-700 border-pink-200",
  returned: "bg-red-50 text-red-700 border-red-200",
  refunded: "bg-red-100 text-red-800 border-red-300",
  rejected: "bg-gray-100 text-gray-600 border-gray-300",
  cancelled: "bg-gray-100 text-gray-500 border-gray-300",
};

export default function SiteReturns({ embedded = false }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("");

  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

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

  useEffect(() => { load(); }, [load]);

  const changeStatus = async (id, status) => {
    try {
      await axios.post(`${API}/orders/returns/${id}/status`, { status }, auth());
      setRows((rs) => rs.map((r) => (r.id === id ? { ...r, status } : r)));
      toast.success("İade durumu güncellendi");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Güncellenemedi");
    }
  };

  const fmt = (d) => (d ? new Date(d).toLocaleString("tr-TR") : "");

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
          <option value="">Tüm Durumlar</option>
          {STATUS_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
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
          {rows.map((r) => (
            <div key={r.id} className="bg-white border rounded-xl p-4 shadow-sm">
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-gray-900">{r.order_number}</span>
                    <span className={`text-[10px] uppercase tracking-wide border px-2 py-0.5 rounded-full ${STATUS_CLS[r.status] || STATUS_CLS.created}`}>
                      {STATUS_OPTS.find((o) => o.value === r.status)?.label || r.status}
                    </span>
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
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <img src={`${BACKEND}${r.barcode_url}`} alt={r.return_code} className="h-14 border border-gray-100 rounded bg-white" />
                  <a href={`${BACKEND}${r.barcode_url}`} target="_blank" rel="noopener noreferrer"
                    className="text-[11px] text-blue-600 hover:text-blue-800 inline-flex items-center gap-1">
                    Barkodu aç <ExternalLink size={11} />
                  </a>
                  <select
                    value={r.status}
                    onChange={(e) => changeStatus(r.id, e.target.value)}
                    className="border px-2 py-1.5 rounded text-sm"
                  >
                    {STATUS_OPTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
