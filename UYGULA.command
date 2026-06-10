#!/bin/bash
# ============================================================
# FACETTE DEPLOY
#  - MOBIL PERFORMANS + ERISILEBILIRLIK: storefront code-split (lazy),
#    lang=tr, ProductCard aria-label, gorsel optimize
#  - Ticimax "Cek" gercek hata + sayfa boyutu 100
#  - Urun: gorsel siralama + Trendyol eksiksiz ozellik + zorunlu kirmizi
#  - Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
# --- Performans / erisilebilirlik ---
grep -q 'html lang="tr"' frontend/public/index.html || { echo "HATA: index.html lang=tr degil."; exit 1; }
grep -q 'lazy(() => import("./pages/Category"))' frontend/src/App.js || { echo "HATA: Storefront code-split (lazy) yok."; exit 1; }
grep -q 'aria-label="Sepete ekle"' frontend/src/components/ProductCard.jsx || { echo "HATA: ProductCard aria-label yok."; exit 1; }
# --- Onceki isler ---
grep -q "first_error" backend/routes/integrations.py || { echo "HATA: Ticimax first_error yok."; exit 1; }
grep -q "safe_page_size" backend/routes/integrations.py || { echo "HATA: safe_page_size yok."; exit 1; }
grep -q "reorderImages" frontend/src/pages/admin/Products.jsx || { echo "HATA: Gorsel siralama yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol eksiksiz ozellik yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Mobil performans+erisilebilirlik: storefront lazy code-split, lang=tr, ProductCard aria-label, gorsel optimize (+onceki Ticimax/urun isleri)" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Cloudflare yeniden build alacak. ~2-4 dk."
echo ""
echo "  Build bitince PageSpeed Insights'i TEKRAR calistir (cache'siz):"
echo "   - Performans: storefront JS kucuduldu -> TBT/LCP iyilesir"
echo "   - Erisilebilirlik: lang=tr + buton adlari -> 79'dan yukari"
echo "  NOT: PageSpeed her olcumde +-5 oynar; 2-3 kez calistirip ortalamaya bak."
echo "============================================"
