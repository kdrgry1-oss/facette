#!/bin/bash
# ============================================================
# FACETTE DEPLOY
#  - TICIMAX WS DOMAIN FIX: panel adresi (*.ticimaxeticaret.com) reddedilir,
#    mağaza domaini kullanılır -> getroottree hatasi biter
#    (siparis cekme + urun cekme/2984-2985 + stok + uye + kategori HEPSI duzelir)
#  - Mobil performans + erisilebilirlik (storefront lazy, lang=tr, aria-label)
#  - Ticimax "Cek" gercek hata + sayfa boyutu 100
#  - Urun: gorsel siralama + Trendyol eksiksiz ozellik + zorunlu kirmizi
#  - Ticimax iade sekmesi + SEO uclusu
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok."; exit 1; fi
# --- Ticimax WS domain fix (kritik) ---
grep -q 'ticimaxeticaret.com' backend/ticimax_client.py || { echo "HATA: set_domain panel-adres korumasi yok."; exit 1; }
# --- Onceki isler ---
grep -q "first_error" backend/routes/integrations.py || { echo "HATA: Ticimax first_error yok."; exit 1; }
grep -q "safe_page_size" backend/routes/integrations.py || { echo "HATA: safe_page_size yok."; exit 1; }
grep -q 'html lang="tr"' frontend/public/index.html || { echo "HATA: lang=tr yok."; exit 1; }
grep -q 'lazy(() => import("./pages/Category"))' frontend/src/App.js || { echo "HATA: code-split yok."; exit 1; }
grep -q "reorderImages" frontend/src/pages/admin/Products.jsx || { echo "HATA: Gorsel siralama yok."; exit 1; }
grep -q "tyMerged" frontend/src/pages/admin/Products.jsx || { echo "HATA: Trendyol eksiksiz ozellik yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax WS domain fix: panel adresini reddet, magaza domainini kullan (getroottree hatasi cozuldu; siparis+urun+stok+uye+kategori) (+onceki isler)" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Railway backend'i yeniden baslatacak. ~1-2 dk."
echo ""
echo "  KONTROL (deploy sonrasi):"
echo "   1. Iadeler > Ticimax > 'Ticimax'tan Cek' -> artik calismali"
echo "      (yesil: 'X yeni siparis eklendi'). getroottree hatasi gitmis olmali."
echo "   2. 2984/2985 atadigin urunleri TEKRAR cek (Katalog > Ticimax urun cekme)."
echo "      Artik dogru domaine gidecegi icin gelmeli."
echo "  NOT: Sorun db'deki Ticimax 'domain' ayari panel adresi (ticimaxeticaret.com)"
echo "       oldugu icindi. Istersen Entegrasyonlar > Ticimax ayarinda domaini"
echo "       www.facette.com.tr yap; kod yine de panel adresini otomatik yok sayar."
echo "============================================"
