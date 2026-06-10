#!/bin/bash
# ============================================================
# FACETTE DEPLOY — Ticimax kategori senkronu + fatura + iade bildirimleri (kismi iade dahil)
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"
if [ ! -d backend ]; then echo "HATA: 'backend' yok. Bu dosyayi facette proje kokune koy. Once: unzip -o facette_update.zip -d ."; exit 1; fi
if [ ! -d .git ]; then echo "HATA: '.git' yok. Repo koku degilsin."; exit 1; fi
if [ ! -f backend/routes/ticimax_category_sync.py ]; then echo "HATA: Yeni dosyalar yerine konmamis. Once: unzip -o facette_update.zip -d ."; exit 1; fi
echo "==> Degisiklikler dogrulandi."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax kategori senkronu (En Yeniler) + fatura fix + iade/kismi-iade bildirimleri" || echo "   (commit edilecek yeni degisiklik yok)"
git push
echo ""
echo "============================================"
echo "  GONDERILDI."
echo "  Railway (backend) + Cloudflare (frontend) build alacak."
echo "  Bu pakette 1 frontend dosyasi var (Account.jsx) -> Cloudflare de build eder."
echo "  ~2-4 dk sonra canli."
echo "============================================"
