/**
 * EmailMarketing.jsx — AWS SES tabanlı e-posta pazarlama paneli.
 * ================================================================
 * SES ayarları (Zoho'dan AYRI kanal — işlemsel maile dokunmaz) + rıza vermiş
 * bülten abonelerine toplu kampanya gönderimi + geçmiş. Alıcılar backend'de
 * yalnız active + consent olanlardan seçilir; her maile abonelikten-çık linki eklenir.
 */
import { useState, useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Mail, Send, Save, Users, RefreshCw, CheckCircle2, AlertTriangle,
  FileText, Eye, Copy, Trash2, X, Star,
  Bold, Italic, List, Link2, AlignLeft, AlignCenter, AlignRight, Heading, Code, SquarePlus } from "lucide-react";

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
  const [editMode, setEditMode] = useState("visual");   // "visual" (WYSIWYG) | "html" (ham)

  // Görsel (WYSIWYG) editör — hafif contentEditable + execCommand (yeni npm paketi YOK).
  const visualRef = useRef(null);
  const lastEditorHtml = useRef("");   // editörün DIŞARI yazdığı son html (dış değişimi ayırt et)

  // camp.html DIŞARIDAN değişince (şablon "Kullan" / HTML modda yazma) görsel alanı senkronla.
  useEffect(() => {
    if (editMode !== "visual") return;
    const el = visualRef.current;
    if (!el) return;
    if (camp.html !== lastEditorHtml.current) {
      el.innerHTML = camp.html || "";
      lastEditorHtml.current = camp.html || "";
    }
  }, [camp.html, editMode]);

  const onVisualInput = () => {
    const el = visualRef.current;
    if (!el) return;
    const html = el.innerHTML;
    lastEditorHtml.current = html;
    setCamp((p) => ({ ...p, html }));
  };

  const exec = (cmd, val = null) => {
    const el = visualRef.current;
    if (el) el.focus();
    try { document.execCommand(cmd, false, val); } catch {}
    onVisualInput();
  };
  const addLink = () => {
    const url = window.prompt("Bağlantı (URL) — placeholder bırakabilirsin:", "URUN_LINKI");
    if (url === null) return;
    exec("createLink", url.trim() || "URUN_LINKI");
  };
  const addButton = () => {
    const text = window.prompt("Buton yazısı:", "Koleksiyonu Keşfet");
    if (text === null) return;
    const url = window.prompt("Buton bağlantısı (URL):", "URUN_LINKI") || "URUN_LINKI";
    const btn = `<div style="text-align:center;margin:22px 0;"><a href="${(url || "URUN_LINKI").trim()}" style="display:inline-block;background:#1a1a1a;color:#ffffff;text-decoration:none;padding:15px 44px;font-size:13px;font-weight:500;letter-spacing:1.5px;text-transform:uppercase;border-radius:2px;">${(text || "Buton").trim()}</a></div>`;
    exec("insertHTML", btn + "<p><br></p>");
  };
  const insertPlaceholder = (ph) => { if (ph) exec("insertText", ph); };

  // ── Canlı önizleme: 600px e-postayı panele SIĞDIR (transform: scale) — yatay kırpma yok ──
  const EMAIL_W = 600;
  const previewBoxRef = useRef(null);
  const [pvScale, setPvScale] = useState(1);
  const [pvH, setPvH] = useState(760);
  useEffect(() => {
    const el = previewBoxRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth || EMAIL_W;
      setPvScale(Math.min(1, Math.max(0.2, (w - 4) / EMAIL_W)));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const onPreviewLoad = (ev) => {
    try {
      const doc = ev.target.contentWindow.document;
      const hh = Math.max(doc.body.scrollHeight, doc.documentElement.scrollHeight, 400);
      setPvH(hh + 8);
    } catch {}
  };

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
        <input value={camp.subject} onChange={(e) => setCamp((p) => ({ ...p, subject: e.target.value }))}
          placeholder="Konu (ör. Yeni Sezon Geldi)" className="w-full border rounded-lg px-3 py-2 text-sm" data-testid="camp-subject" />
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
          {/* Editör: Görsel (WYSIWYG) / HTML modu */}
          <div className="space-y-2 min-w-0">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="inline-flex rounded-lg border overflow-hidden text-xs">
                <button onClick={() => setEditMode("visual")} data-testid="mode-visual"
                  className={`px-3 py-1.5 font-medium ${editMode === "visual" ? "bg-black text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}>Görsel</button>
                <button onClick={() => setEditMode("html")} data-testid="mode-html"
                  className={`px-3 py-1.5 font-medium inline-flex items-center gap-1 ${editMode === "html" ? "bg-black text-white" : "bg-white text-gray-600 hover:bg-gray-50"}`}><Code size={12} /> HTML</button>
              </div>
              <select onChange={(e) => { insertPlaceholder(e.target.value); e.target.value = ""; }} defaultValue=""
                disabled={editMode !== "visual"} className="border rounded-lg px-2 py-1.5 text-xs disabled:opacity-40" title="İmleç konumuna placeholder ekle">
                <option value="" disabled>+ Placeholder</option>
                <option value="{ad}">{"{ad}"} — abone adı</option>
                <option value="{kod}">{"{kod}"} — kupon kodu</option>
                <option value="{indirim}">{"{indirim}"} — indirim oranı</option>
                <option value="URUN_LINKI">URUN_LINKI — bağlantı</option>
                <option value="GORSEL_URL">GORSEL_URL — görsel</option>
              </select>
            </div>

            {editMode === "visual" ? (
              <div className="border rounded-lg overflow-hidden">
                {/* Araç çubuğu */}
                <div className="flex flex-wrap items-center gap-0.5 bg-gray-50 border-b px-1.5 py-1">
                  {[
                    { t: "Kalın", i: <Bold size={14} />, run: () => exec("bold") },
                    { t: "İtalik", i: <Italic size={14} />, run: () => exec("italic") },
                    { t: "Başlık", i: <Heading size={14} />, run: () => exec("formatBlock", "H2") },
                    { t: "Liste", i: <List size={14} />, run: () => exec("insertUnorderedList") },
                    { t: "Link", i: <Link2 size={14} />, run: addLink },
                    { t: "Sola", i: <AlignLeft size={14} />, run: () => exec("justifyLeft") },
                    { t: "Ortala", i: <AlignCenter size={14} />, run: () => exec("justifyCenter") },
                    { t: "Sağa", i: <AlignRight size={14} />, run: () => exec("justifyRight") },
                  ].map((b) => (
                    <button key={b.t} type="button" title={b.t} onMouseDown={(e) => e.preventDefault()} onClick={b.run}
                      className="p-1.5 rounded hover:bg-gray-200 text-gray-700">{b.i}</button>
                  ))}
                  <span className="w-px h-4 bg-gray-300 mx-1" />
                  <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={addButton} title="CTA butonu ekle"
                    className="inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-gray-200 text-gray-700 text-xs"><SquarePlus size={13} /> Buton</button>
                </div>
                {/* Düzenlenebilir gövde (yalnız iç gövde — marka kabuğu gönderimde eklenir) */}
                <div ref={visualRef} contentEditable suppressContentEditableWarning onInput={onVisualInput}
                  data-testid="visual-editor"
                  className="p-4 text-sm text-gray-800 leading-relaxed focus:outline-none overflow-auto bg-white"
                  style={{ minHeight: 360, maxHeight: 460 }} />
                <div className="text-[11px] text-gray-400 px-3 py-1.5 border-t bg-gray-50">
                  Yalnız iç gövdeyi düzenlersiniz; FACETTE başlık/footer gönderimde otomatik eklenir. Placeholder'lar düz metindir.
                </div>
              </div>
            ) : (
              <textarea value={camp.html} onChange={(e) => setCamp((p) => ({ ...p, html: e.target.value }))}
                placeholder="HTML içerik — <p>Merhaba {ad}...</p> (marka kabuğu: logo + footer + abonelikten-çık otomatik eklenir)"
                rows={20} className="w-full border rounded-lg px-3 py-2 text-sm font-mono" style={{ minHeight: 400 }} data-testid="camp-html" />
            )}
          </div>

          {/* Canlı önizleme (tam markalı) — 600px e-posta panele ölçeklenir, yatay kırpma yok */}
          <div className="space-y-2 min-w-0">
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <Eye size={13} /> Canlı Önizleme (gönderilecek gerçek görünüm) — %{Math.round(pvScale * 100)}
            </div>
            <div ref={previewBoxRef} className="border rounded-lg overflow-auto bg-gray-100" style={{ height: 480 }}>
              {previewHtml ? (
                <div style={{ width: EMAIL_W * pvScale, height: pvH * pvScale, margin: "0 auto" }}>
                  <iframe title="onizleme" srcDoc={previewHtml} onLoad={onPreviewLoad} data-testid="live-preview"
                    style={{ width: EMAIL_W, height: pvH, transform: `scale(${pvScale})`, transformOrigin: "top left", border: 0, background: "#fff", display: "block" }} />
                </div>
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
