#!/bin/bash
# ============================================================
# FACETTE DEPLOY
#  - PERFORMANS-2: gorsel kalite 90->75 (~2MB tasarruf), Google Fonts async
#    (render-blocking 460ms gider), LCP hero kalite 78
#  - Ticimax WS domain fix (panel adresini reddet)
#  - Mobil performans + erisilebilirlik (storefront lazy, lang=tr, aria-label)
#  - Urun: gorsel siralama + Trendyol eksiksiz ozellik + zorunlu kirmizi
#  - Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok."; exit 1; fi
# --- Performans-2 ---
grep -q "quality = 75" frontend/src/lib/img.js || { echo "HATA: Gorsel kalite 75 degil."; exit 1; }
grep -q 'preload" as="style"' frontend/public/index.html || { echo "HATA: Font async yuklemesi yok."; exit 1; }
# --- Onceki kritik isler ---
grep -q 'ticimaxeticaret.com' backend/ticimax_client.py || { echo "HATA: Ticimax domain fix yok."; exit 1; }
grep -q "first_error" backend/routes/integrations.py || { echo "HATA: Ticimax first_error yok."; exit 1; }
grep -q 'html lang="tr"' frontend/public/index.html || { echo "HATA: lang=tr yok."; exit 1; }
grep -q 'lazy(() => import("./pages/Category"))' frontend/src/App.js || { echo "HATA: code-split yok."; exit 1; }
grep -q "reorderImages" frontend/src/pages/admin/Products.jsx || { echo "HATA: Gorsel siralama yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol eksiksiz ozellik yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Performans: gorsel kalite 90->75 (~2MB), Google Fonts async (render-blocking gider), LCP hero 78 (+onceki Ticimax/urun/SEO isleri)" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Cloudflare yeniden build alacak. ~2-4 dk."
echo ""
echo "  Build bitince PageSpeed'i 2-3 kez calistir (ortalama):"
echo "   - Resim teslimat (~2MB) ve render-blocking (460ms) cozuldu"
echo "   - Performans skoru belirgin yukselmeli"
echo ""
echo "  KOD DISI (PageSpeed'in kalan uyarilari icin):"
echo "   * Onbellek 328KiB -> cdn.facette.com.tr (Cloudflare R2/Image) ve"
echo "     PostHog/GTM 3.taraf kaynaklari. Cloudflare panelinden cdn icin"
echo "     Cache TTL'i uzun yap (Caching > Cache Rules veya R2 cache)."
echo "   * Eski JS 62KiB -> browserslist modernlestirilebilir (riskli, atlandi)."
echo "============================================"
