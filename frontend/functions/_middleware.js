/**
 * =============================================================================
 * Cloudflare Pages Edge SEO Middleware — functions/_middleware.js
 * =============================================================================
 * SORUN (SEO denetimi P0): Site tamamen client-side render (CRA). Her sayfanın İLK
 * HTML'i public/index.html → HEPSİNDE aynı <title>, aynı description ve
 * ana sayfa canonical değeri vardı. Google tüm ürün/
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
    // API_BASE deployment binding is the bootstrap address. Brand/domain data
    // itself comes from canonical tenant_config via this endpoint.
    const apiBase = env && env.API_BASE;
    if (!apiBase) return response;
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

    if (Object.prototype.hasOwnProperty.call(meta, "title")) {
      rw.on("title", {
        element(el) { el.setInnerContent(meta.title || ""); },
      });
    }
    if (Object.prototype.hasOwnProperty.call(meta, "description")) {
      rw.on('meta[name="description"]', {
        element(el) { el.setAttribute("content", meta.description || ""); },
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
      "og:site_name": meta.og_site_name,
      "og:locale": meta.og_locale,
    };
    for (const [prop, val] of Object.entries(ogMap)) {
      if (val == null) continue;
      rw.on(`meta[property="${prop}"]`, {
        element(el) { el.setAttribute("content", val || ""); },
      });
    }

    const twitterMap = {
      "twitter:title": meta.title,
      "twitter:description": meta.description,
      "twitter:image": meta.og_image,
    };
    for (const [name, val] of Object.entries(twitterMap)) {
      if (val == null) continue;
      rw.on(`meta[name="${name}"]`, {
        element(el) { el.setAttribute("content", val || ""); },
      });
    }

    // <head> sonuna: robots (varsa) + JSON-LD (ürün) + edge marker
    const headAppend = [];
    if (meta.robots) {
      rw.on('meta[name="robots"]', {
        element(el) {
          el.setAttribute("content", meta.robots);
          el.setAttribute("data-seo", "edge");
        },
      });
    }
    if (Array.isArray(meta.jsonld)) {
      for (const item of meta.jsonld) {
        const j = jsonForScript(item);
        if (j) headAppend.push(`<script type="application/ld+json" data-seo="edge">${j}</script>`);
      }
    }
    // İstemciye "edge meta enjekte edildi" işareti (twitter card da ekle)
    headAppend.push('<meta name="twitter:card" content="summary_large_image" data-seo="edge">');
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
