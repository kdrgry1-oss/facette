/**
 * EmailMarketing.jsx — AWS SES tabanlı e-posta pazarlama paneli.
 * ================================================================
 * SES ayarları (Zoho'dan AYRI kanal — işlemsel maile dokunmaz) + rıza vermiş
 * bülten abonelerine toplu kampanya gönderimi + geçmiş. Alıcılar backend'de
 * yalnız active + consent olanlardan seçilir; her maile abonelikten-çık linki eklenir.
 */
import { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Mail, Send, Save, Users, RefreshCw, CheckCircle2, AlertTriangle,
  FileText, Eye, Copy, Trash2, X, Star } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const h = () => ({ Authorization: `Bearer ${localStorage.getItem("token")}` });

export default function EmailMarketing() {
  const [cfg, setCfg] = useState({ enabled: false, region: "", access_key: "", secret_key: "", from_email: "", from_name: "", configuration_set: "" });
  const [configured, setConfigured] = useState(false);
  const [aud, setAud] = useState({ total: 0, eligible: 0 });
  const [testTo, setTestTo] = useState("");
  const [camp, setCamp] = useState({ subject: "", html: "" });
  const [campaigns, setCampaigns] = useState([]);
  const [busy, setBusy] = useState("");
  const [templates, setTemplates] = useState([]);
  const [previewHtml, setPreviewHtml] = useState("");   // canlı önizleme (editörün altında)
  const [previewModal, setPreviewModal] = useState(null); // {html, subject} tam ekran modal

  const load = async () => {
    try {
      const [s, a, c, t] = await Promise.all([
        axios.get(`${API}/admin/email-marketing/settings`, { headers: h() }),
        axios.get(`${API}/admin/email-marketing/audience`, { headers: h() }),
        axios.get(`${API}/admin/email-marketing/campaigns`, { headers: h() }),
        axios.get(`${API}/admin/email-marketing/templates`, { headers: h() }),
      ]);
      setCfg((p) => ({ ...p, ...s.data }));
      setConfigured(!!s.data.configured);
      setAud(a.data || { total: 0, eligible: 0 });
      setCampaigns(c.data?.campaigns || []);
      setTemplates(t.data?.templates || []);
    } catch (e) { toast.error("Yüklenemedi"); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  // Canlı önizleme — Konu/HTML değişince debounce ile tam markalı görünümü çek.
  useEffect(() => {
    if (!camp.subject.trim() && !camp.html.trim()) { setPreviewHtml(""); return; }
    const t = setTimeout(async () => {
      try {
        const r = await axios.post(`${API}/admin/email-marketing/preview`,
          { subject: camp.subject, html: camp.html }, { headers: h() });
        setPreviewHtml(r.data?.html || "");
      } catch { /* önizleme sessiz geç */ }
    }, 500);
    return () => clearTimeout(t);
  }, [camp.subject, camp.html]);

  const useTemplate = (tpl) => {
    setCamp({ subject: tpl.subject || "", html: tpl.html || "" });
    toast.success(`"${tpl.name}" editöre yüklendi — düzenleyip önizleyebilirsin`);
    try { window.scrollTo({ top: document.getElementById("yeni-kampanya")?.offsetTop || 0, behavior: "smooth" }); } catch {}
  };

  const openPreview = async (tpl) => {
    try {
      const r = await axios.post(`${API}/admin/email-marketing/preview`,
        { subject: tpl.subject, html: tpl.html }, { headers: h() });
      setPreviewModal({ html: r.data?.html || "", subject: tpl.subject });
    } catch { toast.error("Önizleme alınamadı"); }
  };

  const saveAsTemplate = async () => {
    if (!camp.html.trim()) { toast.error("Önce içerik (HTML) girin"); return; }
    const name = window.prompt("Şablon adı:", camp.subject || "Yeni Şablon");
    if (!name || !name.trim()) return;
    const category = window.prompt("Kategori (opsiyonel):", "Genel") || "Genel";
    setBusy("savetpl");
    try {
      await axios.post(`${API}/admin/email-marketing/templates`,
        { name: name.trim(), subject: camp.subject, html: camp.html, category: category.trim() }, { headers: h() });
      toast.success("Şablon kaydedildi");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Kaydedilemedi"); }
    finally { setBusy(""); }
  };

  const deleteTemplate = async (tpl) => {
    if (!window.confirm(`"${tpl.name}" şablonu silinsin mi?`)) return;
    try {
      await axios.delete(`${API}/admin/email-marketing/templates/${tpl.id}`, { headers: h() });
      toast.success("Şablon silindi");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Silinemedi"); }
  };

  const saveCfg = async () => {
    setBusy("save");
    try {
      await axios.put(`${API}/admin/email-marketing/settings`, cfg, { headers: h() });
      toast.success("SES ayarları kaydedildi");
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Kaydedilemedi"); }
    finally { setBusy(""); }
  };

  const sendTest = async () => {
    if (!testTo.trim()) { toast.error("Test e-posta adresi girin"); return; }
    setBusy("test");
    try {
      const r = await axios.post(`${API}/admin/email-marketing/test`, { to: testTo.trim() }, { headers: h() });
      toast.success("Test maili gönderildi");
    } catch (e) { toast.error(e.response?.data?.detail || "Gönderilemedi"); }
    finally { setBusy(""); }
  };

  const sendCampaign = async () => {
    if (!camp.subject.trim() || !camp.html.trim()) { toast.error("Konu ve içerik zorunlu"); return; }
    if (!window.confirm(`${aud.eligible} rıza vermiş aboneye "${camp.subject}" kampanyası gönderilecek. Onaylıyor musun?`)) return;
    setBusy("campaign");
    try {
      const r = await axios.post(`${API}/admin/email-marketing/campaigns`, camp, { headers: h() });
      toast.success(`Kampanya başlatıldı — ${r.data?.eligible} aboneye gönderiliyor (arka planda)`);
      setCamp({ subject: "", html: "" });
      setTimeout(load, 1500);
    } catch (e) { toast.error(e.response?.data?.detail || "Başlatılamadı"); }
    finally { setBusy(""); }
  };

  const field = (label, key, type = "text", ph = "") => (
    <label className="block">
      <span className="text-xs font-medium text-gray-600">{label}</span>
      <input type={type} value={cfg[key] || ""} placeholder={ph}
        onChange={(e) => setCfg((p) => ({ ...p, [key]: e.target.value }))}
        className="mt-1 w-full border rounded-lg px-3 py-2 text-sm" />
    </label>
  );

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Mail size={22} /><h1 className="text-xl font-bold">E-posta Pazarlama (AWS SES)</h1>
      </div>

      {/* Kitle */}
      <div className="bg-white border rounded-xl p-4 flex items-center gap-4">
        <Users size={20} className="text-gray-500" />
        <div className="flex-1">
          <p className="text-sm font-semibold">{aud.eligible} rıza vermiş aktif abone</p>
          <p className="text-xs text-gray-500">Toplam {aud.total} kayıt · yalnız KVKK/İYS onaylı ve aktif olanlara gönderilir</p>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full font-semibold ${configured ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
          {configured ? "SES hazır" : "SES ayarı eksik"}
        </span>
      </div>

      {/* SES Ayarları */}
      <div className="bg-white border rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm">SES Ayarları</h2>
          <label className="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" checked={!!cfg.enabled} onChange={(e) => setCfg((p) => ({ ...p, enabled: e.target.checked }))} className="w-4 h-4 accent-black" />
            Aktif
          </label>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {field("AWS Bölgesi", "region", "text", "eu-west-1")}
          {field("Gönderen adresi (doğrulanmış)", "from_email", "text", "club@facette.com.tr")}
          {field("IAM Access Key ID", "access_key")}
          {field("IAM Secret Access Key", "secret_key", "password", "••••••")}
          {field("Gönderen adı", "from_name", "text", "Facette")}
          {/* Yanıt adresi: görünen gönderen gerçek bir posta kutusu olmayabilir
              (club@... yalnız gönderim için). Müşteri yanıtı kaybolmasın diye
              okunan bir adrese yönlendirilir. */}
          {field("Yanıt adresi (ops.)", "reply_to", "text", "info@facette.com.tr")}
          {field("Configuration Set (ops.)", "configuration_set", "text", "açılma/bounce takibi")}
        </div>
        <div className="flex flex-wrap items-center gap-3 pt-2">
          <button onClick={saveCfg} disabled={busy === "save"} className="inline-flex items-center gap-2 bg-black text-white px-4 py-2 rounded-lg text-sm font-semibold hover:bg-gray-800 disabled:opacity-50">
            <Save size={15} /> Kaydet
          </button>
          <div className="flex items-center gap-2">
            <input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="test@ornek.com"
              className="border rounded-lg px-3 py-2 text-sm" />
            <button onClick={sendTest} disabled={busy === "test"} className="inline-flex items-center gap-2 border px-4 py-2 rounded-lg text-sm font-semibold hover:bg-gray-50 disabled:opacity-50">
              <Send size={15} /> Test gönder
            </button>
          </div>
        </div>
        <p className="text-[11px] text-gray-400 leading-relaxed">
          İşlemsel e-postalar (sipariş/şifre) Zoho'dan gitmeye devam eder — burası yalnız pazarlama kanalıdır.
          SES ilk açılışta "sandbox" modundadır; toplu gönderim için AWS'den "production access" onayı alınmalıdır.
        </p>
      </div>

      {/* Hazır Şablonlar */}
      <div className="bg-white border rounded-xl p-4">
        <div className="flex items-center gap-2 mb-3">
          <FileText size={16} className="text-gray-500" />
          <h2 className="font-semibold text-sm">Kampanya Şablonları</h2>
          <span className="text-[11px] text-gray-400">— gönderMEDEN önce önizle & düzenle</span>
        </div>
        {templates.length === 0 ? (
          <p className="text-sm text-gray-400">Şablon yükleniyor…</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="tpl-grid">
            {templates.map((t) => (
              <div key={t.id} className={`border rounded-lg p-3 flex flex-col gap-2 ${t.recommended ? "border-amber-300 bg-amber-50/40" : "border-gray-200"}`} data-testid={`tpl-card-${t.id}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium text-sm text-gray-900 truncate flex items-center gap-1">
                      {t.recommended && <Star size={13} className="text-amber-500 shrink-0" fill="currentColor" />}
                      {t.name}
                    </div>
                    <div className="text-[11px] text-gray-400">{t.category || "Genel"}{t.builtin ? " · hazır" : ""}</div>
                  </div>
                  {!t.builtin && (
                    <button onClick={() => deleteTemplate(t)} title="Sil" className="text-gray-300 hover:text-red-600 shrink-0"><Trash2 size={14} /></button>
                  )}
                </div>
                <div className="text-[11px] text-gray-500 line-clamp-2">{t.subject}</div>
                <div className="flex gap-2 mt-auto pt-1">
                  <button onClick={() => useTemplate(t)} className="flex-1 inline-flex items-center justify-center gap-1 bg-black text-white rounded-md px-2 py-1.5 text-xs font-medium hover:bg-gray-800" data-testid={`tpl-use-${t.id}`}>
                    <Copy size={12} /> Kullan
                  </button>
                  <button onClick={() => openPreview(t)} className="inline-flex items-center justify-center gap-1 border rounded-md px-2 py-1.5 text-xs hover:bg-gray-50" data-testid={`tpl-preview-${t.id}`}>
                    <Eye size={12} /> Önizle
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        <p className="text-[11px] text-gray-400 mt-3 leading-relaxed">
          Placeholder'lar: <code>{"{ad}"}</code> (abone adı), <code>{"{kod}"}</code> (kupon), <code>{"{indirim}"}</code> (oran),
          <code> URUN_LINKI</code> / <code>GORSEL_URL</code> (kendi bağlantın). "Kullan" ile editöre yükle, düzenle, önizle, sonra gönder.
        </p>
      </div>

      {/* Kampanya oluştur + CANLI ÖNİZLEME */}
      <div id="yeni-kampanya" className="bg-white border rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-sm">Yeni Kampanya</h2>
          <button onClick={saveAsTemplate} disabled={busy === "savetpl" || !camp.html.trim()}
            className="inline-flex items-center gap-1.5 border rounded-lg px-3 py-1.5 text-xs font-medium hover:bg-gray-50 disabled:opacity-50" data-testid="save-tpl-btn">
            <Save size={13} /> Şablon olarak kaydet
          </button>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* Editör */}
          <div className="space-y-3">
            <input value={camp.subject} onChange={(e) => setCamp((p) => ({ ...p, subject: e.target.value }))}
              placeholder="Konu (ör. Yeni Sezon Geldi)" className="w-full border rounded-lg px-3 py-2 text-sm" data-testid="camp-subject" />
            <textarea value={camp.html} onChange={(e) => setCamp((p) => ({ ...p, html: e.target.value }))}
              placeholder="HTML içerik — <p>Merhaba {ad}...</p> (marka kabuğu: logo + footer + abonelikten-çık otomatik eklenir)"
              rows={16} className="w-full border rounded-lg px-3 py-2 text-sm font-mono" data-testid="camp-html" />
          </div>
          {/* Canlı önizleme (tam markalı) */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Eye size={13} /> Canlı Önizleme (gönderilecek gerçek görünüm)
            </div>
            <div className="border rounded-lg overflow-hidden bg-gray-50" style={{ height: 420 }}>
              {previewHtml ? (
                <iframe title="onizleme" srcDoc={previewHtml} className="w-full h-full bg-white" data-testid="live-preview" />
              ) : (
                <div className="h-full flex items-center justify-center text-xs text-gray-400 text-center px-4">
                  Konu / içerik yazınca ya da bir şablonu "Kullan" deyince markalı önizleme burada görünür.
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex justify-end">
          <button onClick={sendCampaign} disabled={busy === "campaign" || !configured} className="inline-flex items-center gap-2 bg-black text-white px-5 py-2 rounded-lg text-sm font-bold hover:bg-gray-800 disabled:opacity-50">
            <Send size={15} /> {aud.eligible} aboneye gönder
          </button>
        </div>
      </div>

      {/* Geçmiş */}
      <div className="bg-white border rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-sm">Kampanya Geçmişi</h2>
          <button onClick={load} className="text-gray-400 hover:text-black"><RefreshCw size={16} /></button>
        </div>
        {campaigns.length === 0 ? (
          <p className="text-sm text-gray-400">Henüz kampanya yok.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-gray-500 border-b">
                <th className="py-2">Konu</th><th>Durum</th><th className="text-right">Gönderildi</th><th className="text-right">Hata</th><th className="text-right">Toplam</th><th className="text-right">Tarih</th>
              </tr></thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="py-2 pr-2">{c.subject}</td>
                    <td>
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold ${c.status === "sent" ? "text-green-600" : c.status === "sending" ? "text-blue-600" : c.status === "failed" ? "text-red-600" : "text-gray-500"}`}>
                        {c.status === "sent" ? <CheckCircle2 size={13} /> : c.status === "failed" ? <AlertTriangle size={13} /> : null}
                        {c.status}
                      </span>
                    </td>
                    <td className="text-right">{c.sent || 0}</td>
                    <td className="text-right text-red-500">{c.failed || 0}</td>
                    <td className="text-right">{c.total || 0}</td>
                    <td className="text-right text-xs text-gray-400">{c.created_at ? new Date(c.created_at).toLocaleString("tr-TR") : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Şablon önizleme modalı (tam markalı) */}
      {previewModal && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center p-4" onClick={() => setPreviewModal(null)}>
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative bg-white rounded-xl w-full max-w-2xl h-[80vh] flex flex-col shadow-xl" onClick={(e) => e.stopPropagation()} data-testid="preview-modal">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <div className="text-sm font-semibold truncate">Önizleme · {previewModal.subject || "(konu yok)"}</div>
              <button onClick={() => setPreviewModal(null)} className="text-gray-400 hover:text-black"><X size={18} /></button>
            </div>
            <iframe title="tpl-onizleme" srcDoc={previewModal.html} className="flex-1 w-full bg-white rounded-b-xl" />
          </div>
        </div>
      )}
    </div>
  );
}
