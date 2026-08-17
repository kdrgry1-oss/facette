"""Rapor dedup — ticimax_history ÇİFT kayıtlarını rapor toplamlarından HARİÇ tutar.

Arka plan: Ticimax geçmiş aktarımı (`imported_from="ticimax_history"`) bazı Trendyol
siparişlerini, CANLI Trendyol sync'inde de var olan siparişlerle ÇİFT oluşturdu.
Bu ticimax kopyasının `ticimax_siparis_no` alanı `TY-<ticimaxId>_<GERÇEK_TY_NO>`
biçimindedir; son `_` segmenti (GERÇEK_TY_NO) bir CANLI (native) siparişin
`order_number` değeriyle eşleşir. Kopyanın KENDİ `order_number`'ı ise ticimax id'sidir
(native ile çakışmaz). Böyle bir kopya raporda aynı satışı İKİNCİ kez saydırır.

Bu modül SALT-OKUNUR sorgu-zamanı filtresi üretir — HİÇBİR belgeyi silmez/değiştirmez.
Twin'i OLMAYAN gerçek geçmiş kayıtlara (6791 tekil) DOKUNMAZ; yalnız twin'i olan
kopyalar rapor $match'lerinden düşülür. Sonuç kısa süre cache'lenir (geçmiş veri statik;
backfill tamamlandı). Cache, router'lara eklenen `load_dup_dep` bağımlılığıyla her
istekte tazelenir; `dup_nor()` senkron erişimci tazelenmiş cache'i okur.
"""
import time
from typing import List

from .deps import db

_TTL = 1800.0  # 30 dk — geçmiş veri statik; sık taramaya gerek yok
_cache = {"at": -1e9, "nums": None}  # type: ignore


async def load_dup_order_numbers() -> List[str]:
    """Twin'i olan ticimax_history kopyalarının KENDİ order_number'larını döndürür.

    $lookup ile: her ticimax_history belgesi için gömülü GERÇEK_TY_NO
    (ticimax_siparis_no'nun son '_' segmenti) native (ticimax_history OLMAYAN) bir
    order_number ile eşleşiyorsa, o kopya ÇİFT'tir. order_number index'i kullanılır.
    Hata/boşlukta önceki cache (veya boş) döner — rapor asla patlamaz.
    """
    now = time.monotonic()
    c = _cache
    if c["nums"] is not None and (now - c["at"]) < _TTL:
        return c["nums"]
    nums: List[str] = []
    try:
        pipeline = [
            {"$match": {"imported_from": "ticimax_history"}},
            {"$project": {
                "order_number": 1,
                "_emb": {"$arrayElemAt": [
                    {"$split": [{"$ifNull": ["$ticimax_siparis_no", ""]}, "_"]}, -1]},
            }},
            {"$lookup": {
                "from": "orders",
                "let": {"e": "$_emb"},
                "pipeline": [
                    {"$match": {"$expr": {"$and": [
                        {"$eq": ["$order_number", "$$e"]},
                        {"$ne": ["$imported_from", "ticimax_history"]},
                    ]}}},
                    {"$limit": 1},
                    {"$project": {"_id": 1}},
                ],
                "as": "_twin",
            }},
            {"$match": {"_twin.0": {"$exists": True}}},
            {"$project": {"_id": 0, "order_number": 1}},
        ]
        async for r in db.orders.aggregate(pipeline):
            on = r.get("order_number")
            if on is not None:
                nums.append(str(on))
    except Exception:
        return c["nums"] or []
    c["nums"] = nums
    c["at"] = now
    return nums


def dup_nor() -> dict:
    """Senkron erişimci: rapor $match'ine eklenecek hariç-tutma parçası (veya {}).

    `{"$nor": [{imported_from: ticimax_history, order_number: {$in: [...]}}]}` —
    yalnız twin'i olan ticimax kopyalarını düşürür; native twin ve tekil geçmiş kalır.
    Cache `load_dup_dep` bağımlılığıyla tazelenmiş olmalı; boşsa {} döner (no-op).
    """
    nums = _cache["nums"]
    if not nums:
        return {}
    return {"$nor": [{"imported_from": "ticimax_history",
                      "order_number": {"$in": nums}}]}


def merge_match(base: dict) -> dict:
    """Bir $match dict'ine dup hariç-tutmayı (varsa) ekler. base'i mutasyona uğratmaz."""
    nor = dup_nor()
    if not nor:
        return base
    out = dict(base or {})
    out.update(nor)  # top-level $nor; mevcut $or/status/tarih anahtarlarıyla AND'lenir
    return out


async def load_dup_dep():
    """Router bağımlılığı — handler'dan ÖNCE cache'i tazeler (salt-okuma)."""
    try:
        await load_dup_order_numbers()
    except Exception:
        pass
    return True
