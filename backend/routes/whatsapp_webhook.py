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
async def wa_diag(key: str = ""):
    """PII'siz teşhis — verify_token ile korunur. Webhook geldi mi, AI anahtarı/config
    tam mı, gönderim başarılı mı görülür. Mesaj metni DÖNMEZ (yalnız not/durum)."""
    cfg = await _wa_cfg()
    expected = cfg.get("verify_token") or os.environ.get("WHATSAPP_VERIFY_TOKEN", "")
    if not expected or not hmac.compare_digest(key, expected):
        return PlainTextResponse("forbidden", status_code=403)
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
    return {
        "config": {
            "has_phone_id": bool(cfg.get("phone_number_id")),
            "phone_number_id": (cfg.get("phone_number_id") or "")[-6:],
            "has_token": bool(cfg.get("access_token")),
            "app_secret_set": bool(cfg.get("app_secret")),
            "ai_autoreply": bool(cfg.get("ai_autoreply")),
        },
        "raw_hits": hits,
        "ai": {
            "enabled": settings.get("enabled", True),
            "provider": settings.get("provider"),
            "model": settings.get("fast_model") or settings.get("model"),
            "has_key": bool(_api_key_for(settings)),
        },
        "inbound": {"processed_count": processed, "recent": recent},
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
            own_pnid = (value.get("metadata") or {}).get("phone_number_id")
            contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                        for c in (value.get("contacts") or [])}
            for m in (value.get("messages") or []):
                if m.get("type") != "text":
                    continue  # sadece metin (medya/konum vb. ilk sürümde atlanır)
                sender = m.get("from")
                mid = m.get("id")
                body = ((m.get("text") or {}).get("body") or "").strip()
                if not sender or not mid or not body:
                    continue
                # Arka planda işle (Meta'ya hemen 200 dön)
                background.add_task(
                    _handle_inbound, sender=sender, mid=mid, body=body,
                    name=contacts.get(sender), own_pnid=own_pnid,
                )
    return {"ok": True}


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
        return "", 0
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
        if o.get("payment_status"):
            seg += f", ödeme={o.get('payment_status')}"
        if o.get("tracking_number"):
            seg += f", kargo={o.get('cargo_company') or ''} takip={o.get('tracking_number')}"
        lines.append(seg)
    return "\n".join(lines), len(rows)


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
    """Konuşma metninden (cümlenin içinden) ürünü anahtar-kelime örtüşmesiyle bulur."""
    import re as _r
    kws = _keywords(text)
    if not kws:
        return None
    ors = [{"name": {"$regex": _r.escape(k), "$options": "i"}} for k in kws[:6]]
    try:
        prods = await db.products.find(
            {"$or": ors}, {"_id": 0, "id": 1, "name": 1}).limit(15).to_list(15)
    except Exception:
        return None
    if not prods:
        return None
    def _score(p):
        nm = (p.get("name") or "").lower()
        return sum(1 for k in kws if k in nm)
    prods.sort(key=_score, reverse=True)
    return prods[0] if _score(prods[0]) > 0 else None


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


async def _recent_dialog(sender: str, limit: int = 6) -> str:
    """Bu müşteriyle son konuşma turlarını (kronolojik) döndürür — AI'nın tekrar
    tanıtmaması ve TUTARLI devam etmesi için. Sadece gerçek soru/cevap turları."""
    try:
        cur = db.whatsapp_conversations.find(
            {"phone": sender, "inbound": {"$nin": [None, ""]}},
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


async def _handle_inbound(sender: str, mid: str, body: str,
                          name: Optional[str], own_pnid: Optional[str]):
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
        product = await _find_product(body)
        prod_ctx = await _gather_product_context((product or {}).get("name") or body)
        size_ctx = await _size_context(product)
        ord_ctx, ord_count = await _recent_orders_context(sender)
        extra_ctx = await _extra_context()
        dialog = await _recent_dialog(sender)

        system = settings.get("persona") or DEFAULT_PERSONA
        if extra_ctx.get("store_name"):
            if dialog:
                system += (f"\n\nMağaza: {extra_ctx['store_name']}. Bu DEVAM EDEN bir konuşma — "
                           "kendini TEKRAR tanıtma, tekrar selamlaMA, doğrudan ve tutarlı devam et.")
            else:
                system += (f"\n\nMağaza adı: {extra_ctx['store_name']}. Bu ilk mesaj — kısaca selamla ve "
                           "kendini BİR KEZ kıdemli müşteri temsilcisi olarak tanıt.")
        system += (
            "\n\nKanal: WhatsApp. GÖREV: gerçek bir kıdemli müşteri temsilcisi gibi, müşterinin "
            "HER sorusuna yardımcı ol — ürün açıklaması/beden-ölçü, stok, fiyat/kampanya, kargo "
            "takibi, teslimat süresi, iade/değişim, ödeme ve havale/IBAN hesap bilgisi, üyelik vb. "
            "Kısa, sıcak, samimi yaz (1-4 cümle, gereksiz emoji yok). Müşteri adını uygunsa bir kez "
            "kullan. KENDİNİ HER MESAJDA TEKRAR TANITMA/SELAMLAMA (devam eden konuşmada doğrudan konuş). "
            "TUTARLILIK: Verdiğin bilgiyle çelişme; bir durumu açıkladıktan sonra klişe 'nasıl yardımcı "
            "olabilirim' KAPANIŞI YAPMA — mantıklı, SOMUT bir sonraki adım öner (ör. ödeme başarısız/"
            "süresi dolmuşsa: 'dilerseniz yeniden sipariş oluşturmanıza yardımcı olayım' ya da ödeme "
            "linkine yönlendir; kargo gecikmişse takip no ver; iade istiyorsa süreci anlat). "
            "KURAL: Yalnızca aşağıda sana verilen bilgilerden cevapla; sipariş/stok/fiyat/"
            "kargo/ölçü gibi bir bilgi verilmemişse UYDURMA — kibarca 'kontrol edip döneyim' de ve "
            "insana devret (HANDOFF: yes).\n"
            "BEDEN ÖNERİSİ: Müşteri boyunu/kilosunu veya normalde giydiği bedeni söylerse, ürünün "
            "[Ürün Bilgisi]'ndeki beden tablosu/ölçüleri + KALIP (dar/normal/bol/oversize) + SEZON "
            "bilgisine göre yorumlayıp uygun bedeni öner ve kısa gerekçe ver. Ölçü/kalıp verisi "
            "yoksa uydurma; beden tablosuna yönlendir veya insana devret.\n"
            "SOHBET/KONU-DIŞI: Müşteri konu dışı, samimi ya da tuhaf/'saçma' bir şey sorsa bile "
            "robotik reddetme; kısa, sıcak, hafif esprili ama nazik bir insan temsilci gibi cevapla, "
            "sonra kibarca alışverişe/konuya yönlendir. Hakaret/uygunsuzlukta sakin ve profesyonel kal.\n"
            "--- BİLGİ KAYNAĞI (yalnız bunları kullan) ---\n"
        )
        if dialog:
            system += f"\n[Önceki Konuşma — son mesajlar; buna göre TUTARLI ve tekrarsız devam et]\n{dialog}\n"
        if ord_ctx:
            system += f"\n{ord_ctx}\n"
            if ord_count >= 2:
                system += ("KURAL(sipariş): Müşterinin BİRDEN FAZLA siparişi var. Sipariş/kargo sorusunda "
                           "hemen cevaplama; önce hangisini kastettiğini SOR — siparişleri #no + ürün adı + "
                           "TARİH ile kısaca listele ve 'Hangi siparişiniz için soruyorsunuz?' de. Seçince yanıtla.\n")
            elif ord_count == 1:
                system += ("KURAL(sipariş): Müşterinin TEK siparişi var. Varsaymadan önce "
                           "'#<no> (<ürün>, <tarih>) siparişiniz için mi soruyorsunuz?' diye TEYİT et; onaylayınca detay ver.\n")
        if prod_ctx:
            system += f"\n[Ürün Bilgisi — açıklama/özellik(sezon/kalıp)]\n{prod_ctx}\n"
        if size_ctx:
            system += (f"\n[Beden Tablosu / Ölçüler — müşteri boy/kilo/beden söylerse ölçülere ve "
                       f"manken referansına göre UYGUN BEDENİ öner, kısa gerekçe ver]\n{size_ctx}\n")
        if extra_ctx.get("bank"):
            system += f"\n[Havale/EFT Hesap Bilgisi]\n{extra_ctx['bank']}\n"
        if extra_ctx.get("company"):
            system += f"\n[Firma & İletişim]\n{extra_ctx['company']}\n"
        if extra_ctx.get("policy"):
            system += f"\n[Kargo/İade/Kampanya Kuralları]\n{extra_ctx['policy']}\n"
        if kb_ctx:
            system += f"\n[Bilgi Bankası — önceki onaylı yanıtlar]\n{kb_ctx}\n"
        system += (
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

        await _send(cfg, sender, reply)
        await _log(sender, body, reply, handoff=False, confidence=confidence)
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


async def _handoff(sender: str, body: str, name: Optional[str]):
    """İnsan temsilciye devret: kayıt aç + müşteriye kısa bekletme mesajı."""
    cfg = await _wa_cfg()
    try:
        await db.whatsapp_handoffs.insert_one({
            "phone": sender, "name": name, "question": body,
            "status": "open", "created_at": _now(),
        })
    except Exception:
        pass
    await _send(cfg, sender, "Talebinizi müşteri temsilcimize ilettim, en kısa sürede size dönüş yapacağız. 🙏")


async def _send(cfg: dict, to: str, message: str):
    from notification_service import _whatsapp_send
    # Opt-out kontrolü (bekletme/opt-out onayı hariç zaten çağrılmaz)
    try:
        res = await _whatsapp_send(cfg, to, message)
        if not res.get("success"):
            logger.warning(f"WA send failed to {to[-4:]}: {res.get('response')}")
    except Exception as e:
        logger.warning(f"WA send error: {e}")


async def _log(phone: str, inbound: str, outbound: str, *, handoff: bool,
               confidence: float, note: str = ""):
    try:
        await db.whatsapp_conversations.insert_one({
            "phone": phone, "inbound": inbound, "outbound": outbound,
            "handoff": handoff, "confidence": confidence, "note": note,
            "created_at": _now(),
        })
    except Exception:
        pass


def _strip_html(h: str) -> str:
    import re as _r
    t = _r.sub(r"<[^>]+>", " ", h or "")
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#160;", " ")
    return _r.sub(r"\s+", " ", t).strip()


async def _extra_context() -> dict:
    """Firma + havale/IBAN + iade/kargo/SSS politikası — 'her soruya cevap' için grounded bilgi."""
    out = {"store_name": "", "company": "", "bank": "", "policy": ""}
    # Firma & iletişim
    try:
        import company
        c = await company.get_company(db)
        out["store_name"] = c.get("store_name") or ""
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
