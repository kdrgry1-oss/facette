// Görsel optimizasyon yardımcısı — LCP/CLS ve ağ ağırlığını düşürmek için.
// - Ticimax (Cloudflare) görsellerinde cdn-cgi/image resize param'ları kullanılır
//   (width + quality + format=auto → otomatik WebP/AVIF).
// - Kendi sunucumuzdaki /api/files veya /api/upload/files görsellerinde ?w=&q=
//   query param'larıyla backend on-the-fly WebP resize devreye girer.

const TCMX = "static.ticimax.cloud";
// R2'ye taşınan ürün görselleri bu boyutlarda WebP olarak üretildi (responsive).
const R2_SIZES = [400, 800, 1280, 1920];

export function optimizeImg(url, width = 800, quality = 90) {
  // Boş/geçersiz değerlerde src="" uyarısını ve gereksiz isteği önlemek için undefined döndür
  if (!url || typeof url !== "string") return undefined;

  // Cloudflare R2 (kendi CDN'imiz) — URL'deki boyutu istenen genişliğe en yakın
  // üretilmiş boyutla değiştirir: ...img0-800.webp → ...img0-400.webp
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
