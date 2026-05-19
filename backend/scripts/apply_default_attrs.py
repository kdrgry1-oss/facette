"""Tüm ürünlere sabit/varsayılan değerleri zorla yazar:
  - Cinsiyet = Kadın
  - Yaş Grubu = Yetişkin
  - Menşei   = TR

Ayrıca KATEGORİ-bazlı default'lar:
  - Elbise/Tunik kategorisinde "Boy" değeri ürün adından çıkarılır (Maxi/Midi/Mini)
  - Pantolon/Şort/Etek için "Bel" default
  - Şort/Bermuda → Kol Boyu = Kolsuz (mantıksız çıkarımı kaldırır)

Mevcut manuel girilen değerler KORUNUR; sadece BOŞ olan alanlar doldurulur.

Run: `python /app/backend/scripts/apply_default_attrs.py`
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes.deps import db  # noqa: E402


# Tüm ürünlere uygulanacak hard-default'lar
GLOBAL_DEFAULTS = {
    "Cinsiyet": "Kadın",
    "Yaş Grubu": "Yetişkin",
    "Menşei": "TR",
}


# Kategori → ek default'lar (örn. tüm "Şort"larda Kol Boyu=Kolsuz)
CATEGORY_DEFAULTS = {
    # category name lowercased → defaults dict
    "şort": {"Kol Boyu": "Kolsuz"},
    "bermuda": {"Kol Boyu": "Kolsuz"},
    "askılı": {"Kol Boyu": "Askılı"},
    "büstiyer": {"Kol Boyu": "Askılı"},
    "atlet": {"Kol Boyu": "Kolsuz"},
    "etek": {"Kol Boyu": "Yok"},
    "pantolon": {"Kol Boyu": "Yok"},
    "tulum": {},
}


# Üründen "Boy" çıkarımı (sadece elbise/etek/tulum gibi alt kategoriler için)
BOY_CATEGORIES = {"elbise", "tulum", "etek", "tunik"}
BOY_KEYWORDS = [
    ("maxi", "Maxi"),
    ("midi", "Midi"),
    ("mini", "Mini"),
    ("uzun", "Uzun"),
    ("kısa", "Kısa"),
]


def _norm(s: str) -> str:
    return (s or "").lower().strip()


async def main():
    prods = await db.products.find(
        {"source": {"$in": ["xml_feed", "ticimax", "csv_xml_merge"]}},
        {"_id": 0, "id": 1, "name": 1, "category_name": 1,
         "attributes": 1, "hepsiburada_attributes": 1, "temu_attributes": 1},
    ).to_list(None)

    total = len(prods)
    changed = 0
    counts: dict[str, int] = {}

    for p in prods:
        cat = _norm(p.get("category_name") or "")
        name = _norm(p.get("name") or "")

        attrs = p.get("attributes") or {}
        if isinstance(attrs, list):
            # Eski Trendyol array shape'ini dict'e çevir
            new_dict = {}
            for it in attrs:
                if isinstance(it, dict) and it.get("name"):
                    new_dict[it["name"]] = str(it.get("value", ""))
            attrs = new_dict
        hb = p.get("hepsiburada_attributes") or {}
        temu = p.get("temu_attributes") or {}

        # 1) Global defaults
        applied_changes = False
        for k, v in GLOBAL_DEFAULTS.items():
            for target in (attrs, hb, temu):
                if not target.get(k):
                    target[k] = v
                    counts[k] = counts.get(k, 0) + 1
                    applied_changes = True

        # 2) Kategori defaults
        cat_defaults = {}
        for ckey, vals in CATEGORY_DEFAULTS.items():
            if ckey in cat:
                cat_defaults.update(vals)
        for k, v in cat_defaults.items():
            for target in (attrs, hb, temu):
                if not target.get(k):
                    target[k] = v
                    counts[k] = counts.get(k, 0) + 1
                    applied_changes = True

        # 3) "Boy" — sadece elbise/etek/tulum/tunik için ad'dan çıkar
        if any(c in cat for c in BOY_CATEGORIES) or any(c in name for c in BOY_CATEGORIES):
            if not attrs.get("Boy"):
                for kw, val in BOY_KEYWORDS:
                    if kw in name:
                        for target in (attrs, hb, temu):
                            if not target.get("Boy"):
                                target["Boy"] = val
                                counts["Boy"] = counts.get("Boy", 0) + 1
                                applied_changes = True
                        break

        if applied_changes:
            await db.products.update_one(
                {"id": p["id"]},
                {"$set": {
                    "attributes": attrs,
                    "hepsiburada_attributes": hb,
                    "temu_attributes": temu,
                }},
            )
            changed += 1

    print(f"✅ {changed}/{total} ürüne default uygulandı.")
    print("Eklenen alan dağılımı (her marketplace için ayrı sayar):")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"   {v:5d}  {k}")


if __name__ == "__main__":
    asyncio.run(main())
