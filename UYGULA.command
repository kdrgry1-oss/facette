#!/bin/bash
# ============================================================
# FACETTE DEPLOY — Ticimax kategori senkronu + fatura + iade bildirimleri
# Kullanim: once  unzip -o facette_update.zip -d .   sonra  bash UYGULA.command
# ============================================================
set -e
cd "$(dirname "$0")"
echo "==> Calisma klasoru: $(pwd)"

if [ ! -d backend ]; then
  echo "HATA: 'backend' klasoru yok. Bu dosyayi facette proje kokune koy."
  echo "      Once:  unzip -o facette_update.zip -d ."
  exit 1
fi
if [ ! -d .git ]; then
  echo "HATA: '.git' yok. Repo koku degilsin. Dogru klasore tasi."
  exit 1
fi
if [ ! -f backend/routes/ticimax_category_sync.py ]; then
  echo "HATA: Yeni dosyalar yerine konmamis."
  echo "      Once:  unzip -o facette_update.zip -d ."
  exit 1
fi

echo "==> Degisiklikler dogrulandi (kategori senkronu dosyasi mevcut)."
echo "==> Git: add + commit + push ..."
git add -A
git commit -m "Ticimax kategori senkronu (En Yeniler) + fatura fix + iade bildirimleri" || echo "   (commit edilecek yeni degisiklik yok)"
git push

echo ""
echo "============================================"
echo "  GONDERILDI. Railway (backend) build alacak."
echo "  Railway loglarinda 'Uvicorn running' gor."
echo "  Bu pakette frontend yok; Cloudflare degismez."
echo "============================================"
