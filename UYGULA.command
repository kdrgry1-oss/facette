#!/bin/bash
# ============================================================
# FACETTE DEPLOY
#  - TICIMAX WS DOGRU ADRES + KEY: domain=facette.ticimaxeticaret.com,
#    WS yetki kodu=AKG0M8DTRSEBAIA898JA6HW22EDIU3 (default + tum fallback'ler).
#    Yanlis "panel adresini reddet" mantigi kaldirildi. Cron dahil her sey
#    artik dogru adrese gider -> getroottree hatasi cozulur.
#  - Performans: gorsel kalite 75, Google Fonts async
#  - Mobil: storefront lazy code-split, lang=tr, ProductCard aria-label
#  - Urun: gorsel siralama + Trendyol eksiksiz ozellik + zorunlu kirmizi
#  - Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok."; exit 1; fi
# --- Ticimax dogru adres + key (kritik) ---
grep -q 'facette.ticimaxeticaret.com' backend/ticimax_client.py || { echo "HATA: dogru WS domaini default degil."; exit 1; }
grep -q 'AKG0M8DTRSEBAIA898JA6HW22EDIU3' backend/ticimax_client.py || { echo "HATA: yeni WS key yok."; exit 1; }
if grep -rq 'SSIQWRIYHQWROZGJAEIC2CRRZ5RV5V' backend/ --include=*.py; then echo "HATA: eski WS key hala var."; exit 1; fi
# --- Onceki isler ---
grep -q "first_error" backend/routes/integrations.py || { echo "HATA: first_error yok."; exit 1; }
grep -q "quality = 75" frontend/src/lib/img.js || { echo "HATA: gorsel kalite 75 degil."; exit 1; }
grep -q 'html lang="tr"' frontend/public/index.html || { echo "HATA: lang=tr yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol eksiksiz ozellik yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax WS: dogru adres facette.ticimaxeticaret.com + yeni yetki kodu (eski key/yanlis domain mantigi temizlendi); getroottree cozumu (+onceki isler)" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Railway backend'i yeniden baslatacak. ~1-2 dk."
echo ""
echo "  ONEMLI — db'deki ayar:"
echo "   Entegrasyonlar > Ticimax ayarinda 'domain' = facette.ticimaxeticaret.com"
echo "   ve 'api_key' = AKG0M8DTRSEBAIA898JA6HW22EDIU3 oldugundan emin ol."
echo "   (Kod default'u zaten bu; ama db'de eski www.facette.com.tr varsa onu"
echo "    duzelt ya da domain alanini bos birak.)"
echo ""
echo "  KONTROL:"
echo "   1. Iadeler > Ticimax > 'Ticimax'tan Cek' -> artik calismali."
echo "   2. Hala hata olursa KIRMIZI toast gercek sebebi gosterir; bana ilet."
echo "============================================"
