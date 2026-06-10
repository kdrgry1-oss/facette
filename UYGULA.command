#!/bin/bash
# ============================================================
# FACETTE DEPLOY — Urun: gorsel siralama + Trendyol ozellik (eksiksiz) + zorunlu kirmizi
#                  + Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Proje kokune koy. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
# Dosya dogrulamalari
if [ ! -f frontend/src/pages/admin/TicimaxReturns.jsx ]; then echo "HATA: TicimaxReturns.jsx yok. unzip eksik."; exit 1; fi
grep -q "reorderImages" frontend/src/pages/admin/Products.jsx || { echo "HATA: Gorsel siralama (reorderImages) Products.jsx'te yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol ozellik birlestirme (tyMerged) yok."; exit 1; }
grep -q "ZORUNLU (TRENDYOL)" frontend/src/components/admin/product-form/SearchableAttribute.jsx || { echo "HATA: Zorunlu kirmizi cerceve SearchableAttribute'da yok."; exit 1; }
grep -q "refresh: bool" backend/routes/integrations.py || { echo "HATA: Trendyol attribute refresh parametresi backend'de yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Urun: gorsel siralama (drag+ok) + Trendyol ozellikleri eksiksiz (deger birlestirme+refresh) + zorunlu alan kirmizi cerceve" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Railway + Cloudflare build alacak. ~2-4 dk."
echo ""
echo "  KONTROL (deploy sonrasi):"
echo "   1. Urun Duzenle > Gorseller -> kartlari surukle-birak ile sirala"
echo "      (veya hover'da sol/sag ok ile tasi). Ilk gorsel = KAPAK."
echo "   2. Urun Duzenle > Ozellikler -> Trendyol bolumunde tum ozellikler"
echo "      ve degerleri gelir; zorunlu+bos olanlar KIRMIZI cerceveli."
echo "   3. Bir degeri girince cerceve yesile doner."
echo "============================================"
