import { useState, useEffect } from "react";
import axios from "axios";
import { TrendingUp, Settings, RefreshCw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });
const tl = (v) => `₺${(Number(v) || 0).toLocaleString("tr-TR", { maximumFractionDigits: 0 })}`;

const PLAT = { site: "Site", trendyol: "Trendyol", hepsiburada: "Hepsiburada", temu: "Temu", manual: "Manuel" };
const plat = (p) => PLAT[p] || (p ? p[0].toUpperCase() + p.slice(1) : "—");

export default function ProfitabilityAnalysis() {
  const today = new Date();
  // Bugün dahil tam 30 takvim günü: bugün - 29 gün.
  const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const [from, setFrom] = useState(ymd(new Date(today.getTime() - 29 * 864e5)));
  const [to, setTo] = useState(ymd(today));
  const [source, setSource] = useState("all");
  const [data, setData] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [showCfg, setShowCfg] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = async (f = from, t = to) => {
    setLoading(true);
    try {
      const { data: d } = await axios.get(`${API}/admin/reports/profitability`, {
        headers: authHeaders(), params: { start_date: f, end_date: t + "T23:59:59", source },
      });
      setData(d);
      setCfg(d.config);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [source]);

  const setDatePreset = (kind) => {
    const tn = new Date();
    let f, tt;
    if (kind === "today") { f = tt = ymd(tn); }
    else if (kind === "yesterday") { const y = new Date(tn.getTime() - 864e5); f = tt = ymd(y); }
    else if (kind === "7") { f = ymd(new Date(tn.getTime() - 6 * 864e5)); tt = ymd(tn); }
    else if (kind === "30") { f = ymd(new Date(tn.getTime() - 29 * 864e5)); tt = ymd(tn); }
    else if (kind === "month") { f = ymd(new Date(tn.getFullYear(), tn.getMonth(), 1)); tt = ymd(tn); }
    setFrom(f); setTo(tt); load(f, tt);
  };

  const saveCfg = async () => {
    setSaving(true);
    try {
      await axios.put(`${API}/admin/reports/profitability-config`, cfg, { headers: authHeaders() });
      await load();
      setShowCfg(false);
    } finally { setSaving(false); }
  };

  const items = data?.items || [];
  const t = data?.totals || {};

  // Config düzenleyici — kanal bazlı oran/tutar alanı
  const chField = (group, ch, label) => (
    <label className="flex items-center justify-between gap-2 text-xs">
      <span className="text-gray-600">{label}</span>
      <input type="number" step="0.1" className="w-24 border rounded px-2 py-1 text-right"
        value={cfg?.[group]?.[ch] ?? 0}
        onChange={(e) => setCfg(c => ({ ...c, [group]: { ...c[group], [ch]: parseFloat(e.target.value) || 0 } }))} />
    </label>
  );

  return (
    <div className="space-y-5" data-testid="profitability-page">
      <div className="flex justify-between items-center flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><TrendingUp /> Kârlılık Analizi</h1>
          <p className="text-sm text-gray-500 mt-1">Kategori × pazaryeri bazında GERÇEK net kâr — tüm giderler düşülür.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select value={source} onChange={(e) => setSource(e.target.value)} className="px-3 py-1.5 border rounded text-sm">
            <option value="all">Tüm Kaynaklar</option>
            <option value="site">Site (Kendi)</option>
            <option value="trendyol">Trendyol</option>
            <option value="hepsiburada">Hepsiburada</option>
            <option value="temu">Temu</option>
          </select>
          <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="text-sm px-2 py-1.5 border rounded" />
          <span className="text-gray-400">→</span>
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="text-sm px-2 py-1.5 border rounded" />
          <button onClick={() => load()} className="px-3 py-1.5 bg-black text-white text-xs rounded inline-flex items-center gap-1"><RefreshCw size={12} /> Uygula</button>
          <button onClick={() => setShowCfg(v => !v)} className="px-3 py-1.5 border rounded text-xs inline-flex items-center gap-1"><Settings size={12} /> Gider Ayarları</button>
        </div>
      </div>
      <div className="flex flex-wrap gap-1 items-center">
        {[["today","Bugün"],["yesterday","Dün"],["7","Son 7"],["30","Son 30"],["month","Bu Ay"]].map(([k,l]) => (
          <button key={k} type="button" onClick={() => setDatePreset(k)} className="px-2 py-1 border rounded text-xs bg-white hover:bg-gray-100 transition-colors">{l}</button>
        ))}
      </div>

      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 text-sm text-blue-900">
        <span className="font-semibold">Bu raporda:</span> Her kategori/pazaryeri için <b>Net Ciro − Ürün Maliyeti (COGS) − Pazaryeri Komisyonu − Kargo − Hizmet Bedeli − Reklam Gideri − Ödenecek KDV − Kurumlar Vergisi = NET KÂR</b> ve marj %. Net ciro, ürün/kampanya/kupon/havale indirimleri bir kez düşülmüş tutardır. Komisyon/reklam/vergi oranları <b>Gider Ayarları</b>'ndan yönetilir. Maliyet, ürünlerin <b>alış fiyatından</b> gelir; girilmemişse satış fiyatının %'siyle tahmin edilir (ayarlanabilir).
      </div>

      {/* Gider ayarları editörü */}
      {showCfg && cfg && (
        <div className="bg-white rounded-xl border p-5 space-y-4">
          <h3 className="font-semibold">Gider Varsayımları</h3>
          <div className="grid md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <div className="text-xs font-bold uppercase text-gray-400">Komisyon %</div>
              {["trendyol", "hepsiburada", "temu", "site"].map(ch => chField("commission_pct", ch, plat(ch)))}
            </div>
            <div className="space-y-2">
              <div className="text-xs font-bold uppercase text-gray-400">Aylık Reklam Bütçesi (TL)</div>
              <div className="text-[10px] text-gray-400 -mt-1">Trendyol reklam verisi API'de olmadığından: aylık gir, rapor seçili tarih aralığına otomatik orantılar.</div>
              {["trendyol", "hepsiburada", "site"].map(ch => chField("ad_spend_monthly", ch, plat(ch)))}
            </div>
            <div className="space-y-2">
              <div className="text-xs font-bold uppercase text-gray-400">Hizmet Bedeli %</div>
              {["trendyol", "hepsiburada", "site"].map(ch => chField("service_fee_pct", ch, plat(ch)))}
            </div>
          </div>
          <div className="grid md:grid-cols-3 gap-6 pt-2 border-t">
            <label className="flex items-center justify-between gap-2 text-xs"><span className="text-gray-600">KDV %</span>
              <input type="number" step="0.1" className="w-24 border rounded px-2 py-1 text-right" value={cfg.vat_rate ?? 10}
                onChange={(e) => setCfg(c => ({ ...c, vat_rate: parseFloat(e.target.value) || 0 }))} /></label>
            <label className="flex items-center justify-between gap-2 text-xs"><span className="text-gray-600">Kurumlar Vergisi %</span>
              <input type="number" step="0.1" className="w-24 border rounded px-2 py-1 text-right" value={cfg.corporate_tax_pct ?? 25}
                onChange={(e) => setCfg(c => ({ ...c, corporate_tax_pct: parseFloat(e.target.value) || 0 }))} /></label>
            <label className="flex items-center justify-between gap-2 text-xs"><span className="text-gray-600">Maliyet tahmin oranı (bilinmiyorsa)</span>
              <input type="number" step="0.05" className="w-24 border rounded px-2 py-1 text-right" value={cfg.cog_fallback_ratio ?? 0.5}
                onChange={(e) => setCfg(c => ({ ...c, cog_fallback_ratio: parseFloat(e.target.value) || 0 }))} /></label>
          </div>
          <div className="flex justify-end">
            <button onClick={saveCfg} disabled={saving} className="px-4 py-2 bg-emerald-600 text-white text-sm rounded disabled:opacity-50">{saving ? "Kaydediliyor…" : "Kaydet & Yeniden Hesapla"}</button>
          </div>
        </div>
      )}

      {/* Özet kutuları */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-gradient-to-br from-slate-900 to-slate-700 text-white rounded-xl p-5"><div className="text-[11px] uppercase opacity-80">Net Ciro</div><div className="text-2xl font-bold mt-1">{tl(t.revenue)}</div><div className="text-[10px] opacity-70 mt-1">Brüt {tl(t.gross_revenue)} · İndirim {tl(t.discount)}</div></div>
        <div className="bg-gradient-to-br from-rose-600 to-rose-500 text-white rounded-xl p-5"><div className="text-[11px] uppercase opacity-80">Toplam Gider</div><div className="text-2xl font-bold mt-1">{tl((t.revenue || 0) - (t.net_profit || 0))}</div></div>
        <div className="bg-gradient-to-br from-emerald-600 to-emerald-500 text-white rounded-xl p-5"><div className="text-[11px] uppercase opacity-80">Net Kâr</div><div className="text-2xl font-bold mt-1">{tl(t.net_profit)}</div></div>
        <div className="bg-gradient-to-br from-blue-600 to-blue-500 text-white rounded-xl p-5"><div className="text-[11px] uppercase opacity-80">Net Marj</div><div className="text-2xl font-bold mt-1">%{t.margin_pct ?? 0}</div></div>
      </div>

      {/* Detay tablosu */}
      <div className="bg-white rounded-xl border overflow-hidden">
        <h3 className="font-semibold p-5 pb-3">Kategori × Pazaryeri Net Kâr {loading && <span className="text-xs text-gray-400">(yükleniyor…)</span>}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs whitespace-nowrap">
            <thead className="bg-gray-50 uppercase text-gray-500">
              <tr>
                <th className="text-left p-2.5">Kategori</th><th className="text-left p-2.5">Kanal</th>
                <th className="text-right p-2.5">Adet</th><th className="text-right p-2.5">Net Ciro</th>
                <th className="text-right p-2.5">COGS</th><th className="text-right p-2.5">Komisyon</th>
                <th className="text-right p-2.5">Kargo</th><th className="text-right p-2.5">Reklam</th>
                <th className="text-right p-2.5">Hizmet</th><th className="text-right p-2.5">KDV</th>
                <th className="text-right p-2.5">Kurumlar V.</th><th className="text-right p-2.5">Net Kâr</th>
                <th className="text-right p-2.5">Marj</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r, i) => (
                <tr key={i} className="border-t hover:bg-gray-50">
                  <td className="p-2.5 font-medium max-w-[160px] truncate" title={r.category}>{r.category}</td>
                  <td className="p-2.5">{plat(r.channel)}</td>
                  <td className="p-2.5 text-right">{r.qty}</td>
                  <td className="p-2.5 text-right">{tl(r.revenue)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.cogs)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.commission)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.cargo)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.ad_spend)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.service_fee)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.vat_payable)}</td>
                  <td className="p-2.5 text-right text-gray-500">{tl(r.corporate_tax)}</td>
                  <td className={`p-2.5 text-right font-bold ${r.net_profit < 0 ? "text-red-600" : "text-emerald-700"}`}>{tl(r.net_profit)}</td>
                  <td className={`p-2.5 text-right ${r.margin_pct < 0 ? "text-red-600" : ""}`}>%{r.margin_pct}</td>
                </tr>
              ))}
              {items.length === 0 && <tr><td colSpan={13} className="p-4 text-center text-gray-400">Veri yok.</td></tr>}
            </tbody>
            {items.length > 0 && (
              <tfoot className="bg-gray-50 font-bold border-t-2">
                <tr>
                  <td className="p-2.5" colSpan={2}>TOPLAM</td>
                  <td className="p-2.5 text-right">{t.qty}</td>
                  <td className="p-2.5 text-right">{tl(t.revenue)}</td>
                  <td className="p-2.5 text-right">{tl(t.cogs)}</td>
                  <td className="p-2.5 text-right">{tl(t.commission)}</td>
                  <td className="p-2.5 text-right">{tl(t.cargo)}</td>
                  <td className="p-2.5 text-right">{tl(t.ad_spend)}</td>
                  <td className="p-2.5 text-right">{tl(t.service_fee)}</td>
                  <td className="p-2.5 text-right">{tl(t.vat_payable)}</td>
                  <td className="p-2.5 text-right">{tl(t.corporate_tax)}</td>
                  <td className={`p-2.5 text-right ${t.net_profit < 0 ? "text-red-600" : "text-emerald-700"}`}>{tl(t.net_profit)}</td>
                  <td className="p-2.5 text-right">%{t.margin_pct}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      </div>
    </div>
  );
}
