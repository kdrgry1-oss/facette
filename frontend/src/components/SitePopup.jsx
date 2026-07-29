/**
 * =============================================================================
 * SitePopup.jsx — Admin > Popup'lar (popups) storefront gösterimi
 * =============================================================================
 * DENETİM FIX (#35): Admin'de oluşturulan Popup'lar için storefront tüketimi yoktu.
 * Bu bileşen /api/storefront/popups (aktif + tarih aralığı filtreli) uçtan okur,
 * `delay_seconds` sonra modal olarak gösterir. `show_once` ise oturum başına bir kez.
 *
 * Savunmacı: uç hatası / boş liste → hiçbir şey render etmez (mağazayı asla kırmaz).
 * =============================================================================
 */
import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

// Bülten popup'ı için onay metni — footer bandıyla AYNI (İYS'ye bu metin işlenir).
const POPUP_CONSENT_TEXT =
  "KVKK Aydınlatma Metni'ni okudum; kampanya ve fırsatlar için ticari elektronik ileti (e-posta) almayı kabul ediyorum.";

// Bülten kayıt formu (footer NewsletterBand ile aynı akış: zorunlu KVKK onayı + İYS kaydı).
function PopupNewsletterForm({ popup, onClose }) {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState("idle"); // idle | loading | done | error
  const [msg, setMsg] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    const v = (email || "").trim();
    if (!v || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) {
      setState("error"); setMsg("Lütfen geçerli bir e-posta adresi girin."); return;
    }
    if (!consent) {
      setState("error"); setMsg("Devam etmek için KVKK / ticari ileti onayını işaretlemelisin."); return;
    }
    setState("loading");
    try {
      const r = await axios.post(`${API}/newsletter/subscribe`, {
        email: v, source: "popup", consent: true, consent_text: POPUP_CONSENT_TEXT,
      });
      setState("done"); setMsg(r?.data?.message || "Aramıza hoş geldin!");
    } catch (err) {
      setState("error"); setMsg(err?.response?.data?.detail || "Bir sorun oluştu, tekrar dene.");
    }
  };
  if (state === "done") {
    return (
      <div className="text-center py-4" data-testid="popup-newsletter-done">
        <div className="w-12 h-12 rounded-full bg-black text-white flex items-center justify-center mx-auto mb-3 text-xl">✓</div>
        <p className="text-sm text-neutral-800">{msg}</p>
        <button onClick={onClose} className="mt-4 text-xs underline text-neutral-500 hover:text-black">Kapat</button>
      </div>
    );
  }
  return (
    <form onSubmit={submit} data-testid="popup-newsletter-form">
      <div className="flex items-stretch border-b border-neutral-400 focus-within:border-black transition-colors">
        <input
          type="email" value={email}
          onChange={(e) => { setEmail(e.target.value); if (state === "error") setState("idle"); }}
          placeholder="E-posta adresin"
          className="flex-1 bg-transparent px-1 py-2.5 text-sm text-neutral-900 placeholder-neutral-400 outline-none"
          aria-label="E-posta adresi"
        />
        <button type="submit" disabled={state === "loading"}
          className="px-3 text-sm font-semibold text-neutral-900 hover:opacity-60 disabled:opacity-40">
          {state === "loading" ? "..." : "Üye ol"}
        </button>
      </div>
      {state === "error" && <p className="text-xs text-red-500 mt-2">{msg}</p>}
      <label className="flex items-start gap-2 mt-3 text-left text-[11px] text-neutral-600 leading-snug cursor-pointer">
        <input type="checkbox" checked={consent}
          onChange={(e) => { setConsent(e.target.checked); if (state === "error") setState("idle"); }}
          className="mt-0.5 w-4 h-4 accent-black flex-shrink-0" aria-label="KVKK ve ticari ileti onayı" />
        <span>
          <Link to="/sayfa/kvkk" onClick={onClose} className="underline hover:text-black">KVKK Aydınlatma Metni</Link>'ni
          okudum; kampanya ve fırsatlar için ticari elektronik ileti (e-posta) almayı kabul ediyorum.
        </span>
      </label>
    </form>
  );
}

export default function SitePopup() {
  const [popup, setPopup] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer = null;
    let onExit = null;   // exit-intent (mouseout) dinleyicisi
    const cleanupExit = () => { if (onExit) { document.removeEventListener("mouseout", onExit); onExit = null; } };
    axios
      .get(`${API}/storefront/popups`)
      .then((r) => {
        if (!alive) return;
        const list = Array.isArray(r?.data?.items) ? r.data.items : [];
        const p = list.find((x) => x && (x.content || x.image || x.name || x.newsletter));
        if (!p) return;
        // show_once → bu popup daha önce gösterildiyse atla
        if (p.show_once) {
          try {
            if (localStorage.getItem(`facette_popup_${p.id}`) === "1") return;
          } catch { /* yoksay */ }
        }
        setPopup(p);
        const show = () => { if (alive) { setVisible(true); cleanupExit(); if (timer) clearTimeout(timer); } };
        // Tetikleyici: 'exit_intent' → fare pencereden (üstten) çıkınca; değilse gecikmeli.
        const trigger = String(p.trigger || "delay");
        const isTouch = typeof window !== "undefined" && ("ontouchstart" in window || navigator.maxTouchPoints > 0);
        if (trigger === "exit_intent" && !isTouch) {
          // Masaüstü: imleç viewport'un üstünden çıkarsa (sekme/kapatma niyeti)
          onExit = (e) => { if (e.clientY <= 0 && !e.relatedTarget) show(); };
          document.addEventListener("mouseout", onExit);
          // Emniyet: dokunmatik olmayan ama fare çıkışı yakalanmayan durumlar için 45sn sonra göster
          timer = setTimeout(show, 45000);
        } else if (trigger === "exit_intent" && isTouch) {
          // Dokunmatik cihazda exit-intent olmaz → makul bir gecikmeyle göster (kaybolmasın)
          timer = setTimeout(show, 20000);
        } else {
          const delay = Math.max(0, Number(p.delay_seconds) || 0) * 1000;
          timer = setTimeout(show, delay);
        }
      })
      .catch(() => {});
    return () => { alive = false; if (timer) clearTimeout(timer); cleanupExit(); };
  }, []);

  if (!popup || !visible) return null;

  const close = () => {
    setVisible(false);
    if (popup.show_once) {
      try { localStorage.setItem(`facette_popup_${popup.id}`, "1"); } catch { /* yoksay */ }
    }
  };

  const body = (
    <div className="bg-white rounded-xl overflow-hidden max-w-md w-full shadow-2xl relative">
      <button
        onClick={close}
        className="absolute right-3 top-3 z-10 w-8 h-8 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60"
        aria-label="Kapat"
      >
        ×
      </button>
      {popup.image && (
        <img src={popup.image} alt={popup.name || "Popup"} className="w-full object-cover" />
      )}
      <div className="p-6">
        {(popup.name || popup.title) && (
          <h3 className="text-xl font-semibold mb-2 tracking-tight">{popup.name || popup.title}</h3>
        )}
        {(popup.subtitle || popup.content) && (
          <div className="text-sm text-gray-600 whitespace-pre-line mb-4">{popup.subtitle || popup.content}</div>
        )}
        {popup.newsletter ? (
          /* Bülten kayıt formu (ekran görüntüsündeki gibi): e-posta + zorunlu KVKK onayı + İYS. */
          <PopupNewsletterForm popup={popup} onClose={close} />
        ) : (
          popup.link && (
            <a
              href={popup.link}
              onClick={close}
              className="mt-2 inline-block bg-black text-white px-5 py-2 rounded-lg text-sm hover:bg-gray-800"
            >
              {popup.button_text || "İncele"}
            </a>
          )
        )}
      </div>
    </div>
  );

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 p-4"
      onClick={close}
      data-testid="site-popup"
    >
      <div onClick={(e) => e.stopPropagation()}>{body}</div>
    </div>
  );
}
