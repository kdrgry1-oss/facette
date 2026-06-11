#!/bin/bash
cd "$(dirname "$0")"
echo "== Ticimax TÜM sipariş çekimi (≤5 Haz 2026, TicimaxWeb) — kaldığı yerden devam =="
python3 -c "import pymongo,zeep" 2>/dev/null || pip3 install pymongo zeep -q
python3 tum_siparis_cek.py
echo ""
read -p "Kapatmak için Enter'a bas..."
