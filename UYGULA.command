#!/bin/bash
# ============================================================
# FACETTE DEPLOY (KUMULATIF) — TUM bekleyen isler tek pakette
#  A) Kapida odeme: storefronttan kaldirildi (admin panelden acilabilir) + koruma + migration.
#  B) Checkout adres kaydi + mukerrer uyelik engeli (email/telefon) + telefon alani dogrulamasi.
#  C) Iadeler sayfasi:
#     - "Ticimax" sekmesi KALDIRILDI; icerigi "Web Sitesi" altina tasindi
#       (Web Sitesi'nde: "Siparis Iadeleri" + "Site Iade Talepleri" ic gecisi).
#     - Durum listesine TUM siparis durumlari eklendi (filtre + satir dropdown).
#     - Her siparis detayinda: musteri, urunler (adet x birim = satir tutari),
#       tutar dokumu, iade/iptal durumu.
#  D) "Google Merchant" XML feed kaydi otomatik olusturulur (XML Feed'ler sayfasinda gorunur);
#     /api/products/feed/google-merchant.xml -> google-merchant-feed.xml ile birebir format.
# Kullanim: repo kokunde (.git olan klasor):  unzip -o facette_update.zip -d .  sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo kokunde calistir (unzip'i .git olan klasore yap)."; exit 1; fi

# A
grep -q "_cod_default_off_v1" backend/server.py || { echo "HATA: kapida migration yok."; exit 1; }
grep -q "enabledPM\[key\]" frontend/src/pages/Checkout.jsx || { echo "HATA: checkout odeme filtreleme yok."; exit 1; }
# B
grep -q "_save_guest_address" backend/routes/auth.py || { echo "HATA: misafir adres kaydedici yok."; exit 1; }
grep -q "URLSearchParams" frontend/src/context/AuthContext.jsx || { echo "HATA: register telefon gonderimi yok."; exit 1; }
# C
grep -q "siteView" frontend/src/pages/admin/Returns.jsx || { echo "HATA: Iadeler birlestirme yok."; exit 1; }
grep -q "out_for_delivery" frontend/src/pages/admin/TicimaxReturns.jsx || { echo "HATA: tum durumlar eklenmemis."; exit 1; }
grep -q "Kaynak No" frontend/src/pages/admin/TicimaxReturns.jsx || { echo "HATA: zengin detay yok."; exit 1; }
grep -q "billing_address" backend/routes/ticimax_returns.py || { echo "HATA: backend detay zenginlestirme yok."; exit 1; }
# D
grep -q "_google_feed_seeded_v1" backend/server.py || { echo "HATA: google feed seed yok."; exit 1; }
echo "==> Tum dosyalar dogrulandi (A+B+C+D)."

echo "==> Git: add + commit + push ..."
git add -A
git commit -m "feat: iadeler ticimax->web sitesi birlesimi + tum durumlar + zengin siparis detayi + google xml feed seed (kapida/checkout/uyelik isleriyle kumulatif)" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI. Railway + Cloudflare Pages ~1-3 dk icinde yeniden kurar."
echo ""
echo "  KONTROL:"
echo "   * Iadeler: 'Ticimax' sekmesi yok; Web Sitesi altinda Siparis Iadeleri / Site Iade Talepleri."
echo "   * Durum dropdown'unda tum siparis durumlari secilebilir."
echo "   * Bir siparisi acinca musteri + urunler + tutar dokumu gorunur."
echo "   * SEO/Pazarlama > XML Feed'ler'de 'Google Merchant' feed'i hazir:"
echo "     /api/products/feed/google-merchant.xml"
echo "============================================"
