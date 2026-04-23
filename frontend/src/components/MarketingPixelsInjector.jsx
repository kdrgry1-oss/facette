/**
 * MarketingPixelsInjector — Sayfa yüklemesinde aktif pixel snippet'lerini
 * <head> içine enjekte eder. Public endpoint kullanır (auth gerektirmez).
 *
 * Kullanım: App.js içinde 1 kez render edilir.
 */
import { useEffect } from "react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function MarketingPixelsInjector() {
  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/marketing-pixels/active-public`)
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (cancelled || !data) return;
        if (data.head) {
          const wrap = document.createElement("div");
          wrap.innerHTML = data.head;
          // script'ler innerHTML ile execute edilmez → yeniden oluştur
          wrap.querySelectorAll("script").forEach((s) => {
            const n = document.createElement("script");
            for (const attr of s.attributes) n.setAttribute(attr.name, attr.value);
            if (s.textContent) n.textContent = s.textContent;
            document.head.appendChild(n);
          });
          wrap.querySelectorAll("noscript, meta, link, style").forEach((el) => {
            document.head.appendChild(el.cloneNode(true));
          });
        }
        if (data.body) {
          const wrap = document.createElement("div");
          wrap.innerHTML = data.body;
          document.body.appendChild(wrap);
        }
      })
      .catch(() => { /* sessiz */ });
    return () => { cancelled = true; };
  }, []);
  return null;
}
