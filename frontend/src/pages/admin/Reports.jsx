import { useState, useEffect, useRef, Fragment } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import { TrendingUp, Package, Users, Truck, CreditCard, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import ReportScopeBadge from "../../components/ReportScopeBadge";
import {
  REPORT_MIN_DATE, clampReportDate, defaultReportRange, filterReportChannels,
  productExportParams, productReportScope, reportPresetRange, splitReportRange,
} from "../../lib/reportFilters";
import { createLatestRequestManager, isCanceledRequest } from "../../lib/latestRequest";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
const COLORS = ["#3b82f6", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#ef4444", "#0ea5e9", "#22c55e"];

function useDateRange() {
  const initial = defaultReportRange();
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  return { from, setFrom, to, setTo };
}

// Hazır tarih ön-ayarları — tüm rapor sayfalarında ortak (bu DateBar her rapor tarafından kullanılır).
const DATE_PRESETS = [
  { key: "today", label: "Bugün", days: 1 },
  { key: "yesterday", label: "Dün" },
  { key: "7", label: "Son 7 Gün", days: 7 },
  { key: "30", label: "Son 30 Gün", days: 30 },
  { key: "thismonth", label: "Bu Ay" },
  { key: "90", label: "Son 90 Gün", days: 90 },
  { key: "365", label: "Son 1 Yıl", days: 365 },
];
function DateBar({ from, setFrom, to, setTo, onRefresh }) {
  // Ön-ayar tıklanınca tarihleri güncelle ve tarih STATE'i işlendikten SONRA (ref ile en güncel
  // load'ı) otomatik uygula — böylece bayat kapanış (stale closure) sorunu olmadan tek tıkla çalışır.
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;
  const tickRef = useRef(0);
  const pendingLabelRef = useRef("");
  const [tick, setTick] = useState(0);
  const [activePreset, setActivePreset] = useState("");
  useEffect(() => {
    if (tick !== tickRef.current) {
      tickRef.current = tick;
      const label = pendingLabelRef.current;
      pendingLabelRef.current = "";
      // Bildirimi tıklama anında DEĞİL, veri gerçekten yenilendiğinde göster —
      // onRefresh (load) bir promise döndürür; çözülünce "Filtre uygulandı" çıkar.
      Promise.resolve(onRefreshRef.current && onRefreshRef.current())
        .then(() => { if (label) toast.success(`Filtre uygulandı: ${label}`); })
        .catch(() => {});
    }
  }, [from, to, tick]);

  const applyPreset = (p) => {
    const { from: fromStr, to: toStr } = reportPresetRange(p.key);
    pendingLabelRef.current = p.label;
    setFrom(fromStr); setTo(toStr); setActivePreset(p.key); setTick((x) => x + 1);
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex flex-wrap items-center gap-1">
        {DATE_PRESETS.map((p) => (
          <button key={p.key} onClick={() => applyPreset(p)} data-testid={`date-preset-${p.key}`}
            className={`px-2.5 py-1.5 text-xs rounded border transition-colors ${
              activePreset === p.key
                ? "bg-black text-white border-black font-semibold"
                : "bg-white text-gray-600 border-gray-300 hover:border-black"}`}>
            {p.label}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-2 bg-white p-2 border rounded-lg">
        <input type="date" min={REPORT_MIN_DATE} value={from} onChange={(e) => { setFrom(clampReportDate(e.target.value)); setActivePreset(""); }} className="text-sm px-2 py-1 border-0" />
        <span className="text-gray-400">→</span>
        <input type="date" min={REPORT_MIN_DATE} value={to} onChange={(e) => { setTo(clampReportDate(e.target.value)); setActivePreset(""); }} className="text-sm px-2 py-1 border-0" />
        <button onClick={() => {
            // Bildirim veri yenilendiğinde çıksın (tıklama anında değil).
            Promise.resolve(onRefresh && onRefresh())
              .then(() => toast.success(`Filtre uygulandı: ${from} → ${to}`))
              .catch(() => {});
          }}
          className="px-3 py-1 bg-black text-white text-xs rounded hover:bg-gray-800 inline-flex items-center gap-1">
          <RefreshCw size={12} /> Uygula
        </button>
      </div>
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
  const [cancelRet, setCancelRet] = useState([]);
  const [loadError, setLoadError] = useState("");
  const requestManagerRef = useRef(null);
  if (!requestManagerRef.current) requestManagerRef.current = createLatestRequestManager();
  const paymentNet = paymentData.reduce((a, row) => ({
    revenue: a.revenue + Number(row.revenue || 0),
    orders: a.orders + Number(row.orders || 0),
    units: a.units + Number(row.units || 0),
  }), { revenue: 0, orders: 0, units: 0 });
  const channelNet = cancelRet.reduce((a, row) => ({
    revenue: a.revenue + Number(row.revenue || 0),
    orders: a.orders + Number(row.orders || 0),
    units: a.units + Number(row.units || 0),
  }), { revenue: 0, orders: 0, units: 0 });
  const integrityMismatch = Boolean(brk && paymentData.length && cancelRet.length) && (
    Math.abs(Number(brk.net?.revenue || 0) - paymentNet.revenue) > 0.02 ||
    Number(brk.net?.orders || 0) !== paymentNet.orders ||
    Number(brk.net?.units || 0) !== paymentNet.units ||
    Math.abs(Number(brk.net?.revenue || 0) - channelNet.revenue) > 0.02 ||
    Number(brk.net?.orders || 0) !== channelNet.orders ||
    Number(brk.net?.units || 0) !== channelNet.units
  );

  const load = async () => {
    const query = Object.freeze({ start_date: from, end_date: to, source });
    const request = requestManagerRef.current.begin();
    const config = (params) => ({ headers: authHeaders(), params, signal: request.signal });
    try {
      // Every visible block belongs to one immutable query generation. Commit
      // only after all endpoints succeed, so cards and tables cannot mix scopes.
      const [s, p, b, h, w, c, l] = await Promise.all([
        axios.get(`${API}/admin/reports/sales`, config({ ...query, group_by: groupBy })),
        axios.get(`${API}/admin/reports/payments`, config(query)),
        axios.get(`${API}/admin/reports/sales-breakdown`, config(query)),
        axios.get(`${API}/admin/reports/sales-by-hour`, config(query)),
        axios.get(`${API}/admin/reports/sales-by-weekday`, config(query)),
        axios.get(`${API}/admin/reports/cancel-return-by-source`, config(query)),
        axios.get(`${API}/admin/reports/by-location`, config({ ...query, group: "city", limit: 100 })),
      ]);
      if (!requestManagerRef.current.isCurrent(request.id)) return;
      setData(s.data);
      setPayData(p.data.items || []);
      setBrk(b.data);
      setHourData(h.data);
      setWeekdayData(w.data);
      setCancelRet(filterReportChannels(c.data.items || [], query.source));
      setLocData(l.data.rows || []);
      setLoadError("");
    } catch (error) {
      if (isCanceledRequest(error) || !requestManagerRef.current.isCurrent(request.id)) throw error;
      setLoadError("Satış raporunun tüm bölümleri yüklenemedi. Eski veriler karar amacıyla kullanılmamalıdır.");
      toast.error("Satış raporu eksiksiz yüklenemedi.");
      throw error;
    }
  };
  const [locData, setLocData] = useState([]);


  // Saat/Gün analizi + Sipariş Edilen Ürünler (sayfadaki tarih aralığına bağlı)
  const [hourData, setHourData] = useState(null);
  const [weekdayData, setWeekdayData] = useState(null);
  useEffect(() => { load().catch(() => {}); /* eslint-disable-next-line */ }, [source]);
  useEffect(() => () => requestManagerRef.current?.cancel(), []);
  const tl = (v) => `₺${(v ?? 0).toLocaleString("tr-TR")}`;

  // O8 audit-fix: "Ortalama Sepet (Net)" kartı NET ciro/NET sipariş üzerinden hesaplanır
  // (brk.net — kısmi iptal/iade düşülmüş). Önceden data.totals.aov brüt ciroyu kullanıyordu;
  // etiket "Net" derken değer brüttü. Artık yandaki "Net" ciro kartıyla aynı tabana oturur.
  const netOrders = brk?.net?.orders || 0;
  const netAov = netOrders > 0 ? (brk.net.revenue || 0) / netOrders : 0;

  return (
    <div className="space-y-5" data-testid="sales-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp /> Satış Raporları <ReportScopeBadge kind="mixed" /></h1>
        </div>
        <div className="flex gap-2 items-center">
          <select value={source} onChange={(e) => setSource(e.target.value)} className="px-3 py-1.5 border rounded text-sm" data-testid="sales-source-select">
            <option value="all">Tüm Kaynaklar</option>
            <option value="site">Site (Kendi)</option>
            <option value="trendyol">Trendyol</option>
            <option value="hepsiburada">Hepsiburada</option>
            <option value="temu">Temu</option>
            <option value="n11">n11</option>
            <option value="amazon">Amazon</option>
          </select>
          <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
        </div>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert" data-testid="sales-load-error">
          {loadError}
        </div>
      )}

      {integrityMismatch && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800" data-testid="report-integrity-warning">
          Rapor tutarlılık kontrolü başarısız: üst kart, kanal ve ödeme toplamları eşleşmiyor.
          Bu dönem karar amaçlı kullanılmamalıdır.
        </div>
      )}

      {/* Ciro kırılımı — 4 kademe: dahil → sadece iptal → sadece iade → net (elde kalan) */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { lbl: "İptal & İade DAHİL Ciro", d: brk?.included, c: "from-slate-900 to-slate-700", sub: "Toplam (her şey dahil)" },
          { lbl: "Sadece İptaller", d: brk?.cancels, c: "from-rose-600 to-rose-500", sub: "Kaybedilen (iptal)", partialNote: "kalan ürünler satışta" },
          { lbl: "Sadece İadeler", d: brk?.returns, c: "from-amber-600 to-amber-500", sub: "Kaybedilen (iade)", partialNote: "kalan ürünler satışta" },
          { lbl: "İptal & İade HARİÇ (Net)", d: brk?.net, c: "from-emerald-600 to-emerald-500", sub: "Elimizde kalan net ciro" },
        ].map((k) => (
          <div key={k.lbl} className={`bg-gradient-to-br ${k.c} text-white rounded-xl p-5`}>
            <div className="text-[11px] uppercase opacity-80 leading-tight">{k.lbl}</div>
            <div className="text-2xl font-bold mt-1">{tl(k.d?.revenue)}</div>
            {/* ADET = kalem adetleri toplamı — pazaryeri raporlarıyla (Trendyol "Brüt Satış
                Adedi") AYNI birim. Sipariş sayısıyla karıştırılmasın: 1 sipariş 2-3 adet
                taşıyabilir, mutabakatta fark buradan çıkar. */}
            <div className="text-[11px] opacity-75 mt-1">
              {k.d?.orders ?? 0} sipariş · <span className="font-semibold">{k.d?.units ?? 0} adet</span>
            </div>
            {/* KISMİ notu: "465 iade · 43'ü kısmi" — kısmi iadede siparişin yalnız bir
                kısmı iade edildi, kalan ürünler Net ciroda duruyor. Sipariş sayısı ile
                adet sayısı arasındaki farkı bu açıklar. */}
            {k.d?.partial_orders > 0 && (
              <div className="text-[10px] opacity-90 font-semibold">
                {k.d.partial_orders} tanesi kısmi ({k.partialNote})
              </div>
            )}
            <div className="text-[10px] opacity-60">{k.sub}</div>
          </div>
        ))}
      </div>

      {/* Ortalama Sepet — belirgin kart (kullanıcı isteği) */}
      <div className="inline-flex items-center gap-3 bg-white border-2 border-indigo-200 rounded-xl px-5 py-3 -mt-1 shadow-sm" data-testid="aov-card">
        <span className="text-2xl">🛒</span>
        <div>
          <div className="text-[11px] uppercase tracking-wider text-gray-500 font-semibold">Ortalama Sepet (Net)</div>
          <div className="text-2xl font-bold text-indigo-700 tabular-nums">{tl(netAov)}</div>
        </div>
        <span className="text-[11px] text-gray-400 ml-2">{netOrders} sipariş ortalaması</span>
      </div>

      {/* 🏬 Pazaryerine Göre Satış · İptal · İade — TEK tablo (eski iki ayrı blok birleştirildi) */}
      {cancelRet.length > 0 && (
        <div className="bg-white border rounded-xl p-4" data-testid="channel-combined">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-2">Kanala Göre Satış · İptal · İade</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="text-left p-2">Kanal</th>
                  <th className="text-right p-2" title="NET sipariş sayısı — iptal + iade + ödenmemiş HARİÇ (sipariş birimi)">Sipariş Adeti <span className="text-[9px] text-emerald-600 font-normal">(Net)</span></th>
                  <th className="text-right p-2" title="NET ürün adedi — iptal + iade + ödenmemiş hariç">Ürün Adeti <span className="text-[9px] text-emerald-600 font-normal">(Net)</span></th>
                  <th className="text-right p-2" title="Net + İptal + İade — Trendyol 'Brüt Satış' adediyle karşılaştırın">Brüt Adet</th>
                  <th className="text-right p-2">Net Ciro</th>
                  <th className="text-right p-2">İptal (Ürün Adedi)</th>
                  <th className="text-right p-2">İptal Tutarı</th>
                  <th className="text-right p-2">İptal %</th>
                  <th className="text-right p-2">İade (Ürün Adedi)</th>
                  <th className="text-right p-2">İade Tutarı</th>
                  <th className="text-right p-2">İade %</th>
                  <th className="text-right p-2" title="Seçili tarih aralığında sipariş edilmiş ürünlerden halen sonuçlanmamış iade adedi ve tutarı (sipariş tarihi kapsamı)">Açık İade <span className="text-[9px] font-normal text-gray-400">(seçili dönem)</span></th>
                </tr>
              </thead>
              <tbody>
                {/* TEK KAYNAK: cancel-return-by-source artık satış+iptal+iade+adet+açık
                    iadeyi ciro kartlarıyla AYNI kalem-bazlı mantıkla döndürür. Eskiden
                    burası sales-by-platform ile birleştiriliyordu ve iade tutarı
                    kartlarla çelişiyordu (sipariş-bütünü vs kalem bazlı). */}
                {cancelRet.map((c) => {
                  const totU = c.total_units || 0;
                  const cp = totU ? (100 * (c.cancel_units || 0)) / totU : 0;
                  const rp = totU ? (100 * (c.return_units || 0)) / totU : 0;
                  return (
                    <tr key={c.source} className="border-t">
                      <td className="p-2 font-medium">{c.source}</td>
                      <td className="p-2 text-right tabular-nums">{c.orders || 0}</td>
                      <td className="p-2 text-right tabular-nums font-semibold">{c.units || 0}</td>
                      <td className="p-2 text-right tabular-nums text-gray-500" title="Net + İptal + İade adedi — Trendyol 'Brüt Satış' ile karşılaştırın">{c.total_units || 0}</td>
                      <td className="p-2 text-right tabular-nums font-semibold">{tl(c.revenue)}</td>
                      <td className="p-2 text-right tabular-nums">{c.cancel_units || 0}</td>
                      <td className="p-2 text-right tabular-nums text-rose-600">{tl(c.cancel_total)}</td>
                      <td className={`p-2 text-right tabular-nums text-xs ${cp >= 10 ? "text-rose-600 font-bold" : "text-gray-500"}`}>{cp ? `%${cp.toFixed(1)}` : ""}</td>
                      <td className="p-2 text-right tabular-nums">
                        {c.return_units || 0}
                        {c.return_partial_orders > 0 && (
                          <div className="text-[10px] text-gray-400 font-normal">{c.return_partial_orders} kısmi</div>
                        )}
                      </td>
                      <td className="p-2 text-right tabular-nums text-amber-600">{tl(c.return_total)}</td>
                      <td className={`p-2 text-right tabular-nums text-xs ${rp >= 15 ? "text-rose-600 font-bold" : "text-gray-500"}`}>{rp ? `%${rp.toFixed(1)}` : ""}</td>
                      <td className="p-2 text-right tabular-nums text-xs text-amber-700">
                        {c.pending_units ? `${c.pending_units} adet · ${tl(c.pending_total)}` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

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

      {/* 🗺️ İl Bazında Satış — TAM GENİŞLİK, sığmazsa yatay kaydırma */}
      {locData.length > 0 && (
        <div className="bg-white border rounded-xl p-4" data-testid="location-block">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-sm font-bold uppercase tracking-wider">İl Bazında Satış</h2>
            <span className="text-[11px] text-gray-400">{locData.length} il · sığmazsa yana kaydırın →</span>
          </div>
          <div className="overflow-x-auto pb-1">
            <BarChart width={Math.max(1100, locData.length * 44)} height={300} data={locData}
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
      )}

      <div className="bg-white rounded-xl border p-5">
        {/* Başlık seçilen kırılımı söyler; az kovalı (haftalık/aylık) görünümde iki nokta
            arasına çizgi çekmek yanıltıcıydı → gruplu görünümde ÇUBUK grafik kullanılır. */}
        <h3 className="font-semibold mb-3">{{ day: "Günlük", week: "Haftalık", month: "Aylık" }[groupBy] || "Günlük"} Net Ciro & Sipariş <span className="text-[11px] font-normal text-gray-400">(aralığa göre otomatik)</span></h3>
        <ResponsiveContainer width="100%" height={300}>
          {groupBy === "day" ? (
            <LineChart data={data?.rows || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
              <XAxis dataKey="period" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="revenue" stroke="#10b981" strokeWidth={2} name="Net Ciro (₺)" />
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
              <Bar yAxisId="left" dataKey="revenue" fill="#10b981" name="Net Ciro (₺)" radius={[3, 3, 0, 0]} />
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
                  {/* D3 audit-fix: ciro null gelirse render patlamasın — grafik etiketiyle aynı (value||0) koruması */}
                  <td className="p-2 text-right font-semibold">₺{(p.revenue || 0).toLocaleString("tr-TR")}</td>
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
  const [recon, setRecon] = useState(null);
  const [reconLoading, setReconLoading] = useState(false);
  const [expanded, setExpanded] = useState(() => new Set()); // açılır: beden dağılımı
  const [top90Map, setTop90Map] = useState({});              // İvme: 90 günlük haftalık hız haritası
  const [loadError, setLoadError] = useState("");
  const requestManagerRef = useRef(null);
  if (!requestManagerRef.current) requestManagerRef.current = createLatestRequestManager();
  const toggleExpand = (k) => setExpanded(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const reconcileTrendyol = async () => {
    setReconLoading(true);
    try {
      // Backend tek istekte uzun aralığı bilinçli olarak sınırlar. 5 Haziran'dan
      // bugüne mutabakatı 31 günlük, boşluksuz parçalara bölüp salt-okunur sonuçları
      // birleştir; hiçbir sipariş/statü/stok kaydı değiştirilmez.
      const parts = [];
      for (const chunk of splitReportRange(from, to, 31)) {
        const response = await axios.get(`${API}/integrations/trendyol/reconcile`, {
          headers: authHeaders(), params: {
            start_date: chunk.from, end_date: chunk.to, apply: false, list_limit: 20,
          },
        });
        parts.push(response.data);
      }
      const sum = (pick) => parts.reduce((total, part) => total + Number(pick(part) || 0), 0);
      const collect = (key) => parts.flatMap((part) => part?.[key]?.items || []).slice(0, 20);
      const tyAmount = sum((p) => p.trendyol?.amount);
      const amountDiff = sum((p) => p.diff?.amount);
      setRecon({
        range: { start: from, end: to },
        trendyol: { orders: sum((p) => p.trendyol?.orders), units: sum((p) => p.trendyol?.units), amount: tyAmount },
        panel: { orders: sum((p) => p.panel?.orders), units: sum((p) => p.panel?.units), amount: sum((p) => p.panel?.amount), docs: sum((p) => p.panel?.docs) },
        diff: { orders: sum((p) => p.diff?.orders), units: sum((p) => p.diff?.units), amount: amountDiff,
          amount_pct: tyAmount ? 100 * amountDiff / tyAmount : 0 },
        duplicates: { extra_docs: sum((p) => p.duplicates?.extra_docs), order_numbers: parts.flatMap((p) => p.duplicates?.order_numbers || []).slice(0, 20) },
        missing_in_panel: { count: sum((p) => p.missing_in_panel?.count), active_count: sum((p) => p.missing_in_panel?.active_count), cancelled_count: sum((p) => p.missing_in_panel?.cancelled_count), items: collect("missing_in_panel") },
        extra_in_panel: { count: sum((p) => p.extra_in_panel?.count), items: collect("extra_in_panel") },
        cancel_mismatch: { count: sum((p) => p.cancel_mismatch?.count), items: collect("cancel_mismatch") },
        partial_cancel: { count: sum((p) => p.partial_cancel?.count), items: collect("partial_cancel") },
      });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Trendyol mutabakatı alınamadı");
    } finally {
      setReconLoading(false);
    }
  };

  const load = async () => {
    const query = Object.freeze({ start_date: from, end_date: to, source: platFilter || "all" });
    const d90 = reportPresetRange("90", new Date(`${to}T12:00:00`)).from;
    const request = requestManagerRef.current.begin();
    const config = (params) => ({ headers: authHeaders(), params, signal: request.signal });
    try {
      const [t, c, cr, t90] = await Promise.all([
        axios.get(`${API}/admin/reports/products/top`, config({ ...query, limit: 2000 })),
        axios.get(`${API}/admin/reports/categories`, config(query)),
        axios.get(`${API}/admin/reports/cancel-return-products`, config(query)),
        axios.get(`${API}/admin/reports/products/top`, config({ ...query, start_date: d90, limit: 2000 })),
      ]);
      if (!requestManagerRef.current.isCurrent(request.id)) return;
      const velocityMap = {};
      (t90.data.items || []).forEach(p => { if (p.product_id) velocityMap[p.product_id] = (p.velocity || {}).weekly_rate ?? 0; });
      setTop(t.data.items || []);
      setCats(c.data.items || []);
      setCrRows(cr.data.items || []);
      setTop90Map(velocityMap);
      setLoadError("");
    } catch (error) {
      if (isCanceledRequest(error) || !requestManagerRef.current.isCurrent(request.id)) throw error;
      setLoadError("Ürün raporunun tüm bölümleri yüklenemedi. Eski veriler karar amacıyla kullanılmamalıdır.");
      toast.error("Ürün raporu eksiksiz yüklenemedi.");
      throw error;
    }
  };
  const [crRows, setCrRows] = useState([]);
  const [crQ, setCrQ] = useState("");
  const [crPlat, setCrPlat] = useState("");
  useEffect(() => { load().catch(() => {}); /* eslint-disable-next-line */ }, [platFilter]);
  useEffect(() => () => requestManagerRef.current?.cancel(), []);

  const platLabel = (p) => ({ site: "Site", trendyol: "Trendyol", hepsiburada: "Hepsiburada", temu: "Temu", n11: "n11", amazon: "Amazon" }[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—"));
  // Sezon ürün kartındaki 'Sezon' özniteliğinden gelir (backend normalize eder); yoksa boş.
  const SEASONS = ["İlkbahar/Sonbahar", "Tüm Sezonlar", "Yaz", "Kış"];
  // Kapsama ilk tıkta KÜÇÜKTEN büyüğe: RPT durumu acil olanlar (az haftası kalanlar) üstte.
  const toggleSort = (k) => { if (sortKey === k) setSortDir(d => d === "desc" ? "asc" : "desc"); else { setSortKey(k); setSortDir(k === "name" || k === "best_size" || k === "_cover" ? "asc" : "desc"); } };
  // Filtre seçenekleri (veriden)
  const platOptions = Array.from(new Set([
    "site", "trendyol", "hepsiburada", "temu", "n11", "amazon",
    ...top.flatMap(p => (p.platform_breakdown || []).map(x => x.platform)),
    ...top.flatMap(p => (p.cancel_return_by_platform || []).map(x => x.platform)),
  ])).sort();
  const sizeOptions = Array.from(new Set(top.flatMap(p => (p.size_breakdown || []).map(x => x.size)))).filter(s => s && s !== "—").sort((a, b) => a.localeCompare(b, "tr", { numeric: true }));
  const velMeta = { green: { label: "Hızlı", cls: "bg-green-100 text-green-700 border-green-200" }, yellow: { label: "Orta", cls: "bg-yellow-100 text-yellow-700 border-yellow-200" }, red: { label: "Yavaş", cls: "bg-red-100 text-red-700 border-red-200" } };
  const rows = (() => {
    const f = q.trim().toLocaleLowerCase("tr");
    // Uzman kurulu geliştirmeleri: kapsama (kaç haftalık stok), ivme (30g vs 90g hız), iade %
    let r = top.map(p => {
      const wr = (p.velocity || {}).weekly_rate ?? 0;
      const prev = top90Map[p.product_id];
      const scope = productReportScope(p);
      return {
        ...p,
        qty: scope.netQty,
        revenue: scope.revenue,
        cancel_qty: scope.cancelQty,
        return_qty: scope.returnQty,
        _cover: (p.current_stock != null && wr > 0) ? p.current_stock / wr : null,
        _mom: (prev != null && (wr > 0 || prev > 0)) ? wr - prev : null,
        _scopeReturnPct: scope.returnRatePct,
        _gross: scope.grossQty,
      };
    });
    if (f) r = r.filter(p => (p.name || "").toLocaleLowerCase("tr").includes(f));
    // Platform filtresi: satırı YALNIZ o platforma DARALT (adet/ciro/iptal/iade + Platform sütunu
    // o platforma göre). Stok/kapsama/hız TOPLAM kalır (stok platformlar arası ortaktır).
    if (platFilter) {
      r = r.filter(p => productReportScope(p, platFilter).hasPlatformData)
           .map(p => {
             const scope = productReportScope(p, platFilter);
             return {
               ...p,
               qty: scope.netQty,
               revenue: scope.revenue,
               cancel_qty: scope.cancelQty,
               return_qty: scope.returnQty,
               _gross: scope.grossQty,
               _scopeReturnPct: scope.returnRatePct,
               platform_breakdown: [{ platform: platFilter, qty: scope.netQty, revenue: scope.revenue }],
               top_platform: platFilter,
               _platScoped: true,
             };
           });
    }
    if (sizeFilter) r = r.filter(p => (p.size_breakdown || []).some(x => x.size === sizeFilter));
    if (collFilter) r = r.filter(p => (p.season || "") === collFilter);
    if (velFilter) r = r.filter(p => (p.velocity || {}).code === velFilter);
    r.sort((a, b) => {
      if (sortKey === "velocity") { const va = (a.velocity || {}).weekly_rate ?? -1, vb = (b.velocity || {}).weekly_rate ?? -1; return sortDir === "asc" ? va - vb : vb - va; }
      if (sortKey === "_cover") {
        // Satışsız (∞/—) satırlar HER İKİ yönde de en sona — acil RPT'ler öne çıksın.
        const na = a._cover, nb = b._cover;
        if (na == null && nb == null) return 0;
        if (na == null) return 1;
        if (nb == null) return -1;
        return sortDir === "asc" ? na - nb : nb - na;
      }
      let va = a[sortKey], vb = b[sortKey];
      if (sortKey === "name" || sortKey === "best_size" || sortKey === "top_platform" || sortKey === "season") { va = (va || "").toString(); vb = (vb || "").toString(); return sortDir === "asc" ? va.localeCompare(vb, "tr") : vb.localeCompare(va, "tr"); }
      va = va ?? -1; vb = vb ?? -1; return sortDir === "asc" ? va - vb : vb - va;
    });
    return r;
  })();
  const exportXlsx = async () => {
    try {
      const params = productExportParams({
        from, to, platform: platFilter, size: sizeFilter, season: collFilter,
        velocity: velFilter, query: q, sortKey, sortDir,
      });
      const r = await fetch(`${API}/admin/reports/products/export-xlsx?${params}`, { headers: authHeaders() });
      if (!r.ok) throw new Error(`Excel API ${r.status}`);
      const b = await r.blob();
      const u = URL.createObjectURL(b);
      const a = document.createElement("a"); a.href = u; a.download = "urun-raporu.xlsx"; a.click();
      URL.revokeObjectURL(u);
    } catch { toast.error("Excel raporu indirilemedi."); }
  };
  const SortTh = ({ k, children, right }) => (
    <th onClick={() => toggleSort(k)} className={`p-3 cursor-pointer select-none hover:text-gray-900 ${right ? "text-right" : "text-left"}`}>
      {children}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
  // Tükenme (stok bitiş) tarihi = BUGÜN + kapsama(hafta). _cover SONLU değilse tarih yok
  // (satmayan/stoksuz → ∞ / — Kapsama ile tutarlı). Türkçe kısa format: "12 Eyl 2026".
  const depletionDate = (cover) => {
    if (cover == null || !isFinite(cover)) return null;
    const d = new Date(Date.now() + cover * 7 * 86400000);
    return d.toLocaleDateString("tr-TR", { day: "numeric", month: "short", year: "numeric" });
  };

  return (
    <div className="space-y-5" data-testid="products-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Ürün Raporları <ReportScopeBadge kind="mixed" /></h1>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={reconcileTrendyol} disabled={reconLoading}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm font-semibold hover:bg-orange-700 disabled:opacity-50 shadow-sm"
            data-testid="trendyol-reconcile">
            {reconLoading ? "Karşılaştırılıyor…" : "Trendyol ile Mutabakat"}
          </button>
          <button onClick={exportXlsx} className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700 shadow-sm" data-testid="products-export-xlsx">
            ⬇ Excel İndir
          </button>
          <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
        </div>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert" data-testid="products-load-error">
          {loadError}
        </div>
      )}

      {recon && (
        <div className={`rounded-xl border p-4 ${recon.diff?.orders || recon.diff?.units || Math.abs(recon.diff?.amount || 0) > 0.01 ? "bg-amber-50 border-amber-300" : "bg-emerald-50 border-emerald-300"}`}
          data-testid="trendyol-reconcile-result">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <h3 className="font-semibold">Trendyol ↔ Panel Mutabakatı</h3>
              <p className="text-xs text-gray-600 mt-1">{recon.range?.start} → {recon.range?.end} · Salt okunur; hiçbir siparişi değiştirmez.</p>
            </div>
            <div className="grid grid-cols-3 gap-5 text-sm text-right">
              <div><div className="text-gray-500">Sipariş farkı</div><b>{recon.diff?.orders ?? 0}</b></div>
              <div><div className="text-gray-500">Ürün adedi farkı</div><b>{recon.diff?.units ?? 0}</b></div>
              <div><div className="text-gray-500">Tutar farkı</div><b>₺{(recon.diff?.amount || 0).toLocaleString("tr-TR")}</b></div>
            </div>
          </div>
          <div className="grid md:grid-cols-2 gap-3 mt-3 text-sm">
            <div className="bg-white/70 rounded-lg p-3"><b>Trendyol:</b> {recon.trendyol?.orders || 0} sipariş · {recon.trendyol?.units || 0} adet · ₺{(recon.trendyol?.amount || 0).toLocaleString("tr-TR")}</div>
            <div className="bg-white/70 rounded-lg p-3"><b>Panel (tekil):</b> {recon.panel?.orders || 0} sipariş · {recon.panel?.units || 0} adet · ₺{(recon.panel?.amount || 0).toLocaleString("tr-TR")}</div>
          </div>
          <p className="text-xs text-gray-600 mt-3">
            Ham kopya belge: {recon.duplicates?.extra_docs || 0} · Panelde eksik: {recon.missing_in_panel?.count || 0}
            {recon.missing_in_panel?.count ? ` (${recon.missing_in_panel.active_count || 0} aktif, ${recon.missing_in_panel.cancelled_count || 0} iptal)` : ""}
            {' · '}Panelde fazla: {recon.extra_in_panel?.count || 0} · İptal durum farkı: {recon.cancel_mismatch?.count || 0}
          </p>
        </div>
      )}


      <div className="bg-white rounded-xl border p-5">
        <h3 className="font-semibold mb-3">En Çok Satan 10 Ürün (Net Ciro)</h3>
        <ResponsiveContainer width="100%" height={340}>
          <BarChart data={top.slice(0, 10)} layout="vertical" margin={{ left: 120 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v) => Number(v).toLocaleString("tr-TR")} />
            <YAxis dataKey="name" type="category" width={200} tick={{ fontSize: 10 }} />
            <Tooltip formatter={(v) => [`₺${Number(v).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`, "Ciro"]} />
            <Bar dataKey="revenue" fill="#3b82f6" name="Net Ciro (₺)" />
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
              <option value="green">🟢 Hızlı</option>
              <option value="yellow">🟡 Orta</option>
              <option value="red">🔴 Yavaş</option>
            </select>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ürün ara…" className="border rounded-lg px-3 py-1.5 text-sm w-48" />
            <button onClick={exportXlsx} className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-sm font-semibold hover:bg-emerald-700" data-testid="products-export-xlsx-inline" title="Ürün raporunu Excel olarak indir">
              ⬇ Excel
            </button>
          </div>
        </div>
        <div className="flex items-center justify-between px-1 pb-2 text-xs text-gray-500">
          <span>
            <span className="font-semibold text-gray-800">{rows.length}</span> ürün listeleniyor{rows.length !== top.length ? ` (toplam ${top.length})` : ""} — aktif katalog (satışı olmayanlar dahil) + seçili dönemde satış yapmış pasif ürünler.
            <span className="text-gray-400"> Toplam Satış = Net Satış + İptal + İade. Net Satış ve Ciro, iade+iptal düşülmüş halidir.</span>
          </span>
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
            <thead className="bg-gray-50 text-xs uppercase text-gray-500 sticky top-0 z-10">
              <tr>
                <SortTh k="name">Ürün</SortTh>
                <SortTh k="season">Sezon</SortTh>
                <SortTh k="velocity">Satış Hızı</SortTh>
                <SortTh k="_mom">İvme</SortTh>
                <SortTh k="_gross" right>Toplam Satış</SortTh>
                <SortTh k="cancel_qty" right>İptal Ürün Adedi</SortTh>
                <SortTh k="return_qty" right>İade Ürün Adedi</SortTh>
                <SortTh k="_scopeReturnPct" right>{platFilter ? `${platLabel(platFilter)} İade %` : "Tüm Platformlar İade %"}</SortTh>
                <SortTh k="qty" right>Net Satış</SortTh>
                <SortTh k="revenue" right>Ciro (Net)</SortTh>
                <SortTh k="current_stock" right>Güncel Stok</SortTh>
                <SortTh k="_cover" right>Kapsama</SortTh>
                <th className="p-3 text-right" title="Tahmini stok bitiş tarihi = bugün + kapsama (hafta)">Tükenme Tarihi</th>
                <SortTh k="best_size">En Çok Beden</SortTh>
                <SortTh k="top_platform">Platform</SortTh>
              </tr>
            </thead>
            <tbody>
              {rows.map((p, i) => {
                const key = (p.product_id || p.name) + i;
                const isOpen = expanded.has(key);
                return (
                <Fragment key={key}>
                <tr className="border-t hover:bg-gray-50 cursor-pointer" onClick={() => toggleExpand(key)}>
                  <td className="p-3 font-medium max-w-xs" title={p.name}>
                    <div className="flex items-center gap-1 min-w-0">
                      <span className="inline-block w-3 shrink-0 text-gray-400">{isOpen ? "▾" : "▸"}</span>
                      <span className="truncate">{p.name}</span>
                      {p.catalog_match === false && (
                        <span className="shrink-0 inline-flex rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-800 ring-1 ring-inset ring-amber-300" title="Sipariş kalemi aktif ürün kataloğundaki bir ürün veya varyantla eşleştirilemedi">
                          Katalog eşleşmedi
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="p-3 text-xs whitespace-nowrap">{p.season || ""}</td>
                  <td className="p-3">
                    {p.velocity ? (
                      <span className={`inline-flex items-center px-2 py-0.5 text-xs rounded-full border whitespace-nowrap ${(velMeta[p.velocity.code] || {}).cls || ""}`}
                        title="Seçili tarih aralığındaki ortalama haftalık satış adedi">
                        {(velMeta[p.velocity.code] || {}).label || p.velocity.code} · {(p.velocity.weekly_rate ?? 0).toLocaleString("tr-TR")}/hafta
                      </span>
                    ) : "—"}
                  </td>
                  <td className="p-3 text-xs whitespace-nowrap">
                    {p._mom == null ? "" : (() => {
                      const wr = (p.velocity || {}).weekly_rate ?? 0;
                      const prev = wr - p._mom;
                      if (wr >= prev * 1.25 && p._mom >= 0.5) return <span className="text-emerald-600 font-bold" title={`90g: ${prev.toFixed(1)}/hf → şimdi: ${wr.toFixed(1)}/hf`}>▲ Yükseliyor</span>;
                      if (wr <= prev * 0.75 && -p._mom >= 0.5) return <span className="text-rose-600 font-bold" title={`90g: ${prev.toFixed(1)}/hf → şimdi: ${wr.toFixed(1)}/hf`}>▼ Düşüyor</span>;
                      return <span className="text-gray-400" title={`90g: ${prev.toFixed(1)}/hf → şimdi: ${wr.toFixed(1)}/hf`}>→ Stabil</span>;
                    })()}
                  </td>
                  <td className="p-3 text-right font-semibold tabular-nums" title="Toplam sipariş edilen adet = Net Satış + İptal + İade">{p._gross}</td>
                  <td className={`p-3 text-right tabular-nums ${p.cancel_qty > 0 ? "text-rose-600 font-semibold" : "text-gray-400"}`}
                    title={(p.cancel_return_by_platform || []).map(x => `${platLabel(x.platform)}: iptal ${x.cancel}`).join(", ")}>
                    {p.cancel_qty || 0}
                  </td>
                  <td className={`p-3 text-right tabular-nums ${p.return_qty > 0 ? "text-amber-600 font-semibold" : "text-gray-400"}`}
                    title={(p.cancel_return_by_platform || []).map(x => `${platLabel(x.platform)}: iade ${x.return}`).join(", ")}>
                    {p.return_qty || 0}
                  </td>
                  <td className={`p-3 text-right tabular-nums text-xs ${p._scopeReturnPct >= 15 ? "text-red-600 font-bold" : p._scopeReturnPct >= 8 ? "text-amber-600 font-semibold" : "text-gray-400"}`}
                    title={`${platFilter ? platLabel(platFilter) : "Tüm platformlar"}: İade Ürün Adedi / Toplam Satış Ürün Adedi = ${p.return_qty || 0}/${p._gross || 0}. İptal yalnız toplam adette yer alır; iade adedine eklenmez.`}>
                    <div>%{p._scopeReturnPct.toFixed(1)}</div>
                    <div className="text-[9px] font-normal text-gray-400">iade ürün / toplam ürün</div>
                  </td>
                  <td className="p-3 text-right">{p.qty}</td>
                  <td className="p-3 text-right font-semibold">₺{(p.revenue || 0).toLocaleString("tr-TR")}</td>
                  <td className={`p-3 text-right ${p.current_stock === 0 ? "text-red-600 font-semibold" : ""}`}>{p.current_stock == null ? "—" : p.current_stock}</td>
                  <td className="p-3 text-right text-xs whitespace-nowrap">
                    {p._cover == null ? (
                      ((p.velocity || {}).weekly_rate ?? 0) === 0 && (p.current_stock || 0) > 0 ? <span className="text-gray-400" title="Bu aralıkta hiç satmadı — stok eritilemiyor">∞</span> : "—"
                    ) : p._cover <= 4 ? (
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-600 text-white font-bold animate-pulse cursor-help"
                        title={`RPT (yeniden üretim) açılmalı: mevcut satış hızıyla (${((p.velocity || {}).weekly_rate ?? 0).toLocaleString("tr-TR")}/hafta) eldeki ${p.current_stock ?? "?"} adet stok yalnız ~${p._cover.toFixed(1)} hafta yetiyor. Üretim süresi ~3 hafta olduğundan 4 haftalık kapsamanın altı kritiktir — hemen imalat siparişi açın.`}
                      >
                        RPT AÇ · {p._cover.toFixed(1)} hf
                      </span>
                    ) : p._cover >= 26 ? (
                      <span className="text-gray-400" title="26+ haftalık stok — aşırı stok, eritme adayı">{p._cover.toFixed(0)} hf</span>
                    ) : (
                      <span className="tabular-nums">{p._cover.toFixed(1)} hf</span>
                    )}
                  </td>
                  <td className="p-3 text-right text-xs whitespace-nowrap tabular-nums">
                    {(() => {
                      const dt = depletionDate(p._cover);
                      if (!dt) {
                        return ((p.velocity || {}).weekly_rate ?? 0) === 0 && (p.current_stock || 0) > 0
                          ? <span className="text-gray-400" title="Bu aralıkta hiç satmadı — tükenme tarihi hesaplanamıyor">∞</span>
                          : <span className="text-gray-400">—</span>;
                      }
                      return p._cover <= 4
                        ? <span className="text-red-600 font-bold" title="Kritik: <4 hafta — üretim süresinden kısa">{dt}</span>
                        : <span>{dt}</span>;
                    })()}
                  </td>
                  <td className="p-3">{p.best_size || "—"}</td>
                  <td className="p-3" title={(p.platform_breakdown || []).map(x => `${platLabel(x.platform)}: ${x.qty}`).join(", ")}>
                    {(p.platform_breakdown || []).map(x => platLabel(x.platform)).join(", ") || "—"}
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-gray-50/60">
                    <td colSpan={15} className="px-8 py-3">
                      <div className="flex flex-wrap gap-x-8 gap-y-2 text-xs">
                        <div>
                          <div className="font-semibold text-gray-700 mb-1">Beden Bazında — Toplam / İptal / İade / Net / Kalan Stok</div>
                          {(() => {
                            // Net (size_breakdown) + iptal/iade (cancel_return_by_size) + kalan stok (stock_by_size)
                            const m = {};
                            (p.size_breakdown || []).forEach(s => { m[s.size || "—"] = { net: s.qty, c: 0, r: 0, st: null }; });
                            (p.cancel_return_by_size || []).forEach(s => {
                              const k = s.size || "—";
                              if (!m[k]) m[k] = { net: 0, c: 0, r: 0, st: null };
                              m[k].c += s.cancel || 0; m[k].r += s.return || 0;
                            });
                            Object.entries(p.stock_by_size || {}).forEach(([k0, st]) => {
                              const k = k0 || "—";
                              if (!m[k]) m[k] = { net: 0, c: 0, r: 0, st: 0 };
                              m[k].st = (m[k].st || 0) + Number(st || 0);
                            });
                            const rowsz = Object.entries(m).sort((a, b) => a[0].localeCompare(b[0], "tr", { numeric: true }));
                            return rowsz.length ? (
                              <table className="text-xs bg-white border rounded-lg overflow-hidden">
                                <thead className="bg-gray-100 text-gray-500 uppercase">
                                  <tr>
                                    <th className="px-2.5 py-1 text-left">Beden</th>
                                    <th className="px-2.5 py-1 text-right">Toplam</th>
                                    <th className="px-2.5 py-1 text-right">İptal Ürün Adedi</th>
                                    <th className="px-2.5 py-1 text-right">İade Ürün Adedi</th>
                                    <th className="px-2.5 py-1 text-right">Net</th>
                                    <th className="px-2.5 py-1 text-right">Kalan Stok</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {rowsz.map(([sz, v]) => (
                                    <tr key={sz} className="border-t">
                                      <td className="px-2.5 py-1 font-semibold">{sz}</td>
                                      <td className="px-2.5 py-1 text-right tabular-nums font-semibold">{v.net + v.c + v.r}</td>
                                      <td className={`px-2.5 py-1 text-right tabular-nums ${v.c ? "text-rose-600" : "text-gray-300"}`}>{v.c}</td>
                                      <td className={`px-2.5 py-1 text-right tabular-nums ${v.r ? "text-amber-600" : "text-gray-300"}`}>{v.r}</td>
                                      <td className="px-2.5 py-1 text-right tabular-nums font-bold">{v.net}</td>
                                      <td className={`px-2.5 py-1 text-right tabular-nums font-semibold ${v.st === 0 ? "text-red-600" : v.st == null ? "text-gray-300" : ""}`}>{v.st == null ? "—" : v.st}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            ) : <span className="text-gray-400">—</span>;
                          })()}
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
              {rows.length === 0 && <tr><td colSpan={15} className="p-4 text-center text-gray-400">Veri yok.</td></tr>}
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
                    <th className="text-right p-2.5">İptal Ürün Adedi</th>
                    <th className="text-right p-2.5">İptal Tutar</th>
                    <th className="text-right p-2.5">İade Ürün Adedi</th>
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
  const loadStock = () => axios.get(`${API}/admin/reports/stock`, { headers: authHeaders() })
    .then((r) => setData(r.data)).catch(() => toast.error("Stok raporu alınamadı."));
  useEffect(() => { loadStock(); /* eslint-disable-next-line */ }, []);

  return (
    <div className="space-y-5" data-testid="stock-report-page">
      <div className="flex items-center justify-between"><h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Stok Raporu <ReportScopeBadge kind="stock" /></h1><button onClick={loadStock} className="px-3 py-2 border rounded text-sm inline-flex gap-1 items-center"><RefreshCw size={14}/> Yenile</button></div>

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
          <div className="text-xs uppercase opacity-80">Listelenen Stoksuz Ürün</div>
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
