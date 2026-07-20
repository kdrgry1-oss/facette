/**
 * Instagram.jsx — Admin > Instagram Akışı
 * @facette gönderilerini Graph API token'ı ile otomatik çeker VEYA elle ekler.
 * Anasayfadaki "#FACETTE × YOU" bölümü /api/instagram/feed'i gösterir.
 */
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Save, RefreshCw, Trash2, Plus, Instagram as IgIcon, ExternalLink, Unplug } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function AdminInstagram() {
  const [settings, setSettings] = useState(null);
  const [posts, setPosts] = useState([]);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ access_token: "", ig_user_id: "", source: "media", auto_sync: false });
  // Otomatik kurulum: App ID + Secret + KISA token → backend uzatır, IG hesabını bulur, senkronlar
  const [auto, setAuto] = useState({ app_id: "", app_secret: "", short_token: "" });
  const [autoBusy, setAutoBusy] = useState(false);
  const runAutoSetup = async () => {
    if (!auto.app_id.trim() || !auto.app_secret.trim() || !auto.short_token.trim()) {
      toast.error("App ID, App Secret ve kısa token üçü de gerekli"); return;
    }
    setAutoBusy(true);
    try {
      const token = localStorage.getItem("token");
      const r = await axios.post(`${API}/admin/instagram/auto-setup`, auto,
        { headers: { Authorization: `Bearer ${token}` } });
      toast.success(r.data?.message || "Instagram bağlandı");
      setAuto({ app_id: "", app_secret: "", short_token: "" });
      load();
    } catch (e) { toast.error(e.response?.data?.detail || "Otomatik kurulum başarısız"); }
    finally { setAutoBusy(false); }
  };
  const [manual, setManual] = useState({ image: "", permalink: "", product_link: "", caption: "" });
  const token = localStorage.getItem("token");
  const auth = { headers: { Authorization: `Bearer ${token}` } };

  const loadSettings = async () => {
    try {
      const r = await axios.get(`${API}/admin/instagram/settings`, auth);
      setSettings(r.data);
      setForm((f) => ({
        ...f,
        ig_user_id: r.data.ig_user_id || "",
        source: r.data.source || "media",
        auto_sync: !!r.data.auto_sync,
        access_token: "",
      }));
    } catch { toast.error("Ayarlar alınamadı"); }
  };
  const loadPosts = async () => {
    try {
      const r = await axios.get(`${API}/admin/instagram/posts?limit=60`, auth);
      setPosts(r.data?.posts || []);
    } catch { /* sessiz */ }
  };
  useEffect(() => { loadSettings(); loadPosts(); }, []);

  const saveSettings = async () => {
    setBusy(true);
    try {
      const payload = { ig_user_id: form.ig_user_id, source: form.source, auto_sync: form.auto_sync };
      if (form.access_token.trim()) payload.access_token = form.access_token.trim();
      await axios.put(`${API}/admin/instagram/settings`, payload, auth);
      toast.success("Ayarlar kaydedildi");
      await loadSettings();
    } catch { toast.error("Kaydetme başarısız"); }
    finally { setBusy(false); }
  };

  const syncNow = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/instagram/sync`, {}, auth);
      toast.success(`${r.data?.saved || 0} gönderi güncellendi`);
      await loadPosts(); await loadSettings();
    } catch (e) { toast.error(e?.response?.data?.detail || "Senkron başarısız"); }
    finally { setBusy(false); }
  };

  const disconnect = async () => {
    if (!window.confirm("Token'ı silip bağlantıyı kesmek istiyor musunuz? (Gönderiler silinmez)")) return;
    setBusy(true);
    try { await axios.post(`${API}/admin/instagram/disconnect`, {}, auth); toast.success("Bağlantı kesildi"); await loadSettings(); }
    catch { toast.error("İşlem başarısız"); }
    finally { setBusy(false); }
  };

  const addManual = async () => {
    if (!manual.image.trim()) { toast.error("Görsel URL'si zorunlu"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/admin/instagram/posts`, manual, auth);
      toast.success("Gönderi eklendi");
      setManual({ image: "", permalink: "", product_link: "", caption: "" });
      await loadPosts();
    } catch (e) { toast.error(e?.response?.data?.detail || "Eklenemedi"); }
    finally { setBusy(false); }
  };

  const toggleActive = async (p) => {
    try { await axios.put(`${API}/admin/instagram/posts/${p.id}`, { active: !(p.active !== false) }, auth); await loadPosts(); }
    catch { toast.error("Güncellenemedi"); }
  };
  const setProductLink = async (p, val) => {
    try { await axios.put(`${API}/admin/instagram/posts/${p.id}`, { product_link: val }, auth); }
    catch { toast.error("Kaydedilemedi"); }
  };
  const del = async (p) => {
    if (!window.confirm("Gönderi silinsin mi?")) return;
    try { await axios.delete(`${API}/admin/instagram/posts/${p.id}`, auth); await loadPosts(); }
    catch { toast.error("Silinemedi"); }
  };

  if (!settings) return <div className="p-10 text-center text-gray-400">Yükleniyor...</div>;

  return (
    <div data-testid="admin-instagram">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><IgIcon size={22} /> Instagram Akışı</h1>
          <p className="text-sm text-gray-500 mt-1">Anasayfadaki “#FACETTE × YOU” bölümünü besler.</p>
        </div>
        <div className="flex gap-2">
          {settings.token_set && (
            <button onClick={syncNow} disabled={busy} className="flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50">
              <RefreshCw size={14} className={busy ? "animate-spin" : ""} /> Şimdi Çek
            </button>
          )}
        </div>
      </div>

      {/* Bağlantı durumu */}
      <div className="grid md:grid-cols-3 gap-3 mb-4">
        <div className="bg-white border rounded-xl p-4">
          <p className="text-xs uppercase tracking-wider text-gray-500">Durum</p>
          <p className={`text-lg font-bold mt-1 ${settings.connected ? "text-green-600" : "text-gray-400"}`}>
            {settings.connected ? "Bağlı" : "Bağlı değil"}
          </p>
        </div>
        <div className="bg-white border rounded-xl p-4">
          <p className="text-xs uppercase tracking-wider text-gray-500">Gönderi Sayısı</p>
          <p className="text-lg font-bold mt-1">{settings.post_count}</p>
        </div>
        <div className="bg-white border rounded-xl p-4">
          <p className="text-xs uppercase tracking-wider text-gray-500">Son Senkron</p>
          <p className="text-sm mt-1 text-gray-700">{settings.last_sync ? new Date(settings.last_sync).toLocaleString("tr-TR") : "—"}</p>
        </div>
      </div>
      {settings.last_error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3 mb-4">Son hata: {settings.last_error}</div>
      )}

      {/* ⚡ OTOMATİK KURULUM — kısa token yapıştır, gerisini backend yapar */}
      <div className="bg-emerald-50 border-2 border-emerald-200 rounded-xl p-4 mb-4">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-1 text-emerald-800">⚡ Otomatik Kurulum (Önerilen)</h2>
        <p className="text-xs text-emerald-700 mb-3">
          <a className="underline font-semibold" href="https://developers.facebook.com/tools/explorer" target="_blank" rel="noopener noreferrer">Graph API Explorer</a>'dan
          (izinler: <b>instagram_basic</b> + <b>pages_show_list</b>) aldığınız KISA ömürlü token'ı ve app bilgilerinizi yapıştırın —
          token uzatma (60 gün), Instagram hesabını bulma, kaydetme ve ilk senkronu sistem kendisi yapar.
          App ID/Secret: developers.facebook.com → uygulamanız → Ayarlar → Temel.
        </p>
        <div className="grid md:grid-cols-3 gap-3 mb-3">
          <input value={auto.app_id} onChange={(e) => setAuto({ ...auto, app_id: e.target.value })}
            placeholder="App ID (ör. 1234567890)" className="border px-3 py-2 rounded text-sm" />
          <input type="password" value={auto.app_secret} onChange={(e) => setAuto({ ...auto, app_secret: e.target.value })}
            placeholder="App Secret" className="border px-3 py-2 rounded text-sm" />
          <input type="password" value={auto.short_token} onChange={(e) => setAuto({ ...auto, short_token: e.target.value })}
            placeholder="Kısa ömürlü token (EAAB...)" className="border px-3 py-2 rounded text-sm" />
        </div>
        <button onClick={runAutoSetup} disabled={autoBusy}
          className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-bold hover:bg-emerald-700 disabled:opacity-50">
          {autoBusy ? "Bağlanıyor…" : "⚡ Bağla ve Senkronla"}
        </button>
      </div>

      {/* Token / Ayarlar */}
      <div className="bg-white border rounded-xl p-4 mb-4">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-1">Graph API Bağlantısı</h2>
        <p className="text-xs text-gray-500 mb-3">
          Instagram <b>Business/Creator</b> hesabı + Facebook sayfası gereklidir. Meta Developers'tan alınan uzun
          ömürlü <b>Access Token</b> ve <b>Instagram User ID</b>'yi girin. “Etiketli gönderiler” için hesabın
          <b> tags</b> iznine sahip token gerekir.
        </p>
        <div className="grid md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs uppercase tracking-wider text-gray-500 mb-1">Access Token {settings.token_set && <span className="text-green-600">(kayıtlı)</span>}</label>
            <input type="password" value={form.access_token} onChange={(e) => setForm({ ...form, access_token: e.target.value })}
              placeholder={settings.token_set ? "•••••• (değiştirmek için yeni token yazın)" : "EAAB..."}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wider text-gray-500 mb-1">Instagram User ID</label>
            <input value={form.ig_user_id} onChange={(e) => setForm({ ...form, ig_user_id: e.target.value })}
              placeholder="1784xxxxxxxxxxx" className="w-full border border-gray-300 rounded px-3 py-2 text-sm" />
          </div>
          <div>
            <label className="block text-xs uppercase tracking-wider text-gray-500 mb-1">Kaynak</label>
            <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm">
              <option value="media">Kendi Gönderilerim (media)</option>
              <option value="tags">Etiketlendiğim Gönderiler (tags)</option>
            </select>
          </div>
          <label className="flex items-center gap-2 mt-6 text-sm">
            <input type="checkbox" checked={form.auto_sync} onChange={(e) => setForm({ ...form, auto_sync: e.target.checked })} />
            Otomatik senkron (her 30 dk)
          </label>
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={saveSettings} disabled={busy} className="flex items-center gap-1.5 px-4 py-2 bg-black text-white rounded-lg text-sm disabled:opacity-50">
            <Save size={14} /> Kaydet
          </button>
          {settings.token_set && (
            <button onClick={disconnect} disabled={busy} className="flex items-center gap-1.5 px-4 py-2 border border-gray-200 rounded-lg text-sm hover:bg-gray-50">
              <Unplug size={14} /> Bağlantıyı Kes
            </button>
          )}
        </div>
      </div>

      {/* Elle gönderi ekle */}
      <div className="bg-white border rounded-xl p-4 mb-4">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-1">Elle Gönderi Ekle</h2>
        <p className="text-xs text-gray-500 mb-3">Token olmadan da gönderi ekleyebilirsiniz (görsel URL + Instagram linki).</p>
        <div className="grid md:grid-cols-2 gap-3">
          <input value={manual.image} onChange={(e) => setManual({ ...manual, image: e.target.value })} placeholder="Görsel URL (zorunlu)" className="border border-gray-300 rounded px-3 py-2 text-sm" />
          <input value={manual.permalink} onChange={(e) => setManual({ ...manual, permalink: e.target.value })} placeholder="Instagram gönderi linki" className="border border-gray-300 rounded px-3 py-2 text-sm" />
          <input value={manual.product_link} onChange={(e) => setManual({ ...manual, product_link: e.target.value })} placeholder="Ürün linki (opsiyonel — tıklayınca ürüne gider)" className="border border-gray-300 rounded px-3 py-2 text-sm" />
          <input value={manual.caption} onChange={(e) => setManual({ ...manual, caption: e.target.value })} placeholder="Açıklama (opsiyonel)" className="border border-gray-300 rounded px-3 py-2 text-sm" />
        </div>
        <button onClick={addManual} disabled={busy} className="flex items-center gap-1.5 px-4 py-2 mt-3 bg-gray-900 text-white rounded-lg text-sm disabled:opacity-50">
          <Plus size={14} /> Ekle
        </button>
      </div>

      {/* Gönderiler */}
      <div className="bg-white border rounded-xl p-4">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-3">Gönderiler ({posts.length})</h2>
        {posts.length === 0 ? (
          <p className="text-sm text-gray-400 py-6 text-center">Henüz gönderi yok. Token ile “Şimdi Çek” veya elle ekleyin.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
            {posts.map((p) => (
              <div key={p.id} className={`border rounded-lg overflow-hidden ${p.active === false ? "opacity-40" : ""}`}>
                <div className="relative aspect-square bg-gray-100">
                  <img src={p.image} alt="" className="w-full h-full object-cover" loading="lazy" />
                  {p.source === "manual" && <span className="absolute top-1 left-1 text-[9px] bg-black/60 text-white px-1.5 py-0.5 rounded">elle</span>}
                </div>
                <div className="p-2 space-y-1.5">
                  <input
                    defaultValue={p.product_link || ""}
                    onBlur={(e) => setProductLink(p, e.target.value)}
                    placeholder="/urun/... (ürün linki)"
                    className="w-full border border-gray-200 rounded px-1.5 py-1 text-[11px]"
                    title="Bu gönderiye ürün linki bağla"
                  />
                  <div className="flex items-center justify-between">
                    {p.permalink ? (
                      <a href={p.permalink} target="_blank" rel="noreferrer" className="text-gray-400 hover:text-black"><ExternalLink size={13} /></a>
                    ) : <span />}
                    <div className="flex items-center gap-2">
                      <button onClick={() => toggleActive(p)} title={p.active === false ? "Göster" : "Gizle"} className="text-[10px] text-gray-500 hover:text-black">
                        {p.active === false ? "Göster" : "Gizle"}
                      </button>
                      <button onClick={() => del(p)} className="text-red-500 hover:text-red-700"><Trash2 size={13} /></button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
