import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { XCircle, Search, RefreshCw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Platform etiketi — en başta web sitemiz, sonra pazaryerleri
const PLATFORM_LABELS = {
  "": "Web Sitesi",
  facette: "Web Sitesi",
  trendyol: "Trendyol",
  hepsiburada: "Hepsiburada",
  temu: "Temu",
  n11: "N11",
  amazon: "Amazon",
  amazon_tr: "Amazon TR",
  amazon_de: "Amazon DE",
  aliexpress: "AliExpress",
  etsy: "Etsy",
  ciceksepeti: "Çiçek Sepeti",
  pttavm: "PTT AVM",
};

function platformLabel(p) {
  return PLATFORM_LABELS[(p || "").toLowerCase()] || (p || "Web Sitesi");
}

function money(v) {
  const n = Number(v || 0);
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " ₺";
}

export default function Cancellations() {
  const [orders, setOrders] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(true);
  const pageSize = 20;

  const fetchCancelled = useCallback(async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      let url = `${API}/orders?page=${page}&limit=${pageSize}&status=cancelled`;
      if (search) url += `&search=${encodeURIComponent(search)}`;
      const res = await axios.get(url, { headers: { Authorization: `Bearer ${token}` } });
      setOrders(res.data?.orders || []);
      setTotal(res.data?.total || 0);
    } catch (e) {
      setOrders([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search]);

  useEffect(() => { fetchCancelled(); }, [fetchCancelled]);

  const applySearch = () => { setPage(1); setSearch(searchInput.trim()); };
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="p-4 md:p-6">
      <div className="flex items-center gap-2 mb-1">
        <XCircle className="w-5 h-5 text-red-600" />
        <h1 className="text-xl font-semibold">İptaller</h1>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        Kargolanmadan iptal edilen siparişler. (İade talepleri ayrı "İadeler" menüsündedir.)
      </p>

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <div className="relative flex-1 min-w-[220px] max-w-md">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") applySearch(); }}
            placeholder="Sipariş no / müşteri ara…"
            className="w-full pl-9 pr-3 py-2 border rounded-lg text-sm"
          />
        </div>
        <button onClick={applySearch} className="px-4 py-2 bg-gray-900 text-white rounded-lg text-sm">Ara</button>
        <button onClick={fetchCancelled} className="px-3 py-2 border rounded-lg text-sm flex items-center gap-1">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} /> Yenile
        </button>
        <span className="text-sm text-gray-500 ml-auto">Toplam {total} iptal</span>
      </div>

      <div className="overflow-x-auto border rounded-lg bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left font-medium px-3 py-2">Sipariş No</th>
              <th className="text-left font-medium px-3 py-2">Platform</th>
              <th className="text-left font-medium px-3 py-2">Müşteri</th>
              <th className="text-right font-medium px-3 py-2">Tutar</th>
              <th className="text-left font-medium px-3 py-2">Tarih</th>
              <th className="text-left font-medium px-3 py-2">Durum</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-400">Yükleniyor…</td></tr>
            ) : orders.length === 0 ? (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-gray-400">İptal edilen sipariş bulunamadı.</td></tr>
            ) : orders.map((o) => {
              const addr = o.shipping_address || {};
              const name = `${addr.first_name || ""} ${addr.last_name || ""}`.trim() || o.customer_name || "—";
              const dt = o.created_at ? new Date(o.created_at).toLocaleString("tr-TR") : "—";
              return (
                <tr key={o.id || o.order_number} className="border-t hover:bg-gray-50">
                  <td className="px-3 py-2 font-medium">{o.order_number || o.id}</td>
                  <td className="px-3 py-2">{platformLabel(o.platform)}</td>
                  <td className="px-3 py-2">{name}</td>
                  <td className="px-3 py-2 text-right">{money(o.total ?? o.total_amount ?? o.grand_total)}</td>
                  <td className="px-3 py-2 whitespace-nowrap">{dt}</td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 rounded-full bg-red-50 text-red-700 text-xs">İptal</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-4">
          <button disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="px-3 py-1.5 border rounded-lg text-sm disabled:opacity-40">Önceki</button>
          <span className="text-sm text-gray-600">{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="px-3 py-1.5 border rounded-lg text-sm disabled:opacity-40">Sonraki</button>
        </div>
      )}
    </div>
  );
}
