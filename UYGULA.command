#!/bin/bash
# ============================================================
# FACETTE DEPLOY
#  - Ticimax "Cek" gercek hata gosterimi + guvenli sayfa boyutu (100)
#  - Urun: gorsel siralama + Trendyol ozellik (eksiksiz) + zorunlu kirmizi
#  - Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Proje kokune koy. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
# Dosya dogrulamalari
grep -q "first_error" backend/routes/integrations.py || { echo "HATA: Ticimax gercek-hata yakalama (first_error) yok."; exit 1; }
grep -q "safe_page_size" backend/routes/integrations.py || { echo "HATA: Guvenli sayfa boyutu (safe_page_size) yok."; exit 1; }
grep -q "success === false" frontend/src/pages/admin/TicimaxReturns.jsx || { echo "HATA: Frontend hata-toast mantigi yok."; exit 1; }
grep -q "reorderImages" frontend/src/pages/admin/Products.jsx || { echo "HATA: Gorsel siralama (reorderImages) yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol ozellik birlestirme (tyMerged) yok."; exit 1; }
grep -q "ZORUNLU (TRENDYOL)" frontend/src/components/admin/product-form/SearchableAttribute.jsx || { echo "HATA: Zorunlu kirmizi cerceve yok."; exit 1; }
grep -q "refresh: bool" backend/routes/integrations.py || { echo "HATA: Trendyol attribute refresh parametresi yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax Cek: gercek WS hatasini goster + sayfa boyutu 100; urun gorsel siralama + Trendyol eksiksiz ozellik + zorunlu kirmizi cerceve" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Railway + Cloudflare build alacak. ~2-4 dk."
echo ""
echo "  KONTROL (deploy sonrasi):"
echo "   1. Iadeler > Ticimax > 'Ticimax'tan Cek' -> bu kez sorun varsa"
echo "      KIRMIZI toast'ta GERCEK hata cikar (ornn: WS/WSDL/filtre)."
echo "      O mesaji bana ilet — kesin teshis icin."
echo "   2. Urun Duzenle > Gorseller -> surukle-birak veya ok ile sirala."
echo "   3. Urun Duzenle > Ozellikler > Trendyol -> tum ozellik+degerler;"
echo "      zorunlu+bos olanlar kirmizi cerceveli, dolunca yesil."
echo "============================================"
