import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MessageSquare, CheckCircle2, XCircle, Clock, Star, Trash2, Download, Store } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

// Trendyol Facette mağazasından 4-5★ yorumları toplu çekme paneli. Ürünleri barkodla
// Trendyol listelemesine eşleştirir, public storefront'tan yorumları çeker, product_reviews'a yazar.
function TrendyolReviewSync() {
  const [minRating, setMinRating] = useState(4);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const run = async (dryRun) => {
    setBusy(true); setResult(null);
    try {
      const { data } = await axios.post(
        `${API}/integrations/trendyol/reviews/sync-all`,
        { min_rating: Number(minRating), limit: 0, dry_run: dryRun },
        { headers: authHeaders(), timeout: 600000 },
      );
      setResult(data);
      toast.success(dryRun ? "Önizleme tamamlandı" : `${data?.total_inserted ?? 0} yorum eklendi`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Senkron başarısız");
    } finally { setBusy(false); }
  };

  return (
    <div className="bg-white border rounded-xl p-4" data-testid="trendyol-review-sync">
      <div className="flex items-center gap-2 mb-1">
        <Store size={18} className="text-orange-500" />
        <h2 className="text-sm font-bold uppercase tracking-wider">Trendyol Yorumları (Facette Mağazası)</h2>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        Site ürünlerini barkodla Trendyol listelemene eşleştirir ve <b>{minRating}★ ve üzeri</b> yorumları çeker.
        Yorumlar ürün sayfasında müşteri yorumlarıyla birlikte görünür. Uzun sürebilir.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm flex items-center gap-2">
          Alt yıldız:
          <select value={minRating} onChange={(e) => setMinRating(e.target.value)}
            className="border border-gray-300 rounded px-2 py-1 text-sm">
            <option value={4}>4 ve 5 yıldız</option>
            <option value={5}>Sadece 5 yıldız</option>
            <option value={3}>3, 4 ve 5 yıldız</option>
          </select>
        </label>
        <button onClick={() => run(true)} disabled={busy}
          className="inline-flex items-center gap-1.5 px-3 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50">
          Önizle (yazmadan say)
        </button>
        <button onClick={() => run(false)} disabled={busy}
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-orange-600 text-white rounded-lg text-sm hover:bg-orange-700 disabled:opacity-50">
          <Download size={14} className={busy ? "animate-pulse" : ""} /> {busy ? "Çekiliyor…" : "Yorumları Çek"}
        </button>
      </div>
      {result && (
        <div className="mt-3 text-xs bg-gray-50 border rounded-lg p-3 grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div><span className="text-gray-500">Trendyol ürün:</span> <b>{result.trendyol_products_indexed ?? "—"}</b></div>
          <div><span className="text-gray-500">Eşleşen ürün:</span> <b>{result.matched_products ?? "—"}</b></div>
          <div><span className="text-gray-500">Eşleşmeyen:</span> <b>{result.unmatched_products ?? "—"}</b></div>
          <div><span className="text-gray-500">Çekilen yorum:</span> <b>{result.total_fetched ?? "—"}</b></div>
          <div><span className="text-gray-500">Eklenen:</span> <b className="text-emerald-600">{result.total_inserted ?? "—"}</b></div>
          <div><span className="text-gray-500">Zaten var:</span> <b>{result.skipped_existing ?? "—"}</b></div>
          <div><span className="text-gray-500">Düşük puan:</span> <b>{result.skipped_low_rating ?? "—"}</b></div>
          <div><span className="text-gray-500">Mod:</span> <b>{result.dry_run ? "önizleme" : "gerçek"}</b></div>
          {Array.isArray(result.errors) && result.errors.length > 0 && (
            <div className="col-span-full text-red-600">Hatalar: {result.errors.length} (ilk: {JSON.stringify(result.errors[0])?.slice(0, 120)})</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ProductReviews() {
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState("pending");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/reviews`, { headers: authHeaders(), params: { status, limit: 100 } });
      setItems(data.items || []);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  const moderate = async (rid, newStatus) => {
    try {
      await axios.put(`${API}/admin/reviews/${rid}`, { status: newStatus }, { headers: authHeaders() });
      toast.success(newStatus === "approved" ? "Onaylandı" : "Reddedildi");
      load();
    } catch (_) { toast.error("Hata"); }
  };

  const del = async (rid) => {
    if (!await window.appConfirm("Yorum silinsin mi?")) return;
    await axios.delete(`${API}/admin/reviews/${rid}`, { headers: authHeaders() });
    toast.success("Silindi"); load();
  };

  return (
    <div className="space-y-5" data-testid="reviews-page">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2"><MessageSquare /> Ürün Yorumları</h1>
        <p className="text-sm text-gray-500 mt-1">Müşteri yorumlarını moderasyondan geçirin, Trendyol yorumlarını çekin.</p>
      </div>

      <TrendyolReviewSync />

      <div className="flex gap-2">
        {[
          ["pending", "Beklemede", Clock, "bg-amber-500"],
          ["approved", "Onaylı", CheckCircle2, "bg-emerald-500"],
          ["rejected", "Reddedildi", XCircle, "bg-red-500"],
        ].map(([k, lbl, Icon, color]) => (
          <button key={k} onClick={() => setStatus(k)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm ${status === k ? `${color} text-white` : "bg-white border text-gray-700"}`}
            data-testid={`reviews-tab-${k}`}>
            <Icon size={14} /> {lbl}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {loading ? <div className="text-center text-gray-400 py-8">Yükleniyor…</div>
          : items.length === 0 ? <div className="text-center text-gray-400 py-8 bg-white border rounded-xl">Bu durumda yorum yok.</div>
          : items.map((r) => (
            <div key={r.id} className="bg-white border rounded-xl p-4 flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-500 text-white flex items-center justify-center font-bold">
                  {r.user_name?.[0]?.toUpperCase() || "?"}
                </div>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div>
                    <div className="font-semibold">{r.user_name}</div>
                    <div className="text-xs text-gray-500">Ürün: <span className="text-gray-800">{r.product_name}</span> · {new Date(r.created_at).toLocaleDateString("tr-TR")}</div>
                  </div>
                  <div className="flex gap-0.5">
                    {[1,2,3,4,5].map((n) => (
                      <Star key={n} size={14} className={n <= r.rating ? "fill-yellow-400 text-yellow-400" : "text-gray-300"} />
                    ))}
                  </div>
                </div>
                {r.title && <div className="font-medium mt-2">{r.title}</div>}
                <div className="text-sm text-gray-700 mt-1 whitespace-pre-wrap">{r.comment}</div>
                {r.admin_reply && <div className="mt-2 p-2 bg-blue-50 text-blue-900 text-xs rounded"><strong>Cevabımız:</strong> {r.admin_reply}</div>}
                <div className="flex gap-2 mt-3">
                  {status !== "approved" && (
                    <button onClick={() => moderate(r.id, "approved")} data-testid={`approve-${r.id}`}
                      className="text-xs px-3 py-1 bg-emerald-100 text-emerald-800 border border-emerald-200 rounded hover:bg-emerald-200">Onayla</button>
                  )}
                  {status !== "rejected" && (
                    <button onClick={() => moderate(r.id, "rejected")}
                      className="text-xs px-3 py-1 bg-red-100 text-red-800 border border-red-200 rounded hover:bg-red-200">Reddet</button>
                  )}
                  <button onClick={() => del(r.id)} className="text-xs px-3 py-1 text-gray-600 hover:bg-gray-100 rounded ml-auto inline-flex items-center gap-1">
                    <Trash2 size={12} /> Sil
                  </button>
                </div>
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
