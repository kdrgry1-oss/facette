"""
Influencer CRM & Seeding & ROI (Modül 3 + 4).

- influencers (master) + influencer_campaigns (detail) MongoDB koleksiyonları.
- Kampanya seeding: MNG Kargo barkod üretimi + Netgsm SMS bildirimleri.
- Paylaşım doğrulaması (manuel "Paylaşıldı Onayı" + Meta webhook stub).
- ROI motoru: GET /api/influencers/{id}/roi — Aggregation ile maliyet vs ciro.

Sipariş eşleştirme: orders.create_order, resolve_influencer_for_order() çağırır:
  1) attribution.aff_id (30 günlük çerez) → influencer
  2) Fallback: order.coupon_code, influencer'ın kuponuyla eşleşirse override.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request, UploadFile, File, Form
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid as _uuid

from .deps import db, logger, require_admin, generate_id
from models import Influencer, InfluencerCampaign, DEFAULT_CAMPAIGN_DIRECTIVES

router = APIRouter(tags=["Influencer CRM"])

# Başarılı sayılan sipariş statüleri (ROI ciro hesabı)
SUCCESS_STATUSES = ["confirmed", "processing", "shipped", "delivered"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _influencer_turu(follower_count) -> str:
    """Takipçi sayısına göre influencer türü (Kadir): Nano (<10K) / Micro (10K–100K) /
    Makro (100K+). TÜRETİLİR — panelde ayrı yazılmaz, follower_count'tan hesaplanır."""
    n = _to_int_loose(follower_count)
    if n >= 100_000:
        return "Makro"
    if n >= 10_000:
        return "Micro"
    return "Nano"


def _to_int_loose(v, default: int = 0) -> int:
    """Takipçi sayısı gibi alanları TOLERANSLI biçimde int'e çevirir.
    Türkçe binlik ayracı (nokta/boşluk) ve K/B(bin)/M(milyon) ekleri desteklenir.
    Sebep: panel `type=number` inputu Türk kullanıcının yazdığı "125.500" değerini
    JS `Number()` ile 125.5 (kesirli float) yapıyordu; Pydantic `int` bunu reddedip
    kaydı 500 ile düşürüyordu ("takipçi girince kaydolmuyor" bug'ı). Artık asla patlamaz."""
    if v is None:
        return default
    if isinstance(v, bool):
        return default
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        try:
            return int(round(v))
        except Exception:
            return default
    import re as _re
    s = str(v).strip().lower().replace(" ", "")
    if not s:
        return default
    m = _re.match(r"^([\d.,]+)(k|b|bin|m|mn|milyon)?$", s)
    if m:
        num, suf = m.group(1), m.group(2)
        # Türkçe: virgül = ondalık, nokta = binlik ayraç
        num = num.replace(".", "").replace(",", ".")
        try:
            val = float(num)
        except Exception:
            val = None
        if val is not None:
            if suf in ("k", "b", "bin"):
                val *= 1000
            elif suf in ("m", "mn", "milyon"):
                val *= 1_000_000
            return int(round(val))
    digits = _re.sub(r"\D", "", s)
    return int(digits) if digits else default


# =============================================================================
# Sipariş eşleştirme yardımcı fonksiyonu (orders.py'den çağrılır)
# =============================================================================

async def resolve_influencer_for_order(aff_id: Optional[str], coupon_code: Optional[str]) -> Optional[dict]:
    """Bir siparişi influencer'a bağlar.
    Öncelik: aff_id (çerez) → kupon (fallback override).
    Dönüş: {influencer_id, name, via} veya None."""
    inf = None
    via = None

    aff_id = (aff_id or "").strip()
    if aff_id:
        inf = await db.influencers.find_one({"aff_id": aff_id, "is_active": True}, {"_id": 0})
        if inf:
            via = "aff_id"

    if not inf:
        code = (coupon_code or "").strip().upper()
        if code:
            import re as _re_i
            inf = await db.influencers.find_one(
                {"coupon_code": {"$regex": f"^{_re_i.escape(code)}$", "$options": "i"}, "is_active": True},
                {"_id": 0},
            )
            if inf:
                via = "coupon"

    if not inf:
        return None
    return {"influencer_id": inf["id"], "name": inf.get("name", ""), "via": via}


# =============================================================================
# Direkt SMS (Netgsm) — template gerektirmeden
# =============================================================================

async def _send_direct_sms(phone: str, message: str) -> dict:
    try:
        from notification_service import _get_providers_config, SMS_IMPL, _sms_generic, normalize_phone_tr
        to = normalize_phone_tr(phone)
        if not to:
            return {"success": False, "response": "phone empty"}
        cfg = await _get_providers_config(db)
        providers = cfg.get("providers", {})
        sms_active = cfg.get("sms_active")
        if not sms_active:
            return {"success": False, "response": "no active sms provider"}
        impl = SMS_IMPL.get(sms_active, _sms_generic)
        prov_cfg = providers.get(sms_active, {})
        return await impl(prov_cfg, to, message)
    except Exception as e:
        logger.warning(f"Influencer SMS failed: {e}")
        return {"success": False, "response": str(e)}


# =============================================================================
# INFLUENCERS CRUD
# =============================================================================

@router.post("/influencers")
async def create_influencer(payload: dict, current_user: dict = Depends(require_admin)):
    if payload is not None and "follower_count" in payload:
        payload["follower_count"] = _to_int_loose(payload.get("follower_count"))
    model = Influencer(**payload)
    doc = model.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    if doc.get("coupon_code"):
        doc["coupon_code"] = doc["coupon_code"].upper()
    await db.influencers.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "influencer": doc}


@router.get("/influencers")
async def list_influencers(
    q: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(require_admin),
):
    query = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"handle": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"instagram": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"tiktok": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"phone": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"coupon_code": {"$regex": _re_i.escape(q), "$options": "i"}},
        ]
    if platform:
        query["platform"] = platform
    if is_active is not None:
        query["is_active"] = is_active
    docs = await db.influencers.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    for d in docs:  # KAYITLI türü (elle seçilen) öncelikli; yoksa takipçiden ÖNERİ türet.
        d["influencer_turu"] = d.get("influencer_turu") or _influencer_turu(d.get("follower_count"))
    return {"influencers": docs, "total": len(docs)}


_DEFAULT_INF_TURU = ["Nano", "Micro", "Makro"]


@router.get("/influencer-types")
async def list_influencer_types(current_user: dict = Depends(require_admin)):
    """Influencer türü seçenekleri (Nano/Micro/Makro + admin'in eklediği yeni tipler).
    Kadir: elle yazmak yerine dropdown; gerektiğinde yeni tip eklenebilir."""
    doc = await db.settings.find_one({"id": "influencer_types"}, {"_id": 0})
    types = list((doc or {}).get("types") or [])
    seen = {str(t).lower() for t in types}
    types += [t for t in _DEFAULT_INF_TURU if t.lower() not in seen]  # varsayılanları garanti et
    return {"types": types}


@router.post("/influencer-types")
async def add_influencer_type(payload: dict, current_user: dict = Depends(require_admin)):
    name = str((payload or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tip adı gerekli")
    doc = await db.settings.find_one({"id": "influencer_types"}, {"_id": 0}) or {}
    types = list(doc.get("types") or _DEFAULT_INF_TURU)
    if name.lower() not in {str(t).lower() for t in types}:
        types.append(name)
    await db.settings.update_one(
        {"id": "influencer_types"},
        {"$set": {"types": types, "updated_at": _now_iso()}, "$setOnInsert": {"id": "influencer_types"}},
        upsert=True)
    return {"success": True, "types": types}


@router.get("/influencers/{influencer_id}")
async def get_influencer(influencer_id: str, current_user: dict = Depends(require_admin)):
    doc = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")
    campaigns = await db.influencer_campaigns.find(
        {"influencer_id": influencer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    doc["campaigns"] = campaigns
    doc["influencer_turu"] = doc.get("influencer_turu") or _influencer_turu(doc.get("follower_count"))
    return doc


@router.put("/influencers/{influencer_id}")
async def update_influencer(influencer_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")
    allowed = {
        "name", "platform", "handle", "instagram", "tiktok", "birthday",
        "phone", "email", "follower_count",
        "coupon_code", "aff_id", "commission_rate", "shipping_address", "notes", "is_active",
        # Kadir PR alanları: anlaşma şekli, beden alt+üst, influencer_turu (artık ELLE seçilir —
        # dropdown'dan; takipçiden yalnız ÖNERİ olarak türetilir, kaydedilen değer korunur).
        "anlasma_sekli", "beden_alt", "beden_ust", "influencer_turu",
        # Excel "Kayıtlı Influencer" formu: üst düzey serbest-metin adres (liste sütunu).
        "adres",
    }
    update = {k: v for k, v in payload.items() if k in allowed}
    if "follower_count" in update:
        update["follower_count"] = _to_int_loose(update.get("follower_count"))
    if "coupon_code" in update and update["coupon_code"]:
        update["coupon_code"] = update["coupon_code"].upper()
    update["updated_at"] = _now_iso()
    await db.influencers.update_one({"id": influencer_id}, {"$set": update})
    doc = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    return {"success": True, "influencer": doc}


@router.delete("/influencers/{influencer_id}")
async def delete_influencer(influencer_id: str, current_user: dict = Depends(require_admin)):
    res = await db.influencers.delete_one({"id": influencer_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")
    await db.influencer_campaigns.delete_many({"influencer_id": influencer_id})
    await db.influencer_pr.delete_many({"influencer_id": influencer_id})
    return {"success": True}


# =============================================================================
# PR TAKİP (outreach tracker) — Kadir: haftalık PR listesi.
# Her işlem TEK TEK "sipariş gibi" ayrı kayıt. Alanlar: influencer · tür · tarih ·
# iletişim · teklif · cevap · durum · follow-up · not (+ insta/tiktok linki).
# ⚠️ Bu katman SAF KAYIT: STOK DÜŞÜRMEZ/ARTIRMAZ (iptal/iade dahil). Gerçek ürün
# gönderimi + stok düşümü AYRI akış: influencer_campaigns (seeding). Karıştırma.
# =============================================================================

# Durum seçenekleri (frontend açılır menüsü ile ortak — panelde düzenlenebilir değil,
# outreach akışının sabit adımları).
PR_STATUSES = ["beklemede", "iletildi", "cevap_bekleniyor", "olumlu",
               "olumsuz", "gonderildi", "yayinlandi", "iptal"]

_PR_FIELDS = ("influencer_id", "influencer_name", "influencer_type", "date",
              "contact", "offer", "response", "status", "follow_up", "note",
              "instagram", "tiktok", "products",
              # Kadir: bu alanlar da PR kaydına DOĞRUDAN girilebilsin (bağlı influencer
              # yoksa/boşsa elle) — tablo sütunları form'dan doldurulabilir olsun.
              "urun", "beden", "anlasma_sekli", "phone", "adres",
              # Paylaşım artık KALEM-BAZLI (products[].shared). Kayıt-seviyesi "shared"
              # _PR_FIELDS'ten ÇIKARILDI (eski değer görmezden gelinir); paylasma_tarihi legacy.
              # Çoklu ürün = products[] (her kalem {name,barcode,size,qty,gonderim_tarihi,barkod,shared}).
              "paylasma_tarihi",
              # Kargo: ürün girilmiş PR'dan gönderim yapılınca (kampanya+MNG barkod) işlenir.
              "campaign_id", "cargo_barcode", "cargo_tracking_no", "shipped_at")


def _pr_addr(inf) -> str:
    """Influencer master kargo adresini tek satır string'e çevirir (adres, ilçe, il)."""
    sa = (inf or {}).get("shipping_address") or {}
    if isinstance(sa, dict):
        return ", ".join(str(p) for p in [sa.get("adres"), sa.get("ilce"), sa.get("il")] if p)
    return str(sa or "")


def _pr_beden(inf, e) -> str:
    """Beden: önce SEÇİLEN ÜRÜNLERİN bedeni (products[].size — Kadir: ürünü arayıp bedenini
    seçiyoruz), yoksa kaydın kendi beden alanı, yoksa influencer master alt/üst."""
    prods = (e or {}).get("products") or []
    _psz = ", ".join(str(p.get("size")) for p in prods
                     if isinstance(p, dict) and p.get("size"))
    if _psz:
        return _psz
    if (e or {}).get("beden"):
        return e["beden"]
    alt = (inf or {}).get("beden_alt") or ""
    ust = (inf or {}).get("beden_ust") or ""
    if alt or ust:
        return f"Alt: {alt} / Üst: {ust}"
    return ""


def _pr_urun(e) -> str:
    """Gönderilen ürün(ler) — PR kaydının products listesi (yoksa boş)."""
    prods = (e or {}).get("products")
    if isinstance(prods, list) and prods:
        return ", ".join(
            (str(p.get("name") or p.get("barcode")) if isinstance(p, dict) else str(p))
            for p in prods)
    return ""


def _first_img_abs(imgs) -> str:
    """Ürünün İLK geçerli görselini MUTLAK https URL'ye çevirir (base64/data: atlanır).
    Dict {url} veya string; //→https, http→https, /→site kökü. Yoksa ''."""
    for im in (imgs or []):
        u = (im.get("url") if isinstance(im, dict) else im)
        u = str(u or "").strip()
        if not u or u.startswith("data:"):
            continue
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("http://"):
            return "https://" + u[len("http://"):]
        if u.startswith("https://"):
            return u
        if u.startswith("/"):
            return "https://facette.com.tr" + u
        return u
    return ""


async def _pr_attach_product_images(docs: list) -> None:
    """PR kayıtlarının products[] kalemlerine ürünün İLK görselini (mutlak https) ekler.
    TEK sorguda çözer: kalem barcode → products.barcode / variants.barcode, yoksa ada göre.
    Eşleşmeyen kalemde image boş kalır (frontend nötr placeholder gösterir). base64 YOK."""
    barcodes: set = set()
    names: set = set()
    for d in docs:
        for it in (d.get("products") or []):
            if not isinstance(it, dict):
                continue
            bc = str(it.get("barcode") or "").strip()
            if bc:
                barcodes.add(bc)
            nm = str(it.get("name") or "").strip()
            if nm:
                names.add(nm)
    if not barcodes and not names:
        return
    _or = []
    if barcodes:
        _or.append({"barcode": {"$in": list(barcodes)}})
        _or.append({"variants.barcode": {"$in": list(barcodes)}})
    if names:
        _or.append({"name": {"$in": list(names)}})
    bc_img: dict = {}
    name_img: dict = {}
    try:
        async for p in db.products.find(
            {"$or": _or},
            {"_id": 0, "name": 1, "barcode": 1, "images": 1, "variants.barcode": 1},
        ):
            img = _first_img_abs(p.get("images") or [])
            if not img:
                continue
            pb = str(p.get("barcode") or "").strip()
            if pb:
                bc_img.setdefault(pb, img)
            for v in (p.get("variants") or []):
                vb = str((v or {}).get("barcode") or "").strip()
                if vb:
                    bc_img.setdefault(vb, img)
            nm = str(p.get("name") or "").strip()
            if nm:
                name_img.setdefault(nm, img)
    except Exception as e:
        logger.warning(f"[influencer] PR ürün görseli çözülemedi: {e}")
        return
    for d in docs:
        for it in (d.get("products") or []):
            if not isinstance(it, dict) or it.get("image"):
                continue
            bc = str(it.get("barcode") or "").strip()
            nm = str(it.get("name") or "").strip()
            it["image"] = bc_img.get(bc) or name_img.get(nm) or ""


async def _pr_enrich(docs: list) -> None:
    """PR kayıtlarına bağlı influencer master alanlarını (telefon/adres/beden/anlaşma/türü)
    yerinde ekler — liste tablosu basılı PR listesi gibi görünsün diye. Ayrıca products[]
    kalemlerine ürünün ilk görselini (thumbnail/hover için) çözer."""
    inf_ids = list({d.get("influencer_id") for d in docs if d.get("influencer_id")})
    inf_map: dict = {}
    if inf_ids:
        async for i in db.influencers.find({"id": {"$in": inf_ids}}, {"_id": 0}):
            inf_map[i["id"]] = i
    await _pr_attach_product_images(docs)   # products[] kalemlerine image ekle
    for d in docs:
        inf = inf_map.get(d.get("influencer_id")) or {}
        # Önce KAYDIN kendi değeri (form'dan girilen), yoksa bağlı influencer master'ı.
        d["phone"] = d.get("phone") or inf.get("phone") or ""
        d["adres"] = d.get("adres") or _pr_addr(inf)
        d["beden"] = d.get("beden") or _pr_beden(inf, d)
        d["anlasma_sekli"] = d.get("anlasma_sekli") or inf.get("anlasma_sekli") or ""
        # Influencer Türü: profildeki KAYITLI değer (Mikro/Makro/Nano-UGC/Mid-Tier) öncelikli;
        # yoksa takipçiden türetilen ÖNERİ. (Gönderi Takibi detayında profilden gösterilir.)
        d["influencer_turu"] = (inf.get("influencer_turu")
                                or (_influencer_turu(inf.get("follower_count")) if inf else "") or "")
        d["urun"] = d.get("urun") or _pr_urun(d)
        d["instagram"] = d.get("instagram") or inf.get("instagram") or ""
        d["tiktok"] = d.get("tiktok") or inf.get("tiktok") or ""
        # Gönderi Takibi detay alanları — profilden (expand satırında gösterilir).
        d["platform"] = d.get("platform") or inf.get("platform") or ""
        d["handle"] = d.get("handle") or inf.get("handle") or ""


async def _pr_period_summary() -> dict:
    """Günlük/haftalık/aylık/yıllık PR kaydı SAYISI — TR yerel güne göre
    (reports.py ile aynı 3 saat kayması disiplini). `date` alanı üzerinden sayar."""
    _tr = timedelta(hours=3)
    now_tr = datetime.now(timezone.utc) + _tr
    day0 = now_tr.replace(hour=0, minute=0, second=0, microsecond=0)

    def _u(dt_tr):  # TR yerel → UTC ISO
        return (dt_tr - _tr).isoformat()

    bounds = {
        "today": _u(day0),
        "week": _u(day0 - timedelta(days=day0.weekday())),
        "month": _u(day0.replace(day=1)),
        "year": _u(day0.replace(month=1, day=1)),
    }
    out = {}
    for k, since in bounds.items():
        out[k] = await db.influencer_pr.count_documents({"date": {"$gte": since}})
    out["all"] = await db.influencer_pr.count_documents({})
    return out


def _inf_norm(s) -> str:
    """Influencer eşleştirme için Türkçe-duyarsız normalize (@ ve boşluk temizlenir)."""
    import unicodedata as _ud
    s = str(s or "").strip().lstrip("@")
    s = s.replace("ı", "i").replace("İ", "i")
    s = _ud.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not _ud.combining(c))
    return " ".join(s.split())


async def _resolve_or_create_registry(doc: dict):
    """PR kaydının influencer'ını Kayıtlı Influencerlar (db.influencers) ile EŞLE ya da OLUŞTUR.
    Dönüş: (influencer_id, created_bool). MÜKERRER ÖNLEME sırası: (1) doc.influencer_id doğrudan,
    (2) handle/instagram/tiktok normalize, (3) influencer_name normalize; hiçbiri tutmazsa YENİ
    registry kaydı (PR'daki alanlar taşınır). İDEMPOTENT — aynı influencer 2. kez oluşturulmaz."""
    iid = str(doc.get("influencer_id") or "").strip()
    if iid:
        ex = await db.influencers.find_one({"id": iid}, {"_id": 0, "id": 1})
        if ex:
            return iid, False

    hset = {_inf_norm(h) for h in (doc.get("handle"), doc.get("instagram"), doc.get("tiktok"))}
    hset.discard("")
    nname = _inf_norm(doc.get("influencer_name"))
    if not hset and not nname:
        return iid, False  # linklenecek kimlik yok

    cands = await db.influencers.find(
        {}, {"_id": 0, "id": 1, "name": 1, "handle": 1, "instagram": 1, "tiktok": 1}).to_list(5000)
    if hset:
        for inf in cands:
            ih = {_inf_norm(inf.get("handle")), _inf_norm(inf.get("instagram")), _inf_norm(inf.get("tiktok"))}
            ih.discard("")
            if hset & ih:
                return inf["id"], False
    if nname:
        for inf in cands:
            if _inf_norm(inf.get("name")) == nname:
                return inf["id"], False

    # 4) YENİ registry kaydı — PR'da olan alanları taşı (eksikler boş; kullanıcı sonra düzenler).
    handle = str(doc.get("handle") or doc.get("instagram") or doc.get("tiktok") or "").strip()
    new_id = generate_id()
    new_doc = {
        "id": new_id,
        "name": doc.get("influencer_name") or handle or "İsimsiz",
        "handle": handle,
        "instagram": doc.get("instagram") or "",
        "tiktok": doc.get("tiktok") or "",
        "platform": doc.get("platform")
        or ("İnstagram" if doc.get("instagram") else ("Tiktok" if doc.get("tiktok") else "")),
        "phone": doc.get("phone") or "",
        "adres": doc.get("adres") or "",
        "influencer_turu": doc.get("influencer_type") or "",
        "anlasma_sekli": doc.get("anlasma_sekli") or "",
        "beden": doc.get("beden") or "",
        "is_active": True,
        "source": "pr_auto",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.influencers.insert_one(dict(new_doc))
    return new_id, True


@router.post("/influencer-pr")
async def create_pr_entry(payload: dict, current_user: dict = Depends(require_admin)):
    """PR işlemi ekle (stok hareketi YOK). YALNIZ KAYITLI influencer seçilerek açılabilir:
    geçerli `influencer_id` (db.influencers'ta VAR olan) ZORUNLU — yoksa 400. Serbest-yaz ile
    yeni influencer OLUŞTURULMAZ. Seçilen kaydın alanları (isim/tür/insta/tiktok/telefon/adres/
    beden/anlaşma) girilmemişse otomatik doldurulur (girilmişse override edilmez)."""
    doc = {k: (payload.get(k) if payload else None) for k in _PR_FIELDS}
    iid = str(doc.get("influencer_id") or "").strip()
    if not iid:
        raise HTTPException(status_code=400, detail="Kayıtlı influencer gerekli")
    inf = await db.influencers.find_one({"id": iid}, {"_id": 0})
    if not inf:
        raise HTTPException(status_code=400, detail="Kayıtlı influencer gerekli")
    doc["influencer_id"] = iid
    doc["influencer_name"] = doc.get("influencer_name") or inf.get("name")
    doc["influencer_type"] = doc.get("influencer_type") or inf.get("platform")
    doc["instagram"] = doc.get("instagram") or inf.get("instagram")
    doc["tiktok"] = doc.get("tiktok") or inf.get("tiktok")
    # Kadir: adres/beden/anlaşma/telefon da influencer'dan otomatik dolsun (elle override edilebilir).
    doc["phone"] = doc.get("phone") or inf.get("phone")
    doc["adres"] = doc.get("adres") or _pr_addr(inf)
    doc["beden"] = doc.get("beden") or _pr_beden(inf, doc)
    doc["anlasma_sekli"] = doc.get("anlasma_sekli") or inf.get("anlasma_sekli")
    if (doc.get("status") or "") not in PR_STATUSES:
        doc["status"] = "beklemede"
    doc["date"] = doc.get("date") or _now_iso()
    doc["id"] = generate_id()
    doc["created_at"] = _now_iso()
    doc["updated_at"] = _now_iso()
    await db.influencer_pr.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"success": True, "entry": doc}


@router.post("/influencer-pr/backfill-registry")
async def backfill_pr_registry(current_user: dict = Depends(require_admin)):
    """GERİYE DÖNÜK (idempotent): mevcut TÜM PR kayıtlarını tarar; influencer'ı Kayıtlı
    Influencerlar'da OLMAYANLAR için registry kaydı oluşturur (mükerrer önlemeli) ve PR'ı
    linkler. Tekrar çağrılırsa yeni kayıt oluşturmaz (eşleşmeyi bulur)."""
    entries = await db.influencer_pr.find({}, {"_id": 0}).to_list(20000)
    created = 0
    linked = 0
    scanned = 0
    for e in entries:
        scanned += 1
        try:
            old_id = str(e.get("influencer_id") or "")
            rid, was_created = await _resolve_or_create_registry(e)
            if was_created:
                created += 1
            if rid and rid != old_id:
                await db.influencer_pr.update_one(
                    {"id": e["id"]}, {"$set": {"influencer_id": rid, "updated_at": _now_iso()}})
                linked += 1
        except Exception as _e:
            logger.warning(f"[influencer] backfill PR {e.get('id')} hata: {_e}")
    return {"success": True, "scanned": scanned, "created": created, "linked": linked}


@router.get("/influencer-pr")
async def list_pr_entries(
    q: Optional[str] = Query(None),
    influencer_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """Ana liste: tüm PR işlemleri (tarih filtreli), en yeni üstte. Ayrıca dönem
    sayaçları (günlük/haftalık/aylık/yıllık) + filtrelenmiş sonucun durum kırılımı."""
    query: dict = {}
    if influencer_id:
        query["influencer_id"] = influencer_id
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"influencer_name": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"instagram": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"tiktok": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"note": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"offer": {"$regex": _re_i.escape(q), "$options": "i"}},
        ]
    if start_date or end_date:
        dr: dict = {}
        if start_date:
            dr["$gte"] = start_date
        if end_date:
            dr["$lte"] = end_date
        query["date"] = dr
    docs = await db.influencer_pr.find(query, {"_id": 0}).sort("date", -1).to_list(2000)
    await _pr_enrich(docs)  # telefon/adres/beden/anlaşma/türü — tablo basılı liste gibi görünsün
    status_counts: dict = {}
    for d in docs:
        s = d.get("status") or "beklemede"
        status_counts[s] = status_counts.get(s, 0) + 1
    return {"entries": docs, "total": len(docs),
            "summary": await _pr_period_summary(), "status_counts": status_counts}


_PR_STATUS_LABEL = {
    "beklemede": "Beklemede", "iletildi": "İletildi", "cevap_bekleniyor": "Cevap Bekleniyor",
    "olumlu": "Olumlu", "olumsuz": "Olumsuz", "gonderildi": "Gönderildi",
    "yayinlandi": "Yayınlandı", "iptal": "İptal",
}
_AY_TR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
          "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

# Excel ortak renk paletleri (3 sekmede de tutarlı) — durum ve iş birliği türü rozetleri.
_PR_STATUS_COLORS = {
    "Gönderildi": {"bg": "D1FAE5", "fg": "065F46"}, "Yayınlandı": {"bg": "DBEAFE", "fg": "1E40AF"},
    "Olumlu": {"bg": "D1FAE5", "fg": "065F46"}, "İletildi": {"bg": "E0E7FF", "fg": "3730A3"},
    "Cevap Bekleniyor": {"bg": "FEF3C7", "fg": "92400E"}, "Beklemede": {"bg": "F3F4F6", "fg": "374151"},
    "Olumsuz": {"bg": "FEE2E2", "fg": "991B1B"}, "İptal": {"bg": "FEE2E2", "fg": "991B1B"},
}
_ANLASMA_COLORS = {
    "Barter": {"bg": "DBEAFE", "fg": "1E40AF"}, "PR": {"bg": "D1FAE5", "fg": "065F46"},
    "Ücretli İş Birliği": {"bg": "FEF3C7", "fg": "92400E"},
}


def _exp_barcodes_str(e) -> str:
    """Kalem barkodlarını ' • ' ile birleştir (export ortak yardımcısı)."""
    prods = e.get("products")
    if isinstance(prods, list) and prods:
        return " • ".join(str(p.get("barcode")) for p in prods
                          if isinstance(p, dict) and p.get("barcode"))
    return ""


# ── Export ortak yardımcıları (Gönderi Takibi / Takvim / Kayıtlı Influencer) ──
def _exp_uname(e, inf) -> str:
    """@kullanıcı adı: kaydın handle/instagram/tiktok → yoksa influencer master."""
    return (e.get("handle") or e.get("instagram") or e.get("tiktok")
            or (inf or {}).get("handle") or (inf or {}).get("instagram") or (inf or {}).get("tiktok") or "")


def _exp_products(e) -> str:
    prods = e.get("products")
    if isinstance(prods, list) and prods:
        return " • ".join(
            (str(p.get("name") or p.get("barcode")) if isinstance(p, dict) else str(p))
            for p in prods)
    return e.get("urun") or e.get("offer") or ""


def _exp_bedens(e) -> str:
    prods = e.get("products")
    if isinstance(prods, list) and prods:
        sizes = [str(p.get("size")) for p in prods if isinstance(p, dict) and p.get("size")]
        if sizes:
            return " • ".join(sizes)
    return e.get("beden") or ""


def _exp_effdate(e) -> str:
    """Takvim tarihi: kalem gonderim_tarihi → shipped_at → (eski) date → created_at."""
    prods = e.get("products") or []
    g = next((str(p.get("gonderim_tarihi")) for p in prods
              if isinstance(p, dict) and p.get("gonderim_tarihi")), "")
    return str(g or e.get("shipped_at") or e.get("date") or e.get("created_at") or "")[:10]


def _exp_shared(e) -> str:
    """KALEM-BAZLI paylaşım — her ürün için Evet/Hayır, ürün sırasıyla '•' birleşik
    (Ürün(ler)/Beden(ler) sütunlarıyla AYNI sıra → hizalı). Ürün yoksa eski kayıt-shared."""
    prods = e.get("products")
    if isinstance(prods, list) and prods:
        return " • ".join("Evet" if (isinstance(p, dict) and p.get("shared")) else "Hayır" for p in prods)
    return "Evet" if e.get("shared") else "Hayır"


def _xlsx_response(ws_title, headers, rows, widths, filename, status_col=None, status_colors=None):
    """Stilize XLSX: koyu başlık bandı (beyaz kalın), donmuş başlık, otomatik filtre, ince çerçeve,
    zebra (bir satır bir) gölge, üstten hizalı + metin sarma. status_col verilirse o sütun değere göre
    renklendirilir (status_colors: {etiket:{'bg':hex,'fg':hex}})."""
    import openpyxl
    from io import BytesIO
    from fastapi.responses import Response
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = (ws_title or "Sayfa")[:31]
    hfill = PatternFill("solid", fgColor="1F2937")
    hfont = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="E5E7EB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    ws.append(headers)
    for c in ws[1]:
        c.fill = hfill
        c.font = hfont
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[1].height = 28
    smap = status_colors or {}
    for ri, r in enumerate(rows, start=2):
        ws.append(r)
        band = "FFFFFF" if ri % 2 == 0 else "F5F6F8"
        for c in ws[ri]:
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.fill = PatternFill("solid", fgColor=band)
        if status_col:
            sc = ws.cell(row=ri, column=status_col)
            col = smap.get(str(sc.value or ""))
            if col:
                sc.fill = PatternFill("solid", fgColor=col["bg"])
                sc.font = Font(bold=True, color=col["fg"])
                sc.alignment = Alignment(horizontal="center", vertical="center")
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    buf = BytesIO()
    # DENETİM (injection F8): Excel/CSV formül enjeksiyonu — =+-@ ile başlayan hücreleri kaçır
    for _ws in wb.worksheets:
        for _row in _ws.iter_rows():
            for _c in _row:
                if isinstance(_c.value, str) and _c.value[:1] in ('=', '+', '-', '@', '\t', '\r'):
                    _c.value = "'" + _c.value
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.get("/influencer-pr/export")
async def export_pr_entries(
    q: Optional[str] = Query(None),
    influencer_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """GÖNDERİ TAKİBİ Excel — ekrandaki filtreyle (durum/tarih/arama) AYNI kayıtlar.
    Güncel sütunlar: İletişim Tarihi ÇIKTI, Paylaştı EKLENDİ. Çoklu ürün tek hücrede '•' ile."""
    query: dict = {}
    if influencer_id:
        query["influencer_id"] = influencer_id
    if status:
        query["status"] = status
    if q:
        query["$or"] = [
            {"influencer_name": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"instagram": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"tiktok": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"note": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"offer": {"$regex": _re_i.escape(q), "$options": "i"}},
        ]
    if start_date or end_date:
        dr: dict = {}
        if start_date:
            dr["$gte"] = start_date
        if end_date:
            dr["$lte"] = end_date
        query["date"] = dr
    entries = await db.influencer_pr.find(query, {"_id": 0}).sort("date", 1).to_list(5000)
    await _pr_enrich(entries)  # influencer master + görsel/handle/platform join

    # ── HER ÜRÜN AYRI SATIR: influencer bilgisi her satırda tekrar (filtre/pivot dostu),
    #    'Görsel' sütununa ürünün küçük resmi gömülür, üstte 'Özet' sayfası. ──
    _status_colors = {
        "Gönderildi": {"bg": "D1FAE5", "fg": "065F46"}, "Yayınlandı": {"bg": "DBEAFE", "fg": "1E40AF"},
        "Olumlu": {"bg": "D1FAE5", "fg": "065F46"}, "İletildi": {"bg": "E0E7FF", "fg": "3730A3"},
        "Cevap Bekleniyor": {"bg": "FEF3C7", "fg": "92400E"}, "Beklemede": {"bg": "F3F4F6", "fg": "374151"},
        "Olumsuz": {"bg": "FEE2E2", "fg": "991B1B"}, "İptal": {"bg": "FEE2E2", "fg": "991B1B"},
    }

    def _plabel(p):
        return (p.get("name") or p.get("barcode") or "") if isinstance(p, dict) else str(p or "")

    def _pdate(e, p):
        g = p.get("gonderim_tarihi") if isinstance(p, dict) else None
        return str(g)[:10] if g else _exp_effdate(e)

    def _platform(e):
        return e.get("platform") or ("İnstagram" if e.get("instagram") else "Tiktok" if e.get("tiktok") else "")

    # düz satır listesi: (hücre_değerleri, görsel_url).
    # KOLON SIRASI = EKRAN: [1-12] ekranda görünen (Influencer/İş Birliği/İletişim/Görsel/Ürün/Beden/
    # Barkod/Gönderim Tarihi/Durum/Paylaştı/Not) → [13-23] detay (expand satırındaki alanlar).
    flat = []
    for e in entries:
        # 1-4: ekranın Influencer + İş Birliği + İletişim (platform + @kullanıcı)
        front = [
            e.get("influencer_name") or "",
            e.get("anlasma_sekli") or "",
            _platform(e),
            _exp_uname(e, None) or "",
        ]
        # 13-23: detay (expand satırı) — her ürün satırında tekrar
        detail = [
            e.get("influencer_turu") or "",
            e.get("phone") or "",
            e.get("instagram") or "",
            e.get("tiktok") or "",
            e.get("contact") or "",
            e.get("offer") or "",
            e.get("response") or "",
            e.get("follow_up") or "",
            e.get("adres") or "",
            e.get("cargo_barcode") or "",
            e.get("cargo_gonderi_no") or e.get("cargo_tracking_no") or "",
        ]
        note = e.get("note") or ""
        prods = [p for p in (e.get("products") or []) if isinstance(p, dict)]
        if not prods:
            flat.append(([
                *front, "", _exp_products(e), _exp_bedens(e), "",
                _exp_effdate(e), _exp_shared(e), note, *detail,
            ], None))
            continue
        for p in prods:
            flat.append(([
                *front,
                "", _plabel(p), str(p.get("size") or ""), str(p.get("barcode") or ""),
                _pdate(e, p), ("Evet" if p.get("shared") else "Hayır"), note,
                *detail,
            ], (p.get("image") or None)))

    # benzersiz görselleri eşzamanlı indir + küçült (best-effort; hata → görselsiz devam)
    IMG_CAP = 400
    img_cache: dict = {}
    urls, seen = [], set()
    for _, u in flat:
        if u and u not in seen and len(urls) < IMG_CAP:
            seen.add(u)
            urls.append(u)
    if urls:
        try:
            import asyncio
            import httpx
            from io import BytesIO as _BIO
            from PIL import Image as _PILImage
            _sem = asyncio.Semaphore(8)
            _ua = {"User-Agent": "Mozilla/5.0 (FacetteExcel/1.0)"}
            _ok = 0
            _err_sample = []

            async def _grab(cli, u):
                async with _sem:
                    try:
                        r = await cli.get(u)
                        if r.status_code == 200 and r.content:
                            im = _PILImage.open(_BIO(r.content)).convert("RGB")
                            im.thumbnail((72, 72))
                            b = _BIO()
                            im.save(b, format="PNG")
                            img_cache[u] = b.getvalue()
                    except Exception as _ie:
                        if len(_err_sample) < 2:
                            _err_sample.append(f"{u[:60]}: {type(_ie).__name__}: {_ie}")
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True, headers=_ua) as _cli:
                await asyncio.gather(*[_grab(_cli, u) for u in urls])
            _ok = len(img_cache)
            logger.info(f"[influencer] excel görsel: {_ok}/{len(urls)} indi"
                        + (f" — örnek hata: {_err_sample}" if _err_sample and _ok == 0 else ""))
        except Exception as ex:
            logger.warning(f"[influencer] excel görsel indirme atlandı: {ex}")

    import openpyxl
    from io import BytesIO
    from fastapi.responses import Response
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.drawing.image import Image as XLImage

    wb = openpyxl.Workbook()
    thin = Side(style="thin", color="E5E7EB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ── TEK SAYFA: GÖNDERİ TAKİBİ (Özet sayfası kaldırıldı — kullanıcı isteği). ──
    ws = wb.active
    ws.title = "Gönderi Takibi"
    # Ekran sırası (1-11) + detay (12-22). Gönderim Durumu sütunu kaldırıldı (kullanıcı isteği).
    headers = ["Influencer", "İş Birliği", "İletişim (Platform)", "Kullanıcı Adı", "Görsel", "Ürün",
               "Beden", "Barkod", "Gönderim Tarihi", "Paylaştı", "Not",
               "Influencer Türü", "Telefon", "Instagram", "TikTok", "İletişim Kanalı", "Teklif",
               "Cevap", "Follow-up", "Adres", "Kargo Barkodu", "Kargo Takip No"]
    widths = [22, 13, 15, 18, 12, 30, 9, 20, 14, 9, 26, 14, 13, 16, 14, 16, 24, 22, 18, 30, 16, 18]
    STATUS_COL = None
    IMG_COL = 5
    ws.append(headers)
    for c in ws[1]:
        c.fill = PatternFill("solid", fgColor="1F2937")
        c.font = Font(bold=True, color="FFFFFF", size=11)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border
    ws.row_dimensions[1].height = 30

    for ri, (row, img_url) in enumerate(flat, start=2):
        ws.append(row)
        band = "FFFFFF" if ri % 2 == 0 else "F5F6F8"
        for c in ws[ri]:
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.fill = PatternFill("solid", fgColor=band)
        if STATUS_COL:
            sc = ws.cell(row=ri, column=STATUS_COL)
            col = _status_colors.get(str(sc.value or ""))
            if col:
                sc.fill = PatternFill("solid", fgColor=col["bg"])
                sc.font = Font(bold=True, color=col["fg"])
                sc.alignment = Alignment(horizontal="center", vertical="center")
        data = img_cache.get(img_url) if img_url else None
        if data:
            try:
                ws.add_image(XLImage(BytesIO(data)), f"{get_column_letter(IMG_COL)}{ri}")
                ws.row_dimensions[ri].height = 58
            except Exception:
                pass
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.freeze_panes = "A2"
    if flat:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(flat) + 1}"

    buf = BytesIO()
    # DENETİM (injection F8): Excel/CSV formül enjeksiyonu — =+-@ ile başlayan hücreleri kaçır
    for _ws in wb.worksheets:
        for _row in _ws.iter_rows():
            for _c in _row:
                if isinstance(_c.value, str) and _c.value[:1] in ('=', '+', '-', '@', '\t', '\r'):
                    _c.value = "'" + _c.value
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=gonderi-takibi.xlsx"})


@router.get("/influencer-pr/calendar-export")
async def export_calendar_entries(current_user: dict = Depends(require_admin)):
    """TAKVİM Excel — tüm gönderim kayıtları TARİHE göre sıralı düz liste (kime ne zaman
    ne gönderildi). Tarih önceliği: kalem gonderim_tarihi → shipped_at → created_at.
    Filtre YOK: takvim tümünü gösterir → export da tümü (tarihe göre artan)."""
    entries = await db.influencer_pr.find({}, {"_id": 0}).to_list(5000)
    await _pr_enrich(entries)
    entries.sort(key=lambda e: _exp_effdate(e) or "9999")

    def _ay_lbl(dstr):
        try:
            y, m = str(dstr)[:7].split("-")
            return f"{_AY_TR[int(m)]} {y}"
        except Exception:
            return ""

    rows = []
    for e in entries:
        _d = _exp_effdate(e)
        rows.append([
            _d,
            _ay_lbl(_d),
            e.get("influencer_name") or "",
            e.get("anlasma_sekli") or "",
            e.get("platform") or "",
            e.get("instagram") or _exp_uname(e, None) or "",
            e.get("tiktok") or "",
            e.get("phone") or "",
            _exp_products(e),
            _exp_bedens(e),
            _exp_barcodes_str(e),
            _PR_STATUS_LABEL.get(e.get("status") or "beklemede", e.get("status") or ""),
            _exp_shared(e),
            e.get("cargo_barcode") or "",
            e.get("cargo_gonderi_no") or e.get("cargo_tracking_no") or "",
            e.get("note") or "",
            e.get("offer") or "",
        ])
    headers = ["Tarih", "Ay", "Influencer", "İş Birliği Türü", "Platform", "Instagram", "TikTok",
               "Telefon", "Ürün(ler)", "Beden(ler)", "Barkod(lar)", "Gönderim Durumu", "Paylaştı mı",
               "Kargo Barkodu", "Kargo Takip", "Not", "Teklif"]
    widths = [14, 14, 22, 15, 12, 18, 16, 14, 40, 16, 26, 16, 12, 16, 16, 30, 26]
    return _xlsx_response("Gönderim Takvimi", headers, rows, widths, "gonderim-takvimi.xlsx",
                          status_col=12, status_colors=_PR_STATUS_COLORS)


@router.get("/influencer-registry/export")
async def export_influencers(q: Optional[str] = Query(None), current_user: dict = Depends(require_admin)):
    """KAYITLI INFLUENCERLAR Excel — tablodaki görünür sütunlarla (arama filtresine uyar).
    Yol '/influencers/export' DEĞİL (o /influencers/{id} ile çakışırdı) → '/influencer-registry/export'."""
    query: dict = {}
    if q:
        query["$or"] = [
            {"name": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"handle": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"instagram": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"tiktok": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"phone": {"$regex": _re_i.escape(q), "$options": "i"}},
            {"coupon_code": {"$regex": _re_i.escape(q), "$options": "i"}},
        ]
    docs = await db.influencers.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)

    # Her influencer için PR gönderi sayısı (kaç kez ürün gönderildi) — tek aggregation.
    pr_counts: dict = {}
    try:
        async for row in db.influencer_pr.aggregate([
            {"$match": {"influencer_id": {"$ne": None}}},
            {"$group": {"_id": "$influencer_id", "n": {"$sum": 1}}},
        ]):
            pr_counts[row["_id"]] = int(row.get("n") or 0)
    except Exception as e:
        logger.warning(f"[influencer] PR sayısı hesaplanamadı: {e}")

    def _sa(d):
        return d.get("shipping_address") if isinstance(d.get("shipping_address"), dict) else {}

    def _addr(d):
        a = (d.get("adres") or "").strip()
        if a:
            return a
        sa = _sa(d)
        return ", ".join(str(p) for p in [sa.get("adres"), sa.get("ilce"), sa.get("il")] if p)

    def _dt(d):
        return str(d.get("created_at") or "")[:10]

    rows = []
    for d in docs:
        sa = _sa(d)
        fc = int(d.get("follower_count") or 0)
        rows.append([
            d.get("name") or "",
            d.get("anlasma_sekli") or "",
            d.get("influencer_turu") or _influencer_turu(d.get("follower_count")),
            d.get("platform") or "",
            d.get("instagram") or d.get("handle") or "",
            d.get("tiktok") or "",
            (f"{fc:,}".replace(",", ".") if fc > 0 else ""),
            d.get("coupon_code") or "",
            d.get("phone") or "",
            d.get("email") or "",
            _addr(d),
            sa.get("il") or "",
            sa.get("ilce") or "",
            d.get("beden_ust") or "",
            d.get("beden_alt") or "",
            pr_counts.get(d.get("id"), 0),
            _dt(d),
            d.get("notes") or "",
        ])
    headers = ["İsim Soyisim", "İş Birliği Türü", "Influencer Türü", "Platform", "Instagram", "TikTok",
               "Takipçi", "Kupon Kodu", "Telefon", "E-posta", "Adres", "İl", "İlçe",
               "Beden Üst", "Beden Alt", "PR Gönderi Sayısı", "Kayıt Tarihi", "Not"]
    widths = [24, 16, 14, 12, 18, 16, 12, 15, 15, 26, 38, 14, 14, 11, 11, 15, 14, 32]
    return _xlsx_response(
        "Kayıtlı Influencerlar", headers, rows, widths, "kayitli-influencerlar.xlsx",
        status_col=2, status_colors=_ANLASMA_COLORS)


@router.put("/influencer-pr/{entry_id}")
async def update_pr_entry(entry_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    update = {k: v for k, v in (payload or {}).items() if k in _PR_FIELDS}
    if "status" in update and (update.get("status") or "") not in PR_STATUSES:
        update.pop("status")
    # ELLE TAKİP NO: kurye paketi bizim MNG kaydımız yerine elden irsaliyeyle aldıysa MNG
    # bizim sipariş no'muza takip no atamaz; kurye fişindeki numara buradan girilir.
    if "cargo_gonderi_no" in (payload or {}):
        g = str(payload.get("cargo_gonderi_no") or "").strip()
        if g and g != (existing.get("cargo_gonderi_no") or ""):
            update.update({"cargo_gonderi_no": g, "cargo_tracking_url": f"https://kargotakip.dhlecommerce.com.tr/?takipNo={g}",
                           "cargo_track_note": "Takip no elle girildi", "cargo_track_error": "", "cargo_manual_tracking": True})
        elif not g and existing.get("cargo_manual_tracking"):
            update.update({"cargo_gonderi_no": "", "cargo_tracking_url": "", "cargo_manual_tracking": False, "cargo_track_note": ""})
    update["updated_at"] = _now_iso()
    await db.influencer_pr.update_one({"id": entry_id}, {"$set": update})
    doc = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    # NOT: PR güncellemede registry OTO-OLUŞTURMA YOK — PR yalnız kayıtlı influencer'a bağlanır
    # (create'te zorunlu). Mevcut kayıtların influencer_id'si korunur.
    return {"success": True, "entry": doc}


@router.put("/influencer-pr/{entry_id}/item-shared")
async def update_pr_item_shared(entry_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    """KALEM-BAZLI 'Paylaştı mı?' — yalnız BELİRTİLEN ürün kaleminin `shared`'ını değiştirir;
    kaydın DİĞER kalemleri etkilenmez. body: {index:int, shared:bool}. Ürün dizisi sunucuda
    güncellenir (istemci diziyi resend etmez → hiza/veri güvenli)."""
    existing = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    try:
        idx = int((payload or {}).get("index"))
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz kalem index")
    shared = bool((payload or {}).get("shared"))
    prods = list(existing.get("products") or [])
    if idx < 0 or idx >= len(prods) or not isinstance(prods[idx], dict):
        raise HTTPException(status_code=400, detail="Kalem bulunamadı")
    prods[idx] = {**prods[idx], "shared": shared}
    await db.influencer_pr.update_one(
        {"id": entry_id}, {"$set": {"products": prods, "updated_at": _now_iso()}})
    doc = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    return {"success": True, "entry": doc}


@router.delete("/influencer-pr/{entry_id}")
async def delete_pr_entry(entry_id: str, current_user: dict = Depends(require_admin)):
    res = await db.influencer_pr.delete_one({"id": entry_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    return {"success": True}


@router.post("/influencer-pr/{entry_id}/ship")
async def ship_pr_entry(entry_id: str, current_user: dict = Depends(require_admin)):
    """PR kaydındaki ürünleri KARGOYA VER — İDEMPOTENT. Mevcut influencer kargo akışını kullanır:
    kampanya oluştur → ürünleri işle (STOK DÜŞER, kampanya-bazlı atomik) → MNG barkod + takip.
    Tekrar çağrılırsa yeniden kampanya/stok düşümü YAPMAZ (campaign_id PR'da saklanır) → çift
    stok düşümü riski YOK (frontend zincirinin aksine)."""
    e = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    if e.get("cargo_barcode"):
        return {"success": True, "already": True, "cargo_barcode": e.get("cargo_barcode"),
                "tracking_no": e.get("cargo_tracking_no")}
    if not e.get("influencer_id"):
        raise HTTPException(status_code=400, detail="Kargo için PR kaydı bir influencer'a bağlı olmalı")
    prods = [p for p in (e.get("products") or []) if isinstance(p, dict) and p.get("barcode")]
    if not prods:
        raise HTTPException(status_code=400, detail="Kargolanacak ürün yok (ürünü ara → beden seç)")

    # 1) Kampanya — idempotent: PR'da campaign_id varsa YENİDEN OLUŞTURMA.
    cid = e.get("campaign_id")
    if not cid:
        cr = await create_campaign(
            e["influencer_id"], {"title": f"PR Gönderi · {str(e.get('date') or '')[:10]}"}, current_user)
        cid = (cr.get("campaign") or {}).get("id")
        if not cid:
            raise HTTPException(status_code=500, detail="Kampanya oluşturulamadı")
        # campaign_id'yi HEMEN sakla — sonraki adım (stok/kargo) hata verse bile tekrar denemede
        # yeni kampanya oluşturulup stok İKİNCİ kez düşülmesin.
        await db.influencer_pr.update_one({"id": entry_id}, {"$set": {"campaign_id": cid}})

    # 2) Ürünleri işle (STOK DÜŞER) — kampanya-bazlı atomik; zaten düşülmüşse atla (retry-güvenli).
    camp = await db.influencer_campaigns.find_one({"id": cid}, {"_id": 0, "stock_deducted": 1})
    if not (camp or {}).get("stock_deducted"):
        await commit_campaign_products(
            cid, {"products": [{"barcode": p["barcode"], "qty": p.get("qty") or 1} for p in prods],
                  "auto_cost": True}, current_user)

    # 3) MNG barkod + takip (influencer'ın yapılandırılmış kargo adresi gerekir).
    cg = await create_campaign_cargo(cid, current_user)

    # Gönderi Takibi: her ürün kalemine barkod + gönderim tarihi işaretle (kalem rozeti/tarihi).
    _bc = cg.get("cargo_barcode") or ""
    _today = _now_iso()[:10]
    _stamped = []
    for _p in (e.get("products") or []):
        if isinstance(_p, dict):
            _p = {**_p, "barkod": _p.get("barkod") or _bc,
                  "gonderim_tarihi": _p.get("gonderim_tarihi") or _today}
        _stamped.append(_p)
    upd = {"campaign_id": cid, "cargo_barcode": _bc,
           "cargo_tracking_no": cg.get("tracking_no") or "", "shipped_at": _now_iso(),
           "status": "gonderildi", "updated_at": _now_iso(), "products": _stamped}
    if cg.get("mng_no"):
        upd["cargo_mng_no"] = cg["mng_no"]
    if cg.get("gonderi_no"):   # NZ takip barkodu anında geldiyse rozet hemen yeşil link
        upd.update({"cargo_gonderi_no": cg["gonderi_no"], "cargo_tracking_url": cg.get("tracking_url") or "",
                    "cargo_track_note": "", "cargo_track_error": ""})
    await db.influencer_pr.update_one({"id": entry_id}, {"$set": upd})
    return {"success": True, "cargo_barcode": upd["cargo_barcode"],
            "tracking_no": upd["cargo_tracking_no"], "shipped_at": upd["shipped_at"]}


@router.post("/influencer-pr/{entry_id}/refresh-tracking")
async def refresh_pr_tracking(entry_id: str, current_user: dict = Depends(require_admin)):
    """Siparişler'deki mantıkla PR kargosunun GERÇEK takip no'sunu MNG/DHL e-Commerce'den çeker.
    PR kargosunun MNG sipariş no'su `cargo_tracking_no` (INF… biçimi). Firma gönderi_no üretmişse
    kaydeder: cargo_gonderi_no (gerçek takip no), cargo_tracking_url (DHL takip linki),
    cargo_last_status_text, cargo_status_checked_at. Henüz üretmediyse pending döner."""
    e = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    siparis_no = (e.get("cargo_tracking_no") or "").strip()
    if not siparis_no:
        raise HTTPException(status_code=400, detail="Bu kayıtta kargo yok — önce Kargoya Ver (barkod çıkart).")
    try:
        from .orders import _get_mng_settings
        from mng_kargo_client import get_mng_shipment_status
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Kargo modülü yüklenemedi: {ex}")
    s = await _get_mng_settings()
    if not s.get("is_active") or not s.get("username"):
        raise HTTPException(status_code=400, detail="MNG/DHL kargo entegrasyonu aktif değil.")
    import asyncio as _aio
    # Referans adayları: MNG sipariş no (INF…) ÖNCE, sonra barkod — bazı gönderilerde gerçek
    # takip no barkod referansından döner. İlk gonderi_no bulunan kazanır.
    refs = [r for r in [siparis_no, (e.get("cargo_barcode") or "").strip()] if r]
    refs = list(dict.fromkeys(refs))  # tekilleştir, sıra korunur
    gonderi, statu_ac, last_info = "", "", None
    for ref in refs:
        try:
            info = await _aio.to_thread(
                get_mng_shipment_status, username=s["username"], password=s["password"], siparis_no=ref)
        except Exception as ex:
            raise HTTPException(status_code=502, detail=f"Kargo sorgusu başarısız: {ex}")
        if info and info.get("ok"):
            last_info = info
            statu_ac = (info.get("kargo_statu_aciklama") or "").strip() or statu_ac
            g = (info.get("gonderi_no") or "").strip()
            if g:
                gonderi = g
                break
    if not last_info:
        return {"success": False, "pending": True,
                "message": "Kargo firması henüz takip no üretmedi (kargoya verilmesini bekleyin)."}
    track_no = gonderi or siparis_no
    track_url = (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={track_no}"
                 if track_no else (info.get("kargo_takip_url") or "").strip())
    upd = {"cargo_gonderi_no": gonderi, "cargo_tracking_url": track_url,
           "cargo_last_status_text": statu_ac, "cargo_status_checked_at": _now_iso()}
    await db.influencer_pr.update_one({"id": entry_id}, {"$set": upd})
    return {"success": True, "pending": not gonderi, "gonderi_no": gonderi,
            "tracking_url": track_url, "status_text": statu_ac}


_PR_TRACK_HEALTH_ID = "influencer_pr_track_health"


async def auto_refresh_pr_tracking(limit: int = 150) -> dict:
    """SAATLİK OTOMATİK TARAMA (scheduler): takip no'su henüz oluşmamış PR gönderilerinin
    gerçek DHL/MNG gönderi no'sunu çeker ve kayda yazar ("takip çek" butonu kaldırıldı).

    Aday: kargo barkodu ya da MNG sipariş no'su (INF…) olan, cargo_gonderi_no'su BOŞ,
    son 60 günde kargolanmış kayıtlar. Referans sırası: MNG sipariş no → barkod.
    Sonuç settings.influencer_pr_track_health'e yazılır (son çalışma/sayaçlar/hata);
    her kayda cargo_status_checked_at (+ cargo_last_status_text / cargo_track_error) işlenir.
    MNG günlük sorgu limiti mesajı görülürse tarama o tur için durur (boşa sorgu yok)."""
    import asyncio as _aio
    started = datetime.now(timezone.utc)
    stats = {"status": "running", "last_run_at": started.isoformat(), "candidates": 0,
             "checked": 0, "found": 0, "errors": 0, "limit_hit": False, "last_error": ""}

    async def _health(**extra):
        try:
            doc = dict(stats)
            doc.update(extra)
            doc["id"] = _PR_TRACK_HEALTH_ID
            doc["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.settings.update_one({"id": _PR_TRACK_HEALTH_ID}, {"$set": doc}, upsert=True)
        except Exception as _he:
            logger.warning(f"[pr-track] health write err: {_he}")

    try:
        from .orders import _get_mng_settings
        from mng_kargo_client import get_mng_shipment_status
    except Exception as ex:
        stats.update(status="error", last_error=f"Kargo modülü yüklenemedi: {ex}")
        await _health(last_finish_at=datetime.now(timezone.utc).isoformat())
        return stats
    s = await _get_mng_settings()
    if not s.get("is_active") or not s.get("username"):
        stats.update(status="inactive", last_error="MNG/DHL kargo entegrasyonu aktif değil")
        await _health(last_finish_at=datetime.now(timezone.utc).isoformat())
        return stats
    user, pw = s["username"], s["password"]

    cut = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    q = {
        "$and": [
            {"$or": [{"cargo_tracking_no": {"$nin": [None, ""]}},
                     {"cargo_barcode": {"$nin": [None, ""]}}]},
            {"$or": [{"cargo_gonderi_no": {"$in": [None, ""]}},
                     {"cargo_gonderi_no": {"$exists": False}}]},
            {"$or": [{"shipped_at": {"$gt": cut}}, {"shipped_at": {"$in": [None, ""]}},
                     {"shipped_at": {"$exists": False}}]},
        ],
    }
    try:
        stats["candidates"] = await db.influencer_pr.count_documents(q)
    except Exception:
        pass
    await _health()

    _limit_kw = ("günlük sorgu", "gunluk sorgu", "sorgu limit", "sorgulama sinir", "sorgulama sınır")
    try:
        async for pr in db.influencer_pr.find(
                q, {"_id": 0, "id": 1, "cargo_tracking_no": 1, "cargo_barcode": 1, "shipped_at": 1}).limit(limit):
            refs = [r for r in [str(pr.get("cargo_tracking_no") or "").strip(),
                                str(pr.get("cargo_barcode") or "").strip()] if r]
            refs = list(dict.fromkeys(refs))
            if not refs:
                continue
            gonderi, statu_ac, got_ok, err_txt, mng_no = "", "", False, "", ""
            debug_parts = []
            for ref in refs:
                try:
                    info = await _aio.to_thread(
                        get_mng_shipment_status, username=user, password=pw, siparis_no=ref)
                except Exception as pe:
                    err_txt = str(pe)[:200]
                    debug_parts.append(f"{ref}: istisna {str(pe)[:80]}")
                    stats["errors"] += 1
                    await _aio.sleep(0.2)
                    continue
                if info and info.get("ok"):
                    got_ok = True
                    statu_ac = (info.get("kargo_statu_aciklama") or "").strip() or statu_ac
                    if (info.get("mng_siparis_no") or "").strip():
                        mng_no = str(info.get("mng_siparis_no")).strip()
                    g = (info.get("gonderi_no") or "").strip()
                    debug_parts.append(
                        f"{ref}: {info.get('method') or '?'} statu={info.get('kargo_statu') or '0'} "
                        f"mng_no={info.get('mng_siparis_no') or '-'} gonderi={g or '-'}")
                    if g:
                        gonderi = g
                        break
                else:
                    err_txt = str((info or {}).get("error") or "")[:200]
                    debug_parts.append(f"{ref}: {err_txt[:80] or 'yanıt yok'}")
                await _aio.sleep(0.2)
            stats["checked"] += 1
            now_iso = datetime.now(timezone.utc).isoformat()
            # GERİYE DÖNÜK: son 24 saatte oluşturulmuş, etiketi MNG iç no'lu (NZ'siz) kayıtlara
            # Siparişler'deki gibi MNGGonderiBarkod ile NZ takip barkodu al → etiket yeniden basılınca
            # kurye doğru barkodu okutur. (Daha eski kayıtlar kuryeye verilmiş olabilir; dokunma.)
            if not gonderi and got_ok:
                try:
                    _sa = str(pr.get("shipped_at") or "")[:19]
                    _fresh = bool(_sa) and (datetime.now(timezone.utc) - datetime.fromisoformat(_sa).replace(tzinfo=timezone.utc)) <= timedelta(hours=24)
                    _ref = str(pr.get("cargo_tracking_no") or "").strip()
                    if _fresh and _ref.startswith("INF"):
                        from mng_kargo_client import get_mng_barcode_immediately as _nz
                        _b = await _aio.to_thread(_nz, username=user, password=pw, siparis_no=_ref, urun_bedeli=0, kapida_tahsilat=False)
                        _nzb = ((_b or {}).get("barkod") or (_b or {}).get("gonderi_no") or "").strip() if (_b or {}).get("ok") else ""
                        debug_parts.append(f"NZ: {_nzb or ((_b or {}).get('hata') or '-')}"[:120])
                        if _nzb:
                            gonderi = _nzb
                            stats["nz_retro"] = stats.get("nz_retro", 0) + 1
                            await db.influencer_pr.update_one({"id": pr["id"]}, {"$set": {"cargo_barcode": _nzb, "cargo_track_note": "NZ takip barkodu alındı — etiketi yeniden yazdırın"}})
                            await db.influencer_campaigns.update_many({"cargo_tracking_no": _ref}, {"$set": {"cargo_barcode": _nzb, "cargo_gonderi_no": _nzb}})
                except Exception as _ne:
                    debug_parts.append(f"NZ hata: {str(_ne)[:80]}")
            upd = {"cargo_status_checked_at": now_iso,
                   "cargo_track_debug": " | ".join(debug_parts)[:400]}
            if got_ok:
                upd["cargo_last_status_text"] = statu_ac
                upd["cargo_track_error"] = ""
                if mng_no:
                    upd["cargo_mng_no"] = mng_no   # MNG iç sipariş no (takip no DEĞİL; panelde bilgi amaçlı)
                if not gonderi:
                    # İnsan-okur açıklama: MNG paketi şubede okutana kadar takip no atanmaz.
                    upd["cargo_track_note"] = ("MNG kaydı var, paket henüz MNG tarafından okutulmadı; "
                                               "takip no MNG şubede işleyince otomatik gelir.")
            if gonderi:
                upd["cargo_track_note"] = ""
            elif err_txt:
                upd["cargo_track_error"] = err_txt
                stats["last_error"] = err_txt
            if gonderi:
                upd["cargo_gonderi_no"] = gonderi
                upd["cargo_tracking_url"] = f"https://kargotakip.dhlecommerce.com.tr/?takipNo={gonderi}"
                stats["found"] += 1
            await db.influencer_pr.update_one({"id": pr["id"]}, {"$set": upd})
            if err_txt and any(k in err_txt.lower() for k in _limit_kw):
                stats["limit_hit"] = True
                break
            await _aio.sleep(0.2)
        stats["status"] = "ok" if not stats["limit_hit"] else "limit"
    except Exception as e:
        logger.exception(f"[pr-track] tarama hatası: {e}")
        stats.update(status="error", last_error=str(e)[:200])
    # KURYE REFERANSIYLA (RE-…) AÇILAN PAKETLER: MNG tarih-bazlı gönderi listesinden alıcı adına
    # göre eşle. Bizim INF… referansımıza bağlı olmayan paketlerin takip no'su ancak buradan gelir.
    try:
        pend = await db.influencer_pr.find(
            {"$or": [{"cargo_barcode": {"$nin": [None, ""]}}, {"cargo_tracking_no": {"$nin": [None, ""]}}],
             "$and": [{"$or": [{"cargo_gonderi_no": {"$in": [None, ""]}}, {"cargo_gonderi_no": {"$exists": False}}]}],
             "shipped_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()}},
            {"_id": 0, "id": 1, "influencer_id": 1, "influencer_name": 1, "shipped_at": 1}).to_list(500)
        if pend and not stats.get("limit_hit"):
            from mng_kargo_client import list_shipments_by_date as _by_date
            _end = datetime.now(timezone.utc) + timedelta(days=1)
            _start = _end - timedelta(days=31)
            # Tek-tarih operasyonu için gün listesi: bekleyen kayıtların gönderim günü ve ertesi gün
            # (kurye çoğu zaman ertesi gün okutur). Günlük sorgu limitini korumak için en çok 14 gün.
            _days = set()
            for c in pend:
                try:
                    d0 = datetime.fromisoformat(str(c.get("shipped_at") or "")[:19]).replace(hour=0, minute=0, second=0, microsecond=0)
                    _days.add(d0); _days.add(d0 + timedelta(days=1))
                except Exception:
                    pass
            _days = sorted(_days, reverse=True)[:14]
            res = await _aio.to_thread(_by_date, username=user, password=pw, start=_start, end=_end, dates=_days)
            bd = {"ok": bool(res.get("ok")), "method": res.get("method"), "diag": res.get("diag"),
                  "days": [d.strftime("%d.%m") for d in _days],
                  "rows": len(res.get("rows") or []), "error": (res.get("error") or "")[:400], "matched": 0,
                  "sample_keys": ((res.get("rows") or [{}])[0].get("raw_keys") if res.get("rows") else None),
                  "sample_row": None, "pending": len(pend), "at": datetime.now(timezone.utc).isoformat()}
            if res.get("rows"):
                r0 = dict(res["rows"][0]); r0.pop("raw_keys", None)
                # PII: yalnız alan doluluğu (ad maskeli)
                r0["name"] = (r0.get("name") or "")[:2] + "***" if r0.get("name") else ""
                r0["phone"] = "***" if r0.get("phone") else ""
                bd["sample_row"] = r0
            if res.get("ok"):
                inf_names = {}
                ids = [c.get("influencer_id") for c in pend if c.get("influencer_id")]
                if ids:
                    async for i in db.influencers.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "full_name": 1}):
                        inf_names[i["id"]] = i.get("name") or i.get("full_name") or ""
                used = set()
                for row in res["rows"]:
                    trk = str(row.get("tracking") or "").strip()
                    nm = str(row.get("name") or "").strip()
                    if not trk or not nm or trk in used or "*" in nm:
                        continue
                    hits = [c for c in pend if any(_mng_name_match(n, nm) for n in
                                                   [c.get("influencer_name") or "", inf_names.get(c.get("influencer_id") or "", "")] if n)]
                    if not hits:
                        continue
                    def _dist(c, _d=row.get("date") or ""):
                        try:
                            dd = datetime.strptime(str(_d)[:10].replace("/", ".").replace("-", "."), "%d.%m.%Y") \
                                if "." in str(_d)[:10] or "/" in str(_d)[:10] else datetime.fromisoformat(str(_d)[:19])
                            sa = datetime.fromisoformat(str(c.get("shipped_at") or "")[:19])
                            return abs((sa - dd).days)
                        except Exception:
                            return 9999
                    hits.sort(key=_dist)
                    c = hits[0]
                    if _dist(c) > 20 and _dist(c) != 9999:
                        continue
                    used.add(trk)
                    pend = [x for x in pend if x["id"] != c["id"]]
                    await db.influencer_pr.update_one({"id": c["id"]}, {"$set": {
                        "cargo_gonderi_no": trk, "cargo_tracking_url": f"https://kargotakip.dhlecommerce.com.tr/?takipNo={trk}",
                        "cargo_mng_ref": str(row.get("ref") or ""), "cargo_last_status_text": str(row.get("status") or ""),
                        "cargo_track_note": "MNG gönderi listesinden alıcı adıyla eşlendi", "cargo_track_error": "",
                        "cargo_status_checked_at": datetime.now(timezone.utc).isoformat()}})
                    bd["matched"] += 1
                    stats["found"] += 1
            stats["by_date"] = bd
    except Exception as _bde:
        stats["by_date"] = {"ok": False, "error": str(_bde)[:200]}
    # TEŞHİS: MNG WSDL operasyon listesi (tarih bazlı gönderi listesi var mı?) — günde bir yeter
    try:
        _prev = await db.settings.find_one({"id": _PR_TRACK_HEALTH_ID}, {"_id": 0, "mng_ops_at": 1})
        if not _prev or (str(_prev.get("mng_ops_at") or "") < (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()):
            from mng_kargo_client import list_operations as _mng_ops
            stats["mng_ops"] = await _aio.to_thread(_mng_ops)
            stats["mng_ops_at"] = datetime.now(timezone.utc).isoformat()
    except Exception as _oe:
        stats["mng_ops"] = [f"hata: {str(_oe)[:80]}"]
    fin = datetime.now(timezone.utc)
    await _health(last_finish_at=fin.isoformat(),
                  duration_ms=int((fin - started).total_seconds() * 1000), interval_min=60)
    logger.info(f"[pr-track] bitti — aday {stats['candidates']} · sorgulanan {stats['checked']} · "
                f"takip no bulunan {stats['found']} · hata {stats['errors']}")
    return stats


def _mng_rows_from_upload(data: bytes, filename: str, text: str) -> list:
    """MNG panel listesi (xlsx/csv) ya da yapıştırılmış metin → satır listesi (hücre dizileri)."""
    rows = []
    fn = (filename or "").lower()
    if data and (fn.endswith(".xlsx") or fn.endswith(".xlsm") or data[:2] == b"PK"):
        import io as _io
        import openpyxl
        wb = openpyxl.load_workbook(_io.BytesIO(data), read_only=True, data_only=True)
        for ws in wb.worksheets:
            for r in ws.iter_rows(values_only=True):
                cells = ["" if v is None else (v.strftime("%d.%m.%Y") if hasattr(v, "strftime") else str(v)).strip() for v in r]
                if any(cells):
                    rows.append(cells)
    elif data:
        txt = data.decode("utf-8-sig", errors="ignore")
        text = (text or "") + "\n" + txt
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        sep = "\t" if "\t" in line else (";" if ";" in line else ",")
        rows.append([c.strip().strip('"') for c in line.split(sep)])
    return rows


def _mng_parse_row(cells: list) -> dict:
    """Satırdan takip no (10-14 hane), MNG referansı (RE-…), tarih ve isim adaylarını çıkar."""
    import re as _re
    out = {"tracking": "", "ref": "", "date": "", "names": []}
    for c in cells:
        c = str(c or "").strip()
        if not c:
            continue
        if not out["tracking"] and _re.fullmatch(r"\d{10,14}", c):
            out["tracking"] = c
        elif not out["ref"] and _re.fullmatch(r"[A-Z]{1,3}-?\d{4,}", c):
            out["ref"] = c
        elif not out["date"] and _re.fullmatch(r"\d{2}[./-]\d{2}[./-]\d{4}.*", c):
            out["date"] = c[:10]
        elif "*" not in c and _re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2,}", c) and not _re.search(r"\d{4,}", c):
            out["names"].append(c)
    return out


def _mng_name_match(pr_name: str, cell: str) -> bool:
    a, b = _inf_norm(pr_name), _inf_norm(cell)
    if not a or not b or len(a) < 4:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    return len(ta) >= 2 and ta <= tb or (len(tb) >= 2 and tb <= ta)


@router.post("/influencer-pr/import-mng-tracking")
async def influencer_pr_import_mng_tracking(file: UploadFile = File(None), text: str = Form(""),
                                            apply: str = Form("0"), current_user: dict = Depends(require_admin)):
    """MNG panel gönderi listesini (xlsx/csv/yapıştırılmış metin) alıcı ADINA göre PR kayıtlarıyla eşler
    ve takip no'yu yazar. Neden gerekli: kurye paketi bizim 'INF…' referansımız yerine kendi
    'RE-…' referansıyla açtığında MNG bizim sorgumuza takip no döndürmez (panelde 'işlem yapılmadı'
    kalır); MNG panelindeki liste ise gerçek takip no'yu içerir. apply=0 → yalnız önizleme."""
    data = await file.read() if file is not None else b""
    rows = _mng_rows_from_upload(data, getattr(file, "filename", "") or "", text or "")
    parsed = [_mng_parse_row(r) for r in rows]
    parsed = [p for p in parsed if p["tracking"] and p["names"]]
    if not parsed:
        raise HTTPException(status_code=400, detail="Listede takip no + alıcı adı içeren satır bulunamadı (xlsx/csv ya da panelden kopyalanan satırlar).")
    # Adaylar: kargosu olan, gerçek takip no'su boş PR kayıtları (elle girilenler korunur)
    cands = await db.influencer_pr.find(
        {"$or": [{"cargo_barcode": {"$nin": [None, ""]}}, {"cargo_tracking_no": {"$nin": [None, ""]}}],
         "$and": [{"$or": [{"cargo_gonderi_no": {"$in": [None, ""]}}, {"cargo_gonderi_no": {"$exists": False}}]}]},
        {"_id": 0, "id": 1, "influencer_id": 1, "influencer_name": 1, "shipped_at": 1, "cargo_barcode": 1, "cargo_mng_no": 1}
    ).to_list(2000)
    inf_names = {}
    ids = [c.get("influencer_id") for c in cands if c.get("influencer_id")]
    if ids:
        async for i in db.influencers.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1, "full_name": 1}):
            inf_names[i["id"]] = i.get("name") or i.get("full_name") or ""
    used_tracking, matches, unmatched = set(), [], []
    for p in parsed:
        hit = []
        for c in cands:
            names = [c.get("influencer_name") or "", inf_names.get(c.get("influencer_id") or "", "")]
            if any(_mng_name_match(n, cell) for n in names if n for cell in p["names"]):
                hit.append(c)
        if not hit:
            unmatched.append({"tracking": p["tracking"], "ref": p["ref"], "date": p["date"], "names": p["names"][:3]})
            continue
        # Aynı isimde birden çok bekleyen kayıt: gönderim tarihi liste tarihine en yakın olan
        def _dist(c):
            try:
                d = datetime.strptime(p["date"].replace("/", ".").replace("-", "."), "%d.%m.%Y")
                sa = datetime.fromisoformat(str(c.get("shipped_at") or "")[:19])
                return abs((sa - d).days)
            except Exception:
                return 9999
        hit.sort(key=_dist)
        c = hit[0]
        if p["tracking"] in used_tracking:
            continue
        used_tracking.add(p["tracking"])
        cands = [x for x in cands if x["id"] != c["id"]]
        matches.append({"pr_id": c["id"], "name": c.get("influencer_name") or inf_names.get(c.get("influencer_id") or "", ""),
                        "tracking": p["tracking"], "ref": p["ref"], "date": p["date"], "shipped_at": c.get("shipped_at")})
    applied = 0
    if str(apply) in ("1", "true", "yes") and matches:
        for m in matches:
            await db.influencer_pr.update_one({"id": m["pr_id"]}, {"$set": {
                "cargo_gonderi_no": m["tracking"], "cargo_tracking_url": f"https://kargotakip.dhlecommerce.com.tr/?takipNo={m['tracking']}",
                "cargo_mng_ref": m["ref"], "cargo_track_note": "MNG listesinden eşlendi", "cargo_track_error": "",
                "cargo_manual_tracking": True, "updated_at": _now_iso()}})
            applied += 1
    return {"rows": len(rows), "parsed": len(parsed), "matches": matches, "unmatched": unmatched, "applied": applied}


@router.get("/influencer-pr/tracking-health")
async def influencer_pr_tracking_health(current_user: dict = Depends(require_admin)):
    """Saatlik otomatik takip taramasının sağlık bilgisi (son çalışma, sayaçlar, son hata)."""
    h = await db.settings.find_one({"id": _PR_TRACK_HEALTH_ID}, {"_id": 0}) or {}
    if not h:
        h = {"status": "unknown"}
    return h


@router.post("/influencer-pr/tracking-scan")
async def influencer_pr_tracking_scan(current_user: dict = Depends(require_admin)):
    """Otomatik takip taramasını ŞİMDİ çalıştır (saatlik cron ile aynı iş)."""
    import asyncio as _aio
    return await _aio.wait_for(auto_refresh_pr_tracking(), timeout=240)


@router.get("/influencer-pr/{entry_id}/cargo-label")
async def influencer_pr_cargo_label(entry_id: str, current_user: dict = Depends(require_admin)):
    """Influencer PR gönderisinin YAZDIRILABİLİR kargo etiketi — sipariş etiketiyle AYNI şablon
    (orders._render_cargo_label_html). Alıcı = influencer kargo adresi, barkod = cargo_barcode.
    Authorization başlığı ile kimlik doğrulanır; URL'de oturum anahtarı kabul edilmez."""
    from fastapi.responses import HTMLResponse
    from .orders import _render_cargo_label_html, _get_sender_info, _get_mng_settings
    e = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    bc = (e.get("cargo_barcode") or "").strip()
    if not bc:
        raise HTTPException(status_code=400, detail="Bu gönderi için kargo barkodu yok — önce 'Barkod Çıkart' ile kargoya verin.")
    # SİPARİŞ ETİKETİYLE AYNI KURAL: barkod çubukları = MNG'ye verdiğimiz SİPARİŞ REFERANSI
    # (siparişte W10047, burada INF…). Kurye terminali referansı okutunca paketi bizim kayda bağlar
    # ve takip no otomatik gelir. Eskiden çubuklar MNG iç no'yu (1803461455) kodluyordu; terminal
    # bunu referans olarak bulamayınca kurye kendi RE-… irsaliyesini açıyor, takip no bize gelmiyordu.
    ref = (e.get("cargo_tracking_no") or "").strip()
    if ref.upper().startswith("INF"):
        bc = ref
    inf = await db.influencers.find_one({"id": e.get("influencer_id")}, {"_id": 0}) or {}
    addr = inf.get("shipping_address") or {}
    rname = (addr.get("full_name") or inf.get("name") or e.get("influencer_name") or "Alıcı").strip()
    rphone = (addr.get("phone") or inf.get("phone") or "").strip()
    radres = (addr.get("adres") or addr.get("address") or "").strip()
    rcity = " / ".join([x for x in [(addr.get("ilce") or addr.get("district") or "").strip(),
                                     (addr.get("il") or addr.get("city") or "").strip()] if x])
    rfull = ", ".join([x for x in [radres, rcity] if x])
    sender = await _get_sender_info()
    mng = await _get_mng_settings()
    sender_company = mng.get("customer_code") or sender.get("name") or "FACETTE"
    sender_addr_line = f"{sender.get('address','')}, {sender.get('district','')}/{sender.get('city','')}".strip(" ,/")
    html = _render_cargo_label_html(
        siparis_no=bc, main_barcode=bc,
        sender_company=sender_company, sender_phone=sender.get("phone", "") or "",
        sender_addr_line=sender_addr_line,
        receiver_name=rname, receiver_phone=rphone, receiver_full_addr=rfull,
        cargo_company_display="DHL E-Commerce", odeme_turu="Peşin Ödemeli", kargo_tipi="Peşin Ödemeli Kargo",
    )
    return HTMLResponse(content=html, headers={"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/influencer-pr/{entry_id}/irsaliye")
async def influencer_pr_irsaliye(entry_id: str, current_user: dict = Depends(require_admin)):
    """Influencer PR gönderisinin A4 SEVK İRSALİYESİ (yazdırılabilir/PDF) — gönderilen ürünleri
    (ad, beden, adet, barkod) influencer bilgileriyle listeler. Bedelsiz tanıtım/numune notu içerir.
    Authorization başlığı ile kimlik; ?print=1 ile otomatik yazdır."""
    from fastapi.responses import HTMLResponse
    from .orders import _get_sender_info
    import html as _h
    e = await db.influencer_pr.find_one({"id": entry_id}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="PR kaydı bulunamadı")
    inf = await db.influencers.find_one({"id": e.get("influencer_id")}, {"_id": 0}) or {}
    addr = inf.get("shipping_address") or {}
    rname = (addr.get("full_name") or inf.get("name") or e.get("influencer_name") or "—").strip()
    rphone = (addr.get("phone") or inf.get("phone") or "").strip()
    radres = (addr.get("adres") or addr.get("address") or "").strip()
    rcity = " / ".join([x for x in [(addr.get("ilce") or addr.get("district") or "").strip(),
                                     (addr.get("il") or addr.get("city") or "").strip()] if x])
    rfull = ", ".join([x for x in [radres, rcity] if x]) or "—"
    insta = (inf.get("instagram") or e.get("instagram") or "").strip()
    sender = await _get_sender_info()
    sender_company = sender.get("name") or "FACETTE"
    sender_addr = f"{sender.get('address','')}, {sender.get('district','')}/{sender.get('city','')}".strip(" ,/")
    sender_phone = sender.get("phone", "") or ""
    tarih = (e.get("shipped_at") or e.get("date") or _now_iso())[:10]
    irs_no = (e.get("cargo_barcode") or (e.get("id") or "")[:8]).strip()

    prods = [p for p in (e.get("products") or []) if isinstance(p, dict)]
    rows = ""
    toplam = 0
    for i, p in enumerate(prods, 1):
        q = int(p.get("qty") or 1)
        toplam += q
        rows += (f"<tr><td class='c'>{i}</td><td>{_h.escape(str(p.get('name') or 'Ürün'))}</td>"
                 f"<td class='c'>{_h.escape(str(p.get('size') or '-'))}</td>"
                 f"<td class='c'>{q}</td>"
                 f"<td class='c mono'>{_h.escape(str(p.get('barcode') or ''))}</td></tr>")
    if not rows:
        rows = "<tr><td colspan='5' class='c' style='padding:14px;color:#888'>Ürün bulunmuyor.</td></tr>"

    def _esc(v):
        return _h.escape(str(v if v is not None else ""))

    html = f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="UTF-8"><title>Sevk İrsaliyesi - {_esc(rname)}</title>
<style>
  @page {{ size: A4; margin: 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; color:#111; margin:0; }}
  .hd {{ display:flex; justify-content:space-between; align-items:flex-start; border-bottom:2px solid #111; padding-bottom:10px; }}
  .brand {{ font-size:22px; font-weight:800; letter-spacing:3px; }}
  .brand small {{ display:block; font-size:10px; font-weight:600; letter-spacing:1px; color:#555; margin-top:3px; }}
  .doc {{ text-align:right; }}
  .doc .t {{ font-size:16px; font-weight:800; letter-spacing:1px; }}
  .doc .m {{ font-size:11px; color:#444; margin-top:4px; line-height:1.5; }}
  .parties {{ display:flex; gap:16px; margin-top:14px; }}
  .box {{ flex:1; border:1px solid #ccc; border-radius:6px; padding:10px 12px; }}
  .box .lbl {{ font-size:10px; font-weight:700; letter-spacing:.5px; color:#666; text-transform:uppercase; margin-bottom:5px; }}
  .box .nm {{ font-size:13px; font-weight:700; }}
  .box .ln {{ font-size:11.5px; color:#333; line-height:1.5; }}
  table {{ width:100%; border-collapse:collapse; margin-top:16px; font-size:12px; }}
  th {{ background:#111; color:#fff; text-align:left; padding:8px 10px; font-size:11px; letter-spacing:.4px; }}
  td {{ border-bottom:1px solid #e2e2e2; padding:8px 10px; }}
  td.c, th.c {{ text-align:center; }}
  .mono {{ font-family:'Courier New',monospace; }}
  tfoot td {{ font-weight:800; border-top:2px solid #111; }}
  .note {{ margin-top:14px; font-size:11px; color:#555; background:#f7f7f7; border-radius:6px; padding:10px 12px; }}
  .sign {{ display:flex; gap:40px; margin-top:40px; }}
  .sign .s {{ flex:1; text-align:center; }}
  .sign .line {{ border-top:1px solid #999; margin-top:36px; padding-top:6px; font-size:11px; color:#555; }}
</style></head><body>
  <div class="hd">
    <div class="brand">{_esc(sender_company)}<small>{_esc(sender_addr)}{(' · '+_esc(sender_phone)) if sender_phone else ''}</small></div>
    <div class="doc">
      <div class="t">SEVK İRSALİYESİ</div>
      <div class="m">Belge No: <b>{_esc(irs_no)}</b><br>Tarih: <b>{_esc(tarih)}</b></div>
    </div>
  </div>

  <div class="parties">
    <div class="box">
      <div class="lbl">Gönderen</div>
      <div class="nm">{_esc(sender_company)}</div>
      <div class="ln">{_esc(sender_addr)}</div>
      {('<div class="ln">Tel: '+_esc(sender_phone)+'</div>') if sender_phone else ''}
    </div>
    <div class="box">
      <div class="lbl">Alıcı (Influencer)</div>
      <div class="nm">{_esc(rname)}{('  ·  '+_esc(insta)) if insta else ''}</div>
      <div class="ln">{_esc(rfull)}</div>
      {('<div class="ln">Tel: '+_esc(rphone)+'</div>') if rphone else ''}
    </div>
  </div>

  <table>
    <thead><tr><th class="c" style="width:34px">#</th><th>Ürün</th><th class="c" style="width:70px">Beden</th><th class="c" style="width:56px">Adet</th><th class="c" style="width:150px">Barkod</th></tr></thead>
    <tbody>{rows}</tbody>
    <tfoot><tr><td colspan="3" style="text-align:right">TOPLAM ADET</td><td class="c">{toplam}</td><td></td></tr></tfoot>
  </table>

  <div class="note">Bu sevk irsaliyesi, tanıtım/iş birliği kapsamında <b>bedelsiz numune ürün</b> gönderimi içindir. Satışa konu değildir.</div>

  <div class="sign">
    <div class="s"><div class="line">Teslim Eden (Kaşe / İmza)</div></div>
    <div class="s"><div class="line">Teslim Alan (İmza)</div></div>
  </div>

<script>
  window.addEventListener('load', () => {{
    if (window.location.search.includes('print=1')) setTimeout(() => window.print(), 250);
  }});
</script>
</body></html>"""
    return HTMLResponse(content=html, headers={"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/influencers/{influencer_id}/history")
async def influencer_history(influencer_id: str, current_user: dict = Depends(require_admin)):
    """Yan sayfa: bir influencerla GEÇMİŞ — daha önce ne gönderdik (seeding kampanyaları)
    + tüm PR işlemleri. 'Ne aldık/gönderdik' bu iki kaynaktan gelir."""
    inf = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")
    campaigns = await db.influencer_campaigns.find(
        {"influencer_id": influencer_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    pr_entries = await db.influencer_pr.find(
        {"influencer_id": influencer_id}, {"_id": 0}).sort("date", -1).to_list(500)
    return {"influencer": inf, "campaigns": campaigns, "pr_entries": pr_entries}


# =============================================================================
# CAMPAIGNS CRUD
# =============================================================================

@router.post("/influencers/{influencer_id}/campaigns")
async def create_campaign(influencer_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    inf = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")
    payload["influencer_id"] = influencer_id
    # directives boş gönderilse bile zorunlu standartlar yazılsın
    if not (payload.get("directives") or "").strip():
        payload["directives"] = DEFAULT_CAMPAIGN_DIRECTIVES
    model = InfluencerCampaign(**payload)
    doc = model.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.influencer_campaigns.insert_one(doc)
    doc.pop("_id", None)
    return {"success": True, "campaign": doc}


@router.get("/influencers/{influencer_id}/campaigns")
async def list_campaigns(influencer_id: str, current_user: dict = Depends(require_admin)):
    docs = await db.influencer_campaigns.find(
        {"influencer_id": influencer_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return {"campaigns": docs, "total": len(docs)}


@router.get("/influencer-campaigns")
async def list_all_campaigns(
    q: Optional[str] = Query(None),
    shared: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(require_admin),
):
    """TÜM influencer gönderimleri (ürün yollama geçmişi) — her kayıt influencer
    adı/hesabıyla zenginleştirilir. 'Gönderim Geçmişi' sekmesini besler.
    Filtreler: q (başlık/influencer/ürün adı), shared (paylaşıldı mı), status."""
    query = {}
    if shared is not None:
        query["shared"] = shared
    if status:
        query["status"] = status
    camps = await db.influencer_campaigns.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    inf_ids = list({c.get("influencer_id") for c in camps if c.get("influencer_id")})
    infs = {}
    if inf_ids:
        cursor = db.influencers.find(
            {"id": {"$in": inf_ids}},
            {"_id": 0, "id": 1, "name": 1, "handle": 1, "instagram": 1, "tiktok": 1, "platform": 1},
        )
        async for d in cursor:
            infs[d["id"]] = d
    ql = (q or "").strip().lower()
    out = []
    for c in camps:
        inf = infs.get(c.get("influencer_id"), {})
        c["influencer_name"] = inf.get("name", "")
        c["influencer_handle"] = inf.get("handle") or inf.get("instagram") or inf.get("tiktok") or ""
        c["influencer_platform"] = inf.get("platform", "")
        if ql:
            hay = " ".join([
                str(c.get("title") or ""),
                str(c["influencer_name"]),
                str(c["influencer_handle"]),
                " ".join([str((p or {}).get("name") or "") for p in (c.get("sent_products") or [])]),
            ]).lower()
            if ql not in hay:
                continue
        out.append(c)
    return {"campaigns": out, "total": len(out)}


@router.put("/influencer-campaigns/{campaign_id}")
async def update_campaign(campaign_id: str, payload: dict, current_user: dict = Depends(require_admin)):
    existing = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    allowed = {
        "title", "fee_paid", "product_cost", "cargo_cost", "sent_products",
        "directives", "status", "cargo_status", "cargo_barcode", "cargo_tracking_no",
        "content_url", "notes", "sent_at", "shared", "shared_at",
    }
    update = {k: v for k, v in payload.items() if k in allowed}
    # Paylaşım tik'i (checkbox toggle): shared True↔False; shared_at otomatik damgalanır/silinir.
    if "shared" in update:
        if update["shared"]:
            update.setdefault("shared_at", _now_iso())
            if (existing.get("status") or "draft") in ("draft", "shipped"):
                update.setdefault("status", "shared")
        else:
            update["shared_at"] = None
    update["updated_at"] = _now_iso()
    await db.influencer_campaigns.update_one({"id": campaign_id}, {"$set": update})
    # Kampanya iptal edilirse düşülen seeding stoğu otomatik geri döner (idempotent).
    if update.get("status") == "cancelled" and existing.get("stock_deducted"):
        try:
            await _seeding_restock({**existing, **update, "id": campaign_id}, reason="campaign_cancelled")
        except Exception as e:
            logger.warning(f"[influencer] iptalde stok iadesi başarısız {campaign_id}: {e}")
    doc = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return {"success": True, "campaign": doc}


@router.delete("/influencer-campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, current_user: dict = Depends(require_admin)):
    # Stok düşülmüş kampanya silinirse ürünler stoğa geri döner (kayıp olmasın).
    camp = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if camp and camp.get("stock_deducted"):
        try:
            await _seeding_restock(camp, reason="campaign_deleted")
        except Exception as e:
            logger.warning(f"[influencer] silmede stok iadesi başarısız {campaign_id}: {e}")
    res = await db.influencer_campaigns.delete_one({"id": campaign_id})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    return {"success": True}


# =============================================================================
# SEEDING — Gönderilecek ürünler: seçim + STOK DÜŞÜMÜ (atomik, idempotent)
# =============================================================================

async def _resolve_seeding_items(products: list) -> list:
    """[{barcode, qty}] → doğrulanmış [{barcode, quantity, product_id, name, size, unit_cost}].
    Barkod varyantta veya üründe aranır; bulunamayan/stok yetmeyen kalem hata verir."""
    items = []
    for p in products or []:
        bc = str((p or {}).get("barcode") or "").strip()
        try:
            qty = max(1, int((p or {}).get("qty") or (p or {}).get("quantity") or 1))
        except Exception:
            qty = 1
        if not bc:
            continue
        prod = await db.products.find_one(
            {"$or": [{"variants.barcode": bc}, {"barcode": bc}]},
            {"_id": 0, "id": 1, "name": 1, "price": 1, "cost_price": 1, "variants": 1, "stock": 1})
        if not prod:
            raise HTTPException(status_code=400, detail=f"Barkod bulunamadı: {bc}")
        size = ""
        stock = prod.get("stock")
        for v in (prod.get("variants") or []):
            if str(v.get("barcode") or "").strip() == bc:
                size = v.get("size") or ""
                stock = v.get("stock")
                break
        if stock is not None and int(stock or 0) < qty:
            raise HTTPException(status_code=409,
                                detail=f"Stok yetersiz: {prod.get('name')} {size} (stok {stock}, istenen {qty})")
        # Birim maliyet: manuel product_costs > products.cost_price > fiyatın %50'si (rapor motoruyla aynı kural)
        cost_rec = await db.product_costs.find_one({"product_id": prod["id"]}, {"_id": 0, "cost_price": 1})
        unit_cost = float((cost_rec or {}).get("cost_price") or prod.get("cost_price") or 0) \
            or float(prod.get("price") or 0) * 0.5
        items.append({"barcode": bc, "quantity": qty, "product_id": prod["id"],
                      "name": prod.get("name") or "", "size": size,
                      "unit_cost": round(unit_cost, 2)})
    if not items:
        raise HTTPException(status_code=400, detail="Geçerli ürün seçilmedi")
    return items


async def _seeding_restock(camp: dict, reason: str) -> None:
    """Kampanyanın düşülen stoğunu İDEMPOTENT geri yükler (atomik bayrak kilidi)."""
    lock = await db.influencer_campaigns.update_one(
        {"id": camp["id"], "stock_deducted": True},
        {"$set": {"stock_deducted": False, "updated_at": _now_iso()}})
    if not lock.modified_count:
        return  # zaten iade edilmiş / hiç düşülmemiş
    from .orders import _stock_delta_for_order
    items = [{"barcode": p.get("barcode"), "quantity": p.get("qty") or p.get("quantity") or 1}
             for p in (camp.get("sent_products") or []) if p.get("barcode")]
    moves = await _stock_delta_for_order({"items": items}, +1)
    await db.stock_movements.insert_one({
        "id": str(_uuid.uuid4()), "type": "influencer_seeding_restock",
        "campaign_id": camp["id"], "influencer_id": camp.get("influencer_id"),
        "reason": reason, "items": moves, "created_at": _now_iso()})
    logger.info(f"[influencer] seeding stok iadesi: kampanya {camp['id']} ({reason})")


@router.post("/influencer-campaigns/{campaign_id}/commit-products")
async def commit_campaign_products(campaign_id: str, payload: dict,
                                   current_user: dict = Depends(require_admin)):
    """Gönderilecek ürünleri kampanyaya işler ve STOKTAN DÜŞER.

    Body: {"products": [{"barcode": "868...", "qty": 1}], "auto_cost": true}
    - sent_products doldurulur (ad/beden/barkod/adet), stok stock_movements'a
      'influencer_seeding' hareketiyle düşülür (çift işleme atomik bayrakla kapalı).
    - auto_cost (varsayılan açık): ürün maliyeti toplamı product_cost'a yazılır
      (rapordaki maliyet kuralıyla aynı: manuel maliyet > cost_price > fiyat*0.5) → ROI gerçekçi.
    """
    camp = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    if camp.get("stock_deducted"):
        raise HTTPException(status_code=409,
                            detail="Bu kampanyanın stoğu zaten düşülmüş — önce 'Stok İadesini Geri Al' kullanın")
    items = await _resolve_seeding_items((payload or {}).get("products"))

    # Atomik kilit: aynı anda iki commit gelirse yalnız biri düşer.
    lock = await db.influencer_campaigns.update_one(
        {"id": campaign_id, "stock_deducted": {"$ne": True}},
        {"$set": {"stock_deducted": True, "updated_at": _now_iso()}})
    if not lock.modified_count:
        raise HTTPException(status_code=409, detail="Stok bu kampanya için zaten düşülmüş")

    from .orders import _stock_delta_for_order
    moves = await _stock_delta_for_order({"items": items}, -1)
    await db.stock_movements.insert_one({
        "id": str(_uuid.uuid4()), "type": "influencer_seeding",
        "campaign_id": campaign_id, "influencer_id": camp.get("influencer_id"),
        "items": moves, "created_by": current_user.get("email", ""),
        "created_at": _now_iso()})

    sent = [{"name": it["name"], "barcode": it["barcode"], "size": it["size"], "qty": it["quantity"]}
            for it in items]
    upd = {"sent_products": sent, "updated_at": _now_iso()}
    total_cost = round(sum(it["unit_cost"] * it["quantity"] for it in items), 2)
    if (payload or {}).get("auto_cost", True) and total_cost > 0:
        upd["product_cost"] = total_cost
    await db.influencer_campaigns.update_one({"id": campaign_id}, {"$set": upd})
    doc = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return {"success": True, "campaign": doc, "stock_moves": len(moves), "product_cost": total_cost}


@router.post("/influencer-campaigns/{campaign_id}/uncommit-products")
async def uncommit_campaign_products(campaign_id: str, current_user: dict = Depends(require_admin)):
    """Düşülen seeding stoğunu geri yükler (yanlış seçim / kampanya vazgeçildi)."""
    camp = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    if not camp.get("stock_deducted"):
        raise HTTPException(status_code=400, detail="Bu kampanya için düşülmüş stok yok")
    await _seeding_restock(camp, reason="manual_uncommit")
    doc = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return {"success": True, "campaign": doc}


# =============================================================================
# SEEDING — Kargo barkod üretimi (MNG) + SMS
# =============================================================================

@router.post("/influencer-campaigns/{campaign_id}/cargo")
async def create_campaign_cargo(campaign_id: str, current_user: dict = Depends(require_admin)):
    """Influencer seeding gönderisi için MNG kargo barkodu üretir ve SMS atar."""
    camp = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    inf = await db.influencers.find_one({"id": camp["influencer_id"]}, {"_id": 0})
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")

    addr = inf.get("shipping_address") or {}
    il = (addr.get("il") or addr.get("city") or "").strip()
    ilce = (addr.get("ilce") or addr.get("district") or "").strip()
    adres = (addr.get("adres") or addr.get("address") or "").strip()
    full_name = (addr.get("full_name") or inf.get("name") or "").strip()
    phone = (addr.get("phone") or inf.get("phone") or "").strip()
    if not (il and ilce and adres and phone):
        raise HTTPException(status_code=400, detail="Influencer kargo adresi eksik (il, ilçe, adres, telefon gerekli)")

    # MNG ayarları (helper orders.py içinde tanımlı)
    try:
        from .orders import _get_mng_settings
        mng = await _get_mng_settings()
    except Exception as e:
        logger.warning(f"MNG settings load failed: {e}")
        raise HTTPException(status_code=400, detail="Kargo entegrasyonu yapılandırılmamış")
    username = mng.get("username")
    password = mng.get("password")
    if not (username and password):
        raise HTTPException(status_code=400, detail="MNG Kargo ayarları yapılmamış")

    siparis_no = f"INF{campaign_id[:8].upper()}"
    icerik = ", ".join([p.get("name", "Ürün") for p in (camp.get("sent_products") or [])]) or "Numune Ürün"
    # MNG E022: pChIcerik en fazla 200 karakter. Çok ürünlü gönderide (ör. 7 ürün) isim listesi
    # sınırı aşıp kargoyu reddettiriyordu → 197 kes + "..." (toplam ≤200).
    if len(icerik) > 200:
        icerik = icerik[:197].rstrip(", ") + "..."

    from mng_kargo_client import create_shipment
    from fastapi.concurrency import run_in_threadpool

    def _ship():
        return create_shipment(
            username=username, password=password, siparis_no=siparis_no,
            icerik=icerik, hizmet_sekli="NORMAL", teslim_sekli=1,
            al_sms=0, gn_sms=1 if phone else 0,
            parca_list="1:1:20:30:15:;",
            alici_ad=full_name, il=il, ilce=ilce, adres=adres,
            tel_cep=phone, odeme_sekli="P", platform_adi="", platform_kodu="",
        )

    try:
        res = await run_in_threadpool(_ship)
    except Exception as e:
        # 502 yerine 400: proxy/Cloudflare 5xx gövdesini maskeleyip gerçek sebebi frontend'e
        # ulaştırmıyordu. 400 ile MNG'nin döndürdüğü ASIL hata "Kargo oluşturulamadı" toast'ında görünür.
        logger.warning(f"[influencer] MNG create_shipment exception (kampanya={campaign_id}, ilce={ilce}): {e}")
        raise HTTPException(status_code=400, detail=f"MNG kargo hatası: {e}")

    mng_no = (res.get("barkod") or "").strip()   # MNG iç sipariş no (takip no DEĞİL)
    if not res.get("ok"):
        _hata = str(res.get("hata") or "")
        # E005/"ZATEN VAR": kayıt MNG'de zaten oluşmuş (önceki denemede) — hata değil,
        # barkod aşağıda tamamlanır. Diğer hatalarda GERÇEK SEBEBİ 400 ile döndür.
        if not (("ZATEN VAR" in _hata.upper()) or ("E005" in _hata.upper())):
            logger.warning(f"[influencer] MNG kargo başarısız (kampanya={campaign_id}, ilce={ilce}): {_hata or res}")
            raise HTTPException(status_code=400, detail=f"Kargo oluşturulamadı: {_hata or res}")
    # SİPARİŞLER İLE AYNI ADIM: MNGGonderiBarkod → anında NZ formatlı GERÇEK takip barkodu.
    # Etikete bu basılır; kurye bunu okutunca paket bizim kayda bağlanır ve takip no hazır olur.
    # (Eskiden etikete MNG iç sipariş no basılıyordu → kurye tanımayıp kendi RE-… irsaliyesini
    # açıyor, takip no hiç gelmiyordu.)
    nz_barkod, nz_gonderi = "", ""
    try:
        from mng_kargo_client import get_mng_barcode_immediately
        _b = await run_in_threadpool(
            lambda: get_mng_barcode_immediately(username=username, password=password, siparis_no=siparis_no,
                                                urun_bedeli=0, kapida_tahsilat=False))
        if _b.get("ok"):
            nz_barkod = (_b.get("barkod") or "").strip()
            nz_gonderi = (_b.get("gonderi_no") or "").strip()
            logger.info(f"[influencer] MNG NZ barkod {siparis_no}: {nz_barkod} (gonderi_no={nz_gonderi})")
        else:
            logger.info(f"[influencer] MNGGonderiBarkod başarısız {siparis_no}: {_b.get('hata')}")
    except Exception as _be:
        logger.warning(f"[influencer] MNG barkod çekme başarısız {siparis_no}: {_be}")
    real_tracking = nz_barkod or nz_gonderi
    barkod = real_tracking or mng_no or siparis_no   # etiket barkodu: NZ > MNG no > referans

    await db.influencer_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "cargo_status": "created",
            "cargo_barcode": barkod,
            "cargo_mng_no": mng_no,
            "cargo_gonderi_no": real_tracking,
            "cargo_tracking_url": (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={real_tracking}" if real_tracking else ""),
            "cargo_tracking_no": siparis_no,
            "status": "shipped" if camp.get("status") == "draft" else camp.get("status"),
            "sent_at": camp.get("sent_at") or _now_iso(),   # gönderim tarihi (kargoya verildi)
            "updated_at": _now_iso(),
        }},
    )

    # SMS bildirimi (influencer'a)
    sms_res = await _send_direct_sms(
        phone,
        f"Merhaba {inf.get('name','')}, Facette numune gonderiniz hazirlandi. Takip: {real_tracking or siparis_no}",
    )

    return {"success": True, "cargo_barcode": barkod, "tracking_no": siparis_no, "sms": sms_res,
            "gonderi_no": real_tracking, "mng_no": mng_no,
            "tracking_url": (f"https://kargotakip.dhlecommerce.com.tr/?takipNo={real_tracking}" if real_tracking else "")}


@router.post("/influencers/cargo-webhook")
async def influencer_cargo_webhook(payload: dict, request: Request):
    """Kargo statü değişimi webhook'u → influencer'a SMS.
    Payload: { tracking_no | siparis_no, status }  (Kargoya Verildi / Teslim Edildi).
    GÜVENLİK: Paylaşımlı secret zorunlu (fail-closed) — aksi halde herkes ücretli SMS
    tetikleyip kargo durumu forge edebiliyordu."""
    import os as _os, hmac as _hmac
    _secret = (_os.environ.get("INFLUENCER_WEBHOOK_SECRET", "") or "").strip()
    if not _secret:
        _cfg = await db.settings.find_one({"id": "influencer"}, {"_id": 0, "webhook_secret": 1}) or {}
        _secret = str(_cfg.get("webhook_secret") or "").strip()
    _provided = (request.headers.get("X-Webhook-Secret")
                 or request.query_params.get("key") or "").strip()
    if not _secret or not _provided or not _hmac.compare_digest(_secret, _provided):
        raise HTTPException(status_code=401, detail="Yetkisiz webhook")
    tracking = (payload.get("tracking_no") or payload.get("siparis_no") or "").strip()
    status = (payload.get("status") or "").strip()
    if not tracking:
        raise HTTPException(status_code=400, detail="tracking_no gerekli")

    camp = await db.influencer_campaigns.find_one({"cargo_tracking_no": tracking}, {"_id": 0})
    if not camp:
        return {"success": False, "message": "Eşleşen kampanya yok"}

    inf = await db.influencers.find_one({"id": camp["influencer_id"]}, {"_id": 0})

    status_lower = status.lower()
    new_cargo_status = camp.get("cargo_status")
    sms_text = None
    if "teslim" in status_lower or "delivered" in status_lower:
        new_cargo_status = "delivered"
        sms_text = "Facette numune gonderiniz teslim edildi. Icerik standartlari: 9:16 dikey format, @facette mention. Iyi cekimler!"
    elif "kargo" in status_lower or "shipped" in status_lower or "yola" in status_lower:
        new_cargo_status = "shipped"
        sms_text = f"Facette numune gonderiniz kargoya verildi. Takip: {tracking}"

    await db.influencer_campaigns.update_one(
        {"id": camp["id"]},
        {"$set": {"cargo_status": new_cargo_status, "updated_at": _now_iso()}},
    )

    sms_res = None
    if sms_text and inf and (inf.get("phone") or (inf.get("shipping_address") or {}).get("phone")):
        phone = inf.get("phone") or (inf.get("shipping_address") or {}).get("phone")
        sms_res = await _send_direct_sms(phone, sms_text)

    return {"success": True, "cargo_status": new_cargo_status, "sms": sms_res}


# =============================================================================
# PAYLAŞIM DOĞRULAMASI
# =============================================================================

@router.post("/influencer-campaigns/{campaign_id}/confirm-share")
async def confirm_share(campaign_id: str, payload: dict = None, current_user: dict = Depends(require_admin)):
    """Manuel 'Paylaşıldı Onayı'. payload: { content_url? }"""
    camp = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not camp:
        raise HTTPException(status_code=404, detail="Kampanya bulunamadı")
    content_url = ((payload or {}).get("content_url") or "").strip()
    await db.influencer_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "shared": True,
            "shared_at": _now_iso(),
            "content_url": content_url or camp.get("content_url"),
            "status": "shared",
            "updated_at": _now_iso(),
        }},
    )
    doc = await db.influencer_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    return {"success": True, "campaign": doc}


@router.post("/influencers/meta-webhook")
async def meta_share_webhook(payload: dict):
    """Meta mention webhook stub — markayı mention'layan içeriği yakalar.
    Üretimde Meta App webhook subscription'a bağlanır (verify token + signature)."""
    logger.info(f"Meta mention webhook received: {str(payload)[:300]}")
    return {"success": True, "received": True}


# =============================================================================
# ROI MOTORU (Modül 4)
# =============================================================================

@router.get("/influencers/{influencer_id}/roi")
async def get_influencer_roi(influencer_id: str, current_user: dict = Depends(require_admin)):
    """Influencer ROI: Toplam Maliyet (ücret+ürün+kargo) vs Ciro → Net Kâr & ROAS."""
    inf = await db.influencers.find_one({"id": influencer_id}, {"_id": 0})
    if not inf:
        raise HTTPException(status_code=404, detail="Influencer bulunamadı")

    # --- Maliyet (kampanya aggregation) ---
    cost_pipeline = [
        {"$match": {"influencer_id": influencer_id}},
        {"$group": {
            "_id": None,
            "fee_paid": {"$sum": {"$ifNull": ["$fee_paid", 0]}},
            "product_cost": {"$sum": {"$ifNull": ["$product_cost", 0]}},
            "cargo_cost": {"$sum": {"$ifNull": ["$cargo_cost", 0]}},
            "campaign_count": {"$sum": 1},
            "shared_count": {"$sum": {"$cond": [{"$eq": ["$shared", True]}, 1, 0]}},
        }},
    ]
    cost_agg = await db.influencer_campaigns.aggregate(cost_pipeline).to_list(1)
    c = cost_agg[0] if cost_agg else {}
    fee_paid = float(c.get("fee_paid", 0) or 0)
    product_cost = float(c.get("product_cost", 0) or 0)
    cargo_cost = float(c.get("cargo_cost", 0) or 0)
    total_cost = fee_paid + product_cost + cargo_cost

    # --- Ciro (başarılı siparişler) ---
    rev_pipeline = [
        {"$match": {
            "influencer_id": influencer_id,
            "status": {"$in": SUCCESS_STATUSES},
        }},
        {"$group": {
            "_id": None,
            "revenue": {"$sum": {"$ifNull": ["$total", 0]}},
            "order_count": {"$sum": 1},
        }},
    ]
    rev_agg = await db.orders.aggregate(rev_pipeline).to_list(1)
    r = rev_agg[0] if rev_agg else {}
    revenue = float(r.get("revenue", 0) or 0)
    order_count = int(r.get("order_count", 0) or 0)

    # Toplam (iptal/iade dahil) sipariş sayısı — dönüşüm görünürlüğü için
    total_orders = await db.orders.count_documents({"influencer_id": influencer_id})

    net_profit = revenue - total_cost
    roas = round(revenue / total_cost, 2) if total_cost > 0 else None
    commission = round(revenue * float(inf.get("commission_rate", 0) or 0) / 100.0, 2)

    return {
        "influencer_id": influencer_id,
        "influencer_name": inf.get("name", ""),
        "cost": {
            "fee_paid": round(fee_paid, 2),
            "product_cost": round(product_cost, 2),
            "cargo_cost": round(cargo_cost, 2),
            "total_cost": round(total_cost, 2),
            "campaign_count": int(c.get("campaign_count", 0) or 0),
            "shared_count": int(c.get("shared_count", 0) or 0),
        },
        "revenue": {
            "revenue": round(revenue, 2),
            "successful_orders": order_count,
            "total_orders": total_orders,
            "commission_due": commission,
        },
        "net_profit": round(net_profit, 2),
        "roas": roas,
    }
