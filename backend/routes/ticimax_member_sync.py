"""
=============================================================================
ticimax_member_sync.py — Ticimax Web Servis ÜYE (Üye) İçe Aktarma
=============================================================================
Amaç: Ticimax UyeServis (SelectUyeler / SelectUyeAdres) ile mevcut üyeleri
çekip yerel `users` koleksiyonuna aktarmak. Eşleştirme E-POSTA bazlıdır.

ŞİFRE: Ticimax üye şifreleri çekilmez/aktarılmaz. Yeni oluşturulan üyelere
rastgele (kullanılamaz) bir parola hash'i atanır ve `requires_password_reset`
işaretlenir. Üye, sitede "Şifremi Unuttum" akışıyla kendi şifresini belirler.

GEÇMİŞ SİPARİŞLER: link_orders=True ise, `orders` koleksiyonunda e-postası
üyeyle eşleşen ve `user_id` boş olan siparişler bu üyeye bağlanır
(zaten bir kullanıcıya bağlı siparişlere DOKUNULMAZ).

GÜVENLİK:
  - apply=false (VARSAYILAN) → hiçbir şey yazılmaz, sadece "ne olacak" raporu
  - apply=true               → users/addresses/orders güncellenir

ENDPOINT:
  POST /api/admin/ticimax/import-members?apply=false&link_orders=true
  GET  /api/admin/ticimax/import-members-status
=============================================================================
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import sys, os, time

_BACKEND_PATH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_PATH not in sys.path:
    sys.path.insert(0, _BACKEND_PATH)

from .deps import db, logger, require_admin, hash_password, generate_id
from .marketplace_hub import log_integration_event

import re as _re_mod
def _re_escape(s: str) -> str:
    return _re_mod.escape(s or "")

router = APIRouter(prefix="/admin/ticimax", tags=["admin-ticimax-members"])


def _to_dict(zo) -> Dict:
    try:
        from ticimax_client import _to_dict as _td  # type: ignore
        d = _td(zo)
        return d if isinstance(d, dict) else {}
    except Exception:
        if isinstance(zo, dict):
            return zo
        out = {}
        for k in dir(zo):
            if k.startswith("_"):
                continue
            try:
                v = getattr(zo, k)
            except Exception:
                continue
            if not callable(v):
                out[k] = v
        return out


def _clean(s: Any) -> str:
    return str(s).strip() if s is not None else ""


async def _run_member_import(
    apply: bool,
    max_members: int,
    page_size: int,
    only_active: bool,
    import_addresses: bool,
    link_orders: bool,
) -> Dict:
    started = datetime.now(timezone.utc)
    import ticimax_client as _tc  # type: ignore
    from ticimax_client import get_members, get_member_addresses  # type: ignore

    settings = await db.settings.find_one({"id": "ticimax"}) or {}
    api_key = settings.get("api_key") or os.environ.get("TICIMAX_API_KEY") or "AKG0M8DTRSEBAIA898JA6HW22EDIU3"
    _domain = settings.get("domain") or settings.get("api_url") or os.environ.get("TICIMAX_DOMAIN")
    if _domain:
        try:
            _tc.set_domain(_domain)
        except Exception as e:
            logger.warning(f"[member-import] set_domain hata: {e}")

    # 1) Üyeleri sayfa sayfa çek
    fetched: List[Dict] = []
    page = 1
    while len(fetched) < max_members:
        try:
            chunk = get_members(page=page, page_size=page_size, wscode=api_key, only_active=only_active)
        except Exception as e:
            logger.error(f"[member-import] sayfa {page} hata: {e}")
            if page == 1:
                return {"success": False, "error": f"Ticimax üyeleri alınamadı: {e}"}
            break
        if not chunk:
            break
        fetched.extend([_to_dict(m) for m in chunk])
        if len(chunk) < page_size:
            break
        page += 1
        time.sleep(1.0)
    if len(fetched) > max_members:
        fetched = fetched[:max_members]

    # 2) Her üyeyi işle
    created = 0
    updated = 0
    matched_existing = 0
    skipped_no_email = 0
    linked_orders_total = 0
    addresses_added = 0
    errors: List[str] = []
    sample_created: List[Dict] = []

    now_iso = datetime.now(timezone.utc).isoformat()

    for m in fetched:
        email = _clean(m.get("Mail") or m.get("Email") or m.get("EPosta")).lower()
        if not email or "@" not in email:
            skipped_no_email += 1
            continue

        tc_member_id = m.get("ID") or m.get("UyeID")
        try:
            tc_member_id = int(tc_member_id) if tc_member_id else None
        except Exception:
            tc_member_id = None

        first = _clean(m.get("Isim") or m.get("Ad"))
        last = _clean(m.get("Soyisim") or m.get("Soyad"))
        phone = _clean(m.get("CepTelefonu") or m.get("Telefon"))
        aktif = m.get("Aktif")
        is_active = True if (aktif in (1, True, "1", None)) else False
        mail_izin = bool(m.get("MailIzin") in (1, True, "1"))
        sms_izin = bool(m.get("SmsIzin") in (1, True, "1"))

        existing = await db.users.find_one(
            {"email": email}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "phone": 1}
        )

        target_user_id = None

        if existing:
            matched_existing += 1
            target_user_id = existing["id"]
            # Sadece BOŞ alanları doldur — mevcut veriyi ezme
            patch = {}
            if not _clean(existing.get("first_name")) and first:
                patch["first_name"] = first
            if not _clean(existing.get("last_name")) and last:
                patch["last_name"] = last
            if not _clean(existing.get("phone")) and phone:
                patch["phone"] = phone
            if tc_member_id is not None:
                patch["ticimax_member_id"] = tc_member_id
            patch["ticimax_synced_at"] = now_iso
            if patch and apply:
                await db.users.update_one({"id": existing["id"]}, {"$set": patch})
            if patch:
                updated += 1
        else:
            # YENİ üye — şifresiz (parola-sıfırlama akışı), Ticimax kaynaklı
            new_id = generate_id()
            target_user_id = new_id
            doc = {
                "id": new_id,
                "email": email,
                # kullanılamaz rastgele hash — üye "Şifremi Unuttum" ile belirler
                "password": hash_password(generate_id() + generate_id()),
                "first_name": first,
                "last_name": last,
                "phone": phone,
                "is_admin": False,
                "is_active": is_active,
                "accepts_marketing": mail_izin or sms_izin,
                "acquisition_source": "ticimax_import",
                "ticimax_member_id": tc_member_id,
                "requires_password_reset": True,
                "created_at": now_iso,
                "ticimax_synced_at": now_iso,
            }
            created += 1
            if len(sample_created) < 50:
                sample_created.append({"email": email, "name": f"{first} {last}".strip(),
                                       "phone": phone, "ticimax_member_id": tc_member_id})
            if apply:
                try:
                    await db.users.insert_one(doc)
                except Exception as e:
                    errors.append(f"{email}: {e}")
                    continue

        # 3) Adresleri içe aktar (opsiyonel) — ticimax_address_id ile dedup
        if import_addresses and tc_member_id and target_user_id:
            try:
                addrs = get_member_addresses(tc_member_id, wscode=api_key)
                for a in [_to_dict(x) for x in (addrs or [])]:
                    ta_id = a.get("ID") or a.get("AdresID")
                    if ta_id is None:
                        continue
                    exists_addr = await db.addresses.find_one(
                        {"user_id": target_user_id, "ticimax_address_id": ta_id}, {"_id": 1}
                    )
                    if exists_addr:
                        continue
                    addr_doc = {
                        "id": generate_id(),
                        "user_id": target_user_id,
                        "ticimax_address_id": ta_id,
                        "title": _clean(a.get("AdresBasligi") or a.get("Baslik") or "Adres"),
                        "full_name": _clean(a.get("AdSoyad") or f"{first} {last}".strip()),
                        "phone": _clean(a.get("Telefon") or phone),
                        "city": _clean(a.get("Il") or a.get("Sehir")),
                        "district": _clean(a.get("Ilce")),
                        "address": _clean(a.get("Adres") or a.get("AcikAdres")),
                        "postal_code": _clean(a.get("PostaKodu")),
                        "source": "ticimax_import",
                        "created_at": now_iso,
                    }
                    addresses_added += 1
                    if apply:
                        await db.addresses.insert_one(addr_doc)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"adres {email}: {e}")

        # 4) Geçmiş siparişleri e-posta ile bağla (user_id boş olanlar)
        if link_orders and target_user_id:
            order_q = {
                "$and": [
                    {"$or": [{"user_id": None}, {"user_id": ""}, {"user_id": {"$exists": False}}]},
                    {"$or": [
                        {"shipping_address.email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}},
                        {"email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}},
                        {"customer_email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}},
                        {"user_email": {"$regex": f"^{_re_escape(email)}$", "$options": "i"}},
                    ]},
                ]
            }
            try:
                if apply:
                    res = await db.orders.update_many(
                        order_q, {"$set": {"user_id": target_user_id, "user_linked_at": now_iso}}
                    )
                    linked_orders_total += res.modified_count
                else:
                    linked_orders_total += await db.orders.count_documents(order_q)
            except Exception as e:
                errors.append(f"siparis-baglama {email}: {e}")

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    result = {
        "success": True,
        "apply": apply,
        "fetched": len(fetched),
        "created": created,
        "updated": updated,
        "matched_existing": matched_existing,
        "skipped_no_email": skipped_no_email,
        "linked_orders": linked_orders_total,
        "addresses_added": addresses_added,
        "errors": errors[:50],
        "errors_count": len(errors),
        "sample_created": sample_created,
        "duration_sec": round(duration, 1),
    }
    if not apply:
        result["note"] = ("DRY-RUN: hiçbir kayıt yazılmadı. Raporu kontrol edip apply=true "
                          "ile tekrar çağırarak uygulayın. Yeni üyeler şifresiz oluşturulur; "
                          "üyeler 'Şifremi Unuttum' ile giriş yapar.")
    return result


@router.post("/import-members")
async def import_ticimax_members(
    apply: bool = Query(False, description="false=DRY-RUN rapor (varsayılan), true=uygula"),
    max_members: int = Query(20000, ge=10, le=200000),
    page_size: int = Query(100, ge=10, le=200),
    only_active: bool = Query(False, description="Sadece aktif üyeler"),
    import_addresses: bool = Query(True, description="Üye adreslerini de içe aktar"),
    link_orders: bool = Query(True, description="Geçmiş siparişleri e-posta ile bağla"),
    current_user: dict = Depends(require_admin),
):
    """
    Ticimax üyelerini yerel `users` koleksiyonuna aktarır (e-posta bazlı eşleştirme).
    Şifreler aktarılmaz; yeni üyeler 'Şifremi Unuttum' akışıyla giriş yapar.
    apply=false (varsayılan) → sadece rapor; apply=true → uygular.
    """
    res = await _run_member_import(
        apply=apply, max_members=max_members, page_size=page_size,
        only_active=only_active, import_addresses=import_addresses, link_orders=link_orders,
    )
    try:
        await log_integration_event(
            marketplace="ticimax",
            action=f"member_import{'_apply' if apply else '_dryrun'}",
            status="success" if res.get("success") else "error",
            message=f"created={res.get('created')} matched={res.get('matched_existing')} "
                    f"linked_orders={res.get('linked_orders')}",
        )
    except Exception:
        pass
    if apply:
        await db.settings.update_one(
            {"id": "ticimax_member_import_last"},
            {"$set": {"id": "ticimax_member_import_last", "result": res,
                      "finished_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    return res


@router.get("/import-members-status")
async def import_ticimax_members_status(current_user: dict = Depends(require_admin)):
    """Son uygulanan üye import işleminin sonucunu döner."""
    doc = await db.settings.find_one({"id": "ticimax_member_import_last"}, {"_id": 0})
    if not doc:
        return {"success": True, "found": False, "message": "Henüz üye import uygulanmadı."}
    return {"success": True, "found": True, **doc}
