// Görsel optimizasyon yardımcısı — LCP/CLS ve ağ ağırlığını düşürmek için.
// - Ticimax (Cloudflare) görsellerinde cdn-cgi/image resize param'ları kullanılır
//   (width + quality + format=auto → otomatik WebP/AVIF).
// - Kendi sunucumuzdaki /api/files veya /api/upload/files görsellerinde ?w=&q=
//   query param'larıyla backend on-the-fly WebP resize devreye girer.

const TCMX = "static.ticimax.cloud";

export function optimizeImg(url, width = 800, quality = 90) {
  if (!url || typeof url !== "string") return url;

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
