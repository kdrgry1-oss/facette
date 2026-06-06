// Görsel optimizasyon yardımcısı — LCP/CLS ve ağ ağırlığını düşürmek için.
// - Ticimax (Cloudflare) görsellerinde cdn-cgi/image resize param'ları kullanılır
//   (width + quality + format=auto → otomatik WebP/AVIF).
// - Kendi sunucumuzdaki /api/files veya /api/upload/files görsellerinde ?w=&q=
//   query param'larıyla backend on-the-fly WebP resize devreye girer.

const TCMX = "static.ticimax.cloud";
// Cloudflare R2 özel domaini — Image Transformations (cdn-cgi/image) ile dinamik
// AVIF/WebP + resize sunar (Ticimax ile aynı yöntem).
const R2_CDN = "cdn.facette.com.tr";
// Eski r2.dev (transform desteklemez) — kalan referanslar için boyut-eşleme fallback.
const R2_SIZES = [400, 800, 1280, 1920];

export function optimizeImg(url, width = 800, quality = 90) {
  // Boş/geçersiz değerlerde src="" uyarısını ve gereksiz isteği önlemek için undefined döndür
  if (!url || typeof url !== "string") return undefined;

  // Cloudflare R2 özel domain → cdn-cgi/image ile dinamik resize + format=auto (AVIF/WebP)
  if (url.includes(R2_CDN)) {
    let path = url;
    const m = url.match(/cdn\.facette\.com\.tr\/cdn-cgi\/image\/[^/]+\/(.*)$/i);
    if (m) {
      path = `https://${R2_CDN}/${m[1]}`;
    }
    return path.replace(
      `https://${R2_CDN}/`,
      `https://${R2_CDN}/cdn-cgi/image/width=${width},quality=${quality},format=auto/`
    );
  }

  // Eski r2.dev URL'leri (transform yok) → en yakın üretilmiş boyutu seç
  if (url.includes("r2.dev")) {
    const m = url.match(/-(\d+)\.webp(\?.*)?$/i);
    if (m) {
      const target = R2_SIZES.find((s) => s >= width) || R2_SIZES[R2_SIZES.length - 1];
      return url.replace(/-\d+\.webp/i, `-${target}.webp`);
    }
    return url;
  }

  // Ticimax Cloudflare CDN
  if (url.includes(TCMX)) {
    // Varsa mevcut cdn-cgi transform'unu soy → orijinal path'i al
    let path = url;
    const m = url.match(/static\.ticimax\.cloud\/cdn-cgi\/image\/[^/]+\/(.*)$/i);
    if (m) {
      path = `https://${TCMX}/${m[1]}`;
    }
    return path.replace(
      `https://${TCMX}/`,
      `https://${TCMX}/cdn-cgi/image/width=${width},quality=${quality},format=auto/`
    );
  }

  // Kendi sunucumuz (MongoDB'den servis edilen yüklenmiş görseller)
  if (url.startsWith("/api/files/") || url.startsWith("/api/upload/files/")) {
    const sep = url.includes("?") ? "&" : "?";
    return `${url}${sep}w=${width}&q=${quality}`;
  }

  return url;
}

// Bir görselin en-boy oranını (CSS aspectRatio için) döndürür: "w / h"
export function aspectFromDims(dims, fallback = "16 / 9") {
  if (Array.isArray(dims) && dims.length === 2 && dims[0] && dims[1]) {
    return `${dims[0]} / ${dims[1]}`;
  }
  return fallback;
}
