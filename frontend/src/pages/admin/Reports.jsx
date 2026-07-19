import { useState, useEffect, Fragment } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import { TrendingUp, Package, Users, Truck, CreditCard, RefreshCw } from "lucide-react";
import ReportScopeBadge from "../../components/ReportScopeBadge";

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
  const [groupBy, setGroupBy] = useState("day");
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
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [groupBy, source]);
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
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className="px-3 py-1.5 border rounded text-sm">
            <option value="day">Günlük</option>
            <option value="week">Haftalık</option>
            <option value="month">Aylık</option>
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
      {/* Ortalama sepet (net) küçük satır */}
      <div className="text-sm text-gray-500 -mt-2">Ortalama Sepet (net): <b className="text-gray-800">{tl(data?.totals?.aov)}</b></div>

      <div className="bg-white rounded-xl border p-5">
        <h3 className="font-semibold mb-3">Günlük Ciro & Sipariş</h3>
        <ResponsiveContainer width="100%" height={300}>
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
        </ResponsiveContainer>
      </div>

      <div className="grid md:grid-cols-2 gap-5">
        <div className="bg-white rounded-xl border p-5">
          <h3 className="font-semibold mb-3 flex items-center gap-2"><CreditCard size={16} /> Ödeme Yöntemi Dağılımı</h3>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={paymentData} dataKey="revenue" nameKey="method" cx="50%" cy="50%" outerRadius={90} label={(e) => `${e.method}: ₺${e.revenue.toLocaleString("tr-TR")}`}>
                {paymentData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="bg-white rounded-xl border p-5">
          <h3 className="font-semibold mb-3">Ödeme Yöntemlerine Göre Sipariş</h3>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr><th className="text-left p-2">Yöntem</th><th className="text-right p-2">Sipariş</th><th className="text-right p-2">Ciro</th></tr>
            </thead>
            <tbody>
              {paymentData.map((p) => (
                <tr key={p.method} className="border-t">
                  <td className="p-2 font-medium">{p.method}</td>
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
  const [collFilter, setCollFilter] = useState("");   // D5 — koleksiyon (FcFw/FCss…)
  const [velFilter, setVelFilter] = useState("");      // D4 — satış hızı (green/yellow/red)
  const [expanded, setExpanded] = useState(() => new Set()); // açılır: beden dağılımı
  const toggleExpand = (k) => setExpanded(prev => { const n = new Set(prev); n.has(k) ? n.delete(k) : n.add(k); return n; });

  const load = async () => {
    const [t, c] = await Promise.all([
      axios.get(`${API}/admin/reports/products/top`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", limit: 2000 } }),
      axios.get(`${API}/admin/reports/categories`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } }),
    ]);
    setTop(t.data.items || []);
    setCats(c.data.items || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const platLabel = (p) => ({ site: "Site", trendyol: "Trendyol", hepsiburada: "Hepsiburada", temu: "Temu" }[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—"));
  const toggleSort = (k) => { if (sortKey === k) setSortDir(d => d === "desc" ? "asc" : "desc"); else { setSortKey(k); setSortDir(k === "name" || k === "best_size" ? "asc" : "desc"); } };
  // Filtre seçenekleri (veriden)
  const platOptions = Array.from(new Set(top.flatMap(p => (p.platform_breakdown || []).map(x => x.platform)))).sort();
  const sizeOptions = Array.from(new Set(top.flatMap(p => (p.size_breakdown || []).map(x => x.size)))).filter(s => s && s !== "—").sort((a, b) => a.localeCompare(b, "tr", { numeric: true }));
  const collOptions = Array.from(new Set(top.map(p => (p.collection || "").trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b, "tr"));
  const velMeta = { green: { label: "Hızlı (haftada 5+)", cls: "bg-green-100 text-green-700 border-green-200" }, yellow: { label: "Orta (haftada 1-4)", cls: "bg-yellow-100 text-yellow-700 border-yellow-200" }, red: { label: "Yavaş (ayda 0-2)", cls: "bg-red-100 text-red-700 border-red-200" } };
  const rows = (() => {
    const f = q.trim().toLocaleLowerCase("tr");
    let r = f ? top.filter(p => (p.name || "").toLocaleLowerCase("tr").includes(f)) : [...top];
    if (platFilter) r = r.filter(p => (p.platform_breakdown || []).some(x => x.platform === platFilter));
    if (sizeFilter) r = r.filter(p => (p.size_breakdown || []).some(x => x.size === sizeFilter));
    if (collFilter) r = r.filter(p => (p.collection || "").trim() === collFilter);
    if (velFilter) r = r.filter(p => (p.velocity || {}).code === velFilter);
    r.sort((a, b) => {
      if (sortKey === "velocity") { const va = (a.velocity || {}).weekly_rate ?? -1, vb = (b.velocity || {}).weekly_rate ?? -1; return sortDir === "asc" ? va - vb : vb - va; }
      let va = a[sortKey], vb = b[sortKey];
      if (sortKey === "name" || sortKey === "best_size" || sortKey === "top_platform" || sortKey === "collection") { va = (va || "").toString(); vb = (vb || "").toString(); return sortDir === "asc" ? va.localeCompare(vb, "tr") : vb.localeCompare(va, "tr"); }
      va = va ?? -1; vb = vb ?? -1; return sortDir === "asc" ? va - vb : vb - va;
    });
    return r;
  })();
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
        <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
      </div>

      {/* Rapordan neye erişilir — kılavuz */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-900">
        <span className="font-semibold">Bu raporda:</span> Seçili tarih aralığında (iptal & iade hariç) her ürünün toplam <b>satış adedi</b> ve <b>cirosu</b>, <b>güncel stok</b> durumu, <b>en çok satan bedeni</b> ve <b>hangi platformdan</b> ne kadar sattığı yer alır. Kolon başlıklarına tıklayarak (ör. cirodan yükseğe/düşüğe) sıralayabilir, arama ile ürün filtreleyebilirsiniz.
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
            {collOptions.length > 0 && (
              <select value={collFilter} onChange={e => setCollFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
                <option value="">Tüm Koleksiyonlar</option>
                {collOptions.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            )}
            <select value={velFilter} onChange={e => setVelFilter(e.target.value)} className="border rounded-lg px-2 py-1.5 text-sm">
              <option value="">Tüm Hızlar</option>
              <option value="green">🟢 Hızlı (haftada 5+)</option>
              <option value="yellow">🟡 Orta (haftada 1-4)</option>
              <option value="red">🔴 Yavaş (ayda 0-2)</option>
            </select>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="Ürün ara…" className="border rounded-lg px-3 py-1.5 text-sm w-48" />
          </div>
        </div>
        <div className="overflow-x-auto max-h-[70vh] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500 sticky top-0">
              <tr>
                <SortTh k="name">Ürün</SortTh>
                <SortTh k="velocity">Satış Hızı</SortTh>
                <SortTh k="qty" right>Adet</SortTh>
                <SortTh k="revenue" right>Ciro</SortTh>
                <SortTh k="current_stock" right>Güncel Stok</SortTh>
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
                  <td className="p-3 font-medium max-w-xs truncate" title={p.name}>
                    <span className="inline-block w-3 text-gray-400 mr-1">{isOpen ? "▾" : "▸"}</span>{p.name}
                    {p.collection ? <span className="ml-2 px-1.5 py-0.5 text-[10px] bg-gray-100 text-gray-500 rounded">{p.collection}</span> : null}
                  </td>
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
                </tr>
                {isOpen && (
                  <tr className="bg-gray-50/60">
                    <td colSpan={7} className="px-8 py-3">
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
              {rows.length === 0 && <tr><td colSpan={7} className="p-4 text-center text-gray-400">Veri yok.</td></tr>}
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
