"""
=============================================================================
hb_aktarim.py — "Özel HB Aktarım" modülü (clean-room, yalnız Hepsiburada API'si)
=============================================================================

Bu modül sistemin diğer pazaryeri kodlarından BAĞIMSIZDIR. Tüm alan/kategori/özellik
yapısı Hepsiburada resmi API dökümantasyonundan gelir (bkz. hb_aktarim_client.py).
Sistemden alınan TEK şey kimlik bilgisidir (merchant id + secret key + dev username) —
o da yalnızca "FACETTE'ten kopyala" ucunda, mevcut HB kimliğini bu modüle taşımak için.

KOLEKSİYONLAR (hepsi 'hb_aktarim_' önekli, izole):
  hb_aktarim_config       : { _id:"credentials", merchant_id, secret_key, dev_username,
                              env, oms_username, oms_password, updated_at }
  hb_aktarim_categories   : HB kategori ağacı cache'i (_id = HB kategori id)
  hb_aktarim_attributes   : kategori özellik şeması cache'i (_id = HB kategori id)
  hb_aktarim_attr_values  : özellik enum değer cache'i (_id = "{catId}:{attrId}")

Prefix: /api/hb-aktarim
=============================================================================
"""
from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import asyncio

from .deps import db, require_admin
from hb_aktarim_client import HBAktarimClient, HBAktarimError

router = APIRouter(prefix="/hb-aktarim", tags=["HB Aktarım"])

_PROD_ENVS = ("prod", "production", "live", "canli", "canlı")
# Değer listesi OLMAYAN (enum/eşleştirilemez) özellik tipleri — HB döküman tiplerine göre.
_NOVALUE_TYPES = {
    "numeric", "number", "integer", "int", "long", "decimal", "float", "double",
    "boolean", "bool", "date", "datetime", "time", "year",
    "textarea", "longtext", "html", "richtext",
    "url", "link", "image", "media", "file", "video", "barcode",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _is_masked(s: Optional[str]) -> bool:
    s = (s or "").strip()
    return (not s) or set(s) <= {"*", "•", "·"}


def _mask(s: Optional[str]) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= 4:
        return "•" * len(s)
    return s[:2] + "•" * max(4, len(s) - 4) + s[-2:]


async def _get_config() -> Dict[str, Any]:
    return await db.hb_aktarim_config.find_one({"_id": "credentials"}, {"_id": 0}) or {}


def _public_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """UI'ya dönecek güvenli görünüm — secret asla düz dönmez."""
    env = (cfg.get("env") or "").strip().lower()
    return {
        "merchant_id": cfg.get("merchant_id") or "",
        "dev_username": cfg.get("dev_username") or "",
        "secret_key_masked": _mask(cfg.get("secret_key")),
        "secret_key_set": bool((cfg.get("secret_key") or "").strip()),
        "oms_username": cfg.get("oms_username") or "",
        "oms_password_set": bool((cfg.get("oms_password") or "").strip()),
        "env": env or "sandbox",
        "is_live": env in _PROD_ENVS,
        "configured": bool((cfg.get("merchant_id") or "").strip()
                           and (cfg.get("secret_key") or "").strip()
                           and (cfg.get("dev_username") or "").strip()),
        "updated_at": cfg.get("updated_at"),
    }


async def _build_client():
    """Kayıtlı kimlikten HB istemcisi kurar. Döner: (client, hata_mesajı|None)."""
    cfg = await _get_config()
    mid = (cfg.get("merchant_id") or "").strip()
    sk = (cfg.get("secret_key") or "").strip()
    du = (cfg.get("dev_username") or "").strip()
    if not (mid and sk and du):
        return None, ("HB kimlik bilgileri eksik (Merchant ID / Secret Key / Developer "
                      "Username). Önce 'Kimlik' sekmesinden kaydedin.")
    env = (cfg.get("env") or "").strip().lower()
    test = env not in _PROD_ENVS
    try:
        client = HBAktarimClient(
            mid, sk, du, test=test,
            oms_username=cfg.get("oms_username") or None,
            oms_password=cfg.get("oms_password") or None,
        )
    except Exception as e:
        return None, f"İstemci kurulamadı: {e}"
    return client, None


# ===================================================================== #
#  KİMLİK (credentials)
# ===================================================================== #
@router.get("/credentials")
async def get_credentials(current_user: dict = Depends(require_admin)):
    return _public_config(await _get_config())


@router.post("/credentials")
async def save_credentials(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_admin),
):
    cfg = await _get_config()
    out = dict(cfg)

    if "merchant_id" in payload:
        out["merchant_id"] = (payload.get("merchant_id") or "").strip()
    if "dev_username" in payload:
        out["dev_username"] = (payload.get("dev_username") or "").strip()
    if "oms_username" in payload:
        out["oms_username"] = (payload.get("oms_username") or "").strip()
    if "env" in payload:
        env = (payload.get("env") or "").strip().lower()
        out["env"] = "prod" if env in _PROD_ENVS else "sandbox"

    # secret: maske gelirse mevcut korunur (UI gizli alanı boş/maske gönderebilir)
    if "secret_key" in payload and not _is_masked(payload.get("secret_key")):
        out["secret_key"] = (payload.get("secret_key") or "").strip()
    if "oms_password" in payload and not _is_masked(payload.get("oms_password")):
        out["oms_password"] = (payload.get("oms_password") or "").strip()

    out["updated_at"] = _now()
    out.pop("_id", None)
    await db.hb_aktarim_config.update_one({"_id": "credentials"}, {"$set": out}, upsert=True)
    return _public_config(out)


@router.post("/credentials/copy-from-facette")
async def copy_credentials_from_facette(current_user: dict = Depends(require_admin)):
    """Sistemden alınan TEK veri: mevcut HB kimliği. db.marketplace_accounts(hepsiburada) ve
    db.settings(hepsiburada) içinden SADECE merchant_id + secret_key + dev_username (+ortam)
    okunur ve bu modülün config'ine yazılır. Başka hiçbir alan/yapı taşınmaz."""
    acc = await db.marketplace_accounts.find_one({"key": "hepsiburada"}, {"_id": 0}) or {}
    cr = acc.get("credentials") or {}
    s = await db.settings.find_one({"id": "hepsiburada"}, {"_id": 0}) or {}

    def pick(*vals):
        for v in vals:
            v = (str(v).strip() if v is not None else "")
            if v and not _is_masked(v):
                return v
        return ""

    mid = pick(cr.get("merchant_id"), s.get("merchant_id"))
    sk = pick(cr.get("secret_key"), cr.get("password"), s.get("secret_key"), s.get("password"))
    du = pick(cr.get("dev_username"), s.get("dev_username"))
    env = pick(cr.get("env"), cr.get("mode"), s.get("mode"), s.get("env")).lower()
    oms_u = pick(cr.get("oms_username"), s.get("oms_username"))
    oms_p = pick(cr.get("oms_password"), s.get("oms_password"))

    found = {"merchant_id": bool(mid), "secret_key": bool(sk), "dev_username": bool(du)}
    if not (mid or sk or du):
        raise HTTPException(404, "FACETTE'te kayıtlı Hepsiburada kimliği bulunamadı "
                                 "(marketplace_accounts / settings).")

    cfg = await _get_config()
    out = dict(cfg)
    if mid:
        out["merchant_id"] = mid
    if sk:
        out["secret_key"] = sk
    if du:
        out["dev_username"] = du
    if oms_u:
        out["oms_username"] = oms_u
    if oms_p:
        out["oms_password"] = oms_p
    if env:
        out["env"] = "prod" if env in _PROD_ENVS else "sandbox"
    out["updated_at"] = _now()
    out.pop("_id", None)
    await db.hb_aktarim_config.update_one({"_id": "credentials"}, {"$set": out}, upsert=True)
    return {"copied": found, "config": _public_config(out)}


@router.get("/test")
async def test_connection(current_user: dict = Depends(require_admin)):
    """Kimlik + ortam doğrulaması — 1 kategori çekmeyi dener."""
    client, err = await _build_client()
    if err:
        return {"ok": False, "error": err}
    cfg = await _get_config()
    try:
        res = await asyncio.to_thread(client.ping)
        return {"ok": True, "env": ("prod" if not client.test else "sandbox"),
                "merchant_id": client.merchant_id, "sample_count": res.get("sample_count", 0)}
    except HBAktarimError as e:
        return {"ok": False, "env": ("prod" if not client.test else "sandbox"), "error": str(e)}
    except Exception as e:  # noqa
        return {"ok": False, "error": f"Beklenmeyen hata: {e}"}


# ===================================================================== #
#  KATEGORİLER (HB ağacı, cache'li)
# ===================================================================== #
def _norm_category(c: Dict[str, Any]) -> Dict[str, Any]:
    cid = c.get("categoryId", c.get("id"))
    return {
        "_id": cid,
        "hb_id": cid,
        "name": c.get("name") or c.get("displayName") or "",
        "parent_id": c.get("parentCategoryId", c.get("parentId")),
        "leaf": bool(c.get("leaf", True)),
        "available": bool(c.get("available", True)),
        "status": c.get("status") or "ACTIVE",
        "paths": c.get("paths") or c.get("categoryTree") or [],
    }


async def _category_count() -> int:
    return await db.hb_aktarim_categories.count_documents({})


async def _refresh_categories() -> int:
    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    try:
        rows = await asyncio.to_thread(client.iter_categories, True, True, True, 2000)
    except HBAktarimError as e:
        raise HTTPException(502, f"HB kategori çekme hatası: {e}")
    if not rows:
        return 0
    # toplu upsert
    ops = []
    from pymongo import ReplaceOne
    for c in rows:
        doc = _norm_category(c)
        if doc["_id"] is None:
            continue
        ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
    if ops:
        await db.hb_aktarim_categories.bulk_write(ops, ordered=False)
    return len(ops)


@router.post("/categories/refresh")
async def refresh_categories(current_user: dict = Depends(require_admin)):
    n = await _refresh_categories()
    return {"refreshed": n, "total": await _category_count()}


@router.get("/categories")
async def list_categories(
    search: str = "",
    limit: int = 50,
    current_user: dict = Depends(require_admin),
):
    """HB leaf kategorilerini arar. Cache boşsa otomatik bir kez çeker."""
    if await _category_count() == 0:
        await _refresh_categories()
    q: Dict[str, Any] = {"leaf": True}
    s = (search or "").strip()
    if s:
        # Türkçe-duyarsız regex
        import re as _re
        q["name"] = {"$regex": _re.escape(s), "$options": "i"}
    limit = max(1, min(int(limit or 50), 200))
    cur = db.hb_aktarim_categories.find(q, {"_id": 0}).limit(limit)
    rows = await cur.to_list(length=limit)
    return {"total_cached": await _category_count(), "count": len(rows), "categories": rows}


# ===================================================================== #
#  KATEGORİ ÖZELLİKLERİ (attributes — cache'li)
# ===================================================================== #
def _norm_attribute(a: Dict[str, Any]) -> Dict[str, Any]:
    typ = str(a.get("type") or "string").lower()
    return {
        "id": a.get("id") or a.get("name"),
        "name": a.get("name") or a.get("id"),
        "mandatory": bool(a.get("mandatory", False)),
        "multiValue": bool(a.get("multiValue", False)),
        "type": typ,
        # değer-eşleştirme yapılabilir mi? (enum benzeri tipler)
        "selectable": typ not in _NOVALUE_TYPES,
    }


@router.get("/categories/{category_id}/attributes")
async def get_category_attributes(
    category_id: int,
    refresh: bool = False,
    current_user: dict = Depends(require_admin),
):
    cached = await db.hb_aktarim_attributes.find_one({"_id": category_id}, {"_id": 0})
    if cached and not refresh:
        return cached

    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    try:
        data = await asyncio.to_thread(client.get_category_attributes, category_id)
    except HBAktarimError as e:
        raise HTTPException(502, f"HB özellik çekme hatası: {e}")

    base = [_norm_attribute(x) for x in (data.get("baseAttributes") or [])]
    attrs = [_norm_attribute(x) for x in (data.get("attributes") or [])]
    doc = {
        "category_id": category_id,
        "base_attributes": base,
        "attributes": attrs,
        "fetched_at": _now(),
    }
    await db.hb_aktarim_attributes.replace_one({"_id": category_id}, {**doc, "_id": category_id},
                                               upsert=True)
    return doc


@router.get("/categories/{category_id}/attributes/{attribute_id}/values")
async def get_attribute_values(
    category_id: int,
    attribute_id: str,
    refresh: bool = False,
    current_user: dict = Depends(require_admin),
):
    key = f"{category_id}:{attribute_id}"
    cached = await db.hb_aktarim_attr_values.find_one({"_id": key}, {"_id": 0})
    if cached and not refresh:
        return cached

    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    try:
        rows = await asyncio.to_thread(client.iter_attribute_values, category_id, attribute_id)
    except HBAktarimError as e:
        raise HTTPException(502, f"HB değer çekme hatası: {e}")

    values = []
    for v in rows:
        if isinstance(v, dict):
            values.append({"id": v.get("id"), "name": v.get("name") or v.get("value")})
        else:
            values.append({"id": v, "name": str(v)})
    doc = {"category_id": category_id, "attribute_id": attribute_id,
           "values": values, "count": len(values), "fetched_at": _now()}
    await db.hb_aktarim_attr_values.replace_one({"_id": key}, {**doc, "_id": key}, upsert=True)
    return doc


# ===================================================================== #
#  KATEGORİ EŞLEŞTİRME  (sol taraf = sistem kategorileri, sağ = HB leaf)
#  Sol tarafı sistemin KENDİ kategorilerinden okuruz — bu, isteğin gereği
#  ("sistemdeki değerlerle HB değerlerini eşleştir"). HB tarafı dökümandan.
# ===================================================================== #
async def _system_categories() -> List[Dict[str, Any]]:
    rows = await db.categories.find(
        {}, {"_id": 0, "id": 1, "name": 1, "parent_id": 1, "is_active": 1}
    ).to_list(length=10000)
    by_id = {r.get("id"): r for r in rows if r.get("id")}

    def build_path(r):
        names, seen, cur = [], set(), r
        while cur and cur.get("id") not in seen:
            seen.add(cur.get("id"))
            if cur.get("name"):
                names.append(cur["name"])
            cur = by_id.get(cur.get("parent_id"))
        return " > ".join(reversed(names))

    out = []
    for r in rows:
        if not r.get("id"):
            continue
        out.append({
            "id": r["id"],
            "name": r.get("name") or "",
            "path": build_path(r) or (r.get("name") or ""),
            "is_active": bool(r.get("is_active", True)),
        })
    out.sort(key=lambda x: x["path"].lower())
    return out


@router.get("/mappings/categories")
async def list_category_mappings(
    search: str = "",
    only_unmatched: bool = False,
    limit: int = 1000,
    current_user: dict = Depends(require_admin),
):
    cats = await _system_categories()
    maps_list = await db.hb_aktarim_category_map.find({}, {"_id": 0}).to_list(length=20000)
    maps = {m.get("system_category_id"): m for m in maps_list}

    s = (search or "").strip().lower()
    rows, matched = [], 0
    for c in cats:
        m = maps.get(c["id"])
        is_matched = bool(m and m.get("hb_category_id"))
        if is_matched:
            matched += 1
        if only_unmatched and is_matched:
            continue
        if s and s not in c["path"].lower():
            continue
        rows.append({
            "system_category_id": c["id"],
            "system_category_name": c["name"],
            "system_category_path": c["path"],
            "is_active": c["is_active"],
            "hb_category_id": (m or {}).get("hb_category_id"),
            "hb_category_name": (m or {}).get("hb_category_name"),
            "updated_at": (m or {}).get("updated_at"),
        })
    limit = max(1, min(int(limit or 1000), 5000))
    return {
        "total": len(cats),
        "matched": matched,
        "unmatched": len(cats) - matched,
        "count": len(rows[:limit]),
        "items": rows[:limit],
    }


@router.post("/mappings/categories/{system_category_id}")
async def save_category_mapping(
    system_category_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_admin),
):
    hb_id = payload.get("hb_category_id")
    hb_name = (payload.get("hb_category_name") or "").strip()
    if hb_id in (None, ""):
        raise HTTPException(400, "hb_category_id zorunlu (HB leaf kategori seçin).")
    doc = {
        "_id": system_category_id,
        "system_category_id": system_category_id,
        "hb_category_id": hb_id,
        "hb_category_name": hb_name,
        "updated_at": _now(),
    }
    await db.hb_aktarim_category_map.replace_one({"_id": system_category_id}, doc, upsert=True)
    return {"saved": True, "mapping": {k: v for k, v in doc.items() if k != "_id"}}


@router.delete("/mappings/categories/{system_category_id}")
async def delete_category_mapping(
    system_category_id: str,
    current_user: dict = Depends(require_admin),
):
    res = await db.hb_aktarim_category_map.delete_one({"_id": system_category_id})
    return {"deleted": bool(res.deleted_count)}


# ===================================================================== #
#  KAYNAK ALAN KEŞFİ  (sol taraf — ürün dokümanından CANLI keşfedilir)
#  Hiçbir alan adı gömülü DEĞİL; gerçek ürünlerden okunur. ticimax_fields
#  (legacy + gürültü) hariç tutulur; teknik özellikler 'teknik.<k>',
#  varyant alanları 'variant.<k>' olarak yüzeye çıkar.
# ===================================================================== #
_SRC_SKIP = {"_id", "id", "ticimax_fields", "created_at", "updated_at", "view_count"}


def _is_scalar(v):
    return v is None or isinstance(v, (str, int, float, bool))


@router.get("/source-fields")
async def source_fields(current_user: dict = Depends(require_admin)):
    """Ürün dokümanlarından örnekleyerek kullanılabilir kaynak alanlarını döndürür."""
    docs = await db.products.find({}, {"ticimax_fields": 0}).limit(60).to_list(length=60)
    fields: Dict[str, str] = {}

    def note(key, val):
        if key not in fields:
            fields[key] = ""
        if not fields[key] and val not in (None, ""):
            fields[key] = str(val)[:60]

    for p in docs:
        for k, v in p.items():
            if k in _SRC_SKIP:
                continue
            if k == "variants" and isinstance(v, list):
                for it in v:
                    if isinstance(it, dict):
                        for vk, vv in it.items():
                            if vk in ("_id",) or not _is_scalar(vv):
                                continue
                            note(f"variant.{vk}", vv)
                continue
            if k == "technical_details" and isinstance(v, dict):
                for tk, tv in v.items():
                    if _is_scalar(tv):
                        note(f"teknik.{tk}", tv)
                continue
            if _is_scalar(v):
                note(k, v)
            elif isinstance(v, list) and (not v or isinstance(v[0], str)):
                note(k, (v[0] if v else ""))

    out = [{"key": k, "label": k, "sample": s} for k, s in fields.items()]
    out.sort(key=lambda x: x["key"].lower())
    return {"count": len(out), "fields": out, "scanned": len(docs)}


def _read_source(product: Dict[str, Any], field: str):
    """Bir ürün dokümanından kaynak alan değer(ler)ini okur (variant./teknik. dahil)."""
    if not field:
        return None
    if field.startswith("variant."):
        k = field.split(".", 1)[1]
        vals = []
        for it in product.get("variants") or []:
            if isinstance(it, dict) and it.get(k) not in (None, ""):
                vals.append(it.get(k))
        return vals or None
    if field.startswith("teknik."):
        k = field.split(".", 1)[1]
        return (product.get("technical_details") or {}).get(k)
    return product.get(field)


@router.get("/source-fields/values")
async def source_field_values(
    field: str,
    limit: int = 300,
    current_user: dict = Depends(require_admin),
):
    """Belirli bir kaynak alan için üründe geçen ayırt edici (distinct) değerler —
    değer eşleştirme tablosunun sol sütununu doldurur."""
    if not field:
        raise HTTPException(400, "field zorunlu")
    docs = await db.products.find({}, {"ticimax_fields": 0}).limit(3000).to_list(length=3000)
    vals = set()
    for p in docs:
        r = _read_source(p, field)
        if isinstance(r, list):
            for x in r:
                if x not in (None, ""):
                    vals.add(str(x))
        elif r not in (None, ""):
            vals.add(str(r))
    out = sorted(vals, key=lambda s: s.lower())[: max(1, min(int(limit or 300), 1000))]
    return {"field": field, "count": len(out), "values": out}


# ===================================================================== #
#  ÖZELLİK & DEĞER EŞLEŞTİRME  (HB kategori bazlı)
#  attr_map (_id = HB kategori id):
#    { hb_category_id, attributes: { "<attrId>": {
#        source: "field"|"fixed"|"valuemap"|"ignore",
#        field, fixed, value_map: {"<sistem değeri>": "<HB value id>"} } } }
# ===================================================================== #
@router.get("/mappings/used-hb-categories")
async def used_hb_categories(current_user: dict = Depends(require_admin)):
    """Kategori eşleştirmede kullanılan (en az 1 sistem kategorisi bağlı) HB kategorileri."""
    maps = await db.hb_aktarim_category_map.find({}, {"_id": 0}).to_list(length=20000)
    agg: Dict[Any, Dict[str, Any]] = {}
    for m in maps:
        hid = m.get("hb_category_id")
        if hid in (None, ""):
            continue
        e = agg.setdefault(hid, {"hb_category_id": hid,
                                 "hb_category_name": m.get("hb_category_name") or "",
                                 "system_count": 0})
        e["system_count"] += 1
    out = list(agg.values())
    for e in out:
        am = await db.hb_aktarim_attr_map.find_one({"_id": e["hb_category_id"]},
                                                   {"_id": 0, "attributes": 1})
        e["configured_attrs"] = len((am or {}).get("attributes") or {})
    out.sort(key=lambda x: (x.get("hb_category_name") or "").lower())
    return {"count": len(out), "categories": out}


@router.get("/mappings/attributes/{hb_category_id}")
async def get_attribute_map(
    hb_category_id: int,
    current_user: dict = Depends(require_admin),
):
    doc = await db.hb_aktarim_attr_map.find_one({"_id": hb_category_id}, {"_id": 0})
    return doc or {"hb_category_id": hb_category_id, "attributes": {}}


@router.post("/mappings/attributes/{hb_category_id}/{attribute_id}")
async def save_attribute_map(
    hb_category_id: int,
    attribute_id: str,
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_admin),
):
    source = (payload.get("source") or "ignore").strip().lower()
    if source not in ("field", "fixed", "valuemap", "ignore"):
        raise HTTPException(400, "source: field | fixed | valuemap | ignore olmalı")
    cfg = {
        "source": source,
        "field": (payload.get("field") or "").strip() or None,
        "fixed": payload.get("fixed"),
        "value_map": payload.get("value_map") or {},
    }
    # Dotted-key sorununu önlemek için tüm attributes objesini oku-değiştir-yaz.
    doc = await db.hb_aktarim_attr_map.find_one({"_id": hb_category_id}) or {}
    attrs = doc.get("attributes") or {}
    attrs[attribute_id] = cfg
    await db.hb_aktarim_attr_map.replace_one(
        {"_id": hb_category_id},
        {"_id": hb_category_id, "hb_category_id": hb_category_id,
         "attributes": attrs, "updated_at": _now()},
        upsert=True,
    )
    return {"saved": True, "attribute_id": attribute_id, "config": cfg}


@router.delete("/mappings/attributes/{hb_category_id}/{attribute_id}")
async def delete_attribute_map(
    hb_category_id: int,
    attribute_id: str,
    current_user: dict = Depends(require_admin),
):
    doc = await db.hb_aktarim_attr_map.find_one({"_id": hb_category_id})
    if not doc:
        return {"deleted": False}
    attrs = doc.get("attributes") or {}
    if attribute_id in attrs:
        attrs.pop(attribute_id, None)
        await db.hb_aktarim_attr_map.replace_one(
            {"_id": hb_category_id},
            {"_id": hb_category_id, "hb_category_id": hb_category_id,
             "attributes": attrs, "updated_at": _now()},
            upsert=True,
        )
        return {"deleted": True}
    return {"deleted": False}


# ===================================================================== #
#  ALAN & FİYAT KONFİGÜRASYONU  (global — kategoriden bağımsız)
#  hb_aktarim_config (_id="fields"):
#    base: { "<HB alanı>": {source:"field"|"fixed", field, fixed} }
#    price: {field, margin_pct, round}
#    stock: {field}
#    listing: {dispatch_time, cargo, max_qty}
# ===================================================================== #
HB_BASE_FIELDS = ["UrunAdi", "UrunAciklamasi", "Marka", "Barcode",
                  "merchantSku", "kg", "GarantiSuresi", "tax_vat_rate"]
HB_IMAGE_MAX = 10

DEFAULT_FIELD_CFG = {
    "base": {
        "UrunAdi": {"source": "field", "field": "name"},
        "UrunAciklamasi": {"source": "field", "field": "description"},
        "Marka": {"source": "field", "field": "brand"},
        "Barcode": {"source": "field", "field": "variant.barcode"},
        "merchantSku": {"source": "field", "field": "variant.stock_code"},
        "kg": {"source": "fixed", "fixed": "1"},
        "GarantiSuresi": {"source": "fixed", "fixed": ""},
        "tax_vat_rate": {"source": "fixed", "fixed": "20"},
    },
    "images_field": "images",
    "price": {"field": "price", "margin_pct": 0, "round": 2},
    "stock": {"field": "variant.stock"},
    "listing": {"dispatch_time": 1, "cargo": ["Yurtiçi Kargo"], "max_qty": None},
}


@router.get("/config/fields")
async def get_field_config(current_user: dict = Depends(require_admin)):
    doc = await db.hb_aktarim_config.find_one({"_id": "fields"}, {"_id": 0})
    cfg = dict(DEFAULT_FIELD_CFG)
    if doc:
        # sığ birleştir (kullanıcı kaydı varsayılanı ezer)
        for k, v in doc.items():
            cfg[k] = v
    return {"config": cfg, "hb_base_fields": HB_BASE_FIELDS,
            "cargo_companies": HBAktarimClient.CARGO_COMPANIES}


@router.post("/config/fields")
async def save_field_config(
    payload: Dict[str, Any] = Body(...),
    current_user: dict = Depends(require_admin),
):
    out = {"_id": "fields"}
    for k in ("base", "images_field", "price", "stock", "listing"):
        if k in payload:
            out[k] = payload[k]
    out["updated_at"] = _now()
    await db.hb_aktarim_config.update_one({"_id": "fields"}, {"$set": out}, upsert=True)
    return await get_field_config(current_user)  # type: ignore


# ===================================================================== #
#  PAYLOAD KURUCU  (eşleştirmelerden HB ürün/listing payload'ı üretir)
# ===================================================================== #
def _norm_sku(v) -> str:
    return ("" if v is None else str(v)).upper().replace(" ", "")


def _read_for_variant(product: Dict[str, Any], variant: Optional[Dict[str, Any]], field: Optional[str]):
    if not field:
        return None
    if field.startswith("variant."):
        return (variant or {}).get(field.split(".", 1)[1])
    if field.startswith("teknik."):
        return (product.get("technical_details") or {}).get(field.split(".", 1)[1])
    return product.get(field)


def _resolve_attr_value(acfg, product, variant, value_names):
    """value_names: {hbValueId(str): name} | None. Enum'da id→name çevirir."""
    src = acfg.get("source")
    if src == "fixed":
        fx = acfg.get("fixed")
        if value_names and fx is not None and str(fx) in value_names:
            return value_names[str(fx)]
        return fx
    if src == "field":
        return _read_for_variant(product, variant, acfg.get("field"))
    if src == "valuemap":
        raw = _read_for_variant(product, variant, acfg.get("field"))
        if raw in (None, ""):
            return None
        hid = (acfg.get("value_map") or {}).get(str(raw))
        if hid in (None, ""):
            return None
        if value_names:
            return value_names.get(str(hid), hid)
        return hid
    return None


def _build_product_items(product, hb_cat_id, merchant_id, attr_map, field_cfg, value_names_by_attr):
    """Bir sistem ürününü HB import kalemlerine çevirir (her varyant ayrı kalem, aynı VaryantGroupID).
    Döner: (items, warnings)."""
    base = field_cfg.get("base") or {}
    images_field = field_cfg.get("images_field") or "images"
    images = [u for u in (product.get(images_field) or []) if u][:HB_IMAGE_MAX]
    group_id = str(product.get("id") or product.get("stock_code") or product.get("sku") or "")
    variants = product.get("variants") or [None]
    items, warnings = [], []

    for idx, var in enumerate(variants):
        attrs: Dict[str, Any] = {}
        # merchantSku
        msku_cfg = base.get("merchantSku") or {}
        msku = (_read_for_variant(product, var, msku_cfg.get("field"))
                if msku_cfg.get("source") != "fixed" else msku_cfg.get("fixed"))
        msku = msku or product.get("stock_code") or product.get("sku") or f"{group_id}-{idx + 1}"
        attrs["merchantSku"] = _norm_sku(msku)
        attrs["VaryantGroupID"] = group_id
        # diğer temel metin alanları
        for key in ("UrunAdi", "UrunAciklamasi", "Marka", "Barcode", "kg", "GarantiSuresi", "tax_vat_rate"):
            fc = base.get(key) or {}
            val = fc.get("fixed") if fc.get("source") == "fixed" else _read_for_variant(product, var, fc.get("field"))
            if val not in (None, ""):
                attrs[key] = val
        # görseller
        for i, u in enumerate(images, 1):
            attrs[f"Image{i}"] = u
        # kategori özellikleri
        for aid, acfg in (attr_map or {}).items():
            if (acfg or {}).get("source") in (None, "ignore"):
                continue
            val = _resolve_attr_value(acfg, product, var, value_names_by_attr.get(aid))
            if val not in (None, ""):
                attrs[aid] = val
        items.append({"categoryId": hb_cat_id, "merchant": merchant_id, "attributes": attrs})
    return items, warnings


async def _gather_publish_context():
    """Yayın için gerekli bağlamı toplar: kimlik, alan cfg, kategori haritası, attr_map'ler,
    kategori şemaları (zorunlu alan kontrolü) ve enum değer adları (id→name)."""
    creds = await _get_config()
    merchant_id = (creds.get("merchant_id") or "").strip()

    fc_doc = await db.hb_aktarim_config.find_one({"_id": "fields"}, {"_id": 0})
    field_cfg = dict(DEFAULT_FIELD_CFG)
    if fc_doc:
        for k, v in fc_doc.items():
            field_cfg[k] = v

    cmap_rows = await db.hb_aktarim_category_map.find({}, {"_id": 0}).to_list(length=20000)
    sys_to_hb = {m["system_category_id"]: m for m in cmap_rows if m.get("hb_category_id") not in (None, "")}

    attr_maps = {}
    schemas = {}
    value_names = {}  # hb_cat_id -> {attr_id -> {valueId: name}}
    hb_cats = {m["hb_category_id"] for m in sys_to_hb.values()}
    for hid in hb_cats:
        am = await db.hb_aktarim_attr_map.find_one({"_id": hid}, {"_id": 0})
        attr_maps[hid] = (am or {}).get("attributes") or {}
        sch = await db.hb_aktarim_attributes.find_one({"_id": hid}, {"_id": 0})
        schemas[hid] = sch or {}
        vn = {}
        for aid, acfg in attr_maps[hid].items():
            if (acfg or {}).get("source") in ("valuemap", "fixed"):
                vdoc = await db.hb_aktarim_attr_values.find_one({"_id": f"{hid}:{aid}"}, {"_id": 0})
                if vdoc:
                    vn[aid] = {str(v.get("id")): v.get("name") for v in (vdoc.get("values") or [])}
        value_names[hid] = vn
    return merchant_id, field_cfg, sys_to_hb, attr_maps, schemas, value_names


def _mandatory_ids(schema):
    out = set()
    for grp in ("base_attributes", "attributes"):
        for a in (schema or {}).get(grp, []) or []:
            if a.get("mandatory"):
                out.add(a.get("id"))
    return out


async def _select_mapped_products(sys_to_hb, limit=None):
    sys_ids = list(sys_to_hb.keys())
    if not sys_ids:
        return []
    q = {"category_id": {"$in": sys_ids}}
    cur = db.products.find(q, {"ticimax_fields": 0})
    if limit:
        cur = cur.limit(int(limit))
    return await cur.to_list(length=(limit or 5000))


@router.post("/publish/preview")
async def publish_preview(
    limit: int = 25,
    current_user: dict = Depends(require_admin),
):
    """DRY-RUN: HB'ye HİÇBİR şey göndermez. Payload'ı kurar, zorunlu-alan/değer uyarılarını döndürür."""
    merchant_id, field_cfg, sys_to_hb, attr_maps, schemas, value_names = await _gather_publish_context()
    if not merchant_id:
        raise HTTPException(400, "Kimlik eksik — önce Kimlik sekmesini doldur.")
    if not sys_to_hb:
        raise HTTPException(400, "Eşleşmiş kategori yok — önce Kategori Eşleştirme yap.")

    products = await _select_mapped_products(sys_to_hb, limit=max(1, min(int(limit or 25), 200)))
    sample, warnings, total_items = [], [], 0
    for p in products:
        m = sys_to_hb.get(p.get("category_id"))
        if not m:
            continue
        hid = m["hb_category_id"]
        items, _w = _build_product_items(p, hid, merchant_id, attr_maps.get(hid, {}),
                                         field_cfg, value_names.get(hid, {}))
        mand = _mandatory_ids(schemas.get(hid, {}))
        for it in items:
            total_items += 1
            missing = [k for k in mand if k not in it["attributes"] or it["attributes"].get(k) in (None, "")]
            if missing:
                warnings.append({"merchantSku": it["attributes"].get("merchantSku"),
                                 "product": p.get("name"), "missing_mandatory": missing})
        if len(sample) < 5:
            sample.append({"product": p.get("name"), "category_id": p.get("category_id"),
                           "hb_category_id": hid, "items": items})
    return {
        "dry_run": True,
        "products_in_scope": len(products),
        "items_built": total_items,
        "warnings_count": len(warnings),
        "warnings": warnings[:50],
        "sample": sample,
    }


@router.post("/publish/send")
async def publish_send(
    limit: Optional[int] = None,
    batch_size: int = 200,
    current_user: dict = Depends(require_admin),
):
    """GERÇEK gönderim: eşleşmiş ürünleri HB kataloğuna (products/import) yollar. Döner: trackingId listesi."""
    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    merchant_id, field_cfg, sys_to_hb, attr_maps, schemas, value_names = await _gather_publish_context()
    if not sys_to_hb:
        raise HTTPException(400, "Eşleşmiş kategori yok.")

    products = await _select_mapped_products(sys_to_hb, limit=limit)
    all_items = []
    for p in products:
        m = sys_to_hb.get(p.get("category_id"))
        if not m:
            continue
        hid = m["hb_category_id"]
        items, _w = _build_product_items(p, hid, merchant_id, attr_maps.get(hid, {}),
                                         field_cfg, value_names.get(hid, {}))
        all_items.extend(items)

    if not all_items:
        return {"sent": 0, "tracking_ids": [], "note": "Gönderilecek kalem bulunamadı."}

    bs = max(1, min(int(batch_size or 200), 500))
    tracking, errors = [], []
    for i in range(0, len(all_items), bs):
        batch = all_items[i:i + bs]
        try:
            res = await asyncio.to_thread(client.import_products, batch)
            tid = (res or {}).get("trackingId") or (res or {}).get("tracking_id") or (res or {}).get("data")
            tracking.append({"batch": i // bs, "count": len(batch), "trackingId": tid, "raw": res})
        except HBAktarimError as e:
            errors.append({"batch": i // bs, "count": len(batch), "error": str(e)})
    await db.hb_aktarim_config.update_one(
        {"_id": "last_publish"},
        {"$set": {"_id": "last_publish", "at": _now(), "items": len(all_items),
                  "tracking": tracking, "errors": errors}}, upsert=True)
    return {"sent": len(all_items), "batches": len(tracking) + len(errors),
            "tracking_ids": tracking, "errors": errors,
            "env": "prod" if not client.test else "sandbox"}


@router.get("/publish/status/{tracking_id}")
async def publish_status(tracking_id: str, current_user: dict = Depends(require_admin)):
    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    try:
        return await asyncio.to_thread(client.get_import_status, tracking_id)
    except HBAktarimError as e:
        raise HTTPException(502, str(e))


# ===================================================================== #
#  FİYAT / STOK  (listing)
# ===================================================================== #
def _calc_price(product, variant, price_cfg):
    raw = _read_for_variant(product, variant, (price_cfg or {}).get("field") or "price")
    try:
        val = float(str(raw).replace(",", "."))
    except Exception:
        return None
    margin = float((price_cfg or {}).get("margin_pct") or 0)
    val = val * (1 + margin / 100.0)
    return round(val, int((price_cfg or {}).get("round", 2)))


def _build_listing_rows(products, sys_to_hb, field_cfg):
    base = field_cfg.get("base") or {}
    price_cfg = field_cfg.get("price") or {}
    stock_cfg = field_cfg.get("stock") or {}
    msku_cfg = base.get("merchantSku") or {}
    prices, stocks, rows = [], [], []
    for p in products:
        if p.get("category_id") not in sys_to_hb:
            continue
        for idx, var in enumerate((p.get("variants") or [None])):
            msku = (_read_for_variant(p, var, msku_cfg.get("field"))
                    if msku_cfg.get("source") != "fixed" else msku_cfg.get("fixed"))
            msku = _norm_sku(msku or p.get("stock_code") or p.get("sku") or f"{p.get('id')}-{idx + 1}")
            price = _calc_price(p, var, price_cfg)
            stock_raw = _read_for_variant(p, var, stock_cfg.get("field") or "variant.stock")
            try:
                stock = int(float(stock_raw))
            except Exception:
                stock = 0
            if price is not None:
                prices.append({"merchantSku": msku, "price": price})
            stocks.append({"merchantSku": msku, "availableStock": stock})
            rows.append({"merchantSku": msku, "price": price, "stock": stock, "product": p.get("name")})
    return prices, stocks, rows


@router.post("/listing/price-stock/preview")
async def price_stock_preview(limit: int = 25, current_user: dict = Depends(require_admin)):
    _mid, field_cfg, sys_to_hb, *_ = await _gather_publish_context()
    products = await _select_mapped_products(sys_to_hb, limit=max(1, min(int(limit or 25), 200)))
    prices, stocks, rows = _build_listing_rows(products, sys_to_hb, field_cfg)
    return {"dry_run": True, "count": len(rows), "sample": rows[:20]}


@router.post("/listing/price-stock/send")
async def price_stock_send(limit: Optional[int] = None, current_user: dict = Depends(require_admin)):
    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    _mid, field_cfg, sys_to_hb, *_ = await _gather_publish_context()
    products = await _select_mapped_products(sys_to_hb, limit=limit)
    prices, stocks, rows = _build_listing_rows(products, sys_to_hb, field_cfg)
    out = {}
    try:
        if prices:
            out["price"] = await asyncio.to_thread(client.update_prices, prices)
        if stocks:
            out["stock"] = await asyncio.to_thread(client.update_stocks, stocks)
    except HBAktarimError as e:
        raise HTTPException(502, str(e))
    return {"sent_price": len(prices), "sent_stock": len(stocks), "result": out,
            "env": "prod" if not client.test else "sandbox"}


# ===================================================================== #
#  SİPARİŞ ÇEKME  (OMS — salt-okunur)
# ===================================================================== #
@router.get("/orders")
async def pull_orders(
    begin_date: Optional[str] = None,
    end_date: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
    current_user: dict = Depends(require_admin),
):
    client, err = await _build_client()
    if err:
        raise HTTPException(400, err)
    try:
        res = await asyncio.to_thread(client.get_orders, begin_date, end_date,
                                      offset, max(1, min(int(limit or 50), 200)))
    except HBAktarimError as e:
        raise HTTPException(502, str(e))
    return {"orders": res}
