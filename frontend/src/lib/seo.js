/**
 * seo.js — İstemci-taraflı per-sayfa SEO meta yönetimi (Googlebot JS render eder).
 *
 * Edge middleware (functions/_middleware.js) ilk HTML'e meta bassa da basmasa da,
 * bu yardımcı SPA gezinmesinde <title>/<meta description>/<link canonical>/OG'yi
 * gerçek sayfa değerine günceller. Eskiden HER sayfa ana sayfanın meta'sını taşıyordu
 * (canonical=ana sayfa → ürün/kategori indekslenmiyordu).
 *
 * Savunmacı: DOM yoksa / hata olursa hiçbir şey yapmaz. Yönettiği etiketleri
 * data-seo-client="1" ile işaretler.
 */

function _setMeta(selectorAttr, key, content) {
  if (typeof document === "undefined") return;
  const sel = `meta[${selectorAttr}="${key}"]`;
  let el = document.head.querySelector(sel);
  if (!content) return;
  if (!el) {
    el = document.createElement("meta");
    el.setAttribute(selectorAttr, key);
    el.setAttribute("data-seo-client", "1");
    document.head.appendChild(el);
  }
  el.setAttribute("content", content);
}

function _setCanonical(href) {
  if (typeof document === "undefined" || !href) return;
  let el = document.head.querySelector('link[rel="canonical"]');
  if (!el) {
    el = document.createElement("link");
    el.setAttribute("rel", "canonical");
    document.head.appendChild(el);
  }
  el.setAttribute("href", href);
}

function _origin() {
  try {
    return (window.location && window.location.origin) || "https://facette.com.tr";
  } catch (_) {
    return "https://facette.com.tr";
  }
}

/**
 * setPageSeo({ title, description, canonical, ogImage, ogType })
 * Verilen alanlarla sayfa meta'sını günceller. canonical mutlak veya path olabilir.
 */
export function setPageSeo(opts = {}) {
  if (typeof document === "undefined") return;
  try {
    const { title, description, canonical, ogImage, ogType } = opts;
    if (title) {
      document.title = title;
      _setMeta("property", "og:title", title);
    }
    if (description) {
      _setMeta("name", "description", description);
      _setMeta("property", "og:description", description);
    }
    let canon = canonical;
    if (canon && !/^https?:\/\//i.test(canon)) canon = _origin() + (canon.startsWith("/") ? "" : "/") + canon;
    if (canon) {
      _setCanonical(canon);
      _setMeta("property", "og:url", canon);
    }
    if (ogImage) _setMeta("property", "og:image", ogImage);
    if (ogType) _setMeta("property", "og:type", ogType);
  } catch (_) {
    /* sessiz */
  }
}

/** Ürün/kategori sayfasından çıkınca canonical'ı ana sayfaya döndürmek yerine,
 *  gezinmede her sayfa kendi setPageSeo'sunu çağırdığı için reset gerekmez.
 *  Yalnız ana sayfa/statikler için varsayılana döndürmek istenirse kullanılır. */
export function resetPageSeoToHome(defaults = {}) {
  setPageSeo({
    title: defaults.title || "FACETTE | Yeni Sezon Kadın Giyim & Moda",
    description:
      defaults.description ||
      "FACETTE — kadın modasında yeni sezon koleksiyonu. Zamansız elbise, pantolon, ceket ve aksesuar parçaları.",
    canonical: _origin() + "/",
    ogType: "website",
  });
}

function _clean(s, limit = 160) {
  const t = String(s || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return t.length > limit ? t.slice(0, limit).trim() + "…" : t;
}

/** Ürün nesnesinden meta üretip uygular. */
export function setProductSeo(product, brand = "FACETTE") {
  if (!product) return;
  const slug = product.slug || product.id;
  const title = (product.meta_title || `${product.name || ""} | ${brand}`).trim();
  const description = _clean(
    product.meta_description || product.seo_description || product.description || product.name || ""
  );
  let ogImage;
  const imgs = Array.isArray(product.images) ? product.images : [];
  const first = imgs.find((im) => (typeof im === "string" ? im : im && (im.url || im.src || im.image)));
  if (first) ogImage = typeof first === "string" ? first : first.url || first.src || first.image;
  setPageSeo({
    title,
    description,
    canonical: `/urun/${slug}`,
    ogImage,
    ogType: "product",
  });
}

/** Kategori adı/slug'ından meta üretip uygular. */
export function setCategorySeo(name, slug, brand = "FACETTE", description) {
  if (!name && !slug) return;
  const title = `${name || slug} | ${brand}`;
  const desc = _clean(description || `${name || slug} kategorisindeki yeni sezon ürünleri ${brand}'te keşfedin.`);
  setPageSeo({ title, description: desc, canonical: `/${slug || ""}`, ogType: "website" });
}
