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
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SitePopup() {
  const [popup, setPopup] = useState(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer = null;
    axios
      .get(`${API}/storefront/popups`)
      .then((r) => {
        if (!alive) return;
        const list = Array.isArray(r?.data?.items) ? r.data.items : [];
        const p = list.find((x) => x && (x.content || x.image || x.name));
        if (!p) return;
        // show_once → bu popup daha önce gösterildiyse atla
        if (p.show_once) {
          try {
            if (localStorage.getItem(`facette_popup_${p.id}`) === "1") return;
          } catch { /* yoksay */ }
        }
        setPopup(p);
        const delay = Math.max(0, Number(p.delay_seconds) || 0) * 1000;
        timer = setTimeout(() => { if (alive) setVisible(true); }, delay);
      })
      .catch(() => {});
    return () => { alive = false; if (timer) clearTimeout(timer); };
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
      <div className="p-5">
        {(popup.name || popup.title) && (
          <h3 className="text-lg font-semibold mb-2">{popup.name || popup.title}</h3>
        )}
        {popup.content && (
          <div className="text-sm text-gray-600 whitespace-pre-line">{popup.content}</div>
        )}
        {popup.link && (
          <a
            href={popup.link}
            onClick={close}
            className="mt-4 inline-block bg-black text-white px-5 py-2 rounded-lg text-sm hover:bg-gray-800"
          >
            İncele
          </a>
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
