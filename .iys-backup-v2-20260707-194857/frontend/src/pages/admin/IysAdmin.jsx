/**
 * IysAdmin.jsx — İYS (İleti Yönetim Sistemi) yönetim paneli
 * Endpoints: /api/admin/iys/{status, query, register, query-batch}
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Cable, ShieldCheck, Search, Send, AlertCircle, CheckCircle2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

export default function IysAdmin() {
  const [status, setStatus] = useState(null);
  const [q, setQ] = useState({ recipient: "", recipient_type: "BIREYSEL", message_type: "EPOSTA" });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    axios.get(`${API}/admin/iys/status`, auth())
      .then((r) => setStatus(r.data))
      .catch(() => toast.error("Status alınamadı"));
  }, []);

  const doQuery = async () => {
    if (!q.recipient) { toast.error("Alıcı boş"); return; }
    setLoading(true);
    try {
      const r = await axios.post(`${API}/admin/iys/query`, q, auth());
      setResult(r.data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Sorgu hatası"); }
    finally { setLoading(false); }
  };

  const doRegister = async (consent_status) => {
    if (!q.recipient) { toast.error("Alıcı boş"); return; }
    try {
      await axios.post(`${API}/admin/iys/register`, { ...q, status: consent_status, source: "ADMIN_PANEL" }, auth());
      toast.success(`${consent_status} kaydedildi`);
      doQuery();
    } catch (e) { toast.error(e?.response?.data?.detail || "Kayıt hatası"); }
  };

  return (
    <div data-testid="iys-page" className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-light text-gray-900 flex items-center gap-2">
          <Cable className="w-6 h-6" /> İYS — İleti Yönetim Sistemi
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          B2C ticari ileti gönderimi öncesi yasal izin kontrolü (Türkiye zorunluluğu).
          Credential'ları <strong>Secrets Vault</strong>'a ekleyin: <code>IYS_API_USERNAME</code>, <code>IYS_API_PASSWORD</code>, <code>IYS_BRAND_CODE</code>.
        </p>
      </div>

      <div className={`border rounded-lg p-4 ${status?.configured ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"}`}>
        <div className="flex items-center gap-2 text-sm">
          {status?.configured ? <CheckCircle2 className="w-5 h-5 text-emerald-700" /> : <AlertCircle className="w-5 h-5 text-amber-700" />}
          <span className="font-medium">{status?.configured ? "Yapılandırılmış" : "Eksik yapılandırma"}</span>
          {status && <span className="text-gray-600">· Brand: <code>{status.brand_code}</code> · API: <code>{status.base_url}</code></span>}
        </div>
        {status && status.token_valid_seconds > 0 && (
          <p className="text-xs text-gray-500 mt-1">Token geçerli: {status.token_valid_seconds} saniye</p>
        )}
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
        <h3 className="font-medium text-gray-900 flex items-center gap-2"><Search className="w-4 h-4" /> İzin Sorgula / Yönet</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            type="text" value={q.recipient}
            onChange={(e) => setQ({ ...q, recipient: e.target.value })}
            placeholder="+905435955290 veya kullanici@mail.com"
            className="border rounded px-3 py-2 text-sm" data-testid="iys-recipient" />
          <select value={q.recipient_type} onChange={(e) => setQ({ ...q, recipient_type: e.target.value })} className="border rounded px-3 py-2 text-sm">
            <option value="BIREYSEL">BIREYSEL</option>
            <option value="TACIR">TACIR</option>
          </select>
          <select value={q.message_type} onChange={(e) => setQ({ ...q, message_type: e.target.value })} className="border rounded px-3 py-2 text-sm">
            <option value="EPOSTA">E-POSTA</option>
            <option value="MESAJ">SMS / MESAJ</option>
            <option value="ARAMA">ARAMA</option>
          </select>
        </div>
        <div className="flex gap-2">
          <button onClick={doQuery} disabled={loading} className="px-4 py-2 bg-gray-900 text-white rounded text-sm hover:bg-gray-800" data-testid="iys-query-btn">
            {loading ? "..." : "Sorgula"}
          </button>
          <button onClick={() => doRegister("ONAY")} className="px-4 py-2 bg-emerald-700 text-white rounded text-sm hover:bg-emerald-800">
            İzin Ekle (ONAY)
          </button>
          <button onClick={() => doRegister("RET")} className="px-4 py-2 bg-red-700 text-white rounded text-sm hover:bg-red-800">
            İzin İptal (RET)
          </button>
        </div>

        {result && (
          <div data-testid="iys-result" className={`mt-3 border rounded p-3 text-sm ${result.is_compliant ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"}`}>
            <div className="flex items-center gap-2">
              {result.is_compliant
                ? <><ShieldCheck className="w-4 h-4 text-emerald-700" /><strong>İzin VAR (ONAY)</strong></>
                : <><AlertCircle className="w-4 h-4 text-red-700" /><strong>İzin yok / bilinmiyor</strong></>}
            </div>
            <pre className="mt-2 text-xs text-gray-600 whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
          </div>
        )}
      </div>

      <div className="text-xs text-gray-500 bg-blue-50 border border-blue-200 rounded p-3">
        💡 <strong>İzin akışı:</strong> Müşteri kaydı sırasında "Tanıtım e-postası kabul ediyorum" işaretlerse otomatik ONAY kaydı eklenir. Pazarlama kampanyalarından önce toplu sorgu (<code>/api/admin/iys/query-batch</code>) ile sadece izinli alıcılara gönderim yapılır.
      </div>
    </div>
  );
}
