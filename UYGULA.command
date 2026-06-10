#!/bin/bash
# ============================================================
# FACETTE DEPLOY — Ticimax senkron + bildirimler + SEO ÜÇLÜSÜ (sitemap/robots/JSON-LD)
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Bu dosyayi facette proje kokune koy. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
if [ ! -f backend/routes/ticimax_member_sync.py ]; then echo "HATA: Yeni dosyalar yerine konmamis. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -f backend/routes/seo.py ]; then echo "HATA: backend/routes/seo.py yok. unzip eksik."; exit 1; fi
if [ ! -f frontend/public/robots.txt ]; then echo "HATA: frontend/public/robots.txt yok. unzip eksik."; exit 1; fi
grep -q "seo_router" backend/server.py || { echo "HATA: server.py'da seo_router include edilmemis."; exit 1; }
grep -q "application/ld+json" frontend/src/pages/ProductDetail.jsx || { echo "HATA: ProductDetail.jsx'te JSON-LD yok."; exit 1; }
echo "==> SEO uclusu dogrulandi (sitemap.xml + robots.txt + JSON-LD)."
echo "==> Tum degisiklikler dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "SEO uclusu: dinamik sitemap.xml + robots.txt + urun JSON-LD yapisal veri" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI."
echo "  Railway (backend) + Cloudflare (frontend) build alacak."
echo "  Frontend dosyalari degisti (robots.txt + ProductDetail.jsx) -> Cloudflare de build eder."
echo "  ~2-4 dk sonra canli."
echo ""
echo "  KONTROL (deploy sonrasi):"
echo "   - https://facette.com.tr/robots.txt        (Sitemap satiri gorunmeli)"
echo "   - https://api.facette.com.tr/sitemap.xml   (urun+kategori URL'leri)"
echo "   - Bir urun sayfasi -> Kaynak -> 'application/ld+json' araminda gorunur"
echo "   - Google Rich Results Test'e urun URL'i yapistir."
echo "============================================"
