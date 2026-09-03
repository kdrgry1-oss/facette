/**
 * =============================================================================
 * Cloudflare Pages Edge SEO Middleware — functions/_middleware.js
 * =============================================================================
 * SORUN (SEO denetimi P0): Site tamamen client-side render (CRA). Her sayfanın İLK
 * HTML'i public/index.html → HEPSİNDE aynı <title>, aynı description ve
 * <link rel="canonical" href="https://facette.com.tr/"> vardı. Google tüm ürün/
 * kategori URL'lerini ANA SAYFAYA canonical'ledi → ürün/kategori sayfaları
 * indekslenmiyordu (uzun-kuyruk trafiğinin tamamı kayıp).
 *
 * ÇÖZÜM: Her HTML isteğinde backend'den /api/seo/page-meta?path=... çekilir ve
 * dönen title/description/canonical/OG + (ürün) JSON-LD ilk HTML'in <head>'ine
 * HTMLRewriter ile enjekte edilir. Böylece crawler ilk HTML'de sayfaya-özel
 * doğru meta'yı görür. Bilinmeyen yollar noindex olur (soft-404 giderilir).
 *
 * GÜVENLİK/DAYANIKLILIK: Sadece text/html yanıtlarında çalışır (asset'ler
 * dokunulmaz). Meta çekimi zaman-aşımlı (2.5sn) ve HER hatada sayfayı OLDUĞU GİBİ
 * döndürür (fail-open) → mağazayı asla kırmaz. Yanıt edge'de kısa süre cache'lenir.
 * Client tarafı (ProductDetail.jsx) data-seo="edge" markerını görürse JSON-LD'yi
 * tekrar eklemez (duplicate önlenir).
 * =============================================================================
 */

const NONHTML_EXT = /\.(js|css|map|png|jpe?g|webp|avif|gif|svg|ico|woff2?|ttf|eot|mp4|webm|json|xml|txt|pdf|wasm)$/i;

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// JSON-LD güvenli gömme: </script> ve < kaçırma
function jsonForScript(obj) {
  try {
    return JSON.stringify(obj).replace(/</g, "\\u003c");
  } catch (_) {
    return "";
  }
}

export async function onRequest(context) {
  const { request, next, env } = context;

  // 1) Yalnız GET; asset uzantılı yollar → dokunma
  let url;
  try {
    url = new URL(request.url);
  } catch (_) {
    return next();
  }
  const path = url.pathname || "/";
  if (request.method !== "GET" || NONHTML_EXT.test(path) || path.startsWith("/api/")) {
    return next();
  }

  // 2) SPA yanıtını al (index.html)
  const response = await next();
  try {
    const ct = response.headers.get("content-type") || "";
    if (!ct.includes("text/html")) return response;

    // 3) Backend'den sayfa meta'sını çek (zaman-aşımlı, edge-cache'li, fail-open)
    const apiBase = (env && env.API_BASE) || "https://api.facette.com.tr/api";
    const metaUrl = `${apiBase}/seo/page-meta?path=${encodeURIComponent(path)}`;
    let meta = null;
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2500);
      const r = await fetch(metaUrl, {
        signal: ctrl.signal,
        cf: { cacheTtl: 300, cacheEverything: true },
        headers: { accept: "application/json" },
      });
      clearTimeout(t);
      if (r.ok) meta = await r.json();
    } catch (_) {
      meta = null;
    }
    if (!meta || meta.found !== true) return response;

    // 4) HTMLRewriter ile <head>'i güncelle
    const rw = new HTMLRewriter();

    if (meta.title) {
      rw.on("title", {
        element(el) { el.setInnerContent(meta.title); },
      });
    }
    if (meta.description) {
      rw.on('meta[name="description"]', {
        element(el) { el.setAttribute("content", meta.description); },
      });
    }
    if (meta.canonical) {
      rw.on('link[rel="canonical"]', {
        element(el) { el.setAttribute("href", meta.canonical); },
      });
    }
    // Open Graph (index.html'de mevcut etiketleri yerinde güncelle)
    const ogMap = {
      "og:title": meta.og_title || meta.title,
      "og:description": meta.og_description || meta.description,
      "og:url": meta.og_url || meta.canonical,
      "og:image": meta.og_image,
      "og:type": meta.og_type,
    };
    for (const [prop, val] of Object.entries(ogMap)) {
      if (!val) continue;
      rw.on(`meta[property="${prop}"]`, {
        element(el) { el.setAttribute("content", val); },
      });
    }

    // <head> sonuna: robots (varsa) + JSON-LD (ürün) + edge marker
    const headAppend = [];
    if (meta.robots) {
      headAppend.push(`<meta name="robots" content="${esc(meta.robots)}" data-seo="edge">`);
    }
    if (Array.isArray(meta.jsonld)) {
      for (const item of meta.jsonld) {
        const j = jsonForScript(item);
        if (j) headAppend.push(`<script type="application/ld+json" data-seo="edge">${j}</script>`);
      }
    }
    // İstemciye "edge meta enjekte edildi" işareti (twitter card da ekle)
    headAppend.push('<meta name="twitter:card" content="summary_large_image" data-seo="edge">');
    if (meta.og_image) {
      headAppend.push(`<meta name="twitter:image" content="${esc(meta.og_image)}" data-seo="edge">`);
    }
    if (headAppend.length) {
      rw.on("head", {
        element(el) { el.append("\n" + headAppend.join("\n") + "\n", { html: true }); },
      });
    }

    return rw.transform(response);
  } catch (_) {
    // Herhangi bir hata → sayfayı olduğu gibi döndür (mağazayı kırma)
    return response;
  }
}
