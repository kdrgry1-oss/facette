#!/bin/bash
# ============================================================
# FACETTE DEPLOY — SEO uclusu + Ticimax IADE siparisleri sekmesi
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Facette proje kokune koy. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
# Yeni dosyalar yerinde mi
if [ ! -f backend/routes/ticimax_returns.py ]; then echo "HATA: backend/routes/ticimax_returns.py yok. unzip eksik."; exit 1; fi
if [ ! -f frontend/src/pages/admin/TicimaxReturns.jsx ]; then echo "HATA: TicimaxReturns.jsx yok. unzip eksik."; exit 1; fi
if [ ! -f backend/routes/seo.py ]; then echo "HATA: seo.py yok. unzip eksik."; exit 1; fi
grep -q "ticimax_returns_router" backend/server.py || { echo "HATA: server.py'da ticimax_returns_router include edilmemis."; exit 1; }
grep -q "TicimaxReturns" frontend/src/pages/admin/Returns.jsx || { echo "HATA: Returns.jsx'e Ticimax sekmesi eklenmemis."; exit 1; }
echo "==> Tum dosyalar dogrulandi (SEO uclusu + Ticimax iade sekmesi)."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax iade/kismi iade siparisleri sekmesi (odeme tipi + durum degistirme) + SEO uclusu" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI."
echo "  Railway (backend) + Cloudflare (frontend) build alacak. ~2-4 dk."
echo ""
echo "  KULLANIM (deploy sonrasi):"
echo "   1. Admin > Iadeler > 'Ticimax' sekmesi"
echo "   2. 'Ticimax'tan Cek' butonu -> iade/kismi iade siparisleri gelir"
echo "      (ilk cekim birkac dakika surebilir)"
echo "   3. Her satirda odeme tipi gorunur; durum dropdown'undan degistirilebilir"
echo "      (durum degisince musteriye SMS/e-posta gider)"
echo "============================================"
