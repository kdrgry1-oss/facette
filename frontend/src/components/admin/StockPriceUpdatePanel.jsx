import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { TrendingUp, RefreshCw, Clock } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

/**
 * Pazaryeri Stok / Fiyat Güncelleme Paneli.
 * Tüm pazaryeri sekmelerinde görünür. Backend stok/fiyat gönderimi yalnız
 * Trendyol için mevcut olduğundan, diğer pazaryerlerinde panel "backend
 * entegrasyonu gerekiyor" şeffaf durumunda (buton pasif) gösterilir.
 * Yalnız stok adedi ve fiyat gönderilir — ürün açıklaması/görseli değişmez.
 */
const SUPPORTED = ["trendyol"];

export default function StockPriceUpdatePanel({ marketplace, auth }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const mp = (marketplace || "").toUpperCase();
  const supported = SUPPORTED.includes(marketplace);

  const syncAll = async () => {
    if (!window.confirm(`Tüm aktif ürünlerin güncel stok ve fiyatı ${mp}'a gönderilecek. Devam edilsin mi?`)) return;
    setLoading(true);
    setResult(null);
    const t = toast.loading(`Stok/fiyat ${mp}'a gönderiliyor...`);
    try {
      const r = await axios.post(`${API}/integrations/${marketplace}/products/inventory-sync`, {}, auth);
      setResult(r.data);
      toast.success(r.data?.message || "Stok/fiyat gönderildi", { id: t });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Stok/fiyat gönderilemedi", { id: t });
    } finally {
      setLoading(false);
    }
  };

  if (!supported) {
    return (
      <div className="mb-4 border border-gray-200 bg-gray-50 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-1">
          <Clock size={16} className="text-gray-400" />
          <div className="font-bold text-gray-600 text-sm">Stok / Fiyat Güncelle — {mp}</div>
        </div>
        <p className="text-xs text-gray-500">
          {mp} için stok/fiyat güncelleme backend entegrasyonu henüz eklenmedi
          (şu an yalnız Trendyol aktif). Bu pazaryerinin ürün/stok API'si bağlandığında
          bu alan otomatik aktifleşecek.
        </p>
      </div>
    );
  }

  return (
    <div className="mb-4 border border-emerald-200 bg-emerald-50/60 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-1">
        <TrendingUp size={16} className="text-emerald-700" />
        <div className="font-bold text-emerald-900 text-sm">Stok / Fiyat Güncelle — {mp}</div>
      </div>
      <p className="text-xs text-emerald-800/80 mb-3">
        Tüm aktif ürünlerin güncel <b>stok adedi ve fiyatını</b> {mp}'a gönderir (barkod eşleşmesiyle).
        Ürün açıklaması/görseli değişmez — yalnızca stok ve fiyat güncellenir.
      </p>
      <button
        onClick={syncAll}
        disabled={loading}
        className="inline-flex items-center gap-2 bg-emerald-700 text-white text-sm px-4 py-2 rounded-lg hover:bg-emerald-800 disabled:opacity-50"
      >
        <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        {loading ? "Gönderiliyor..." : "Tüm Stok + Fiyatı Gönder"}
      </button>
      {result && (
        <div className="mt-3 text-xs text-emerald-900 bg-white border border-emerald-200 rounded-lg p-2">
          {result.message || (result.success ? "Gönderildi" : JSON.stringify(result))}
          {result.batch_id && <span className="ml-2 font-mono text-gray-500">Batch: {result.batch_id}</span>}
          {typeof result.updated === "number" && <span className="ml-2 text-gray-500">({result.updated} ürün)</span>}
        </div>
      )}
    </div>
  );
}
