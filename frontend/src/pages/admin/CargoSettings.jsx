/**
 * CargoSettings.jsx — Kargo Firması Ayarları sayfası.
 *
 * İki bölümden oluşur:
 *   1) DhlPollMonitor — DHL/MNG kargo takip senkronizasyonunun CANLI İZLEME paneli.
 *      Backend her 5 dk'da bir site siparişlerini MNG/DHL'den sorgular; bu panel
 *      o taramanın son durumunu (ne zaman çalıştı, kaç sipariş sorgulandı, kaçı
 *      güncellendi, hata var mı, ayar aktif mi) gösterir ve "Şimdi Çalıştır" ile
 *      elle tetiklenebilir.
 *        - GET  /api/orders/cargo/poll-health  → izleme verisi
 *        - POST /api/orders/cargo/poll-now     → taramayı hemen çalıştır
 *   2) ProviderSettings (kind="cargo") — kargo firması credential ayarları.
 *
 * Bağlantılı:
 *   - components/admin/ProviderSettings.jsx (provider credential UI)
 *   - backend/scheduler.py  (_dhl_cargo_poll_tick + db.settings.dhl_poll_health)
 *   - backend/routes/orders.py (poll-health / poll-now endpointleri)
 */
import { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Truck, RefreshCw, Play, CheckCircle2, AlertTriangle,
  PauseCircle, Clock, HelpCircle,
} from "lucide-react";
import ProviderSettings from "../../components/admin/ProviderSettings";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const authHeaders = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

/** ISO zamanı "3 dk önce" gibi göreli Türkçe metne çevirir. */
function relTime(iso) {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 0) return "az sonra";
  if (sec < 60) return `${sec} sn önce`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} dk önce`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} saat önce`;
  const d = Math.floor(hr / 24);
  return `${d} gün önce`;
}

function fmtClock(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "medium" });
}

/** Durum koduna göre rozet stili + Türkçe etiket + ikon. */
const STATUS_META = {
  ok:       { label: "Çalışıyor", cls: "bg-emerald-100 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  running:  { label: "Şu an taranıyor", cls: "bg-blue-100 text-blue-700 border-blue-200", Icon: RefreshCw },
  skipped:  { label: "Atlandı (ayar kapalı)", cls: "bg-amber-100 text-amber-700 border-amber-200", Icon: PauseCircle },
  error:    { label: "Hata", cls: "bg-red-100 text-red-700 border-red-200", Icon: AlertTriangle },
  unknown:  { label: "Henüz çalışmadı", cls: "bg-gray-100 text-gray-600 border-gray-200", Icon: HelpCircle },
};

function StatCard({ label, value, accent }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-4">
      <div className="text-[11px] uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-2xl font-bold mt-1 ${accent || "text-gray-900"}`}>{value}</div>
    </div>
  );
}

function DhlPollMonitor() {
  const [h, setH] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/orders/cargo/poll-health`, { headers: authHeaders() });
      setH(data || null);
    } catch {
      // sessiz geç — panel "yüklenemedi" gösterir
      setH((prev) => prev || { _failed: true });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000); // 30 sn'de bir tazele
    return () => clearInterval(t);
  }, [load]);

  const runNow = async () => {
    setRunning(true);
    try {
      await axios.post(`${API}/orders/cargo/poll-now`, {}, { headers: authHeaders() });
      toast.success("DHL/MNG kargo taraması çalıştırıldı.");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Tarama çalıştırılamadı.");
    } finally {
      setRunning(false);
    }
  };

  const status = h?.status || (h?._failed ? "error" : "unknown");
  const meta = STATUS_META[status] || STATUS_META.unknown;
  const Icon = meta.Icon;
  const interval = h?.interval_min || 5;

  return (
    <div className="bg-gradient-to-br from-slate-50 to-white border border-gray-200 rounded-2xl p-5 space-y-4">
      {/* Başlık + aksiyonlar */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2 text-gray-900">
            <Truck className="w-5 h-5 text-indigo-600" /> DHL / MNG Takip Senkron İzleme
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            Site siparişlerinin kargo durumu her <b>{interval} dk</b>'da bir DHL/MNG'den
            otomatik çekilir (ilk okutma → Kargoya Verildi, teslim → Teslim Edildi).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-gray-300 text-sm text-gray-700 hover:bg-gray-50"
            title="Paneli yenile"
          >
            <RefreshCw className="w-4 h-4" /> Yenile
          </button>
          <button
            onClick={runNow}
            disabled={running}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-60"
          >
            <Play className={`w-4 h-4 ${running ? "animate-pulse" : ""}`} />
            {running ? "Çalışıyor…" : "Şimdi Çalıştır"}
          </button>
        </div>
      </div>

      {/* Durum rozeti + son çalışma */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${meta.cls}`}>
          <Icon className={`w-4 h-4 ${status === "running" ? "animate-spin" : ""}`} /> {meta.label}
        </span>
        <span className="inline-flex items-center gap-1.5 text-sm text-gray-500">
          <Clock className="w-4 h-4" />
          Son çalışma: <b className="text-gray-700">{relTime(h?.last_finish_at)}</b>
          <span className="text-gray-400">({fmtClock(h?.last_finish_at)})</span>
        </span>
      </div>

      {/* Ayar kapalı / hata uyarısı */}
      {status === "skipped" && (
        <div className="flex items-start gap-2 text-sm bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-3">
          <PauseCircle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <b>Senkron atlanıyor.</b> {h?.skipped_reason || "MNG/DHL ayarı aktif değil."}
            {" "}Aşağıdaki kargo firması ayarlarından MNG/DHL'i aktif edip kullanıcı adını girin.
          </div>
        </div>
      )}
      {status === "error" && (
        <div className="flex items-start gap-2 text-sm bg-red-50 border border-red-200 text-red-800 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <b>Son taramada hata oluştu.</b>
            {h?.last_error ? <div className="font-mono text-xs mt-1 break-all">{h.last_error}</div> : null}
          </div>
        </div>
      )}

      {/* Sayaçlar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Sorgulanan sipariş" value={h?.processed ?? 0} />
        <StatCard label="Kargoya verilen" value={h?.shipped ?? 0} accent="text-indigo-600" />
        <StatCard label="Teslim edilen" value={h?.delivered ?? 0} accent="text-emerald-600" />
        <StatCard label="Hatalı sorgu" value={h?.errors ?? 0} accent={(h?.errors ?? 0) > 0 ? "text-red-600" : "text-gray-900"} />
      </div>

      {/* Ayar/süre özeti */}
      <div className="flex items-center gap-4 flex-wrap text-xs text-gray-500">
        <span>MNG/DHL ayarı: {h?.mng_active ? <b className="text-emerald-600">Aktif</b> : <b className="text-red-600">Kapalı</b>}</span>
        <span>Kullanıcı adı: {h?.mng_user_set ? <b className="text-emerald-600">Girilmiş</b> : <b className="text-red-600">Boş</b>}</span>
        {typeof h?.duration_ms === "number" && h?.duration_ms > 0 && (
          <span>Son tarama süresi: <b className="text-gray-700">{(h.duration_ms / 1000).toFixed(1)} sn</b></span>
        )}
      </div>

      {/* Geçmiş (son koşular) */}
      {Array.isArray(h?.history) && h.history.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer text-gray-600 hover:text-gray-900 select-none">
            Son taramalar ({h.history.length})
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs border-collapse">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-200">
                  <th className="py-1.5 pr-3 font-medium">Zaman</th>
                  <th className="py-1.5 pr-3 font-medium">Sonuç</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Sorgulanan</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Kargoya</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Teslim</th>
                  <th className="py-1.5 pr-3 font-medium text-right">Hata</th>
                  <th className="py-1.5 pr-3 font-medium">Not</th>
                </tr>
              </thead>
              <tbody>
                {h.history.map((r, i) => {
                  const m = STATUS_META[r.status] || STATUS_META.unknown;
                  return (
                    <tr key={i} className="border-b border-gray-100">
                      <td className="py-1.5 pr-3 whitespace-nowrap text-gray-600">{fmtClock(r.at)}</td>
                      <td className="py-1.5 pr-3"><span className={`px-2 py-0.5 rounded-full border ${m.cls}`}>{m.label}</span></td>
                      <td className="py-1.5 pr-3 text-right">{r.processed ?? 0}</td>
                      <td className="py-1.5 pr-3 text-right">{r.shipped ?? 0}</td>
                      <td className="py-1.5 pr-3 text-right">{r.delivered ?? 0}</td>
                      <td className={`py-1.5 pr-3 text-right ${(r.errors ?? 0) > 0 ? "text-red-600 font-medium" : ""}`}>{r.errors ?? 0}</td>
                      <td className="py-1.5 pr-3 text-gray-500 max-w-[220px] truncate" title={r.error || ""}>{r.error || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {loading && !h && <div className="text-sm text-gray-400">İzleme verisi yükleniyor…</div>}
    </div>
  );
}

export default function CargoSettings() {
  return (
    <div className="space-y-6">
      <DhlPollMonitor />
      <ProviderSettings
        kind="cargo"
        title="Kargo Firması Ayarları"
        subtitle="Çalışacağınız kargo firmalarını yapılandırın. Birden fazla firma için bilgi girilebilir, sistem aktif seçilen firmayı kullanır (sipariş kargo oluşturma, etiket basma vb.)."
      />
    </div>
  );
}
