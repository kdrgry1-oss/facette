"""One-off: Re-parse product descriptions to populate attributes,
without touching variants/sizes (which come from SOAP)."""
import asyncio
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from routes.deps import db  # noqa: E402

# Wider label set + multiple aliases
LABELS = [
    ("Ürün Bilgisi",           "urun_bilgisi"),
    ("Kumaş & İçerik Bilgisi", "kumas"),
    ("Kumaş ve İçerik",        "kumas"),
    ("Kumaş İçeriği",          "kumas"),
    ("Kumaş içeriği",          "kumas"),
    ("Kumaş Bilgisi",          "kumas"),
    ("Kumaş",                  "kumas"),
    ("Materyal",               "materyal"),
    ("İçerik",                 "icerik"),
    ("Kalıp",                  "kalip"),
    ("Beden Ölçüleri",         "beden_olculeri"),
    ("STD Beden Ölçüleri",     "beden_olculeri"),
    ("Model Ölçüleri",         "model_olculeri"),
    ("Yıkama Talimatı",        "yikama"),
    ("Yıkama",                 "yikama"),
    ("Bakım Talimatı",         "bakim"),
    ("Bakım",                  "bakim"),
    ("Astar Bilgisi",          "astar"),
    ("Astar",                  "astar"),
    ("Renk",                   "renk"),
    ("Ürün Kodu",              "urun_kodu"),
]


def parse_html_attrs(html_text: str) -> dict:
    if not html_text:
        return {}
    text = html.unescape(html_text)
    text = re.sub(r"<\s*br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</\s*(p|div|li|tr|h\d)\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|\u00a0", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text).strip()

    label_pattern = "|".join(re.escape(lbl) for lbl, _ in LABELS)
    splitter = re.compile(rf"(?:^|\n)\s*({label_pattern})\s*:?\s*", re.IGNORECASE)
    parts = splitter.split(text)
    attrs: dict = {}
    if len(parts) <= 1:
        return attrs
    i = 1
    while i < len(parts) - 1:
        lbl_raw = parts[i].strip()
        val = parts[i + 1].strip()
        val = re.sub(r"\s+", " ", val).strip()
        # match LABELS — first occurrence wins (don't overwrite)
        slug = next(
            (s for n, s in LABELS if n.lower() == lbl_raw.lower()), None
        )
        if slug and val and slug not in attrs:
            attrs[slug] = {"label": lbl_raw, "value": val[:600]}
        i += 2
    return attrs


async def main():
    prods = await db.products.find(
        {"source": "xml_feed"}, {"_id": 0, "id": 1, "description": 1, "name": 1}
    ).to_list(None)
    updated = 0
    enriched = 0
    for p in prods:
        attrs = parse_html_attrs(p.get("description") or "")
        await db.products.update_one(
            {"id": p["id"]}, {"$set": {"attributes": attrs}}
        )
        updated += 1
        if attrs:
            enriched += 1
    print(f"Updated {updated} products, enriched {enriched} with attributes.")


if __name__ == "__main__":
    asyncio.run(main())
