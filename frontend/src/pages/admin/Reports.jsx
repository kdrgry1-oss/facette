import { useState, useEffect } from "react";
import { useLocation, Link } from "react-router-dom";
import axios from "axios";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend, CartesianGrid } from "recharts";
import { TrendingUp, Package, Users, Truck, CreditCard, RefreshCw } from "lucide-react";

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
  const [data, setData] = useState(null);
  const [paymentData, setPayData] = useState([]);

  const load = async () => {
    const [s, p] = await Promise.all([
      axios.get(`${API}/admin/reports/sales`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", group_by: groupBy } }),
      axios.get(`${API}/admin/reports/payments`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } }),
    ]);
    setData(s.data);
    setPayData(p.data.items || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [groupBy]);

  return (
    <div className="space-y-5" data-testid="sales-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp /> Satış Raporları</h1>
          <p className="text-sm text-gray-500 mt-1">Tarih aralığına göre satış performansı.</p>
        </div>
        <div className="flex gap-2 items-center">
          <select value={groupBy} onChange={(e) => setGroupBy(e.target.value)} className="px-3 py-1.5 border rounded text-sm">
            <option value="day">Günlük</option>
            <option value="week">Haftalık</option>
            <option value="month">Aylık</option>
          </select>
          <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-3">
        {[
          { lbl: "Sipariş", val: data?.totals?.orders ?? 0, c: "from-slate-900 to-slate-700" },
          { lbl: "Ciro", val: `₺${(data?.totals?.revenue ?? 0).toLocaleString("tr-TR")}`, c: "from-emerald-600 to-emerald-500" },
          { lbl: "Ortalama Sepet", val: `₺${(data?.totals?.aov ?? 0).toLocaleString("tr-TR")}`, c: "from-blue-600 to-blue-500" },
        ].map((k) => (
          <div key={k.lbl} className={`bg-gradient-to-br ${k.c} text-white rounded-xl p-5`}>
            <div className="text-xs uppercase opacity-80">{k.lbl}</div>
            <div className="text-3xl font-bold mt-1">{k.val}</div>
          </div>
        ))}
      </div>

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

  const load = async () => {
    const [t, c] = await Promise.all([
      axios.get(`${API}/admin/reports/products/top`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59", limit: 20 } }),
      axios.get(`${API}/admin/reports/categories`, { headers: authHeaders(), params: { start_date: from, end_date: to + "T23:59:59" } }),
    ]);
    setTop(t.data.items || []);
    setCats(c.data.items || []);
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  return (
    <div className="space-y-5" data-testid="products-report-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Ürün Raporları</h1>
          <p className="text-sm text-gray-500 mt-1">En çok satan ürünler ve kategoriler.</p>
        </div>
        <DateBar from={from} setFrom={setFrom} to={to} setTo={setTo} onRefresh={load} />
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
      <h1 className="text-2xl font-bold flex items-center gap-2"><Package /> Stok Raporu</h1>

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
      <h1 className="text-2xl font-bold flex items-center gap-2"><Users /> Üye Raporu</h1>

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
