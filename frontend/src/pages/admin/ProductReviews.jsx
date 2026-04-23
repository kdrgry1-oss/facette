import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { MessageSquare, CheckCircle2, XCircle, Clock, Star, Trash2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

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
        <p className="text-sm text-gray-500 mt-1">Müşteri yorumlarını moderasyondan geçirin.</p>
      </div>

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
