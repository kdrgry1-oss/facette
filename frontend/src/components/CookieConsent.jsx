/**
 * CookieConsent.jsx — Siteye ilk giren ziyaretçiye gösterilen çerez izni barı.
 * ---------------------------------------------------------------------------
 * • Karar localStorage'da "facette_cookie_consent" altında tutulur:
 *     { necessary:true, analytics:bool, marketing:bool, ts:ISO, v:1 }
 * • Karar verildiğinde:
 *     1) dataLayer'a Google Consent Mode "consent_update" event'i gönderilir
 *        (GTM tarafındaki etiketler buna göre tetiklenir/durur).
 *     2) Arka uca best-effort POST /api/consent/log atılır (endpoint yoksa
 *        sessizce yutulur — site kırılmaz). İzin veren/reddeden tespiti için.
 * • Karar verilmişse bar hiç render edilmez.
 */
import { useEffect, useState } from "react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const LS_KEY = "facette_cookie_consent";

const readConsent = () => {
  try {
    const s = localStorage.getItem(LS_KEY);
    return s ? JSON.parse(s) : null;
  } catch {
    return null;
  }
};

// Google Consent Mode (v2) güncellemesi — GTM dataLayer üzerinden.
const pushConsent = ({ analytics, marketing }) => {
  try {
    window.dataLayer = window.dataLayer || [];
    window.dataLayer.push({
      event: "cookie_consent_update",
      consent: {
        ad_storage: marketing ? "granted" : "denied",
        ad_user_data: marketing ? "granted" : "denied",
        ad_personalization: marketing ? "granted" : "denied",
        analytics_storage: analytics ? "granted" : "denied",
      },
    });
  } catch {
    /* sessiz */
  }
};

const logConsent = (decision) => {
  // İzin veren/reddedenlerin arka uçta tespiti — endpoint yoksa sessiz geç.
  try {
    axios.post(`${API}/consent/log`, {
      ...decision,
      path: typeof window !== "undefined" ? window.location.pathname : "",
      ua: typeof navigator !== "undefined" ? navigator.userAgent : "",
    }).catch(() => {});
  } catch {
    /* sessiz */
  }
};

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [analytics, setAnalytics] = useState(true);
  const [marketing, setMarketing] = useState(true);

  useEffect(() => {
    // Karar yoksa kısa gecikmeyle göster (LCP'yi bloklamasın).
    if (readConsent()) return;
    const t = setTimeout(() => setVisible(true), 600);
    return () => clearTimeout(t);
  }, []);

  const persist = (a, m) => {
    const decision = {
      necessary: true,
      analytics: a,
      marketing: m,
      ts: new Date().toISOString(),
      v: 1,
    };
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(decision));
    } catch {
      /* sessiz */
    }
    pushConsent(decision);
    logConsent(decision);
    setVisible(false);
  };

  const acceptAll = () => persist(true, true);
  const rejectAll = () => persist(false, false);
  const savePrefs = () => persist(analytics, marketing);

  if (!visible) return null;

  return (
    <div
      className="fixed inset-x-0 bottom-0 z-[70] px-3 pb-3 md:px-6 md:pb-6"
      style={{ animation: "fctCookieUp .35s ease-out" }}
      role="dialog"
      aria-label="Çerez tercihleri"
      data-testid="cookie-consent"
    >
      <style>{`@keyframes fctCookieUp{from{opacity:0;transform:translateY(16px)}to{opacity:1;transform:translateY(0)}}`}</style>
      <div className="max-w-screen-lg mx-auto bg-white border border-black/10 shadow-[0_8px_40px_rgba(0,0,0,0.12)]">
        <div className="px-5 py-5 md:px-8 md:py-6">
          <div className="md:flex md:items-start md:gap-8">
            <div className="flex-1">
              <p className="text-[10px] tracking-[0.32em] uppercase text-black/45 mb-2">Gizliliğe Saygı</p>
              <p className="text-sm font-light text-black/75 leading-relaxed max-w-2xl">
                Deneyimini iyileştirmek, içerikleri kişiselleştirmek ve trafiği analiz etmek için
                çerezler kullanıyoruz. Tercihini istediğin zaman değiştirebilirsin.{" "}
                <a href="/sayfa/gizlilik" className="underline hover:no-underline">Gizlilik Politikası</a>
              </p>

              {settingsOpen && (
                <div className="mt-5 space-y-3 max-w-md">
                  <label className="flex items-center justify-between gap-4 text-sm">
                    <span className="font-light text-black/80">Zorunlu çerezler</span>
                    <span className="text-[11px] tracking-wider uppercase text-black/40">Her zaman açık</span>
                  </label>
                  <label className="flex items-center justify-between gap-4 text-sm cursor-pointer">
                    <span className="font-light text-black/80">Analitik çerezler</span>
                    <input
                      type="checkbox"
                      checked={analytics}
                      onChange={(e) => setAnalytics(e.target.checked)}
                      className="h-4 w-4 accent-black"
                    />
                  </label>
                  <label className="flex items-center justify-between gap-4 text-sm cursor-pointer">
                    <span className="font-light text-black/80">Pazarlama çerezleri</span>
                    <input
                      type="checkbox"
                      checked={marketing}
                      onChange={(e) => setMarketing(e.target.checked)}
                      className="h-4 w-4 accent-black"
                    />
                  </label>
                </div>
              )}
            </div>

            <div className="mt-5 md:mt-0 flex flex-col gap-2 md:w-56 flex-shrink-0">
              <button
                onClick={acceptAll}
                className="w-full bg-black text-white text-xs tracking-[0.18em] uppercase py-3 hover:bg-black/85 transition-colors"
                data-testid="cookie-accept"
              >
                Tümünü Kabul Et
              </button>
              {settingsOpen ? (
                <button
                  onClick={savePrefs}
                  className="w-full border border-black text-xs tracking-[0.18em] uppercase py-3 hover:bg-black hover:text-white transition-colors"
                  data-testid="cookie-save"
                >
                  Tercihleri Kaydet
                </button>
              ) : (
                <button
                  onClick={rejectAll}
                  className="w-full border border-black/25 text-xs tracking-[0.18em] uppercase py-3 hover:border-black transition-colors"
                  data-testid="cookie-reject"
                >
                  Reddet
                </button>
              )}
              <button
                onClick={() => setSettingsOpen((o) => !o)}
                className="text-[11px] tracking-[0.12em] uppercase text-black/45 hover:text-black transition-colors py-1"
                data-testid="cookie-settings"
              >
                {settingsOpen ? "Kapat" : "Tercihleri Yönet"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
