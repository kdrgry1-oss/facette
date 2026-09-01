"""
Admin → Üyeler (Members) module.

Provides CRUD + analytics for registered customers. A "member" here is a
document in the `users` collection that is NOT an admin.

Endpoints (all admin-protected):
  GET    /api/admin/members                – list, filters, pagination
  GET    /api/admin/members/stats          – totals, segments, acquisition sources
  GET    /api/admin/members/{mid}          – detail with orders + addresses
  POST   /api/admin/members                – create manually
  PUT    /api/admin/members/{mid}          – update
  DELETE /api/admin/members/{mid}          – delete
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional

from .deps import db, require_admin, hash_password, generate_id, logger

router = APIRouter(prefix="/admin/members", tags=["admin-members"])


def _member_order_match(user: dict) -> dict:
    """Üyenin siparişlerini yakalayan koşul: user_id VE e-posta.
    Misafirken verilen (user_id=null) siparişler yalnız user_id ile aranınca
    üye detayında hiç görünmez — e-posta eşleşmesi aynı kişinin geçmiş
    siparişlerini güvenle kapsar (customer.py'deki _owner_or_clauses ile aynı ilke)."""
    import re as _re
    uid = user.get("id")
    ors = [{"user_id": uid}]
    email = (user.get("email") or "").strip()
    if email:
        rx = {"$regex": f"^{_re.escape(email)}$", "$options": "i"}
        ors += [{"shipping_address.email": rx}, {"email": rx}, {"billing_address.email": rx}]
    return {"$or": ors}


async def _annotate(user: dict) -> dict:
    uid = user.get("id")
    # Aggregate order stats
    pipeline = [
        {"$match": {"$and": [_member_order_match(user), {"status": {"$ne": "cancelled"}}]}},
        {
            "$group": {
                "_id": None,
                "orders": {"$sum": 1},
                "total_spent": {"$sum": {"$ifNull": ["$total", 0]}},
                "last_order_at": {"$max": "$created_at"},
            }
        },
    ]
    agg = None
    async for row in db.orders.aggregate(pipeline):
        agg = row
    user["orders_count"] = int(agg["orders"]) if agg else 0
    user["total_spent"] = round(float(agg["total_spent"]), 2) if agg else 0.0
    user["last_order_at"] = agg.get("last_order_at") if agg else None

    # Segment
    spent = user["total_spent"]
    if spent >= 5000:
        user["segment"] = "vip"
    elif user["orders_count"] >= 2:
        user["segment"] = "returning"
    elif user["orders_count"] == 1:
        user["segment"] = "new"
    else:
        user["segment"] = "prospect"
    return user


@router.get("")
async def list_members(
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=200),
    search: Optional[str] = None,
    segment: Optional[str] = None,
    source: Optional[str] = None,
    sort: Optional[str] = "created",
    dir: Optional[str] = "desc",
    date_field: Optional[str] = "created",   # created (Katılım) | last_order (Son Sipariş)
    start: Optional[str] = None,
    end: Optional[str] = None,
    current_user: dict = Depends(require_admin),
):
    query: dict = {"is_admin": {"$ne": True}}
    if search:
        # DENETİM FIX: kaçışsız regex özel karakterlerde ('(' '[' vb.) 500 / ReDoS veriyordu.
        import re as _re
        _s = _re.escape(str(search).strip())
        query["$or"] = [
            {"email": {"$regex": _s, "$options": "i"}},
            {"first_name": {"$regex": _s, "$options": "i"}},
            {"last_name": {"$regex": _s, "$options": "i"}},
            {"phone": {"$regex": _s, "$options": "i"}},
        ]
    if source:
        query["acquisition_source"] = source

    # TARİH FİLTRESİ — Katılım (created_at) veya Son Sipariş (cached_last_order) aralığı.
    _dfld = "cached_last_order" if (date_field == "last_order") else "created_at"
    if start or end:
        _dq = {}
        if start:
            _dq["$gte"] = start
        if end:
            _dq["$lte"] = end if len(end) > 10 else end + "T23:59:59"
        query[_dfld] = _dq

    skip = (page - 1) * limit

    # HIZLANDIRMA: sipariş istatistikleri artık kullanıcı belgesinde ÖNBELLEKTE (cached_*),
    # _refresh_member_stats ile periyodik/isteğe-bağlı tek geçişte yazılır. Liste/segment BU
    # alanları okur → korelasyonlu $lookup (O(üye×sipariş)) KALDIRILDI. Önbellek YOKSA 0/prospect.
    # (Üye 360 detayı tam eşleşmeyi ayrıca canlı yapar; liste görünümü için önbellek yeterli+hızlı.)
    # addFields SIRALAMADAN ÖNCE — türetilmiş alanlara (aov) göre de sıralanabilsin. cached_* zaten
    # kullanıcı belgesinde; aov = harcama/sipariş (0'a bölme korumalı).
    _cached_fields = [{"$addFields": {
        "orders_count": {"$ifNull": ["$cached_orders", 0]},
        "total_spent": {"$ifNull": ["$cached_spent", 0]},
        "last_order_at": "$cached_last_order",
        "segment": {"$ifNull": ["$cached_segment", "prospect"]},
        "aov": {"$cond": [{"$gt": [{"$ifNull": ["$cached_orders", 0]}, 0]},
                          {"$divide": [{"$ifNull": ["$cached_spent", 0]}, "$cached_orders"]}, 0]},
    }}]
    _project = {"$project": {"_id": 0, "password": 0}}

    if segment:
        seg_match = ({"$or": [{"cached_segment": "prospect"}, {"cached_segment": {"$exists": False}}]}
                     if segment == "prospect" else {"cached_segment": segment})
        query = {"$and": [query, seg_match]}

    # SIRALAMA — tüm sütunlar artan/azalan (sunucu-taraflı → tüm sayfalarda geçerli).
    _sort_map = {
        "name": "first_name", "orders": "cached_orders", "spent": "cached_spent",
        "aov": "aov", "last_order": "cached_last_order", "created": "created_at",
        "segment": "cached_segment", "source": "acquisition_source",
    }
    _sf = _sort_map.get((sort or "created"), "created_at")
    _dir = -1 if (dir or "desc").lower() != "asc" else 1

    total = await db.users.count_documents(query)
    pipeline = [
        {"$match": query},
        *_cached_fields,
        {"$sort": {_sf: _dir, "_id": 1}},  # _id ikincil → sayfalama kararlı
        {"$skip": skip},
        {"$limit": limit},
        _project,
    ]
    items = [r async for r in db.users.aggregate(pipeline, allowDiskUse=True)]
    return {"items": items, "total": total, "page": page, "pages": (total + limit - 1) // limit}


async def _refresh_member_stats() -> dict:
    """orders → users.cached_* (orders/spent/last_order/segment) TEK GEÇİŞTE yazar (bulk).
    user_id ile eşleşen (kayıtlı üye) sipariş­leri baz alır — liste/segment görünümü için hızlı ve
    yeterli. Misafir-email-only siparişler hariç (üye 360 detayı tam eşleşmeyi ayrıca yapar)."""
    from pymongo import UpdateOne
    pipeline = [
        {"$match": {"user_id": {"$ne": None}, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$user_id", "o": {"$sum": 1},
                    "t": {"$sum": {"$ifNull": ["$total", 0]}}, "last": {"$max": "$created_at"}}},
    ]
    ops, n = [], 0
    _now = datetime.now(timezone.utc).isoformat()
    async for row in db.orders.aggregate(pipeline, allowDiskUse=True):
        o = int(row.get("o") or 0)
        t = round(float(row.get("t") or 0), 2)
        seg = "vip" if t >= 5000 else ("returning" if o >= 2 else ("new" if o == 1 else "prospect"))
        ops.append(UpdateOne({"id": row["_id"]}, {"$set": {
            "cached_orders": o, "cached_spent": t, "cached_last_order": row.get("last"),
            "cached_segment": seg, "stats_refreshed_at": _now}}))
        if len(ops) >= 500:
            await db.users.bulk_write(ops, ordered=False)
            n += len(ops)
            ops = []
    if ops:
        await db.users.bulk_write(ops, ordered=False)
        n += len(ops)
    return {"updated": n, "at": _now}


@router.post("/refresh-stats")
async def refresh_stats(current_user: dict = Depends(require_admin)):
    """Üye sipariş istatistiklerini (cached_*) yeniden hesapla — liste/segment/stats bundan okur."""
    return await _refresh_member_stats()


@router.get("/stats")
async def stats(current_user: dict = Depends(require_admin)):
    total = await db.users.count_documents({"is_admin": {"$ne": True}})
    since_30 = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_30 = await db.users.count_documents({"is_admin": {"$ne": True}, "created_at": {"$gte": since_30}})

    # Acquisition by source (from user.acquisition_source OR first order attribution.channel)
    pipeline = [
        {"$match": {"user_id": {"$ne": None}}},
        {"$sort": {"created_at": 1}},
        {"$group": {"_id": "$user_id", "first_channel": {"$first": "$attribution.channel"}}},
        {"$group": {"_id": "$first_channel", "members": {"$sum": 1}}},
        {"$sort": {"members": -1}},
    ]
    by_channel = []
    async for row in db.orders.aggregate(pipeline):
        by_channel.append({"channel": row["_id"] or "direct", "members": row["members"]})

    # Segments — ÖNBELLEKTEN (cached_segment). Eskiden her üye için ayrı aggregation vardı
    # (O(üye) sorgu → 10k+ üyede dakikalarca). Artık tek grup sorgusu; önbellek _refresh_member_stats
    # ile güncellenir. cached_segment yoksa 'prospect' sayılır.
    seg = {"vip": 0, "returning": 0, "new": 0, "prospect": 0}
    seg_pipe = [
        {"$match": {"is_admin": {"$ne": True}}},
        {"$group": {"_id": {"$ifNull": ["$cached_segment", "prospect"]}, "n": {"$sum": 1}}},
    ]
    async for row in db.users.aggregate(seg_pipe):
        key = row["_id"] if row["_id"] in seg else "prospect"
        seg[key] += int(row["n"])

    return {"total": total, "new_last_30_days": new_30, "segments": seg, "acquisition_by_channel": by_channel}


@router.get("/{mid}")
async def detail(mid: str, current_user: dict = Depends(require_admin)):
    u = await db.users.find_one({"id": mid, "is_admin": {"$ne": True}}, {"_id": 0, "password": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")

    u = await _annotate(u)
    orders = await db.orders.find(_member_order_match(u), {"_id": 0}).sort("created_at", -1).to_list(200)
    addresses = await db.addresses.find({"user_id": mid}, {"_id": 0}).to_list(20)
    # Adres defteri boşsa geçmiş siparişlerin teslimat adreslerinden türet (görüntüleme amaçlı)
    if not addresses and orders:
        seen = set()
        for o in orders:
            sa = o.get("shipping_address") or {}
            key = ((sa.get("address") or "").strip().lower(), (sa.get("city") or "").strip().lower())
            if not key[0] or key in seen:
                continue
            seen.add(key)
            addresses.append({
                "id": "", "user_id": mid, "title": f"Sipariş Adresi ({o.get('order_number','')})",
                "first_name": sa.get("first_name", ""), "last_name": sa.get("last_name", ""),
                "phone": sa.get("phone", ""), "address": sa.get("address", ""),
                "city": sa.get("city", ""), "district": sa.get("district", ""),
                "postal_code": sa.get("postal_code", ""), "is_default": False,
                "source": "order",
            })
            if len(addresses) >= 5:
                break

    # Attribution breakdown from orders
    ch_map: dict = {}
    for o in orders:
        ch = (o.get("attribution") or {}).get("channel") or "direct"
        ch_map[ch] = ch_map.get(ch, 0) + 1
    attribution_summary = [{"channel": k, "orders": v} for k, v in sorted(ch_map.items(), key=lambda x: -x[1])]

    return {
        "member": u,
        "orders": orders,
        "addresses": addresses,
        "attribution_summary": attribution_summary,
    }


async def _member_360_data(u: dict, start=None, end=None):
    """Müşteri 360 çekirdek hesabı (auth'suz) — JSON ucu + PDF/print ucu ortak kullanır."""
    q = {"$and": [_member_order_match(u)]}
    dm = {}
    if start:
        dm["$gte"] = start
    if end:
        dm["$lte"] = end if len(end) > 10 else end + "T23:59:59"
    if dm:
        q["$and"].append({"created_at": dm})
    orders = await db.orders.find(q, {"_id": 0}).sort("created_at", -1).to_list(1000)

    CANCELLED = {"cancelled", "cancel_refunded"}
    JUNK = {"awaiting_payment", "payment_failed", "failed"}

    valid, cancels = [], []
    brut, qty_total = 0.0, 0
    pay_ct, ch_ct, monthly, prod_ct, cat_ct, coupons = {}, {}, {}, {}, {}, {}
    size_ct, color_ct = {}, {}
    for o in orders:
        st = (o.get("status") or "").lower()
        tot = float(o.get("total") or o.get("total_amount") or 0)
        if st in CANCELLED:
            cancels.append(o)
            continue
        if st in JUNK:
            continue
        valid.append(o)
        brut += tot
        m = (o.get("created_at") or "")[:7]
        if m:
            monthly[m] = round(monthly.get(m, 0) + tot, 2)
        pm = (o.get("payment_method") or "—").lower()
        pay_ct[pm] = pay_ct.get(pm, 0) + 1
        ch = (o.get("attribution") or {}).get("channel") or "direct"
        ch_ct[ch] = ch_ct.get(ch, 0) + 1
        cc = (o.get("coupon_code") or o.get("coupon") or "").strip()
        if cc:
            coupons[cc] = coupons.get(cc, 0) + 1
        for it in (o.get("items") or o.get("lines") or []):
            qn = int(it.get("quantity") or it.get("qty") or 1)
            qty_total += qn
            nm = (it.get("name") or it.get("product_name") or "Ürün")
            prod_ct[nm] = prod_ct.get(nm, 0) + qn
            ct = (it.get("category") or it.get("category_name") or "")
            if ct:
                cat_ct[ct] = cat_ct.get(ct, 0) + qn
            sz = str(it.get("size") or "").strip()
            if sz:
                size_ct[sz] = size_ct.get(sz, 0) + qn
            cl = str(it.get("color") or "").strip()
            if cl:
                color_ct[cl] = color_ct.get(cl, 0) + qn

    oid = [o.get("id") for o in orders if o.get("id")]
    ret_amt, ret_n, returns_list = 0.0, 0, []
    if oid:
        async for r in db.customer_returns.find({"order_id": {"$in": oid}}, {"_id": 0}):
            ra = float(r.get("refund_amount") or 0)
            ret_amt += ra
            ret_n += 1
            returns_list.append({"order_number": r.get("order_number"), "status": r.get("status"),
                                 "refund_amount": round(ra, 2), "reason": r.get("reason"),
                                 "created_at": r.get("created_at") or r.get("updated_at")})

    sip_n = len(valid)
    iptal_amt = round(sum(float(o.get("total") or 0) for o in cancels), 2)
    net = round(brut - ret_amt, 2)

    def _top(d, n=6):
        return [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]]

    def _days(iso):
        try:
            return (datetime.now(timezone.utc) - datetime.fromisoformat(str(iso).replace("Z", "+00:00"))).days
        except Exception:
            return None

    first_ord = min((o.get("created_at") for o in valid), default=None)
    last_ord = max((o.get("created_at") for o in valid), default=None)

    # ── Gelişmiş: tekrar-satın-alma aralığı, RFM, churn riski, CLV tahmini ──
    def _parse(iso):
        try:
            return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        except Exception:
            return None
    vdates = sorted([d for d in (_parse(o.get("created_at")) for o in valid) if d])
    repurchase_days = None
    if len(vdates) >= 2:
        gaps = [(vdates[i + 1] - vdates[i]).days for i in range(len(vdates) - 1)]
        gaps = [g for g in gaps if g >= 0]
        if gaps:
            repurchase_days = round(sum(gaps) / len(gaps), 1)
    rec = _days(last_ord) if last_ord else None

    def _sc(v, ths):  # artan eşikler → 1..5
        s = 1
        for i, t in enumerate(ths):
            if v is not None and v >= t:
                s = i + 2
        return min(s, 5)
    r_score = 5 if rec is None else (5 if rec <= 30 else 4 if rec <= 60 else 3 if rec <= 120 else 2 if rec <= 240 else 1)
    f_score = _sc(sip_n, [2, 3, 5, 10])
    m_score = _sc(net, [500, 2000, 5000, 10000])
    if sip_n == 0:
        seg = "Ziyaretçi"
    elif r_score >= 4 and f_score >= 4:
        seg = "Şampiyon"
    elif f_score >= 3 and m_score >= 3:
        seg = "Sadık"
    elif r_score >= 4 and f_score <= 2:
        seg = "Yeni / Umut Vaat Eden"
    elif r_score <= 2 and f_score >= 3:
        seg = "Risk Altında"
    elif r_score <= 2:
        seg = "Kayıp / Uykuda"
    else:
        seg = "Gelişmekte"

    churn = {"level": "low", "reason": "Aktif müşteri"}
    if sip_n >= 1 and rec is not None:
        if repurchase_days and rec > repurchase_days * 2 and rec > 45:
            churn = {"level": "high", "reason": f"Ort. {int(repurchase_days)} günde bir alırken {rec} gündür sipariş yok"}
        elif rec > 180:
            churn = {"level": "high", "reason": f"{rec} gündür sipariş yok"}
        elif rec > 90:
            churn = {"level": "medium", "reason": f"{rec} gündür sipariş yok"}

    tenure = _days(u.get("created_at")) or 0
    orders_per_year = (sip_n / (tenure / 365.0)) if (tenure and tenure > 30) else float(sip_n)
    aov_v = (brut / sip_n) if sip_n else 0.0
    proj = (aov_v * orders_per_year * 2) if (churn["level"] != "high" and orders_per_year > 0) else 0.0
    clv_estimate = round(net + proj, 2)

    return {
        "member": await _annotate(u),
        "range": {"start": start, "end": end},
        "kpi": {
            "orders": sip_n, "gross_revenue": round(brut, 2), "net_revenue": net,
            "returns_count": ret_n, "returns_amount": round(ret_amt, 2),
            "cancels_count": len(cancels), "cancels_amount": iptal_amt,
            "return_rate": round(ret_n / sip_n * 100, 1) if sip_n else 0,
            "aov": round(brut / sip_n, 2) if sip_n else 0, "items_total": qty_total,
            "first_order": first_ord, "last_order": last_ord,
            "recency_days": _days(last_ord) if last_ord else None,
            "tenure_days": _days(u.get("created_at")) if u.get("created_at") else None,
            "accepts_marketing": bool(u.get("accepts_marketing")),
        },
        "monthly": [{"month": k, "revenue": monthly[k]} for k in sorted(monthly.keys())],
        "payment_breakdown": _top(pay_ct),
        "channel_breakdown": _top(ch_ct),
        "top_products": _top(prod_ct),
        "top_categories": _top(cat_ct),
        "coupons": _top(coupons),
        "advanced": {
            "rfm": {"r": r_score, "f": f_score, "m": m_score, "total": r_score + f_score + m_score, "segment": seg},
            "churn": churn,
            "repurchase_days": repurchase_days,
            "clv_estimate": clv_estimate,
            "orders_per_year": round(orders_per_year, 1),
            "fav_size": _top(size_ct, 3),
            "fav_color": _top(color_ct, 3),
        },
        "orders": [{"order_number": o.get("order_number") or o.get("id"), "created_at": o.get("created_at"),
                    "status": o.get("status"), "total": float(o.get("total") or 0),
                    "platform": o.get("platform"), "payment_method": o.get("payment_method")} for o in orders[:200]],
        "returns": returns_list[:100],
        "cancels": [{"order_number": o.get("order_number") or o.get("id"), "created_at": o.get("created_at"),
                     "total": float(o.get("total") or 0), "reason": o.get("cancel_reason")} for o in cancels[:100]],
    }


@router.get("/{mid}/360")
async def member_360(mid: str, start: Optional[str] = None, end: Optional[str] = None,
                     current_user: dict = Depends(require_admin)):
    """Müşteri 360 JSON — tarih-bazlı ciro/sipariş/iade/iptal + RFM/CLV/churn/favori beden-renk."""
    u = await db.users.find_one({"id": mid, "is_admin": {"$ne": True}}, {"_id": 0, "password": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")
    return await _member_360_data(u, start, end)


@router.get("/{mid}/360/print")
async def member_360_print(mid: str, start: Optional[str] = None, end: Optional[str] = None, token: str = None):
    """Müşteri 360 A4 rapor (PDF/yazdır). token query ile kimlik; ?print=1 ile otomatik yazdır."""
    from fastapi.responses import HTMLResponse
    from .orders import verify_admin_token
    import html as _h
    await verify_admin_token(token)
    u = await db.users.find_one({"id": mid, "is_admin": {"$ne": True}}, {"_id": 0, "password": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")
    d = await _member_360_data(u, start, end)
    m, k, a = d["member"], d["kpi"], d["advanced"]

    def esc(v):
        return _h.escape(str(v if v is not None else ""))

    def tl(n):
        return "₺" + f"{float(n or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    name = f"{m.get('first_name','')} {m.get('last_name','')}".strip() or m.get("email") or "Üye"
    rng = (f"{esc(start or '…')} – {esc(end or '…')}") if (start or end) else "Tüm zamanlar"
    _churn_tr = {"low": "Düşük", "medium": "Orta", "high": "Yüksek"}
    kpis = [
        ("Net Ciro", tl(k["net_revenue"])), ("Brüt Ciro", tl(k["gross_revenue"])),
        ("Sipariş", str(k["orders"])), ("Ort. Sepet", tl(k["aov"])),
        ("İade", f"{tl(k['returns_amount'])} ({k['returns_count']})"),
        ("İptal", f"{tl(k['cancels_amount'])} ({k['cancels_count']})"),
        ("İade Oranı", f"%{k['return_rate']}"), ("Ürün Adedi", str(k["items_total"])),
        ("RFM Segment", esc(a['rfm']['segment']) + f" (R{a['rfm']['r']}/F{a['rfm']['f']}/M{a['rfm']['m']})"),
        ("Kayıp Riski", esc(_churn_tr.get(a['churn']['level'], a['churn']['level']))),
        ("CLV (tahmini)", tl(a["clv_estimate"])),
        ("Tekrar Alım", (f"{a['repurchase_days']} günde bir" if a.get("repurchase_days") else "—")),
        ("Son Sipariş", (f"{k['recency_days']} gün önce" if k.get("recency_days") is not None else "—")),
        ("Üyelik Yaşı", (f"{k['tenure_days']} gün" if k.get("tenure_days") is not None else "—")),
    ]
    kpi_html = "".join(f"<div class='k'><div class='kl'>{esc(l)}</div><div class='kv'>{v}</div></div>" for l, v in kpis)

    def _rows(items, cols):
        r = "".join("<tr>" + "".join(f"<td>{esc(c(it))}</td>" for c in cols) + "</tr>" for it in items)
        return r or "<tr><td colspan='9' style='color:#999'>—</td></tr>"

    ord_rows = _rows(d["orders"], [lambda o: o.get("order_number"), lambda o: (o.get("created_at") or "")[:10],
                                   lambda o: o.get("status"), lambda o: tl(o.get("total"))])
    ret_rows = _rows(d["returns"], [lambda o: o.get("order_number"), lambda o: o.get("reason") or o.get("status"),
                                    lambda o: tl(o.get("refund_amount"))])

    def chips(arr):
        return ", ".join(f"{esc(x['name'])}·{x['count']}" for x in (arr or [])) or "—"

    html = f"""<!DOCTYPE html><html lang="tr"><head><meta charset="UTF-8"><title>Müşteri 360 - {esc(name)}</title>
<style>@page{{size:A4;margin:13mm}} *{{box-sizing:border-box}} body{{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;color:#141414;margin:0}}
.h{{display:flex;justify-content:space-between;border-bottom:2px solid #111;padding-bottom:8px}} .brand{{font-weight:800;letter-spacing:2px;font-size:18px}}
.t{{font-weight:800;font-size:15px}} .sub{{font-size:11px;color:#555}} h2{{font-size:12px;margin:16px 0 6px;text-transform:uppercase;letter-spacing:.5px;color:#444;border-bottom:1px solid #ddd;padding-bottom:3px}}
.who{{margin-top:10px}} .who .n{{font-size:16px;font-weight:800}} .who .m{{font-size:11px;color:#555}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:8px}} .k{{border:1px solid #e2e2e2;border-radius:6px;padding:7px 9px}}
.kl{{font-size:9px;color:#777;text-transform:uppercase}} .kv{{font-size:13px;font-weight:700}}
table{{width:100%;border-collapse:collapse;font-size:10.5px;margin-top:4px}} th{{background:#111;color:#fff;text-align:left;padding:5px 7px}} td{{border-bottom:1px solid #eee;padding:5px 7px}}
.chips{{font-size:11px;color:#333;line-height:1.7}}</style></head><body>
<div class="h"><div class="brand">FACETTE</div><div style="text-align:right"><div class="t">MÜŞTERİ 360 RAPORU</div><div class="sub">Dönem: {rng}</div></div></div>
<div class="who"><div class="n">{esc(name)}</div><div class="m">{esc(m.get('email'))}{(' · '+esc(m.get('phone'))) if m.get('phone') else ''} · Segment: {esc(a['rfm']['segment'])}</div></div>
<div class="grid">{kpi_html}</div>
<div style="font-size:9px;color:#888;margin-top:4px">RFM: R = Recency (Yakınlık — son siparişten bu yana) · F = Frequency (Sıklık — sipariş sayısı) · M = Monetary (Parasal — toplam harcama); her biri 1–5 puan.</div>
<h2>Kırılımlar &amp; Tercihler</h2>
<div class="chips"><b>Ödeme:</b> {chips(d['payment_breakdown'])}<br><b>Kanal:</b> {chips(d['channel_breakdown'])}<br>
<b>En çok ürün:</b> {chips(d['top_products'])}<br><b>Kategori:</b> {chips(d['top_categories'])}<br>
<b>Favori beden:</b> {chips(a['fav_size'])} &nbsp;&nbsp; <b>Favori renk:</b> {chips(a['fav_color'])}<br>
<b>Kuponlar:</b> {chips(d['coupons'])}{('<br><b>Kayıp riski:</b> '+esc(a['churn']['reason'])) if a['churn']['level']!='low' else ''}</div>
<h2>Siparişler ({len(d['orders'])})</h2><table><thead><tr><th>Sipariş No</th><th>Tarih</th><th>Durum</th><th>Tutar</th></tr></thead><tbody>{ord_rows}</tbody></table>
<h2>İadeler ({len(d['returns'])})</h2><table><thead><tr><th>Sipariş No</th><th>Sebep / Durum</th><th>İade Tutarı</th></tr></thead><tbody>{ret_rows}</tbody></table>
<script>window.addEventListener('load',()=>{{if(location.search.includes('print=1'))setTimeout(()=>window.print(),300)}})</script>
</body></html>"""
    return HTMLResponse(content=html, headers={"Content-Type": "text/html; charset=utf-8"})


@router.post("")
async def create_member(payload: dict, current_user: dict = Depends(require_admin)):
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="E-posta gerekli")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="E-posta zaten kayıtlı")
    doc = {
        "id": generate_id(),
        "email": email,
        "password": hash_password(payload.get("password", "Facette123!")),
        "first_name": payload.get("first_name", ""),
        "last_name": payload.get("last_name", ""),
        "phone": payload.get("phone", ""),
        "is_admin": False,
        "is_active": True,
        "accepts_marketing": bool(payload.get("accepts_marketing", False)),
        "acquisition_source": payload.get("acquisition_source", "admin_manual"),
        "notes": payload.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by_admin": current_user.get("email", ""),
    }
    await db.users.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("password", None)
    return {"success": True, "member": doc}


@router.put("/{mid}")
async def update_member(mid: str, payload: dict, current_user: dict = Depends(require_admin)):
    # DENETİM FIX (#41): group_id atanabilir olmalı — Üye Grupları indirimi gruba bağlı üyeye uygulanır.
    allowed = ("first_name", "last_name", "phone", "is_active", "accepts_marketing", "acquisition_source", "notes", "segment_tags", "group_id")
    update = {k: v for k, v in payload.items() if k in allowed}
    if payload.get("password"):
        update["password"] = hash_password(payload["password"])
    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    res = await db.users.update_one({"id": mid, "is_admin": {"$ne": True}}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")
    return {"success": True}


@router.delete("/{mid}")
async def delete_member(mid: str, current_user: dict = Depends(require_admin)):
    res = await db.users.delete_one({"id": mid, "is_admin": {"$ne": True}})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Üye bulunamadı")
    return {"success": True}
