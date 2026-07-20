import { useState, useEffect, Fragment } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import { TrendingUp, Package, Users, Truck, CreditCard, RefreshCw } from "lucide-react";
import ReportScopeBadge from "../../components/ReportScopeBadge";
import DecisionBoard from "./DecisionBoard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
const COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444", "#0ea5e9", "#22c55e"];

function useDateRange() {
  const today = new Date();
  const [from, setFrom] = useState(new Date(today.getTime() - 30 * 864e5).toISOString().slice(0, 10));
  const [to, setTo] = useState(today.toISOString().slice(0, 10));
  return { from, setFrom, to, setTo };
}

function DateBar({ from, setFrom, to, setTo, onRefresh }) {
  return (
    <div className="flex items-center gap-2 bg-white p-2 border rounded-lg">
      <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="text-sm px-2 py-1 border-0" />
      <span className="text-gray-400">→</span>
      <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="text-sm px-2 py-1 border-0" />
      <button onClick={onRefresh} className="px-3 py-1 bg-black text-white text-xs rounded hover:bg-gray-800 inline-flex items-center gap-1">
        <RefreshCw size={12} /> Uygula
      </button>
    </div>
  );
}

// --- Sales ---
export function SalesReport() {
  const { from, setFrom, to, setTo } = useDateRange();
  // Günlük/Haftalık/Aylık seçici KALDIRILDI (tarih filtresiyle çakışıyordu) —
  // kırılım aralığın uzunluğundan otomatik: ≤31 gün günlük, ≤120 gün haftalık, üstü aylık.
  const _rangeDays = Math.max(1, Math.round((new Date(to) - new Date(from)) / 864e5) + 1);
  const groupBy = _rangeDays <= 31 ? "day" : _rangeDays <= 120 ? "week" : "month";
  const [source, setSource] = useState("all");
  const [data, setData] = useState(null);
  const [paymentData, setPayData] = useState([]);
  const [brk, setBrk] = useState(null);

  const load = async () => {
    const [s, p, b] = await Promise.all([
      axios.get(`${API}/admin/reports/sales`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", group_by: groupBy, source } }),
      axios.get(`${API}/admin/reports/payments`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", source } }),
      axios.get(`${API}/admin/reports/sales-breakdown`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", source } }),
    ]);
    setData(s.data);
    setPayData(p.data.items || []);
    setBrk(b.data);
    // Saat + Gün analizi (reklam planlaması) — aynı tarih aralığı ve kaynak filtresiyle
    axios.get(`${API}/admin/reports/sales-by-hour`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", source } })
      .then((r) => setHourData(r.data)).catch(() => {});
    axios.get(`${API}/admin/reports/sales-by-weekday`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", source } })
      .then((r) => setWeekdayData(r.data)).catch(() => {});
    axios.get(`${API}/admin/reports/cancel-return-by-source`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } })
      .then((r) => setCancelRet(r.data.items || [])).catch(() => {});
    loadRangeDetail();
    // İl/İlçe & Kanal (eski ayrı sekme buraya taşındı — kullanıcı isteği)
    axios.get(`${API}/admin/reports/by-location`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", group: "city", source, limit: 100 } })
      .then((r) => setLocData(r.data.rows || [])).catch(() => {});
    // Kanal = yalnız Site + pazaryerleri (Instagram/Google trafik kaynakları değil)
    axios.get(`${API}/admin/reports/sales-by-platform`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } })
      .then((r) => setSrcData(r.data.rows || [])).catch(() => {});
  };
  const [cancelRet, setCancelRet] = useState([]);
  const [locData, setLocData] = useState([]);
  const [srcData, setSrcData] = useState([]);

  // Saat/Gün analizi + Sipariş Edilen Ürünler (sayfadaki tarih aralığına bağlı)
  const [hourData, setHourData] = useState(null);
  const [weekdayData, setWeekdayData] = useState(null);
  const [dayDetail, setDayDetail] = useState(null);
  const [ddQ, setDdQ] = useState("");                       // ürün adı araması
  const [ddOpen, setDdOpen] = useState(() => new Set());    // bedenleri açık ürünler
  const toggleDd = (k) => setDdOpen(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const loadRangeDetail = () => {
    axios.get(`${API}/admin/reports/day-orders`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", source } })
      .then((r) => setDayDetail(r.data)).catch(() => setDayDetail(null));
  };
  useEffect(() => { loadRangeDetail(); /* eslint-disable-next-line */ }, [source]);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [source]);
  const tl = (v) => `₺${(v ?? 0).toLocaleString("tr-TR")}`;

  return (
    <div className="space-y-5" data-testid="sales-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp /> Satış Raporları <ReportScopeBadge kind="exclude" /></h1>
          <p className="text-sm text-gray-500 mt-1">Tarih aralığına göre satış performansı. <span className="text-gray-400">(İptal ve iade siparişleri tutarlara dahil edilmez.)</span></p>
        </div>
        <div className="flex gap-2 items-center">
          <select value={source} onChange={(e) => setSource(e.target.value)} className="px-3 py-1.5 border rounded text-sm" data-testid="sales-source-select">
            <option value="all">Tüm Kaynaklar</option>
            <option value="site">Site (Kendi)</option>
            <option value="trendyol">Trendyol</option>
            <option value="hepsiburada">Hepsiburada</option>
            <option value="temu">Temu</option>
          </select>
          <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
        </div>
      </div>


      {/* Ciro kırılımı — 4 kademe: dahil → sadece iptal → sadece iade → net (elde kalan) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { lbl: "İptal & İade DAHİL Ciro", d: brk?.included, c: "from-slate-900 to-slate-700", sub: "Toplam (her şey dahil)" },
          { lbl: "Sadece İptaller", d: brk?.cancels, c: "from-rose-600 to-rose-500", sub: "Kaybedilen (iptal)" },
          { lbl: "Sadece İadeler", d: brk?.returns, c: "from-amber-600 to-amber-500", sub: "Kaybedilen (iade)" },
          { lbl: "İptal & İade HARİÇ (Net)", d: brk?.net, c: "from-emerald-600 to-emerald-500", sub: "Elimizde kalan net ciro" },
        ].map((k) => (
          <div key={k.lbl} className={`bg-gradient-to-br ${k.c} text-white rounded-xl p-5`}>
            <div className="text-[11px] uppercase opacity-80 leading-tight">{k.lbl}</div>
            <div className="text-2xl font-bold mt-1">{tl(k.d?.revenue)}</div>
            <div className="text-[11px] opacity-75 mt-1">{k.d?.orders ?? 0} sipariş · {k.sub}</div>
          </div>
        ))}
      </div>
      {/* Ortalama Sepet — belirgin kart (kullanıcı isteği) */}
      <div className="inline-flex items-center gap-3 bg-white border-2 border-indigo-200 rounded-xl px-5 py-3 -mt-1 shadow-sm" data-testid="aov-card">
        <span className="text-2xl">🛒</span>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-gray-500 font-semibold">Ortalama Sepet (Net)</div>
          <div className="text-2xl font-bold text-indigo-700 tabular-nums">{tl(data?.totals?.aov)}</div>
        </div>
        <span className="text-[11px] text-gray-400 ml-2">{data?.totals?.orders ?? 0} sipariş ortalaması</span>
      </div>

      {/* ⏰ Saat Analizi + 📅 Gün Analizi — reklam planlaması için */}
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="bg-white border rounded-xl p-4" data-testid="hour-analysis">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider">Saat Analizi</h2>
            {hourData?.peak && (
              <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5">
                Zirve: {hourData.peak.range} ({hourData.peak.orders} sipariş)
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-400 mb-2">Seçili tarih aralığında siparişlerin saat dağılımı (TR saati)</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={hourData?.rows || []}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 9 }} interval={2} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip formatter={(v, n) => n === "revenue" ? [tl(v), "Ciro"] : [v, "Sipariş"]} />
              <Bar dataKey="orders" name="Sipariş" fill="#3b82f6" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-white border rounded-xl p-4" data-testid="weekday-analysis">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider">Gün Analizi</h2>
            {weekdayData?.peak && (
              <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-2 py-0.5">
                En güçlü gün: {weekdayData.peak}
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-400 mb-2">Haftanın hangi günü daha çok satıyor — reklam planlamasında kullanın</p>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={weekdayData?.rows || []}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
              <Tooltip formatter={(v, n) => n === "revenue" ? [tl(v), "Ciro"] : [v, "Sipariş"]} />
              <Bar dataKey="orders" name="Sipariş" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 🗺️ İl & Kanal — İl artık GRAFİK (81 il sığmazsa yatay kaydırma) */}
      {(locData.length > 0 || srcData.length > 0) && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div className="bg-white border rounded-xl p-4" data-testid="location-block">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-bold uppercase tracking-wider">İl Bazında Satış</h2>
              <span className="text-[11px] text-gray-400">{locData.length} il · sığmazsa yana kaydırın →</span>
            </div>
            <div className="overflow-x-auto pb-1">
              <BarChart width={Math.max(560, locData.length * 44)} height={280} data={locData}
                margin={{ top: 8, right: 8, left: 0, bottom: 48 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="location" interval={0} angle={-45} textAnchor="end" height={60} tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
                <Tooltip content={({ active, payload, label }) => (active && payload?.length) ? (
                  <div className="bg-white border rounded-lg shadow px-3 py-2 text-xs">
                    <div className="font-semibold mb-0.5">{label}</div>
                    <div>Sipariş: <b>{payload[0].payload.orders}</b></div>
                    <div>Ciro: <b>{tl(payload[0].payload.revenue)}</b></div>
                  </div>
                ) : null} />
                <Bar dataKey="orders" name="Sipariş" fill="#0ea5e9" radius={[3, 3, 0, 0]} />
              </BarChart>
            </div>
          </div>
          <div className="bg-white border rounded-xl p-4" data-testid="channel-block">
            <h2 className="text-sm font-bold uppercase tracking-wider mb-2">Kanal Bazında Satış</h2>
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr><th className="text-left p-2">Kanal</th><th className="text-right p-2">Sipariş</th><th className="text-right p-2">Ciro</th></tr>
              </thead>
              <tbody>
                {srcData.map((r) => (
                  <tr key={r.channel} className="border-t">
                    <td className="p-2 font-medium">{r.channel}</td>
                    <td className="p-2 text-right tabular-nums">{r.orders}</td>
                    <td className="p-2 text-right tabular-nums font-semibold">{tl(r.revenue)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 🔄 Pazaryerlerine göre iade & iptal durumları */}
      {cancelRet.length > 0 && (
        <div className="bg-white border rounded-xl p-4" data-testid="cancel-return-by-source">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-2">Pazaryerlerine Göre İade &amp; İptal</h2>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="text-left p-2">Kaynak</th>
                <th className="text-right p-2">İptal (adet)</th>
                <th className="text-right p-2">İptal Tutarı</th>
                <th className="text-right p-2">İade (adet)</th>
                <th className="text-right p-2">İade Tutarı</th>
              </tr>
            </thead>
            <tbody>
              {cancelRet.map((r) => (
                <tr key={r.source} className="border-t">
                  <td className="p-2 font-medium">{r.source}</td>
                  <td className="p-2 text-right tabular-nums">{r.cancel_orders}</td>
                  <td className="p-2 text-right tabular-nums text-rose-600">{tl(r.cancel_total)}</td>
                  <td className="p-2 text-right tabular-nums">{r.return_orders}</td>
                  <td className="p-2 text-right tabular-nums text-amber-600">{tl(r.return_total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* 📋 Gün Detayı — seçilen günde NE sipariş edilmiş (ürün/beden bazında) */}
      <div className="bg-white border rounded-xl p-4" data-testid="day-detail">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h2 className="text-sm font-bold uppercase tracking-wider">Sipariş Edilen Ürünler ({from} → {to})</h2>
          <div className="flex items-center gap-2">
            <input value={ddQ} onChange={(e) => setDdQ(e.target.value)} placeholder="Ürün adı ara…"
              className="border rounded-lg px-3 py-1.5 text-xs w-48" data-testid="day-detail-search" />
            <span className="text-[11px] text-gray-400 hidden sm:inline">Üstteki tarih aralığı + kaynak filtresine göre</span>
          </div>
        </div>
        {dayDetail ? (
          <>
            <p className="text-[11px] text-gray-500 mb-2">
              {dayDetail.date}: <b>{dayDetail.order_count}</b> sipariş · <b>{dayDetail.total_qty}</b> ürün
              {source !== "all" && <> · kaynak: {source}</>} · ürüne tıklayınca beden kırılımı açılır
            </p>
            {(() => {
              // Varsayılan görünüm ÜRÜN toplamı (tüm bedenler); tıklayınca bedenler ayrı satır açılır
              const f = ddQ.trim().toLocaleLowerCase("tr");
              const flt = (dayDetail.rows || []).filter(r => !f || (r.name || "").toLocaleLowerCase("tr").includes(f));
              const groups = []; const gi = {};
              flt.forEach(r => {
                const k = r.name || "—";
                if (gi[k] == null) { gi[k] = groups.length; groups.push({ name: k, qty: 0, revenue: 0, sizes: [] }); }
                const g = groups[gi[k]]; g.qty += r.qty || 0; g.revenue += r.revenue || 0; g.sizes.push(r);
              });
              groups.sort((a, b) => b.qty - a.qty);
              return groups.length ? (
              <div className="max-h-80 overflow-y-auto border rounded-lg">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 text-gray-500 text-xs uppercase sticky top-0">
                    <tr>
                      <th className="text-left p-2.5">Ürün</th>
                      <th className="text-left p-2.5">Beden</th>
                      <th className="text-right p-2.5">Adet</th>
                      <th className="text-right p-2.5">Ciro</th>
                    </tr>
                  </thead>
                  <tbody>
                    {groups.map((g) => {
                      const open = ddOpen.has(g.name);
                      return (
                        <Fragment key={g.name}>
                          <tr className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => toggleDd(g.name)}>
                            <td className="p-2.5 font-medium">
                              <span className="inline-block w-3 text-gray-400 mr-1">{open ? "▾" : "▸"}</span>{g.name}
                            </td>
                            <td className="p-2.5 text-xs text-gray-400">{g.sizes.length > 1 ? `${g.sizes.length} beden` : (g.sizes[0]?.size || "—")}</td>
                            <td className="p-2.5 text-right font-semibold tabular-nums">{g.qty}</td>
                            <td className="p-2.5 text-right tabular-nums">{tl(g.revenue)}</td>
                          </tr>
                          {open && g.sizes.map((r, i) => (
                            <tr key={g.name + i} className="bg-gray-50/60">
                              <td className="p-2 pl-10 text-xs text-gray-500">↳ {r.name}</td>
                              <td className="p-2 text-xs font-semibold">{r.size || "—"}</td>
                              <td className="p-2 text-right tabular-nums text-xs">{r.qty}</td>
                              <td className="p-2 text-right tabular-nums text-xs">{tl(r.revenue)}</td>
                            </tr>
                          ))}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              ) : (
                <p className="text-sm text-gray-400 py-4 text-center">{f ? "Aramayla eşleşen ürün yok." : "Bu aralıkta sipariş yok."}</p>
              );
            })()}
          </>
        ) : (
          <p className="text-sm text-gray-400 py-4 text-center">Yükleniyor…</p>
        )}
      </div>

      <div className="bg-white rounded-xl border p-5">
        {/* Başlık seçilen kırılımı söyler; az kovalı (haftalık/aylık) görünümde iki nokta
            arasına çizgi çekmek yanıltıcıydı → gruplu görünümde ÇUBUK grafik kullanılır. */}
        <h3 className="font-semibold mb-3">{{ day: "Günlük", week: "Haftalık", month: "Aylık" }[groupBy] || "Günlük"} Ciro & Sipariş <span className="text-[11px] font-normal text-gray-400">(aralığa göre otomatik)</span></h3>
        <ResponsiveContainer width="100%" height={300}>
          {groupBy === "day" ? (
            <LineChart data={data?.rows || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={2} name="Ciro (₺)" />
              <Line yAxisId="right" type="monotone" dataKey="orders" stroke="#3b82f6" strokeWidth={2} name="Sipariş" />
            </LineChart>
          ) : (
            <BarChart data={data?.rows || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" vertical={false} />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar yAxisId="left" dataKey="revenue" fill="#10b981" name="Ciro (₺)" radius={[3, 3, 0, 0]} />
              <Bar yAxisId="right" dataKey="orders" fill="#3b82f6" name="Sipariş" radius={[3, 3, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>

      {/* Ödeme Yöntemi Dağılımı — grafik + sipariş sayıları TEK blokta (Trendyol/HB ayrık) */}
      <div className="bg-white rounded-xl border p-5" data-testid="payment-distribution">
        <h3 className="font-semibold mb-3 flex items-center gap-2"><CreditCard size={16} /> Ödeme Yöntemi &amp; Sipariş Dağılımı</h3>
        <div className="grid md:grid-cols-2 gap-5 items-center">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={paymentData} dataKey="revenue" nameKey="method" cx="50%" cy="50%" outerRadius={85}
                label={(pr) => {
                  // Tüm dilimler ÇİZGİYLE etiketli; küçük dilimler kademeli yerleşir (üst üste binmez)
                  const RAD = Math.PI / 180;
                  const r = pr.outerRadius + 20 + (pr.percent < 0.1 ? (pr.index % 2) * 16 : 0);
                  const x = pr.cx + r * Math.cos(-pr.midAngle * RAD);
                  const y = pr.cy + r * Math.sin(-pr.midAngle * RAD);
                  return (
                    <text x={x} y={y} fill="#374151" fontSize={11} textAnchor={x > pr.cx ? "start" : "end"} dominantBaseline="central">
                      {`${pr.payload.method}: ₺${(pr.payload.revenue || 0).toLocaleString("tr-TR")}`}
                    </text>
                  );
                }}
                labelLine={true}>
                {paymentData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr><th className="text-left p-2">Yöntem</th><th className="text-right p-2">Sipariş</th><th className="text-right p-2">Ciro</th></tr>
            </thead>
            <tbody>
              {paymentData.map((p, i) => (
                <tr key={p.method} className="border-t">
                  <td className="p-2 font-medium">
                    <span className="inline-block w-2.5 h-2.5 rounded-full mr-2" style={{ background: COLORS[i % COLORS.length] }} />
                    {p.method}
                  </td>
                  <td className="p-2 text-right">{p.orders}</td>
                  <td className="p-2 text-right font-semibold">₺{p.revenue.toLocaleString("tr-TR")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// --- Products Top ---
export function ProductsReport() {
  const { from, setFrom, to, setTo } = useDateRange();
  const [top, setTop] = useState([]);
  const [cats, setCats] = useState([]);
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState("revenue");
  const [sortDir, setSortDir] = useState("desc");
  const [platFilter, setPlatFilter] = useState("");
  const [sizeFilter, setSizeFilter] = useState("");
  const [collFilter, setCollFilter] = useState("");   // Sezon filtresi (İlkbahar/Yaz/Sonbahar/Kış)
  const [velFilter, setVelFilter] = useState("");      // D4 — satış hızı (green/yellow/red)
  const [expanded, setExpanded] = useState(() => new Set()); // açılır: beden dağılımı
  const [showBoard, setShowBoard] = useState(false);         // Karar Destek Kurulu paneli (gömülü)
  const toggleExpand = (k) => setExpanded(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const load = async () => {
    const [t, c] = await Promise.all([
      axios.get(`${API}/admin/reports/products/top`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", limit: 2000 } }),
      axios.get(`${API}/admin/reports/categories`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } }),
    ]);
    setTop(t.data.items || []);
    setCats(c.data.items || []);
    // İade & İptal raporu (ürün bazlı — platform/tarih/ada göre filtrelenebilir)
    axios.get(`${API}/admin/reports/cancel-return-products`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } })
      .then((r) => setCrRows(r.data.items || [])).catch(() => {});
  };
  const [crRows, setCrRows] = useState([]);
  const [crQ, setCrQ] = useState("");
  const [crPlat, setCrPlat] = useState("");
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const platLabel = (p) => ({ site: "Site", trendyol: "Trendyol", hepsiburada: "Hepsiburada", temu: "Temu" }[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—"));
  // Sezon ürün kartındaki 'Sezon' özniteliğinden gelir (backend normalize eder); yoksa boş.
  const SEASONS = ["İlkbahar", "Yaz", "Sonbahar", "Kış"];
  const toggleSort = (k) => { if (sortKey === k) setSortDir(d => d === "desc" ? "asc" : "desc"); else { setSortKey(k); setSortDir(k === "name" || k === "best_size" ? "asc" : "desc"); } };
  // Filtre seçenekleri (veriden)
  const platOptions = Array.from(new Set(top.flatMap(p => (p.platform_breakdown || []).map(x => x.platform)))).sort();
  const sizeOptions = Array.from(new Set(top.flatMap(p => (p.size_breakdown || []).map(x => x.size)))).filter(s => s && s !== "—").sort((a, b) => a.localeCompare(b, "tr", { numeric: true }));
  const velMeta = { green: { label: "Hızlı (haftada 5+)", cls: "bg-green-100 text-green-700 border-green-200" }, yellow: { label: "Orta (haftada 1-4)", cls: "bg-yellow-100 text-yellow-700 border-yellow-200" }, red: { label: "Yavaş (ayda 0-2)", cls: "bg-red-100 text-red-700 border-red-200" } };
  const rows = (() => {
    const f = q.trim().toLocaleLowerCase("tr");
    let r = f ? top.filter(p => (p.name || "").toLocaleLowerCase("tr").includes(f)) : [...top];
    if (platFilter) r = r.filter(p => (p.platform_breakdown || []).some(x => x.platform === platFilter));
    if (sizeFilter) r = r.filter(p => (p.size_breakdown || []).some(x => x.size === sizeFilter));
    if (collFilter) r = r.filter(p => (p.season || "") === collFilter);
    if (velFilter) r = r.filter(p => (p.velocity || {}).code === velFilter);
    r.sort((a, b) => {
      if (sortKey === "velocity") { const va = (a.velocity || {}).weekly_rate ?? -1, vb = (b.velocity || {}).weekly_rate ?? -1; return sortDir === "asc" ? va - vb : vb - va; }
      let va = a[sortKey], vb = b[sortKey];
      if (sortKey === "name" || sortKey === "best_size" || sortKey === "top_platform" || sortKey === "season") { va = (va || "").toString(); vb = (vb || "").toString(); return sortDir === "asc" ? va.localeCompare(vb, "tr") : vb.localeCompare(va, "tr"); }
      va = va ?? -1; vb = vb ?? -1; return sortDir === "asc" ? va - vb : vb - va;
    });
    return r;
  })();
  const exportXlsx = async () => {
    try {
      const r = await fetch(`${API}/admin/reports/products/export-xlsx?start_date=${from}&end_date=${to}T23:59:59`, { headers: authHeaders() });
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement("a"); a.href = u; a.download = "urun-raporu.xlsx"; a.click();
      URL.revokeObjectURL(u);
    } catch { /* sessiz */ }
  };
  const SortTh = ({ k, children, right }) => (
    <th onClick={() => toggleSort(k)} className={`p-3 cursor-pointer select-none hover:text-gray-900 ${right ? "text-right" : "text-left"}`}>
      {children}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );

  return (
    <div className="space-y-5" data-testid="products-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Ürün Raporları <ReportScopeBadge kind="exclude" /></h1>
          <p className="text-sm text-gray-500 mt-1">Tüm ürünlerin satış performansı — adet, ciro, güncel stok, en çok satan beden ve platform dağılımı.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={exportXlsx} className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 shadow-sm" data-testid="products-export-xlsx">
            ⬇ Excel İndir
          </button>
          <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
        </div>
      </div>

      {/* Rapordan neye erişilir — kılavuz */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-900">
        <span className="font-semibold">Bu raporda:</span> Seçili tarih aralığında (iptal & iade hariç) her ürünün toplam <b>satış adedi</b> ve <b>cirosu</b>, <b>güncel stok</b> durumu, <b>en çok satan bedeni</b> ve <b>hangi platformdan</b> ne kadar sattığı yer alır. Kolon başlıklarına tıklayarak (ör. cirodan yükseğe/düşüğe) sıralayabilir, arama ile ürün filtreleyebilirsiniz.
      </div>

      {/* 🧠 Karar Destek Kurulu — ürün raporunun İÇİNDE (ayrı sekme değil, kullanıcı isteği) */}
      <div className="bg-white border-2 border-violet-200 rounded-xl">
        <button onClick={() => setShowBoard(v => !v)} data-testid="toggle-decision-board"
          className="w-full flex items-center justify-between px-5 py-3 text-left">
          <span className="font-bold text-violet-800 flex items-center gap-2">
            🧠 Karar Destek Kurulu <span className="text-xs font-normal text-violet-500">— uzman ajanlar bu rapordaki verileri tartışır, kararların altına yorum yazarsınız</span>
          </span>
          <span className="text-violet-600 text-sm font-semibold">{showBoard ? "Gizle ▴" : "Raporu Aç ▾"}</span>
        </button>
        {showBoard && <div className="px-5 pb-5"><DecisionBoard embed /></div>}
      </div>

      <div className="bg-white rounded-xl border p-5">
        <h3 className="font-semibold mb-3">En Çok Satan 10 Ürün (Ciro)</h3>
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={top.slice(0, 10)} layout="vertical" margin={{ left: 120 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} />
            <YAxis dataKey="name" type="category" width={200} tick={{ fontSize: 10 }} />
            <Tooltip />
            <Bar dataKey="revenue" fill="#3b82f6" name="Ciro (₺)" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* TÜM ÜRÜNLER — sıralanabilir/filtrelenebilir tablo */}
      <div className="bg-white rounded-xl border">
        <div className="flex items-center justify-between gap-3 p-5 pb-3 flex-wrap">
          <h3 className="font-semibold">Tüm Ürünler ({rows.length})</h3>
          <div className="flex items-center gap-2 flex-wrap">
            <select value={platFilter} onChange={e => setPlatFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
              <option value="">Tüm Platformlar</option>
              {platOptions.map(p => <option key={p} value={p}>{platLabel(p)}</option>)}
            </select>
            <select value={sizeFilter} onChange={e => setSizeFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
              <option value="">Tüm Bedenler</option>
              {sizeOptions.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
            <select value={collFilter} onChange={e => setCollFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm" data-testid="season-filter">
              <option value="">Tüm Sezonlar</option>
              {SEASONS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={velFilter} onChange={e => setVelFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
              <option value="">Tüm Hızlar</option>
              <option value="green">🟢 Hızlı (haftada 5+)</option>
              <option value="yellow">🟡 Orta (haftada 1-4)</option>
              <option value="red">🔴 Yavaş (ayda 0-2)</option>
            </select>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ürün ara…" className="border rounded-lg px-3 py-1.5 text-sm w-48" />
            <button onClick={exportXlsx} className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700" data-testid="products-export-xlsx-inline" title="Ürün raporunu Excel olarak indir">
              ⬇ Excel
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between px-1 pb-2 text-xs text-gray-500">
          <span><span className="font-semibold text-gray-800">{rows.length}</span> ürün listeleniyor{rows.length !== top.length ? ` (toplam ${top.length})` : ""} — satışı olmayan ürünler de dahildir.</span>
          {/* Satış hızı dağılımı — filtrelenmiş listeye göre yüzde + adet */}
          {rows.length > 0 && (() => {
            const cnt = { green: 0, yellow: 0, red: 0 };
            rows.forEach(r => { const c = (r.velocity || {}).code; if (cnt[c] != null) cnt[c]++; });
            const pct = (n) => Math.round((n / rows.length) * 100);
            return (
              <span className="inline-flex items-center gap-2" data-testid="velocity-distribution">
                <span className="inline-flex h-2.5 w-40 rounded overflow-hidden border border-gray-200">
                  <span style={{ width: `${pct(cnt.green)}%` }} className="bg-green-500" />
                  <span style={{ width: `${pct(cnt.yellow)}%` }} className="bg-yellow-400" />
                  <span style={{ width: `${pct(cnt.red)}%` }} className="bg-red-500" />
                </span>
                <span className="text-[11px]">🟢 %{pct(cnt.green)} ({cnt.green}) · 🟡 %{pct(cnt.yellow)} ({cnt.yellow}) · 🔴 %{pct(cnt.red)} ({cnt.red})</span>
              </span>
            );
          })()}
        </div>
        <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500 sticky top-0">
              <tr>
                <SortTh k="name">Ürün</SortTh>
                <SortTh k="season">Sezon</SortTh>
                <SortTh k="velocity">Satış Hızı</SortTh>
                <SortTh k="qty" right>Adet</SortTh>
                <SortTh k="revenue" right>Ciro</SortTh>
                <SortTh k="current_stock" right>Güncel Stok</SortTh>
                <SortTh k="best_size">En Çok Beden</SortTh>
                <SortTh k="top_platform">Platform</SortTh>
                <SortTh k="cancel_qty" right>İptal</SortTh>
                <SortTh k="return_qty" right>İade</SortTh>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => {
                const key = (p.product_id || p.name) + i;
                const isOpen = expanded.has(key);
                return (
                <Fragment key={key}>
                <tr className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => toggleExpand(key)}>
                  <td className="p-3 font-medium max-w-xs truncate" title={p.name}>
                    <span className="inline-block w-3 text-gray-400 mr-1">{isOpen ? "▾" : "▸"}</span>{p.name}
                  </td>
                  <td className="p-3 text-xs whitespace-nowrap">{p.season || ""}</td>
                  <td className="p-3">
                    {p.velocity ? (
                      <span className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border ${(velMeta[p.velocity.code] || {}).cls || ""}`} title={`${p.velocity.weekly_rate}/hafta`}>
                        {(velMeta[p.velocity.code] || {}).label || p.velocity.code}
                      </span>
                    ) : "—"}
                  </td>
                  <td className="p-3 text-right">{p.qty}</td>
                  <td className="p-3 text-right font-semibold">₺{(p.revenue || 0).toLocaleString("tr-TR")}</td>
                  <td className={`p-3 text-right ${p.current_stock === 0 ? "text-red-600 font-semibold" : ""}`}>{p.current_stock == null ? "—" : p.current_stock}</td>
                  <td className="p-3">{p.best_size || "—"}</td>
                  <td className="p-3" title={(p.platform_breakdown || []).map(x => `${platLabel(x.platform)}: ${x.qty}`).join(", ")}>
                    {(p.platform_breakdown || []).map(x => platLabel(x.platform)).join(", ") || "—"}
                  </td>
                  <td className={`p-3 text-right tabular-nums ${p.cancel_qty > 0 ? "text-rose-600 font-semibold" : "text-gray-400"}`}
                    title={(p.cancel_return_by_platform || []).map(x => `${platLabel(x.platform)}: iptal ${x.cancel}`).join(", ")}>
                    {p.cancel_qty || 0}
                  </td>
                  <td className={`p-3 text-right tabular-nums ${p.return_qty > 0 ? "text-amber-600 font-semibold" : "text-gray-400"}`}
                    title={(p.cancel_return_by_platform || []).map(x => `${platLabel(x.platform)}: iade ${x.return}`).join(", ")}>
                    {p.return_qty || 0}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-gray-50/60">
                    <td colSpan={10} className="px-8 py-3">
                      <div className="flex flex-wrap gap-x-8 gap-y-2 text-xs">
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">Beden Dağılımı (adet)</div>
                          <div className="flex flex-wrap gap-1.5">
                            {(p.size_breakdown || []).length ? (p.size_breakdown || []).map(s => (
                              <span key={s.size} className="px-2 py-0.5 bg-white border rounded-full">{s.size}: <b>{s.qty}</b></span>
                            )) : <span className="text-gray-400">—</span>}
                          </div>
                        </div>
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">Platform Dağılımı (adet)</div>
                          <div className="flex flex-wrap gap-1.5">
                            {(p.platform_breakdown || []).map(x => (
                              <span key={x.platform} className="px-2 py-0.5 bg-white border rounded-full">{platLabel(x.platform)}: <b>{x.qty}</b></span>
                            ))}
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
                </Fragment>
                );
              })}
              {rows.length === 0 && <tr><td colSpan={10} className="p-4 text-center text-gray-400">Veri yok.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white rounded-xl border">
        <h3 className="font-semibold p-5 pb-3">Kategori Bazında Satış</h3>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr><th className="text-left p-3">Kategori</th><th className="text-right p-3">Adet</th><th className="text-right p-3">Ciro</th></tr>
          </thead>
          <tbody>
            {cats.map((c) => (
              <tr key={c.category} className="border-t">
                <td className="p-3 font-medium">{c.category}</td>
                <td className="p-3 text-right">{c.qty}</td>
                <td className="p-3 text-right font-semibold">₺{c.revenue.toLocaleString("tr-TR")}</td>
              </tr>
            ))}
            {cats.length === 0 && <tr><td colSpan={3} className="p-4 text-center text-gray-400">Veri yok.</td></tr>}
          </tbody>
        </table>
      </div>

      {/* 🔄 İADE & İPTAL RAPORU — platform / tarih (üst filtre) / ürün adına göre */}
      <div className="bg-white border rounded-xl p-4" data-testid="cr-products-block">
        <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
          <h2 className="text-sm font-bold uppercase tracking-wider">İade &amp; İptal Raporu ({from} → {to})</h2>
          <div className="flex gap-2">
            <select value={crPlat} onChange={(e) => setCrPlat(e.target.value)} className="border rounded px-2 py-1.5 text-xs" data-testid="cr-plat-filter">
              <option value="">Tüm Platformlar</option>
              {[...new Set(crRows.map(r => r.platform))].map(pl => <option key={pl} value={pl}>{pl}</option>)}
            </select>
            <input value={crQ} onChange={(e) => setCrQ(e.target.value)} placeholder="Ürün adı ara..."
              className="border rounded px-3 py-1.5 text-xs w-44" data-testid="cr-name-search" />
          </div>
        </div>
        {(() => {
          const f = crQ.trim().toLocaleLowerCase("tr");
          const list = crRows.filter(r => (!crPlat || r.platform === crPlat) && (!f || (r.name || "").toLocaleLowerCase("tr").includes(f)));
          const tot = list.reduce((a, r) => ({ cq: a.cq + r.cancel_qty, ct: a.ct + r.cancel_total, rq: a.rq + r.return_qty, rt: a.rt + r.return_total }), { cq: 0, ct: 0, rq: 0, rt: 0 });
          return list.length === 0 ? (
            <p className="text-sm text-gray-400 py-4 text-center">Bu filtrede iade/iptal kaydı yok.</p>
          ) : (
            <div className="max-h-96 overflow-y-auto border rounded-lg">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 text-gray-500 text-xs uppercase sticky top-0">
                  <tr>
                    <th className="text-left p-2.5">Ürün</th>
                    <th className="text-left p-2.5">Platform</th>
                    <th className="text-right p-2.5">İptal Adet</th>
                    <th className="text-right p-2.5">İptal Tutar</th>
                    <th className="text-right p-2.5">İade Adet</th>
                    <th className="text-right p-2.5">İade Tutar</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((r, i) => (
                    <tr key={i} className="border-t">
                      <td className="p-2.5">{r.name}</td>
                      <td className="p-2.5">{r.platform}</td>
                      <td className="p-2.5 text-right tabular-nums text-rose-600 font-semibold">{r.cancel_qty || ""}</td>
                      <td className="p-2.5 text-right tabular-nums">{r.cancel_total ? `₺${r.cancel_total.toLocaleString("tr-TR")}` : ""}</td>
                      <td className="p-2.5 text-right tabular-nums text-amber-600 font-semibold">{r.return_qty || ""}</td>
                      <td className="p-2.5 text-right tabular-nums">{r.return_total ? `₺${r.return_total.toLocaleString("tr-TR")}` : ""}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot className="bg-gray-50 font-bold sticky bottom-0">
                  <tr className="border-t-2">
                    <td className="p-2.5" colSpan={2}>TOPLAM</td>
                    <td className="p-2.5 text-right tabular-nums text-rose-700">{tot.cq}</td>
                    <td className="p-2.5 text-right tabular-nums">₺{tot.ct.toLocaleString("tr-TR")}</td>
                    <td className="p-2.5 text-right tabular-nums text-amber-700">{tot.rq}</td>
                    <td className="p-2.5 text-right tabular-nums">₺{tot.rt.toLocaleString("tr-TR")}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

// --- Stock ---
export function StockReport() {
  const [data, setData] = useState(null);
  useEffect(() => {
    axios.get(`${API}/admin/reports/stock`, { headers: authHeaders() }).then((r) => setData(r.data));
  }, []);

  return (
    <div className="space-y-5" data-testid="stock-report-page">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Stok Raporu <ReportScopeBadge kind="stock" /></h1>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-900">
        <span className="font-semibold">Bu raporda:</span> Deponuzun anlık durumunu görürsünüz — <b>toplam stok adedi</b>, güncel satış fiyatı üzerinden <b>toplam stok değeri (₺)</b> ve <b>stoğu biten ürün sayısı</b>. Altta <b>kritik stok (≤5 adet)</b> ve <b>tamamen tükenmiş</b> ürünler listelenir; hangi ürünleri acilen yeniden sipariş etmeniz veya ürettirmeniz gerektiğini buradan fark eder, "Düzenle" ile doğrudan ürüne gidersiniz.
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        <div className="bg-gradient-to-br from-blue-600 to-blue-500 text-white rounded-xl p-5">
          <div className="text-xs uppercase opacity-80">Toplam Stok Adedi</div>
          <div className="text-3xl font-bold mt-1">{data?.totals?.units ?? 0}</div>
        </div>
        <div className="bg-gradient-to-br from-emerald-600 to-emerald-500 text-white rounded-xl p-5">
          <div className="text-xs uppercase opacity-80">Stok Değeri</div>
          <div className="text-3xl font-bold mt-1">₺{(data?.totals?.value ?? 0).toLocaleString("tr-TR")}</div>
        </div>
        <div className="bg-gradient-to-br from-red-600 to-red-500 text-white rounded-xl p-5">
          <div className="text-xs uppercase opacity-80">Stoğu Biten Ürün</div>
          <div className="text-3xl font-bold mt-1">{data?.out_of_stock?.length ?? 0}</div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="bg-white border rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-amber-800">Kritik Stok (≤5)</h3>
          {(data?.low_stock || []).length === 0 ? <div className="text-sm text-gray-400">Kritik stok yok</div> : (
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {data.low_stock.map((p) => (
                <div key={p.id} className="flex justify-between items-center p-2 bg-amber-50 rounded">
                  <div>
                    <div className="font-medium text-sm">{p.name}</div>
                    <div className="text-xs text-gray-500 font-mono">{p.stock_code}</div>
                  </div>
                  <div className="text-amber-700 font-bold">{p.stock}</div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="bg-white border rounded-xl p-5">
          <h3 className="font-semibold mb-3 text-red-800">Stoğu Biten</h3>
          {(data?.out_of_stock || []).length === 0 ? <div className="text-sm text-gray-400">Stoksuz ürün yok</div> : (
            <div className="space-y-1 max-h-96 overflow-y-auto">
              {data.out_of_stock.map((p) => (
                <div key={p.id} className="flex justify-between items-center p-2 bg-red-50 rounded">
                  <div>
                    <div className="font-medium text-sm">{p.name}</div>
                    <div className="text-xs text-gray-500 font-mono">{p.stock_code}</div>
                  </div>
                  <Link to={`/admin/urunler?edit=${p.id}`} className="text-xs text-blue-600 hover:underline">Düzenle →</Link>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Members ---
export function MembersReport() {
  const [top, setTop] = useState([]);
  useEffect(() => {
    axios.get(`${API}/admin/reports/members`, { headers: authHeaders() }).then((r) => setTop(r.data.top_members || []));
  }, []);
  return (
    <div className="space-y-5" data-testid="members-report-page">
      <h1 className="text-2xl font-bold flex items-center gap-2"><Users /> Üye Raporu <ReportScopeBadge kind="cancelOnly" /></h1>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-900">
        <span className="font-semibold">Bu raporda:</span> Sitenize <b>en çok harcayan 20 üyeyi</b> görürsünüz — her üyenin <b>sipariş sayısı</b>, <b>toplam harcaması</b> ve <b>son sipariş tarihi</b> ile birlikte. En değerli müşterilerinizi tespit edip sadakat/kampanya çalışmalarını bu kişilere yönlendirebilir, uzun süredir sipariş vermeyenleri son sipariş tarihinden fark edebilirsiniz.
      </div>

      <div className="bg-white border rounded-xl overflow-hidden">
        <h3 className="font-semibold p-5 pb-3">En Çok Harcayan 20 Üye</h3>
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="text-left p-3 w-10">#</th>
              <th className="text-left p-3">Üye</th>
              <th className="text-left p-3">E-posta</th>
              <th className="text-right p-3">Sipariş</th>
              <th className="text-right p-3">Harcama</th>
              <th className="text-left p-3">Son Sipariş</th>
            </tr>
          </thead>
          <tbody>
            {top.length === 0 ? (
              <tr><td colSpan={6} className="p-6 text-center text-gray-400">Veri yok.</td></tr>
            ) : top.map((m, i) => (
              <tr key={m.user_id} className="border-t hover:bg-gray-50">
                <td className="p-3 text-gray-400">{i + 1}</td>
                <td className="p-3 font-medium">{m.name}</td>
                <td className="p-3 text-gray-500">{m.email}</td>
                <td className="p-3 text-right">{m.orders}</td>
                <td className="p-3 text-right font-semibold">₺{m.revenue.toLocaleString("tr-TR")}</td>
                <td className="p-3 text-xs text-gray-500">{m.last_order_at ? new Date(m.last_order_at).toLocaleDateString("tr-TR") : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
