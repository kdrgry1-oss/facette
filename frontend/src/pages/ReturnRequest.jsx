import { useState, useEffect } from "react";
import { useParams, Navigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { RotateCcw, CheckCircle2, AlertTriangle } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MS_14D = 14 * 24 * 3600 * 1000;

export default function ReturnRequest() {
  const { orderNumber } = useParams();
  const token = localStorage.getItem("token");
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState({});
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [ret, setRet] = useState(null); // oluşturulan/var olan iade

  const auth = token ? { headers: { Authorization: `Bearer ${token}` } } : {};

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const o = await axios.get(`${API}/orders/by-number/${orderNumber}`);
        setOrder(o.data);
        // varsa mevcut iade
        try {
          const r = await axios.get(`${API}/orders/${o.data.id}/return`, auth);
          if (r.data?.return) setRet(r.data.return);
        } catch (_) { /* iade yok */ }
      } catch (e) {
        // sipariş yok
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line
  }, [orderNumber, token]);

  if (!token) return <Navigate to="/giris" replace />;

  if (loading) return <div className="max-w-xl mx-auto px-4 py-20 text-center text-gray-400">Yükleniyor…</div>;

  if (!order) {
    return (
      <div className="max-w-xl mx-auto px-4 py-20 text-center">
        <h1 className="text-xl font-medium mb-2">Sipariş bulunamadı</h1>
        <p className="text-sm text-gray-500">“{orderNumber}” numaralı sipariş bulunamadı.</p>
      </div>
    );
  }

  const items = order.items || [];
  const deliveredAt = order.delivered_at ? new Date(order.delivered_at) : null;
  const within14 = deliveredAt ? (Date.now() - deliveredAt.getTime()) <= MS_14D : false;
  const deadline = deliveredAt ? new Date(deliveredAt.getTime() + MS_14D) : null;

  const toggle = (i) => setSelected((s) => ({ ...s, [i]: !s[i] }));

  const submit = async () => {
    const idxs = Object.keys(selected).filter((k) => selected[k]).map(Number);
    try {
      setSubmitting(true);
      const res = await axios.post(
        `${API}/orders/${order.id}/return-request`,
        { items: idxs, reason },
        auth
      );
      if (res.data?.return) {
        setRet(res.data.return);
        toast.success("İade talebiniz oluşturuldu");
      }
    } catch (e) {
      toast.error(e.response?.data?.detail || "İade talebi oluşturulamadı");
    } finally {
      setSubmitting(false);
    }
  };

  // --- Oluşturulan / mevcut iade görünümü ---
  if (ret) {
    const vu = ret.valid_until ? new Date(ret.valid_until).toLocaleString("tr-TR") : "";
    return (
      <div className="max-w-xl mx-auto px-4 py-10 md:py-16">
        <div className="flex items-center gap-2 mb-6">
          <CheckCircle2 className="text-emerald-600" size={22} />
          <h1 className="text-2xl font-medium tracking-wide">İade Talebiniz Hazır</h1>
        </div>
        <div className="border border-gray-200 p-5 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-gray-400 mb-1">İade Kargo Kodu</p>
            <p className="text-xl font-mono font-semibold">{ret.return_code}</p>
            <p className="text-xs text-gray-500 mt-1">{ret.cargo_provider_name} · Son geçerlilik: <b>{vu}</b> (3 gün)</p>
          </div>
          {ret.barcode_data_url && (
            <div className="bg-white border border-gray-100 p-4 flex justify-center">
              <img src={ret.barcode_data_url} alt={ret.return_code} className="h-24 object-contain" />
            </div>
          )}
          <p className="text-sm text-gray-600">
            Ürünü en yakın <b>DHL / MNG</b> şubesine bu <b>kodu</b> veya <b>barkodu</b> göstererek teslim edebilirsiniz.
            İade bilgisi hesabınızdaki siparişte de görünür.
          </p>
          {!ret.mng_ok && (
            <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
              Kargo etiketi hazırlanıyor; şube tarafında kod tanınmazsa ekibimiz sizinle iletişime geçecektir.
            </p>
          )}
        </div>
        <a href="/hesabim" className="inline-block text-xs uppercase tracking-[0.15em] mt-6 underline underline-offset-4">Hesabıma Dön</a>
      </div>
    );
  }

  // --- İade formu ---
  return (
    <div className="max-w-xl mx-auto px-4 py-10 md:py-16">
      <div className="flex items-center gap-2 mb-1">
        <RotateCcw size={18} className="text-gray-500" />
        <p className="text-xs uppercase tracking-[0.2em] text-gray-400">İade Talebi</p>
      </div>
      <h1 className="text-2xl font-medium tracking-wide mb-6">Sipariş {order.order_number}</h1>

      {!deliveredAt ? (
        <div className="border border-amber-200 bg-amber-50 p-4 flex items-start gap-2">
          <AlertTriangle size={18} className="text-amber-600 mt-0.5" />
          <p className="text-sm text-amber-900">Bu sipariş henüz teslim edilmedi. İade, teslimattan sonra başlatılabilir.</p>
        </div>
      ) : !within14 ? (
        <div className="border border-red-200 bg-red-50 p-4 flex items-start gap-2">
          <AlertTriangle size={18} className="text-red-600 mt-0.5" />
          <p className="text-sm text-red-900">İade süresi (teslimden itibaren 14 gün) dolmuştur.</p>
        </div>
      ) : (
        <>
          <p className="text-xs text-gray-500 mb-4">
            İade etmek istediğiniz ürünleri seçin. Son iade tarihi: <b>{deadline.toLocaleDateString("tr-TR")}</b>
          </p>
          <div className="border border-gray-200 divide-y mb-5">
            {items.map((it, i) => (
              <label key={i} className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50">
                <input type="checkbox" checked={!!selected[i]} onChange={() => toggle(i)} className="rounded" />
                <div className="w-12 h-14 bg-gray-50 border border-gray-100 overflow-hidden shrink-0">
                  {it.image ? <img src={it.image} alt="" className="w-full h-full object-contain" /> : null}
                </div>
                <div className="flex-1 min-w-0 text-sm">
                  <p className="truncate">{it.name || it.product_name || "Ürün"}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {it.size ? `Beden: ${it.size} · ` : ""}{it.color ? `Renk: ${it.color} · ` : ""}Adet: {it.quantity || 1}
                  </p>
                </div>
              </label>
            ))}
          </div>

          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="İade nedeni (opsiyonel)"
            rows={3}
            className="w-full border border-gray-200 p-3 text-sm resize-none focus:outline-none focus:border-gray-500 mb-4"
          />

          <button
            onClick={submit}
            disabled={submitting}
            className="w-full bg-black text-white py-3 text-xs uppercase tracking-[0.2em] hover:bg-gray-800 transition-colors disabled:opacity-40"
          >
            {submitting ? "Oluşturuluyor…" : "İade Talebi Oluştur"}
          </button>
          <p className="text-[11px] text-gray-400 mt-3">
            Hiç ürün seçmezseniz siparişteki tüm ürünler için iade oluşturulur. Onay sonrası 3 gün geçerli bir kargo kodu/barkodu verilir.
          </p>
        </>
      )}
    </div>
  );
}
