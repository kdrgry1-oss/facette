"""
WhatsApp AI Müşteri Temsilcisi — Meta Cloud API webhook.

Akış:
  Müşteri WhatsApp'tan yazar → Meta bu uca POST atar → mevcut AI beyni
  (ai_chatbot: persona + bilgi bankası + ürün + sipariş bağlamı + güven/handoff)
  "gerçek bir kıdemli müşteri temsilcisi" tonunda Türkçe yanıt üretir → 24-saat
  müşteri-hizmetleri penceresinde SERBEST METİN olarak geri gönderilir
  (müşteri ilk yazdığı için template gerekmez).

Güvenlik/guardrail:
  - Kimlik: settings.notification_providers.providers.whatsapp_meta
    (phone_number_id, access_token, verify_token, app_secret[ops]).
  - AÇ/KAPA: ai_chatbot.enabled VE ai_chatbot.channels.whatsapp (varsayılan KAPALI).
  - Düşük güven / handoff → cevabı UYDURMAZ; kısa bir "temsilcimize ilettim" mesajı
    gönderir + whatsapp_handoffs'a kaydeder (insan devralır).
  - Opt-out (DURDUR/STOP/IPTAL) → yanıt vermez, opt-out kaydı tutar.
  - Idempotent: her Meta mesaj id'si bir kez işlenir (döngü/çift-yanıt yok).
  - Kendi numaramızdan geleni ve statü-webhook'larını yok sayar.
  - Meta imza doğrulaması (X-Hub-Signature-256) app_secret varsa uygulanır.
  - Meta'ya HIZLI 200 döner; AI üretimi arka planda yapılır.
"""
import os
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse

from .deps import db, logger
from .ai_chatbot import (
    get_ai_settings, _api_key_for, llm_chat, DEFAULT_PERSONA,
    _gather_kb_context, _gather_product_context,
)

router = APIRouter(prefix="/whatsapp", tags=["whatsapp-ai"])

_OPT_OUT = {"durdur", "stop", "iptal", "çık", "cik", "abonelikten çık"}
_OPT_IN = {"başla", "basla", "devam", "aç", "ac"}


async def _wa_cfg() -> dict:
    s = await db.settings.find_one({"id": "notification_providers"}, {"_id": 0}) or {}
    return ((s.get("providers") or {}).get("whatsapp_meta") or {})


# ── Webhook doğrulama (Meta panel: Callback URL kaydı) ──────────────────────
@router.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    cfg = await _wa_cfg()
    expected = cfg.get("verify_token") or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge or "")
    return PlainTextResponse("forbidden", status_code=403)


@router.get("/diag")
async def wa_diag(key: str = "", q: str = ""):
    """PII'siz teşhis — verify_token ile korunur. Webhook geldi mi, AI anahtarı/config
    tam mı, gönderim başarılı mı görülür. Mesaj metni DÖNMEZ (yalnız not/durum).
    q verilirse ürün-bulma + beden tablosu probu çalışır (satış/beden teşhisi)."""
    cfg = await _wa_cfg()
    expected = cfg.get("verify_token") or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if not expected or not hmac.compare_digest(key, expected):
        return PlainTextResponse("forbidden", status_code=403)
    probe = {}
    if q:
        try:
            prod = await _find_product(q)
            sc = await _size_context(prod) if prod else ""
            pc = await _gather_product_context((prod or {}).get("name") or q)
            probe = {
                "keywords": _keywords(q),
                "product_found": (prod or {}).get("name"),
                "size_table_len": len(sc or ""),
                "size_table_head": (sc or "")[:400],
                "product_ctx_len": len(pc or ""),
            }
        except Exception as e:
            probe = {"err": str(e)[:200]}
    settings = await get_ai_settings()
    recent = []
    try:
        cur = db.whatsapp_conversations.find(
            {}, {"_id": 0, "note": 1, "handoff": 1, "confidence": 1, "outbound": 1, "created_at": 1}
        ).sort("created_at", -1).limit(8)
        async for r in cur:
            recent.append({
                "note": r.get("note", ""), "handoff": r.get("handoff"),
                "confidence": r.get("confidence"), "out_sent": bool(r.get("outbound")),
                "at": r.get("created_at"),
            })
    except Exception as e:
        recent = [{"err": str(e)[:120]}]
    try:
        processed = await db.whatsapp_processed.count_documents({})
    except Exception:
        processed = -1
    try:
        hits = await db.whatsapp_hits.find_one({"_id": "count"}, {"_id": 0}) or {}
    except Exception:
        hits = {}
    # Token ömrü — Meta debug_token: expires_at=0 => KALICI, tarih => geçici (o an dolar).
    token_info = {}
    tok = cfg.get("access_token", "")
    if tok:
        try:
            import httpx as _hx
            async with _hx.AsyncClient(timeout=10) as _c:
                _r = await _c.get("https://graph.facebook.com/debug_token",
                                  params={"input_token": tok, "access_token": tok})
                _d = (_r.json() or {}).get("data") or {}
            _exp = _d.get("expires_at")
            token_info = {
                "is_valid": _d.get("is_valid"),
                "type": _d.get("type"),
                "expires_at": _exp,
                "kalici_mi": (_exp == 0),
                "expires_human": ("KALICI (süresiz)" if _exp == 0 else
                                  (datetime.fromtimestamp(_exp, tz=timezone.utc).isoformat() if _exp else "?")),
                "scopes": _d.get("scopes"),
            }
        except Exception as e:
            token_info = {"err": str(e)[:150]}
    return {
        "config": {
            "has_phone_id": bool(cfg.get("phone_number_id")),
            "phone_number_id": (cfg.get("phone_number_id") or "")[-6:],
            "has_token": bool(cfg.get("access_token")),
            "app_secret_set": bool(cfg.get("app_secret")),
            "ai_autoreply": bool(cfg.get("ai_autoreply")),
            "handoff_phone_set": bool(_admin_tail(cfg)),
            "handoff_phone_tail": (_admin_tail(cfg) or "")[-4:],
        },
        "raw_hits": hits,
        "handoff": {
            "open": await db.whatsapp_handoffs.count_documents({"status": "open"}),
            "answered": await db.whatsapp_handoffs.count_documents({"status": "answered"}),
        },
        "ai": {
            "enabled": settings.get("enabled", True),
            "provider": settings.get("provider"),
            "model": settings.get("fast_model") or settings.get("model"),
            "has_key": bool(_api_key_for(settings)),
        },
        "inbound": {"processed_count": processed, "recent": recent},
        "token": token_info,
        "probe": probe,
    }


def _verify_signature(app_secret: str, raw: bytes, header: str) -> bool:
    if not app_secret:
        return True  # app_secret ayarlı değilse imza kontrolü atlanır (Meta panelinden zorunlu kılınabilir)
    if not header or not header.startswith("sha256="):
        return False
    mac = hmac.new(app_secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, header.split("=", 1)[1])


# ── Gelen mesaj → arka planda AI yanıt ──────────────────────────────────────
@router.post("/webhook")
async def receive_webhook(request: Request, background: BackgroundTasks):
    raw = await request.body()
    # HAM POST sayacı — imza kontrolünden ÖNCE (Meta hiç mi göndermiyor, yoksa
    # gelip imzada mı reddediliyor ayrımı için). Teşhis amaçlı.
    try:
        await db.whatsapp_hits.update_one(
            {"_id": "count"}, {"$inc": {"n": 1}, "$set": {"last": _now()}}, upsert=True)
    except Exception:
        pass
    cfg = await _wa_cfg()
    # İmza doğrulama (app_secret varsa)
    if not _verify_signature(cfg.get("app_secret", ""), raw,
                             request.headers.get("x-hub-signature-256", "")):
        try:
            await db.whatsapp_hits.update_one(
                {"_id": "count"}, {"$inc": {"sig_fail": 1}}, upsert=True)
        except Exception:
            pass
        return PlainTextResponse("bad signature", status_code=403)
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return {"ok": True}

    for entry in (data.get("entry") or []):
        for ch in (entry.get("changes") or []):
            value = ch.get("value") or {}
            # COEXISTENCE HISTORY SYNC — telefon uygulamasındaki eski sohbet geçmişi (~6 ay).
            # field=history veya value.history varsa: arka planda içe aktar (AI per-müşteri
            # bağlamı + ham kayıt). Canlı mesaj değil; AI cevabı TETİKLEMEZ.
            if ch.get("field") == "history" or value.get("history"):
                background.add_task(_ingest_history, value)
                continue
            own_pnid = (value.get("metadata") or {}).get("phone_number_id")
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                        for c in (value.get("contacts") or [])}
            for m in (value.get("messages") or []):
                sender = m.get("from")
                mid = m.get("id")
                if not sender or not mid:
                    continue
                mtype = m.get("type")
                # TEMSİLCİ (ana) numaradan gelen mesaj = bekleyen handoff'a CEVAP.
                # AI'a MÜŞTERİ gibi sokulmaz; relay handler'ına gider (metin dışı yok sayılır).
                if _is_admin(sender, cfg):
                    if mtype == "text":
                        body = ((m.get("text") or {}).get("body") or "").strip()
                        if not body:
                            continue
                        ctx_id = (m.get("context") or {}).get("id") or ""
                        background.add_task(
                            _handle_admin_reply, sender=sender, mid=mid,
                            body=body, context_id=ctx_id,
                        )
                    continue
                if mtype == "text":
                    body = ((m.get("text") or {}).get("body") or "").strip()
                    if not body:
                        continue
                    # Müşteri bir mesajı ALINTILAYIP yanıtladıysa (WhatsApp reply) → o mesajın id'si
                    q_id = (m.get("context") or {}).get("id") or ""
                    background.add_task(
                        _handle_inbound, sender=sender, mid=mid, body=body,
                        name=contacts.get(sender), own_pnid=own_pnid, quoted_id=q_id,
                    )
                elif mtype == "image":
                    media_id = (m.get("image") or {}).get("id")
                    caption = (m.get("image") or {}).get("caption") or ""
                    if media_id:
                        background.add_task(
                            _handle_image, sender=sender, mid=mid, media_id=media_id,
                            caption=caption, name=contacts.get(sender), own_pnid=own_pnid,
                        )
                elif mtype in ("audio", "voice"):
                    # Sesli mesaj / ses notu → indir + yazıya çevir + AI yazarak cevaplasın.
                    _a = m.get("audio") or m.get("voice") or {}
                    media_id = _a.get("id")
                    if media_id:
                        background.add_task(
                            _handle_audio, sender=sender, mid=mid, media_id=media_id,
                            name=contacts.get(sender), own_pnid=own_pnid,
                        )
                # diğer türler (konum/döküman) ilk sürümde atlanır
    return {"ok": True}


async def _ingest_history(value: dict):
    """Coexistence history sync payload'ını içe aktarır. Meta'nın history şeması
    değişebildiğinden SAVUNMACI: ham payload'ı whatsapp_history_raw'a saklar (şema
    incelemesi için) + mesaj-benzeri kayıtları özyinelemeli çıkarıp whatsapp_conversations'a
    'history' kaynağıyla yazar → AI o müşteriyle geçmiş konuşmayı bağlamda görür.
    Bilgi bankası beslemesi ayrı, admin onaylı yapılır (ham geçmişi körlemesine 'doğru
    cevap' saymayız)."""
    try:
        await db.whatsapp_history_raw.insert_one({"value": value, "at": _now()})
    except Exception:
        pass
    own = (value.get("metadata") or {}).get("phone_number_id") or ""

    def _walk(node, out):
        if isinstance(node, dict):
            txt = ""
            t = node.get("text")
            if isinstance(t, dict):
                txt = t.get("body") or ""
            elif isinstance(t, str):
                txt = t
            frm = node.get("from") or ""
            if txt and (frm or node.get("id")):
                out.append({"from": str(frm), "text": str(txt)[:1000],
                            "ts": node.get("timestamp") or "", "id": node.get("id") or ""})
            for v in node.values():
                _walk(v, out)
        elif isinstance(node, list):
            for v in node:
                _walk(v, out)

    msgs = []
    try:
        _walk(value.get("history") or value, msgs)
    except Exception:
        return
    for m in msgs:
        try:
            mid = m.get("id") or f"hist_{m.get('from','')}_{m.get('ts','')}_{hash(m.get('text',''))}"
            if await _already_processed(mid):
                continue
            frm = m.get("from") or ""
            # Yön: bizim numaramızdan gidenler 'Sen' (temsilci), diğerleri 'Müşteri'.
            outgoing = bool(own) and frm == own
            peer = own if outgoing else frm
            await db.whatsapp_conversations.insert_one({
                "phone": peer,
                "inbound": "" if outgoing else m.get("text", ""),
                "outbound": m.get("text", "") if outgoing else "",
                "handoff": False, "confidence": 1.0, "note": "history",
                "created_at": _now(),
            })
        except Exception:
            continue


async def _already_processed(mid: str) -> bool:
    """Idempotency — aynı Meta mesaj id'si iki kez işlenmesin."""
    try:
        res = await db.whatsapp_processed.update_one(
            {"_id": mid},
            {"$setOnInsert": {"at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return res.upserted_id is None
    except Exception:
        return False


async def _recent_orders_context(phone: str):
    """Müşterinin telefonuna göre son siparişleri (grounded veri) + ÜRÜN içeriğiyle
    bağlam olarak verir. Döner: (metin, sipariş_sayısı)."""
    from notification_service import normalize_phone_tr
    norm = normalize_phone_tr(phone)
    tail = (norm or phone or "")[-10:]
    rows = []
    if tail:
        try:
            cur = db.orders.find(
                {"$or": [{"phone": {"$regex": tail + "$"}},
                         {"shipping_address.phone": {"$regex": tail + "$"}}]},
                {"_id": 0, "order_number": 1, "status": 1, "payment_status": 1,
                 "total": 1, "created_at": 1, "tracking_number": 1, "cargo_company": 1,
                 "items": 1},
            ).sort("created_at", -1).limit(5)
            rows = await cur.to_list(5)
        except Exception:
            rows = []
    if not rows:
        return "", 0, 0
    # Kargo durumu sınıflandırma — "siparişim nerede" için: YOLDA olanlara odaklan,
    # hepsi teslimse #no+tarihten sor.
    def _is_delivered(o):
        s = (o.get("status") or "").lower()
        return any(k in s for k in ("teslim", "deliver", "tamamlan", "complete"))

    def _is_in_transit(o):
        s = (o.get("status") or "").lower()
        if _is_delivered(o):
            return False
        if o.get("tracking_number"):
            return True
        return any(k in s for k in ("kargo", "transit", "shipped", "yolda", "gonderi", "gönderi", "sevk"))

    in_transit = [o for o in rows if _is_in_transit(o)]
    lines = ["[Müşterinin Son Siparişleri — sipariş/kargo/ürün bilgisini SADECE buradan ver, uydurma]"]
    for o in rows:
        prods = []
        for it in (o.get("items") or [])[:3]:
            nm = it.get("name") or it.get("product_name") or it.get("title") or ""
            if nm:
                prods.append(nm)
        prod_txt = ", ".join(prods) if prods else "ürün bilgisi yok"
        ca = (o.get("created_at") or "")[:10]
        date_str = ""
        if len(ca) == 10 and ca[4:5] == "-":
            y, m, d = ca.split("-")
            date_str = f"{d}.{m}.{y}"
        seg = f"- #{o.get('order_number','?')} | {prod_txt}"
        if date_str:
            seg += f" | tarih={date_str}"
        seg += f" | durum={o.get('status','?')}"
        if _is_in_transit(o):
            seg += " [KARGODA]"
        elif _is_delivered(o):
            seg += " [TESLİM EDİLDİ]"
        if o.get("payment_status"):
            seg += f", ödeme={o.get('payment_status')}"
        if o.get("tracking_number"):
            seg += f", kargo={o.get('cargo_company') or ''} takip={o.get('tracking_number')}"
        lines.append(seg)
    return "\n".join(lines), len(rows), len(in_transit)


_KW_STOP = {"ben", "için", "icin", "hangi", "bana", "olur", "boyunda", "boyum", "kiloyum",
            "kilo", "boy", "cm", "var", "yok", "nasıl", "nasil", "mısın", "misin", "bir", "mi",
            "mu", "mü", "hakkında", "hakkinda", "bilgi", "almak", "istiyorum", "merhaba", "selam",
            "acaba", "lütfen", "lutfen", "sipariş", "siparis", "numaram", "numara", "beden",
            "önerir", "onerir", "misiniz", "musunuz"}


def _keywords(text: str):
    import re as _r
    toks = _r.findall(r"[a-zçğıöşü0-9]{3,}", (text or "").lower())
    return [t for t in toks if t not in _KW_STOP]


async def _find_product(text: str):
    """Konuşma metninden ürünü bulur. 'mini/elbise' gibi kelimeler yüzlerce ürüne
    uyduğundan, aday havuzunu EN AYIRT EDİCİ (en az eşleşen) kelimeyle kurar; böylece
    'maris' gibi belirleyici kelimedeki ürün havuza girer, sonra TAM örtüşmeyle sıralanır."""
    import re as _r
    kws = _keywords(text)[:8]
    if not kws:
        return None
    counts = {}
    for k in kws:
        try:
            c = await db.products.count_documents({"name": {"$regex": _r.escape(k), "$options": "i"}})
        except Exception:
            c = 0
        if c > 0:
            counts[k] = c
    if not counts:
        return None
    rare = min(counts, key=counts.get)  # en ayırt edici kelime (en az eşleşen)
    try:
        cands = await db.products.find(
            {"name": {"$regex": _r.escape(rare), "$options": "i"}},
            {"_id": 0, "id": 1, "name": 1, "slug": 1}).limit(60).to_list(60)
    except Exception:
        return None
    if not cands:
        return None
    def _score(p):
        nm = (p.get("name") or "").lower()
        return sum(1 for k in kws if k in nm)
    cands.sort(key=_score, reverse=True)
    return cands[0] if _score(cands[0]) > 0 else None


# ── ÜRÜN KİLİDİ (konu takibi) ────────────────────────────────────────────────
# AI'nın müşterinin sorduğu ürünü konuşma boyunca SABİT tutması için. Eskiden ürün
# her mesajda TÜM diyalogdan (AI'nın kendi önceki tahminleri dahil) yeniden bulunuyor,
# bu da AI'yı adım adım BAŞKA ürüne kaydırıyordu (görseldeki takım → 'Lumea ceket' →
# 'Kapri Pantolon'). Artık ürün müşterinin AÇIK niyetinden (bu mesaj / alıntı / görsel)
# bir kez kilitlenir; ürünsüz mesajlarda (ör. '170 boy 67 kilo') kilit sürdürülür.
async def _set_active_product(phone: str, product: dict):
    if not product or not product.get("id"):
        return
    try:
        await db.whatsapp_active_product.update_one(
            {"_id": phone},
            {"$set": {"product_id": product.get("id"), "name": product.get("name"),
                      "slug": product.get("slug"), "at": _now()}},
            upsert=True)
    except Exception:
        pass


async def _get_active_product(phone: str, max_age_hours: int = 8):
    """Kilitli (aktif) ürünü döndür — çok eskiyse (yeni konuşma) yok say."""
    try:
        rec = await db.whatsapp_active_product.find_one({"_id": phone})
    except Exception:
        rec = None
    if not rec or not rec.get("product_id"):
        return None
    try:
        at = rec.get("at") or ""
        if at:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(at)).total_seconds()
            if age > max_age_hours * 3600:
                return None
    except Exception:
        pass
    try:
        p = await db.products.find_one({"id": rec["product_id"]},
                                       {"_id": 0, "id": 1, "name": 1, "slug": 1})
        if p:
            return p
    except Exception:
        pass
    return {"id": rec["product_id"], "name": rec.get("name"), "slug": rec.get("slug")}


async def _quoted_context(quoted_id: str):
    """Müşteri bir mesajı ALINTILAYIP (WhatsApp reply) yazdıysa: alıntılanan mesajın
    metnini + (varsa o mesajın konuştuğu) ürünü döndür → (ürün, metin)."""
    if not quoted_id:
        return None, ""
    try:
        row = await db.whatsapp_conversations.find_one({"wamid": quoted_id})
    except Exception:
        row = None
    if not row:
        return None, ""
    qtext = row.get("outbound") or row.get("inbound") or ""
    prod = None
    pid = row.get("product_id")
    if pid:
        try:
            prod = await db.products.find_one({"id": pid}, {"_id": 0, "id": 1, "name": 1, "slug": 1})
        except Exception:
            prod = None
    return prod, qtext


async def _size_context(product) -> str:
    """Ürünün beden tablosu (beden×ölçü) + manken ölçüleri — boy/kilo/beden önerisi için."""
    if not product:
        return ""
    pid = product.get("id")
    st = await db.size_tables.find_one({"product_id": pid}, {"_id": 0})
    if not (st and st.get("sizes")):
        try:
            from routes.size_tables import _inherited_size_table
            st = await _inherited_size_table(pid)
        except Exception:
            st = None
    if not (st and st.get("sizes")):
        return ""
    cols = st.get("columns") or []
    values = st.get("values") or {}
    rows = ["Beden | " + " | ".join(cols)] if cols else ["Bedenler: " + ", ".join(st.get("sizes") or [])]
    if cols:
        for sz in (st.get("sizes") or []):
            m = values.get(sz) or {}
            rows.append(f"{sz} | " + " | ".join(str(m.get(c, "-")) for c in cols))
    block = f"{product.get('name')} — beden tablosu (cm):\n" + "\n".join(rows)
    mi = st.get("model_info") or {}
    mparts = [f"{k}: {v}" for k, v in mi.items() if v]
    if mparts:
        block += "\nManken ölçüleri (referans): " + ", ".join(mparts)
    return block


_SIZE_TOKENS = {"XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL", "4XL"}


def _detect_size(text: str):
    """Mesaj bir beden mi (XL, M, 38...) — beden ön-seçili link için."""
    t = (text or "").strip().upper().replace("BEDEN", "").replace("BEDENİ", "").strip()
    if t in _SIZE_TOKENS:
        return t
    if t.isdigit() and len(t) == 2:
        return t
    return None


def _product_link(product, site_url: str, size=None) -> str:
    if not product or not site_url:
        return ""
    slug = product.get("slug") or product.get("id")
    url = f"{site_url.rstrip('/')}/urun/{slug}"
    if size:
        url += f"?beden={size}"
    return url


async def _recent_dialog(sender: str, limit: int = 6) -> str:
    """Bu müşteriyle son konuşma turlarını (kronolojik) döndürür — AI'nın tekrar
    tanıtmaması ve TUTARLI devam etmesi için. Sadece gerçek soru/cevap turları."""
    try:
        cur = db.whatsapp_conversations.find(
            {"phone": sender,
             "$or": [{"inbound": {"$nin": [None, ""]}}, {"outbound": {"$nin": [None, ""]}}]},
            {"_id": 0, "inbound": 1, "outbound": 1, "created_at": 1}
        ).sort("created_at", -1).limit(limit)
        rows = await cur.to_list(limit)
    except Exception:
        return ""
    lines = []
    for r in reversed(rows):  # eskiden yeniye
        if r.get("inbound"):
            lines.append(f"Müşteri: {str(r['inbound'])[:200]}")
        if r.get("outbound"):
            lines.append(f"Sen: {str(r['outbound'])[:300]}")
    return "\n".join(lines[-12:])


async def _download_wa_media(media_id: str, token: str, api_ver: str = "v23.0"):
    """WhatsApp medyasını indir: önce media_id -> geçici URL, sonra URL -> bytes (Bearer token)."""
    import httpx as _hx
    try:
        async with _hx.AsyncClient(timeout=30) as c:
            r = await c.get(f"https://graph.facebook.com/{api_ver}/{media_id}",
                            headers={"Authorization": f"Bearer {token}"})
            url = (r.json() or {}).get("url")
            if not url:
                return None, None
            r2 = await c.get(url, headers={"Authorization": f"Bearer {token}"})
            if r2.status_code != 200:
                return None, None
            return r2.content, (r2.headers.get("content-type") or "image/jpeg").split(";")[0]
    except Exception:
        return None, None


async def _vision_describe(img_bytes: bytes, mime: str, api_key: str, model: str, provider: str) -> str:
    """Görseli sağlayıcı-bağımsız betimle (Türkçe): tür/renk/desen/ayırt edici özellik + anahtar kelime."""
    import base64
    b64 = base64.b64encode(img_bytes).decode()
    prov = (provider or "openai").strip().lower()
    prompt = ("Bu bir kadın giyim ürünü fotoğrafı olabilir. Ürünü TÜRKÇE kısaca tanımla: tür "
              "(elbise/bluz/gömlek/pantolon/etek/takım/triko...), ana renk, desen, kol/yaka/boy gibi "
              "ayırt edici özellikler. 1-2 cümle yaz, sonuna aramada kullanılacak 3-6 anahtar kelime ekle.")
    if prov in ("anthropic", "claude"):
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=model or "claude-sonnet-4-6", max_tokens=250,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}}]}])
        return "".join(getattr(b, "text", "") or "" for b in (msg.content or [])).strip()
    if prov in ("gemini", "google", "google-gemini"):
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = await client.aio.models.generate_content(
            model=model or "gemini-3.1-flash",
            contents=[{"role": "user", "parts": [
                {"text": prompt}, {"inline_data": {"mime_type": mime, "data": b64}}]}])
        return (getattr(resp, "text", None) or "").strip()
    # varsayılan: OpenAI vision
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model or "gpt-5.6-luna",
        messages=[{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
        max_completion_tokens=250)
    return (resp.choices[0].message.content or "").strip()


async def _transcribe_audio(audio_bytes: bytes, mime: str, api_key: str,
                            model: str, provider: str) -> str:
    """Sesli mesajı Türkçe yazıya çevirir (STT). Sağlayıcıya göre:
      - openai (varsayılan): Whisper (whisper-1)
      - gemini/google: doğrudan ses transkripsiyonu (inline_data)
      - anthropic/claude (ses girişi DESTEKLEMEZ): OPENAI/GEMINI env anahtarı varsa
        ona düşer; yoksa boş döner → çağıran insana devreder (uydurmaz).
    Boş string dönerse çeviri yapılamadı demektir."""
    prov = (provider or "openai").strip().lower()
    mm = (mime or "audio/ogg").lower()
    fname = "audio.ogg"
    if "mpeg" in mm or "mp3" in mm:
        fname = "audio.mp3"
    elif "mp4" in mm or "m4a" in mm or "aac" in mm:
        fname = "audio.m4a"
    elif "wav" in mm:
        fname = "audio.wav"
    elif "amr" in mm:
        fname = "audio.amr"

    async def _via_openai(key: str) -> str:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
        tr = await client.audio.transcriptions.create(
            model="whisper-1",
            file=(fname, audio_bytes, mime or "audio/ogg"),
            language="tr",
        )
        return (getattr(tr, "text", "") or "").strip()

    async def _via_gemini(key: str) -> str:
        from google import genai
        import base64 as _b64
        client = genai.Client(api_key=key)
        gmodel = model if prov in ("gemini", "google", "google-gemini") else "gemini-3.1-flash"
        resp = await client.aio.models.generate_content(
            model=gmodel or "gemini-3.1-flash",
            contents=[{"role": "user", "parts": [
                {"text": "Bu ses kaydını birebir Türkçe metne dök. SADECE konuşulan metni yaz; "
                         "yorum, açıklama veya köşeli parantez ekleme."},
                {"inline_data": {"mime_type": mime or "audio/ogg",
                                 "data": _b64.standard_b64encode(audio_bytes).decode()}}]}])
        return (getattr(resp, "text", None) or "").strip()

    try:
        if prov in ("gemini", "google", "google-gemini"):
            return await _via_gemini(api_key)
        if prov in ("anthropic", "claude"):
            # Claude ses girişi desteklemez → env yedeği (Whisper > Gemini)
            if os.environ.get("OPENAI_API_KEY"):
                return await _via_openai(os.environ["OPENAI_API_KEY"])
            if os.environ.get("GEMINI_API_KEY"):
                return await _via_gemini(os.environ["GEMINI_API_KEY"])
            return ""
        return await _via_openai(api_key)
    except Exception:
        logger.exception("WA audio transcribe failed")
        return ""


async def _handle_audio(sender: str, mid: str, media_id: str,
                        name: Optional[str], own_pnid: Optional[str]):
    """Sesli mesaj: Meta'dan indir → STT ile yazıya çevir → metni normal AI akışına ver
    (müşteriye YAZARAK cevap gider). Çeviremezse uydurmaz, insana devreder."""
    try:
        if await _already_processed(mid):
            return
        cfg = await _wa_cfg()
        settings = await get_ai_settings()
        if not settings.get("enabled", True) or not cfg.get("ai_autoreply", False):
            return
        api_key = _api_key_for(settings)
        if not api_key:
            await _handoff(sender, "[sesli mesaj]", name)
            return
        audio, mime = await _download_wa_media(media_id, cfg.get("access_token", ""),
                                               cfg.get("api_version", "v23.0"))
        if not audio:
            await _handoff(sender, "[sesli mesaj indirilemedi]", name)
            await _log(sender, "[sesli mesaj]", "", handoff=True, confidence=0.0, note="audio_dl_fail")
            return
        text = await _transcribe_audio(
            audio, mime, api_key,
            settings.get("fast_model") or settings.get("model"),
            settings.get("provider", "openai"))
        if not text:
            await _handoff(sender, "[sesli mesaj — yazıya çevrilemedi]", name)
            await _log(sender, "[sesli mesaj]", "", handoff=True, confidence=0.0, note="stt_empty")
            return
        # Yazıya çevrilen metni normal akışa ver — ürün/sipariş/beden bağlamıyla cevaplasın.
        body = f"[Müşteri sesli mesaj gönderdi — yazıya çevrildi] {text}"
        await _handle_inbound(sender, mid + "_aud", body, name, own_pnid)
    except Exception as e:
        logger.exception(f"WA audio handler error: {e}")


async def _handle_image(sender: str, mid: str, media_id: str, caption: str,
                        name: Optional[str], own_pnid: Optional[str]):
    """Görsel mesaj: Meta'dan indir → vision ile betimle → betimlemeyi normal metin akışına
    ver (ürünü bulup 'bu ürün mü?' linkiyle sorsun). Uydurmaz; bulamazsa devreder."""
    try:
        if await _already_processed(mid):
            return
        cfg = await _wa_cfg()
        settings = await get_ai_settings()
        if not settings.get("enabled", True) or not cfg.get("ai_autoreply", False):
            return
        api_key = _api_key_for(settings)
        if not api_key:
            await _handoff(sender, "[görsel]", name)
            return
        img, mime = await _download_wa_media(media_id, cfg.get("access_token", ""),
                                             cfg.get("api_version", "v23.0"))
        if not img:
            await _handoff(sender, "[görsel indirilemedi]", name)
            await _log(sender, "[görsel]", "", handoff=True, confidence=0.0, note="media_dl_fail")
            return
        try:
            desc = await _vision_describe(
                img, mime, api_key,
                settings.get("fast_model") or settings.get("model"),
                settings.get("provider", "openai"))
        except Exception as e:
            logger.exception("WA vision failed")
            await _handoff(sender, "[görsel]", name)
            await _log(sender, "[görsel]", "", handoff=True, confidence=0.0, note=f"vision_err:{str(e)[:80]}")
            return
        # Görsel betimlemesini normal akışa ver — ürünü bulup linkle "bu ürün mü?" desin.
        body = f"[Müşteri bir ürün GÖRSELİ gönderdi] Görseldeki ürün: {desc}"
        if caption:
            body += f" | Müşteri notu: {caption}"
        await _handle_inbound(sender, mid + "_img", body, name, own_pnid)
    except Exception as e:
        logger.exception(f"WA image handler error: {e}")


async def _handle_inbound(sender: str, mid: str, body: str,
                          name: Optional[str], own_pnid: Optional[str],
                          quoted_id: str = ""):
    try:
        if await _already_processed(mid):
            return
        cfg = await _wa_cfg()
        # Kendi numaramızdan geldiyse yok say (döngü koruması)
        if own_pnid and cfg.get("phone_number_id") and own_pnid == cfg.get("phone_number_id") and sender == own_pnid:
            return

        low = body.lower().strip()
        # Opt-out / opt-in
        if low in _OPT_OUT:
            await db.whatsapp_optout.update_one(
                {"_id": sender}, {"$set": {"opted_out": True, "at": _now()}}, upsert=True)
            await _send(cfg, sender, "Bilgilendirme mesajlarımız durduruldu. Yeniden başlatmak için 'BAŞLA' yazabilirsiniz.")
            await _log(sender, body, "[opt-out]", handoff=False, confidence=1.0)
            return
        if low in _OPT_IN:
            await db.whatsapp_optout.update_one(
                {"_id": sender}, {"$set": {"opted_out": False, "at": _now()}}, upsert=True)

        settings = await get_ai_settings()
        # AÇ/KAPA: AI beyni genel açık VE WhatsApp otomatik-yanıt anahtarı açık olmalı
        # (Bildirim Ayarları > WhatsApp Meta > "AI otomatik yanıt"). Varsayılan KAPALI.
        if not settings.get("enabled", True) or not cfg.get("ai_autoreply", False):
            await _log(sender, body, "", handoff=True, confidence=0.0, note="ai_whatsapp_disabled")
            return

        api_key = _api_key_for(settings)
        if not api_key:
            await _log(sender, body, "", handoff=True, confidence=0.0, note="no_api_key")
            return

        # Bağlam topla (grounded): bilgi bankası + ürün(açıklama/ölçü) + son siparişler +
        # firma/banka/politika. Amaç: müşterinin HER sorusuna sağlanan bilgiyle cevap.
        kb_ctx = await _gather_kb_context(body)
        dialog = await _recent_dialog(sender)
        # ÜRÜN KİLİDİ — müşterinin sorduğu ürünü SABİT tut, AI kendi kendine ürün DEĞİŞTİRMESİN.
        # Öncelik: (1) BU mesajda açıkça geçen ürün → kilitle; (2) müşteri bir mesajı
        # ALINTILADIYSA o mesajın ürünü; (3) daha önce kilitlenen aktif ürün (drift YOK).
        quoted_product, quoted_text = await _quoted_context(quoted_id)
        explicit = await _find_product(body)
        if explicit:
            product = explicit
            await _set_active_product(sender, explicit)
        elif quoted_product:
            product = quoted_product
            await _set_active_product(sender, quoted_product)
        else:
            product = await _get_active_product(sender)   # kilitli ürünü sürdür (dialog'dan TÜRETME)
        prod_ctx = await _gather_product_context((product or {}).get("name") or body)
        size_ctx = await _size_context(product)
        ord_ctx, ord_count, ord_transit = await _recent_orders_context(sender)
        extra_ctx = await _extra_context()
        camp_ctx = await _campaigns_context()
        plink = _product_link(product, extra_ctx.get("site_url"), _detect_size(body))

        system = settings.get("persona") or DEFAULT_PERSONA
        if extra_ctx.get("store_name"):
            if dialog:
                system += (f"\n\nMağaza: {extra_ctx['store_name']}. Bu DEVAM EDEN bir konuşma — "
                           "kendini TEKRAR tanıtma, tekrar selamlaMA, doğrudan ve tutarlı devam et.")
            else:
                system += (f"\n\nMağaza: {extra_ctx['store_name']}. Bu ilk mesaj — kısaca ve sıcak selamla; "
                           "kendini unvanla ('kıdemli temsilci' vb.) TANITMA.")
        if name:
            system += f"\nMüşterinin WhatsApp adı: {name}"
        system += (
            "\n\nKanal: WhatsApp. GÖREV: gerçek bir kıdemli müşteri temsilcisi gibi, müşterinin "
            "HER sorusuna yardımcı ol — ürün açıklaması/beden-ölçü, stok, fiyat/kampanya, kargo "
            "takibi, teslimat süresi, iade/değişim, ödeme ve havale/IBAN hesap bilgisi, üyelik vb. "
            "Kısa, sıcak, samimi yaz (1-4 cümle). Arada bir hafif/çiçek emojisi (🌸 gibi) kullanabilirsin, "
            "abartma. HİTAP: müşteriye ADIYLA hitap et — isim kadın veya unisex ise '<Ad> Hanım', bariz "
            "erkek ismiyse '<Ad> Bey', isim belirsiz/yoksa 'efendim' de. Çoğunlukla kadın müşteri "
            "olduğundan unisex isimde HANIM tercih et. Kendini unvanla ('kıdemli temsilci' vb.) TANITMA; "
            "her mesajda tekrar tanıtma/selamlaMA (devam eden konuşmada doğrudan konuş). "
            "KİMLİK: Adın Buse; FACETTE müşteri ekibindensin. 'Bot musun / yapay zeka mısın' diye "
            "sorulursa tartışmaya girme, yapay zeka olduğunu söyleme; 'Ben Buse, FACETTE ekibinden size "
            "yardımcı oluyorum 🌸' deyip sıcakça konuya dön. "
            "GİZLİLİK (KVKK): YALNIZCA bu müşterinin KENDİ bilgilerini paylaş. Başka müşterilerin sipariş, "
            "isim, telefon, adres gibi kişisel bilgilerini ASLA verme. Sana verilen sipariş listesi zaten "
            "bu müşteriye aittir; başka birinin siparişini/bilgisini isterse kibarca reddet. "
            "TUTARLILIK: Verdiğin bilgiyle çelişme; bir durumu açıkladıktan sonra klişe 'nasıl yardımcı "
            "olabilirim' KAPANIŞI YAPMA — mantıklı, SOMUT bir sonraki adım öner (ör. ödeme başarısız/"
            "süresi dolmuşsa: 'dilerseniz yeniden sipariş oluşturmanıza yardımcı olayım' ya da ödeme "
            "linkine yönlendir; kargo gecikmişse takip no ver; iade istiyorsa süreci anlat). "
            "KURAL: Yalnızca aşağıda sana verilen bilgilerden cevapla; sipariş/stok/fiyat/"
            "kargo/ölçü gibi bir bilgi verilmemişse UYDURMA — kibarca 'kontrol edip döneyim' de ve "
            "insana devret (HANDOFF: yes).\n"
            "BEDEN ÖNERİSİ: Aşağıda [Beden Tablosu / Ölçüler] SANA VERİLDİYSE, müşterinin boy/kilo/"
            "bedenine göre o ölçülere + manken referansına + KALIP/SEZON bilgisine bakıp UYGUN BEDENİ "
            "MUTLAKA KENDİN ÖNER, kısa gerekçe ver ve HANDOFF: no yap — bu durumda SAKIN insana "
            "devretme, 'temsilciye ilettim' DEME. Yalnızca beden tablosu HİÇ verilmediyse kibarca beden "
            "tablosuna yönlendir. Ölçü uydurma.\n"
            "SOHBET/KONU-DIŞI: Müşteri konu dışı, samimi ya da tuhaf/'saçma' bir şey sorsa bile "
            "robotik reddetme; kısa, sıcak, hafif esprili ama nazik bir insan temsilci gibi cevapla, "
            "sonra kibarca alışverişe/konuya yönlendir. Hakaret/uygunsuzlukta sakin ve profesyonel kal.\n"
            "SATIŞ YAKLAŞIMI (sıcak & güven odaklı — asla ısrarcı/agresif değil, GÜVEN her şeyden önce): "
            "1) Önce ihtiyacı anla, sonra danışman gibi öner. 2) Güven kur: güvenli ödeme (3D Secure/"
            "iyzico), kolay iade, hızlı kargo, X TL üzeri ücretsiz kargo eşiğini uygun yerde hatırlat. "
            "3) Sosyal kanıt: çok tercih edilen/çok satan/beğenilen ürünü belirt (YALNIZ gerçekse). "
            "4) Aciliyet/kıtlık SADECE gerçekse: stok az/'son birkaç adet'/kampanya bitişi — UYDURMA. "
            "5) Kişiselleştir + nazik cross-sell: bedenine/tarzına uygun öner, tamamlayıcı parça (kombin) "
            "öner. 6) İtirazı (fiyat/kararsızlık) empatiyle karşıla; değer + risksizlik (iade güvencesi) "
            "vurgula. 7) Ücretsiz kargo eşiğine az kaldıysa üstüne tamamlamayı nazikçe öner. 8) Yumuşak "
            "kapanış: net ve zorlamasız bir sonraki adım ('sepete ekleyip ödemeye geçebilirsiniz', "
            "link/yönlendirme). Fiyat/stok/kampanyayı ASLA uydurma; yalnız sistemdeki gerçek veriyle.\n"
            "LİNK & SATIŞA GÖTÜRME: [Ürün Linki] verildiyse kullan. (a) Hangi üründen bahsedildiğinden "
            "EMİN DEĞİLSEN linki paylaş ve 'Emin olmak için soruyorum, bu üründen mi bahsediyoruz? 🌸' de; "
            "müşteri bundan rahatsız olursa kibarca 'bazı müşterilerimiz ürün adını farklı söyleyebiliyor, "
            "o yüzden emin olmak istedim' de. (b) Müşteri BİR BEDEN seçtiyse ya da almak istiyorsa ürün "
            "linkini (beden ön-seçili) paylaş ve 'linke tıklayıp sepete ekleyerek ödemeye geçebilirsiniz' "
            "diye nazikçe ödemeye yönlendir — bu durumda İNSANA DEVRETME (HANDOFF: no), satışı tamamlamaya "
            "yardım et.\n"
            "--- BİLGİ KAYNAĞI (yalnız bunları kullan) ---\n"
        )
        if dialog:
            system += f"\n[Önceki Konuşma — son mesajlar; buna göre TUTARLI ve tekrarsız devam et]\n{dialog}\n"
        if quoted_text:
            system += (f"\n[Müşteri ŞU mesajı ALINTILAYIP yanıtladı — sorusu DOĞRUDAN bununla ilgili, "
                       f"buna göre cevapla]\n\"{quoted_text[:400]}\"\n")
        if ord_ctx:
            system += f"\n{ord_ctx}\n"
            # KARGO ODAK: "siparişim nerede" için yoldaki siparişe odaklan, hepsi teslimse sor.
            if ord_transit >= 1:
                system += ("KURAL(kargo): Müşteride KARGODA (yolda) sipariş VAR. 'Siparişim nerede/kargom' "
                           "sorusunda YALNIZ [KARGODA] işaretli sipariş(ler) hakkında bilgi ver: kargo firması + "
                           "takip no + güncel durum. Teslim edilmiş siparişleri KARIŞTIRMA. Birden fazla KARGODA "
                           "sipariş varsa hangisi olduğunu #no+tarih ile sor.\n")
            elif ord_count >= 2:
                system += ("KURAL(sipariş): Müşterinin BİRDEN FAZLA siparişi var ve hepsi teslim/kargoda değil. "
                           "Sipariş/kargo sorusunda hemen cevaplama; önce hangisini kastettiğini SOR — siparişleri "
                           "#no + ürün adı + TARİH ile kısaca listele ve 'Hangi siparişiniz için soruyorsunuz?' de.\n")
            elif ord_count == 1:
                system += ("KURAL(sipariş): Müşterinin TEK siparişi var. Varsaymadan önce "
                           "'#<no> (<ürün>, <tarih>) siparişiniz için mi soruyorsunuz?' diye TEYİT et; onaylayınca detay ver.\n")
        if product and product.get("name"):
            system += (f"\n[AKTİF ÜRÜN — müşterinin ŞU AN sorduğu ürün]\n{product.get('name')}\n"
                       "KURAL(ürün): SADECE bu ürün hakkında konuş. KENDİ KENDİNE başka bir ürün adı UYDURMA/ÖNERME/"
                       "DEĞİŞTİRME. Müşteri açıkça yeni bir ürün adı vermedikçe ürünü DEĞİŞTİRME. Bu üründen mi "
                       "bahsedildiğinden emin değilsen [Ürün Linki] paylaşıp 'bu ürün mü?' diye SOR; rastgele ürün ADI UYDURMA.\n")
        if prod_ctx:
            system += f"\n[Ürün Bilgisi — açıklama/özellik(sezon/kalıp)]\n{prod_ctx}\n"
        if size_ctx:
            system += (f"\n[Beden Tablosu / Ölçüler — müşteri boy/kilo/beden söylerse ölçülere ve "
                       f"manken referansına göre UYGUN BEDENİ öner, kısa gerekçe ver]\n{size_ctx}\n")
        if plink:
            system += f"\n[Ürün Linki]\n{plink}\n"
        if camp_ctx:
            system += (f"\n[Aktif Kampanyalar — 'hangi kampanya/indirim/kupon var' sorulursa BUNLARI anlat]\n{camp_ctx}\n"
                       "KURAL(kampanya): Kampanya/indirim/kupon sorulursa yukarıdaki AKTİF kampanyaları koşullarıyla "
                       "(min tutar, ilk sipariş) anlat; otomatik olanları 'sepete ekleyince otomatik uygulanır', kodu "
                       "olanı kodla söyle. Uygun bir kampanya varsa satışa nazikçe yönlendir. Kampanya/kod ASLA UYDURMA; "
                       "listede yoksa 'şu an aktif bir kampanya görünmüyor' de. Bu soruda İNSANA DEVRETME (HANDOFF: no).\n")
        else:
            system += ("\nKURAL(kampanya): Kampanya/indirim sorulursa ve sana kampanya verilmediyse dürüstçe "
                       "'şu an aktif bir kampanya görünmüyor' de; kod/kampanya UYDURMA. Bu soruda da HANDOFF: no.\n")
        if extra_ctx.get("bank"):
            system += f"\n[Havale/EFT Hesap Bilgisi]\n{extra_ctx['bank']}\n"
        if extra_ctx.get("company"):
            system += f"\n[Firma & İletişim]\n{extra_ctx['company']}\n"
        if extra_ctx.get("policy"):
            system += f"\n[Kargo/İade/Kampanya Kuralları]\n{extra_ctx['policy']}\n"
        if kb_ctx:
            system += f"\n[Bilgi Bankası — önceki onaylı yanıtlar]\n{kb_ctx}\n"
        system += (
            "\nÖNEMLİ — DEVRETME KURALI: HANDOFF: yes'i SADECE gerçekten ilgili bilgin YOKSA ya da "
            "işlem (iptal/iade onayı gibi) senin yetkinde değilse kullan. Sana yukarıda VERİLEN bilgiyle "
            "(sipariş/ürün/beden tablosu/kargo/politika/IBAN) cevaplanabilen HER soruyu SEN cevapla ve "
            "HANDOFF: no yap. Elinde cevap varken 'temsilciye ilettim' DEME.\n"
            "\nCevabın SONUNA ayrı satırda şu bloğu ekle:\n"
            "---META---\nCONFIDENCE: <0.0-1.0>\nHANDOFF: <yes|no>\n"
        )
        user_text = f"Müşteri ({name or 'isimsiz'}): {body}"

        try:
            resp = await llm_chat(
                api_key=api_key,
                provider=settings.get("provider", "anthropic"),
                model=settings.get("fast_model") or settings.get("model", "claude-haiku-4-5"),
                system_message=system, user_text=user_text, max_tokens=500,
            )
        except Exception as e:
            logger.exception("WA AI reply failed")
            await _log(sender, body, "", handoff=True, confidence=0.0, note=f"llm_error:{e}")
            await _handoff(sender, body, name)
            return

        reply, confidence, handoff = _parse_meta(str(resp or ""))
        threshold = float(settings.get("confidence_threshold", 0.7) or 0.7)
        if confidence < threshold:
            handoff = True

        # Opt-out ettiyse yine cevaplarız (müşteri-hizmetleri penceresi); pazarlama göndermeyiz.
        if handoff or not reply:
            await _handoff(sender, body, name)
            await _log(sender, body, reply, handoff=True, confidence=confidence)
            return

        reply_wamid = await _send(cfg, sender, reply)
        await _log(sender, body, reply, handoff=False, confidence=confidence,
                   wamid=reply_wamid, product_id=(product or {}).get("id"))
    except Exception as e:
        logger.exception(f"WA inbound handler error: {e}")


def _parse_meta(text: str):
    import re
    confidence, handoff = 0.7, False
    reply = text.strip()
    m = re.search(r"---META---\s*CONFIDENCE:\s*([0-9.]+)\s*HANDOFF:\s*(\w+)", text, re.I)
    if m:
        try:
            confidence = max(0.0, min(1.0, float(m.group(1))))
        except Exception:
            pass
        handoff = m.group(2).lower().startswith("y")
        reply = text[:m.start()].strip()
    reply = re.split(r"-{2,}\s*META", reply, 1)[0].strip()
    return reply, confidence, handoff


# ── İNSAN TEMSİLCİYE DEVRET (canlı relay) ───────────────────────────────────
# AI cevaplayamadığında müşteriye UYDURMA yapmaz; soruyu TEMSİLCİ (ana) numaraya
# WhatsApp'tan iletir. Temsilci o alarmı YANITLAYIP cevabı yazınca (_handle_admin_reply)
# cevap otomatik müşteriye gider. Müşteriye bu sırada MESAJ GÖNDERİLMEZ (sessiz bekleme).
def _phone_tail(p) -> str:
    """Karşılaştırma için telefon kuyruğu (son 10 hane) — +90/0/905 farklarını yutar."""
    digits = "".join(ch for ch in str(p or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _admin_tail(cfg: dict) -> str:
    return _phone_tail(cfg.get("handoff_notify_phone") or "")


def _is_admin(sender, cfg: dict) -> bool:
    """Gelen mesaj, panelde tanımlı TEMSİLCİ (ana) numarasından mı? (cevap relay'i için)"""
    at = _admin_tail(cfg)
    return bool(at) and _phone_tail(sender) == at


def _fmt_phone_display(p) -> str:
    d = "".join(ch for ch in str(p or "") if ch.isdigit())
    if len(d) >= 10:
        t = d[-10:]
        return f"+90 {t[:3]} {t[3:6]} {t[6:8]} {t[8:]}"
    return str(p or "")


async def _handoff(sender: str, body: str, name: Optional[str]):
    """AI cevaplayamadı → İNSAN temsilciye devret (canlı relay).
    - whatsapp_handoffs'a 'open' kayıt aç (müşteri no + soru + admin alarm mesaj id'si).
    - TEMSİLCİ (ana) numarasına WhatsApp'tan alarm gönder (24-saat penceresi açıksa düşer).
    - Yedek: admin mobil push + firma e-postası (WhatsApp penceresi kapalıysa kaçmasın).
    - MÜŞTERİYE MESAJ YOK (kullanıcı tercihi: sessiz bekle). Cevabı temsilci iletir.
    """
    cfg = await _wa_cfg()
    admin_num = cfg.get("handoff_notify_phone") or ""
    who = name or "Müşteri"
    cust_disp = _fmt_phone_display(sender)
    alert_wamid = ""
    if _admin_tail(cfg):
        alert = (
            "🔴 *Yanıtlayamadığım bir müşteri sorusu var.*\n\n"
            f"👤 {who} ({cust_disp})\n"
            f"💬 \"{body[:900]}\"\n\n"
            "Cevaplamak için *bu mesajı yanıtlayıp* (kaydır/reply) sadece cevabı yazın — "
            "müşteriye ben ileteceğim. (Alternatif: cevabın başına müşteri numarasını yazın.)"
        )
        try:
            alert_wamid = await _send(cfg, admin_num, alert)
        except Exception:
            alert_wamid = ""
    try:
        await db.whatsapp_handoffs.insert_one({
            "phone": sender, "name": name, "question": body,
            "status": "open", "created_at": _now(),
            "alert_wamid": alert_wamid, "source": "whatsapp",
        })
    except Exception:
        pass
    # Yedek alarm 1 — mobil admin push (panel)
    try:
        from .push import send_push_to_admins
        await send_push_to_admins(
            "📞 Yanıt bekleyen müşteri",
            f"{who} ({cust_disp}): {body[:120]}",
            {"type": "whatsapp_handoff", "phone": sender},
        )
    except Exception as e:
        logger.warning(f"handoff admin push atlandı: {e}")
    # Yedek alarm 2 — firma e-postası (best-effort)
    try:
        import company
        from notification_service import _email_send
        c = await company.get_company(db)
        admin_email = c.get("contact_email") or ""
        if admin_email:
            html = (f"<p>WhatsApp AI yanıtlayamadı, bir müşteri yanıt bekliyor:</p>"
                    f"<p><b>{who}</b> ({cust_disp})</p>"
                    f"<blockquote>{body[:1500]}</blockquote>"
                    f"<p>Cevaplamak için WhatsApp'tan temsilci numaranıza gelen alarmı "
                    f"yanıtlayın; cevap otomatik müşteriye iletilir.</p>")
            await _email_send(db, admin_email, "📞 WhatsApp'ta yanıt bekleyen müşteri", html)
    except Exception as e:
        logger.warning(f"handoff admin email atlandı: {e}")


async def _handle_admin_reply(sender: str, mid: str, body: str, context_id: str = ""):
    """TEMSİLCİ (ana) numaradan gelen mesaj = bekleyen bir handoff'a CEVAP.
    Hedef müşteriyi belirle → cevabı müşteriye ilet → handoff'u kapat → temsilciye onay.
    Hedef bulma sırası: (1) yanıtlanan alarm mesajı (context_id → alert_wamid),
    (2) mesaj başına yazılan müşteri numarası, (3) tek açık handoff varsa o."""
    try:
        if await _already_processed(mid):
            return
        cfg = await _wa_cfg()
        text = (body or "").strip()
        low = text.lower()
        # Basit komutlar — açık talepleri listele
        if low in ("liste", "list", "bekleyenler", "kim var"):
            cur = db.whatsapp_handoffs.find({"status": "open"}).sort("created_at", -1).limit(10)
            rows = await cur.to_list(10)
            if not rows:
                await _send(cfg, sender, "Şu an bekleyen müşteri yok. ✅")
            else:
                lines = ["*Bekleyen müşteriler:*"]
                for r in rows:
                    lines.append(f"• {r.get('name') or 'Müşteri'} "
                                 f"({_fmt_phone_display(r.get('phone'))}): "
                                 f"{(r.get('question') or '')[:70]}")
                lines.append("\nCevaplamak için ilgili alarmı yanıtlayın ya da "
                             "cevabın başına müşteri numarasını yazın.")
                await _send(cfg, sender, "\n".join(lines))
            return

        target = None
        answer = text
        # (1) Alarm mesajını yanıtladıysa → alert_wamid eşleşmesi (en kesin)
        if context_id:
            target = await db.whatsapp_handoffs.find_one(
                {"alert_wamid": context_id, "status": "open"})
        # (2) Başına müşteri numarası yazıldıysa
        if not target:
            import re as _re
            mnum = _re.match(r"^[\s@]*(\+?\d[\d\s\-]{8,})[\s:>\-]+(.+)$", text, _re.S)
            if mnum:
                cand_tail = _phone_tail(mnum.group(1))
                rest = (mnum.group(2) or "").strip()
                if cand_tail and rest:
                    t = await db.whatsapp_handoffs.find_one(
                        {"status": "open",
                         "phone": {"$regex": cand_tail + "$"}},
                        sort=[("created_at", -1)])
                    if t:
                        target, answer = t, rest
        # (3) Tek açık handoff varsa ona ata
        if not target:
            opens = await db.whatsapp_handoffs.find({"status": "open"}).to_list(3)
            if len(opens) == 1:
                target = opens[0]
            elif len(opens) > 1:
                await _send(cfg, sender,
                            "Birden fazla müşteri bekliyor — hangisine cevap verdiğinizi "
                            "belirtmek için ilgili *alarmı yanıtlayın* ya da cevabın başına "
                            "müşteri numarasını yazın. (Liste için: 'liste')")
                return
        if not target:
            await _send(cfg, sender,
                        "Şu an cevabınızı iletebileceğim bekleyen bir müşteri bulamadım. "
                        "(Bekleyenler için: 'liste')")
            return
        if not answer:
            await _send(cfg, sender, "Boş cevap — müşteriye iletebilmem için cevap metni yazın.")
            return

        cust = target.get("phone")
        await _send(cfg, cust, answer)
        try:
            await db.whatsapp_handoffs.update_one(
                {"_id": target.get("_id")},
                {"$set": {"status": "answered", "answer": answer,
                          "answered_at": _now(), "answered_by": "human"}})
        except Exception:
            pass
        # Diyalog belleğine yaz (AI sonraki mesajda tutarlı devam etsin)
        await _log(cust, "", answer, handoff=False, confidence=1.0, note="human_reply")
        await _send(cfg, sender,
                    f"✅ Cevabınız iletildi → {target.get('name') or 'Müşteri'} "
                    f"({_fmt_phone_display(cust)})")
    except Exception as e:
        logger.warning(f"admin reply relay hata: {e}")


async def _send(cfg: dict, to: str, message: str) -> str:
    """Mesaj gönderir; başarılıysa Meta mesaj id'sini (wamid) döner, yoksa ''.
    (wamid, temsilci alarmının yanıt-eşleşmesi için handoff kaydına yazılır.)"""
    from notification_service import _whatsapp_send
    try:
        res = await _whatsapp_send(cfg, to, message)
        if not res.get("success"):
            logger.warning(f"WA send failed to {str(to)[-4:]}: {res.get('response')}")
            return ""
        try:
            j = json.loads(res.get("response") or "{}")
            return (((j.get("messages") or [{}])[0]) or {}).get("id") or ""
        except Exception:
            return ""
    except Exception as e:
        logger.warning(f"WA send error: {e}")
        return ""


async def _log(phone: str, inbound: str, outbound: str, *, handoff: bool,
               confidence: float, note: str = "", wamid: str = "", product_id=None):
    try:
        doc = {
            "phone": phone, "inbound": inbound, "outbound": outbound,
            "handoff": handoff, "confidence": confidence, "note": note,
            "created_at": _now(),
        }
        if wamid:
            doc["wamid"] = wamid          # gönderilen AI mesajının Meta id'si (alıntı-yanıt eşleşmesi)
        if product_id:
            doc["product_id"] = product_id  # bu turda konuşulan ürün (kilit/alıntı için)
        await db.whatsapp_conversations.insert_one(doc)
    except Exception:
        pass


def _strip_html(h: str) -> str:
    import re as _r
    t = _r.sub(r"<[^>]+>", " ", h or "")
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#160;", " ")
    return _r.sub(r"\s+", " ", t).strip()


async def _extra_context() -> dict:
    """Firma + havale/IBAN + iade/kargo/SSS politikası — 'her soruya cevap' için grounded bilgi."""
    out = {"store_name": "", "company": "", "bank": "", "policy": "", "site_url": ""}
    # Firma & iletişim
    try:
        import company
        c = await company.get_company(db)
        out["store_name"] = c.get("store_name") or ""
        out["site_url"] = (c.get("site_url") or "").rstrip("/")
        parts = []
        for label, key in (("Mağaza", "store_name"), ("Site", "site_url"),
                           ("E-posta", "contact_email"), ("Telefon", "contact_phone"),
                           ("WhatsApp", "whatsapp"), ("Instagram", "instagram")):
            v = c.get(key)
            if v:
                parts.append(f"{label}: {v}")
        out["company"] = " | ".join(parts)
    except Exception:
        pass
    # Havale/EFT hesabı (settings.payment.bank_accounts)
    try:
        pay = await db.settings.find_one({"id": "payment"}, {"_id": 0, "bank_accounts": 1}) or {}
        banks = pay.get("bank_accounts") or []
        b = next((x for x in banks if x.get("is_default")), None) or (banks[0] if banks else None)
        if b:
            out["bank"] = (f"Alıcı: {b.get('account_holder','')} | Banka: {b.get('bank_name','')} "
                           f"| Şube: {b.get('branch','')} | IBAN: {b.get('iban','')}")
    except Exception:
        pass
    # İade/kargo/SSS politikaları (db.pages — HTML temizlenir, kısaltılır)
    try:
        slugs = ["iade-kosullari", "iade-ve-degisim", "iade", "kargo-ve-teslimat",
                 "kargo", "teslimat", "sikca-sorulan-sorular", "sss"]
        chunks = []
        cur = db.pages.find({"slug": {"$in": slugs}}, {"_id": 0, "title": 1, "content": 1}).limit(4)
        async for p in cur:
            txt = _strip_html(p.get("content", ""))[:900]
            if txt:
                chunks.append(f"{p.get('title','')}: {txt}")
        out["policy"] = "\n".join(chunks)[:2500]
    except Exception:
        pass
    return out


async def _campaigns_context() -> str:
    """Aktif (herkese AÇIK) kampanyaları koşullarıyla listeler — 'hangi kampanyalardan
    faydalanabilirim / indirim var mı' sorusuna AI cevap verebilsin diye. Kişiye ÖZEL
    (user_id / customer_email hedefli) kuponlar GİZLENİR (KVKK + kod sızıntısı yok)."""
    now_iso = _now()

    def _win_ok(c):
        s = c.get("start_at")
        e = c.get("end_at")
        if s and str(s) > now_iso:
            return False
        if e:
            es = str(e)
            if len(es) == 10 and "T" not in es:
                es = es + "T23:59:59+00:00"
            if es < now_iso:
                return False
        return True

    try:
        rows = await db.coupons.find(
            {"is_active": True},
            {"_id": 0, "code": 1, "title": 1, "name": 1, "type": 1, "value": 1,
             "min_cart_total": 1, "free_shipping": 1, "auto_apply": 1, "first_order_only": 1,
             "start_at": 1, "end_at": 1, "usage_limit": 1, "user_id": 1, "customer_email": 1,
             "buy_quantity": 1, "free_quantity": 1, "min_quantity": 1},
        ).sort("value", -1).to_list(80)
    except Exception:
        return ""
    lines = []
    for c in rows:
        if c.get("user_id") or c.get("customer_email"):
            continue  # kişiye özel → müşteriye açıklama
        if not _win_ok(c):
            continue
        title = c.get("title") or c.get("name") or c.get("code") or "Kampanya"
        typ = (c.get("type") or "percent").lower()
        val = float(c.get("value") or 0)
        if c.get("free_shipping"):
            benefit = "ücretsiz kargo"
        elif typ == "percent" and val > 0:
            benefit = f"%{val:g} indirim"
        elif typ == "fixed" and val > 0:
            benefit = f"{val:g} TL indirim"
        elif typ == "nth_discount":
            bq = c.get("buy_quantity") or c.get("min_quantity") or 0
            fq = c.get("free_quantity") or 1
            benefit = f"{bq} al {fq} bedava" if bq else "adet kampanyası"
        else:
            benefit = "indirim"
        conds = []
        mct = float(c.get("min_cart_total") or 0)
        if mct > 0:
            conds.append(f"{mct:g} TL üzeri sepette")
        if c.get("first_order_only"):
            conds.append("ilk siparişe özel")
        how = "otomatik uygulanır" if c.get("auto_apply") else (f"kod: {c.get('code')}" if c.get("code") else "")
        seg = f"• {title}: {benefit}"
        if conds:
            seg += " (" + ", ".join(conds) + ")"
        if how:
            seg += f" — {how}"
        lines.append(seg)
        if len(lines) >= 10:
            break
    return "\n".join(lines)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
