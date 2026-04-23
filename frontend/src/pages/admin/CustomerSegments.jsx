/**
 * CustomerSegments.jsx — RFM Müşteri Segmentasyonu
 *
 * Recency / Frequency / Monetary puanlarına göre müşteri grupları.
 * Pazarlama ekibi segment bazlı kupon, SMS, e-posta kampanyaları üretir.
 *
 * Backend: /api/analytics-extra/rfm?lookback_days=365
 */
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Users, Trophy, HeartPulse, Rocket, AlertOctagon, UserMinus, Search, Download } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const SEGMENT_META = {
  "VIP / Şampiyon": { cls: "bg-purple-100 text-purple-700 border-purple-200", icon: Trophy },
  "Sadık Müşteri": { cls: "bg-green-100 text-green-700 border-green-200", icon: HeartPulse },
  "Yeni Müşteri": { cls: "bg-blue-100 text-blue-700 border-blue-200", icon: Rocket },
  "Potansiyel Sadık": { cls: "bg-teal-100 text-teal-700 border-teal-200", icon: HeartPulse },
  "Risk Altında (Kayıp Uyarısı)": { cls: "bg-orange-100 text-orange-700 border-orange-200", icon: AlertOctagon },
  "Dikkat Edilmeli": { cls: "bg-yellow-100 text-yellow-800 border-yellow-200", icon: AlertOctagon },
  "Kaybedilen": { cls: "bg-red-100 text-red-700 border-red-200", icon: UserMinus },
  "Hibernasyon": { cls: "bg-gray-100 text-gray-600 border-gray-200", icon: UserMinus },
  "Standart": { cls: "bg-gray-50 text-gray-600 border-gray-200", icon: Users },
};

export default function CustomerSegments() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lookback, setLookback] = useState(365);
  const [search, setSearch] = useState("");
  const [segmentFilter, setSegmentFilter] = useState("");

  const token = useMemo(() => localStorage.getItem("token"), []);
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/analytics-extra/rfm?lookback_days=${lookback}`, auth);
      setData(r.data);
    } catch { toast.error("Yüklenemedi"); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [lookback]);

  const filtered = useMemo(() => {
    if (!data) return [];
    let items = data.items;
    if (segmentFilter) items = items.filter((i) => i.segment === segmentFilter);
    if (search) {
      const s = search.toLocaleLowerCase("tr");
      items = items.filter((i) =>
        (i.email || "").toLocaleLowerCase("tr").includes(s) ||
        (i.name || "").toLocaleLowerCase("tr").includes(s)
      );
    }
    return items;
  }, [data, segmentFilter, search]);

  const exportCsv = () => {
    if (!filtered.length) return;
    const header = ["Email", "Ad", "Telefon", "Segment", "R", "F", "M", "RFM", "Sipariş", "Toplam Harcama", "Son Sipariş", "Recency (gün)"];
    const rows = filtered.map((i) => [i.email, i.name || "", i.phone || "", i.segment, i.r, i.f, i.m, i.rfm, i.order_count, i.total_spent, i.last_order, i.recency_days]);
    const csv = [header, ...rows].map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `musteri-segmentleri-${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div data-testid="customer-segments-page">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Users size={20} /> Müşteri Segmentasyonu (RFM)
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Recency (yakınlık) · Frequency (sıklık) · Monetary (ciro) skorlarına göre müşteriler segmentlere ayrılır.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={lookback} onChange={(e) => setLookback(parseInt(e.target.value))}
            className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm bg-white"
            data-testid="rfm-lookback">
            <option value={90}>Son 90 gün</option>
            <option value={180}>Son 180 gün</option>
            <option value={365}>Son 1 yıl</option>
            <option value={730}>Son 2 yıl</option>
          </select>
          <button onClick={exportCsv} disabled={!filtered.length}
            className="flex items-center gap-1 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50">
            <Download size={14} /> Excel'e Aktar
          </button>
        </div>
      </div>

      {/* Segment özet kartları */}
      {data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4" data-testid="rfm-segment-cards">
          {Object.entries(data.segments).map(([seg, cnt]) => {
            const meta = SEGMENT_META[seg] || SEGMENT_META["Standart"];
            const Icon = meta.icon;
            const active = segmentFilter === seg;
            return (
              <button key={seg}
                onClick={() => setSegmentFilter(active ? "" : seg)}
                className={`text-left border rounded-xl p-3 transition-all ${meta.cls} ${active ? "ring-2 ring-black" : ""}`}
                data-testid={`rfm-segment-${seg}`}>
                <div className="flex items-center gap-2 mb-1">
                  <Icon size={14} />
                  <span className="text-xs font-bold uppercase tracking-wider">{seg}</span>
                </div>
                <div className="text-2xl font-black">{cnt}</div>
                <div className="text-[11px]">müşteri</div>
              </button>
            );
          })}
        </div>
      )}

      {/* Arama */}
      <div className="flex items-center gap-3 mb-3">
        <div className="relative flex-1 max-w-md">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Email veya isim..."
            className="w-full border border-gray-200 rounded-lg pl-8 pr-3 py-1.5 text-sm"
            data-testid="rfm-search" />
        </div>
        {segmentFilter && (
          <button onClick={() => setSegmentFilter("")}
            className="text-xs text-gray-500 hover:text-black">
            Filtreyi Temizle (× {segmentFilter})
          </button>
        )}
        <span className="text-xs text-gray-500 ml-auto">
          {filtered.length} / {data?.total || 0} gösteriliyor
        </span>
      </div>

      <div className="bg-white border rounded-xl shadow-sm overflow-hidden">
        <table className="admin-table admin-table-compact">
          <thead>
            <tr>
              <th>Segment</th>
              <th>Email</th>
              <th>Ad</th>
              <th>R</th><th>F</th><th>M</th>
              <th>Sipariş</th>
              <th>Toplam Harcama</th>
              <th>Son Sipariş</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="text-center py-8 text-gray-400">Yükleniyor...</td></tr>
            ) : filtered.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-10 text-gray-400">Kayıt yok</td></tr>
            ) : (
              filtered.slice(0, 300).map((i, idx) => {
                const meta = SEGMENT_META[i.segment] || SEGMENT_META["Standart"];
                return (
                  <tr key={idx}>
                    <td>
                      <span className={`inline-flex items-center text-[10px] font-bold px-2 py-0.5 rounded-full border ${meta.cls}`}>
                        {i.segment}
                      </span>
                    </td>
                    <td className="text-xs font-mono text-gray-700">{i.email}</td>
                    <td className="text-sm">{i.name || "-"}</td>
                    <td><span className="font-mono text-xs font-bold">{i.r}</span></td>
                    <td><span className="font-mono text-xs font-bold">{i.f}</span></td>
                    <td><span className="font-mono text-xs font-bold">{i.m}</span></td>
                    <td className="text-sm font-semibold">{i.order_count}</td>
                    <td className="text-sm font-bold text-green-700">{i.total_spent?.toFixed(2)} ₺</td>
                    <td className="text-[11px] text-gray-500">
                      {i.last_order ? `${new Date(i.last_order).toLocaleDateString("tr-TR")} (${i.recency_days}g)` : "-"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
