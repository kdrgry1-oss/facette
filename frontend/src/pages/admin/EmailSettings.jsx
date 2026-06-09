import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Mail, Save, Send, Lock } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function EmailSettings() {
  const [cfg, setCfg] = useState({
    enabled: true,
    host: "smtp.zoho.com",
    port: 465,
    secure: "ssl",
    username: "",
    from_name: "FACETTE",
  });
  const [password, setPassword] = useState("");
  const [passwordSet, setPasswordSet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  const auth = () => ({ headers: { Authorization: `Bearer ${localStorage.getItem("token")}` } });

  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get(`${API}/settings/email-smtp`, auth());
        const d = res.data || {};
        setCfg({
          enabled: d.enabled !== false,
          host: d.host || "smtp.zoho.com",
          port: d.port || 465,
          secure: d.secure || "ssl",
          username: d.username || "",
          from_name: d.from_name || "FACETTE",
        });
        setPasswordSet(!!d.password_set);
      } catch (e) {
        toast.error("Ayarlar yüklenemedi");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const save = async () => {
    if (!cfg.username.trim()) { toast.error("E-posta adresi gerekli"); return; }
    if (!passwordSet && !password.trim()) { toast.error("Şifre gerekli (Zoho hesap/uygulama şifresi)"); return; }
    try {
      setSaving(true);
      const payload = { ...cfg, port: Number(cfg.port) || 465 };
      if (password.trim()) payload.password = password.trim();
      await axios.post(`${API}/settings/email-smtp`, payload, auth());
      toast.success("E-posta ayarları kaydedildi");
      if (password.trim()) { setPasswordSet(true); setPassword(""); }
    } catch (e) {
      toast.error(e.response?.data?.detail || "Kaydedilemedi");
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    if (!testTo.trim()) { toast.error("Test için alıcı e-posta girin"); return; }
    try {
      setTesting(true);
      await axios.post(`${API}/settings/email-smtp/test`, { to: testTo.trim() }, auth());
      toast.success("Test e-postası gönderildi — gelen kutunu kontrol et");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Test gönderilemedi");
    } finally {
      setTesting(false);
    }
  };

  const field = "w-full border rounded-lg px-3 py-2 text-sm focus:border-stone-900 outline-none";
  const lbl = "block text-[11px] font-bold text-gray-500 uppercase mb-1";

  return (
    <div data-testid="admin-email-settings" className="max-w-2xl p-4 md:p-6">
      <div className="flex items-start justify-between mb-2 gap-4">
        <div className="flex items-center gap-2">
          <Mail size={22} className="text-gray-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">E-posta (SMTP / Zoho)</h1>
            <p className="text-sm text-gray-500 mt-1">Tüm bildirim ve toplu e-postalar bu hesaptan gönderilir.</p>
          </div>
        </div>
        <button onClick={save} disabled={saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-semibold hover:bg-gray-800 disabled:opacity-50 shrink-0">
          <Save size={16} /> {saving ? "Kaydediliyor…" : "Kaydet"}
        </button>
      </div>

      {loading ? (
        <div className="p-10 text-center text-gray-400">Yükleniyor…</div>
      ) : (
        <div className="space-y-4">
          <div className="bg-white border rounded-xl p-5 shadow-sm space-y-4">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={cfg.enabled} onChange={(e) => setCfg({ ...cfg, enabled: e.target.checked })} className="accent-black" />
              E-posta gönderimi aktif
            </label>

            <div>
              <label className={lbl}>E-posta Adresi (kullanıcı adı)</label>
              <input className={field} placeholder="info@facette.com.tr" value={cfg.username}
                onChange={(e) => setCfg({ ...cfg, username: e.target.value.trim() })} autoComplete="off" />
            </div>

            <div>
              <label className={lbl}>Şifre {passwordSet && <span className="text-green-600 normal-case font-normal">· kayıtlı (değiştirmek için yeni şifre gir)</span>}</label>
              <div className="relative">
                <Lock size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input type="password" className={`${field} pl-9`} placeholder={passwordSet ? "••••••• (değiştirmek için yaz)" : "Zoho hesap / uygulama şifresi"}
                  value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
              </div>
              <p className="text-[11px] text-gray-400 mt-1">Zoho'da 2 adımlı doğrulama açıksa normal şifre değil <b>uygulamaya özel şifre</b> gerekir.</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className={lbl}>SMTP Sunucu</label>
                <input className={field} value={cfg.host} onChange={(e) => setCfg({ ...cfg, host: e.target.value.trim() })} placeholder="smtp.zoho.com" />
              </div>
              <div>
                <label className={lbl}>Port</label>
                <input type="number" className={field} value={cfg.port} onChange={(e) => setCfg({ ...cfg, port: e.target.value })} placeholder="465" />
              </div>
              <div>
                <label className={lbl}>Güvenlik</label>
                <select className={field} value={cfg.secure} onChange={(e) => setCfg({ ...cfg, secure: e.target.value })}>
                  <option value="ssl">SSL (port 465)</option>
                  <option value="tls">STARTTLS (port 587)</option>
                </select>
              </div>
              <div>
                <label className={lbl}>Gönderen Adı</label>
                <input className={field} value={cfg.from_name} onChange={(e) => setCfg({ ...cfg, from_name: e.target.value })} placeholder="FACETTE" />
              </div>
            </div>
            <p className="text-[11px] text-gray-400">
              Zoho bölgen Avrupa ise sunucu <code>smtp.zoho.eu</code> olabilir. Gönderen adresi, giriş yaptığın Zoho hesabıyla aynı olmalıdır.
            </p>
          </div>

          <div className="bg-gray-50 border rounded-xl p-5">
            <div className="text-sm font-medium mb-2">Test E-postası Gönder</div>
            <div className="flex flex-wrap items-center gap-2">
              <input className={`${field} flex-1 min-w-[220px]`} placeholder="ornek@mail.com" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
              <button onClick={sendTest} disabled={testing}
                className="inline-flex items-center gap-2 px-4 py-2 border rounded-lg text-sm hover:bg-gray-100 disabled:opacity-50">
                <Send size={15} /> {testing ? "Gönderiliyor…" : "Test Gönder"}
              </button>
            </div>
            <p className="text-[11px] text-gray-400 mt-2">Önce kaydet, sonra test et (test kayıtlı ayarları kullanır).</p>
          </div>
        </div>
      )}
    </div>
  );
}
