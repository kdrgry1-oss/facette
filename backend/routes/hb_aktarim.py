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
