"""
=============================================================================
marketing_pixels.py — Pazarlama Pixel & Etiket Yönetimi (FAZ 9)
=============================================================================

Admin panelden sadece kod yapıştırıp aktifleştirerek sitenin her sayfasında
otomatik çalışan pixel'ler:
  - Google Analytics 4 (GA4)
  - Meta Pixel (Facebook)
  - Google Ads Conversion
  - TikTok Pixel
  - Yandex Metrica
  - Özel HTML snippet'ler

Endpoint'ler:
  GET    /api/marketing-pixels               → admin tüm listesi
  POST   /api/marketing-pixels               → ekle/güncelle
  DELETE /api/marketing-pixels/{id}          → sil
  GET    /api/marketing-pixels/active-public → PUBLIC (auth yok) — aktif pixel head+body snippet'leri

Güvenlik: active-public sadece AKTİF pixel'lerin KAYITLI snippet'lerini döner.
Admin dışında kimse yeni kod ekleyemez.
=============================================================================
"""
from datetime import datetime, timezone
from typing import Optional, List
import logging
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from .deps import db, require_admin, generate_id

router = APIRouter(prefix="/marketing-pixels", tags=["marketing-pixels"])


PIXEL_PROVIDERS = [
    {"key": "ga4", "name": "Google Analytics 4", "supports_capi": True},
    {"key": "meta", "name": "Meta Pixel (Facebook) + CAPI", "supports_capi": True},
    {"key": "google_ads", "name": "Google Ads (Enhanced Conv)", "supports_capi": True},
    {"key": "tiktok", "name": "TikTok Pixel + Events API", "supports_capi": True},
    {"key": "pinterest", "name": "Pinterest + Conversions API", "supports_capi": True},
    {"key": "snapchat", "name": "Snapchat + Conversions API", "supports_capi": True},
    {"key": "gtm", "name": "Google Tag Manager (container)", "supports_capi": False},
    {"key": "yandex", "name": "Yandex Metrica", "supports_capi": False},
    {"key": "hotjar", "name": "Hotjar", "supports_capi": False},
    {"key": "clarity", "name": "Microsoft Clarity", "supports_capi": False},
    {"key": "custom", "name": "Özel Kod", "supports_capi": False},
]


def _template_snippet(provider: str, tag_id: str) -> dict:
    """Hızlı tag-id tabanlı snippet oluşturur (GA4, Meta gibi)."""
    head = ""
    body = ""
    if provider == "ga4" and tag_id:
        head = f"""
<!-- Google Analytics 4 -->
<script async src="https://www.googletagmanager.com/gtag/js?id={tag_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{tag_id}');
</script>
""".strip()
    elif provider == "meta" and tag_id:
        head = f"""
<!-- Meta Pixel -->
<script>
!function(f,b,e,v,n,t,s)
{{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '{tag_id}');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={tag_id}&ev=PageView&noscript=1"/></noscript>
""".strip()
    elif provider == "google_ads" and tag_id:
        head = f"""
<!-- Google Ads -->
<script async src="https://www.googletagmanager.com/gtag/js?id={tag_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{tag_id}');
</script>
""".strip()
    elif provider == "tiktok" and tag_id:
        head = f"""
<!-- TikTok Pixel -->
<script>
!function (w, d, t) {{
  w.TiktokAnalyticsObject=t;var ttq=w[t]=w[t]||[];ttq.methods=["page","track","identify","instances","debug","on","off","once","ready","alias","group","enableCookie","disableCookie"],ttq.setAndDefer=function(t,e){{t[e]=function(){{t.push([e].concat(Array.prototype.slice.call(arguments,0)))}}}};for(var i=0;i<ttq.methods.length;i++)ttq.setAndDefer(ttq,ttq.methods[i]);ttq.instance=function(t){{for(var e=ttq._i[t]||[],n=0;n<ttq.methods.length;n++)ttq.setAndDefer(e,ttq.methods[n]);return e}},ttq.load=function(e,n){{var i="https://analytics.tiktok.com/i18n/pixel/events.js";ttq._i=ttq._i||{{}},ttq._i[e]=[],ttq._i[e]._u=i,ttq._t=ttq._t||{{}},ttq._t[e]=+new Date,ttq._o=ttq._o||{{}},ttq._o[e]=n||{{}};var o=document.createElement("script");o.type="text/javascript",o.async=!0,o.src=i+"?sdkid="+e+"&lib="+t;var a=document.getElementsByTagName("script")[0];a.parentNode.insertBefore(o,a)}};
  ttq.load('{tag_id}');
  ttq.page();
}}(window, document, 'ttq');
</script>
""".strip()
    elif provider == "pinterest" and tag_id:
        # tag_id = Pinterest TAG ID for browser pixel (PT-XXXX)
        head = f"""
<!-- Pinterest Tag -->
<script>
!function(e){{if(!window.pintrk){{window.pintrk = function () {{
window.pintrk.queue.push(Array.prototype.slice.call(arguments))}};var
n=window.pintrk;n.queue=[],n.version="3.0";var
t=document.createElement("script");t.async=!0,t.src=e;var
r=document.getElementsByTagName("script")[0];
r.parentNode.insertBefore(t,r)}}}}("https://s.pinimg.com/ct/core.js");
pintrk('load', '{tag_id}');
pintrk('page');
</script>
<noscript><img height="1" width="1" style="display:none;" alt="" src="https://ct.pinterest.com/v3/?event=init&tid={tag_id}&noscript=1" /></noscript>
""".strip()
    elif provider == "snapchat" and tag_id:
        head = f"""
<!-- Snap Pixel Code -->
<script type='text/javascript'>
(function(e,t,n){{if(e.snaptr)return;var a=e.snaptr=function(){{
a.handleRequest?a.handleRequest.apply(a,arguments):a.queue.push(arguments)}};
a.queue=[];var s='script';r=t.createElement(s);r.async=!0;
r.src=n;var u=t.getElementsByTagName(s)[0];
u.parentNode.insertBefore(r,u);}})(window,document,'https://sc-static.net/scevent.min.js');
snaptr('init', '{tag_id}', {{}});
snaptr('track', 'PAGE_VIEW');
</script>
""".strip()
    elif provider == "gtm" and tag_id:
        # tag_id = GTM-XXXX container id
        head = f"""
<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','{tag_id}');</script>
""".strip()
        body = f"""
<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={tag_id}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
""".strip()
    elif provider == "yandex" and tag_id:
        head = f"""
<!-- Yandex Metrica -->
<script type="text/javascript">
(function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};
m[i].l=1*new Date();for (var j = 0; j < document.scripts.length; j++) {{if (document.scripts[j].src === r) {{ return; }}}}
k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)}})
(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");
ym({tag_id}, "init", {{clickmap:true,trackLinks:true,accurateTrackBounce:true}});
</script>
""".strip()
    elif provider == "hotjar" and tag_id:
        head = f"""
<!-- Hotjar -->
<script>
(function(h,o,t,j,a,r){{
  h.hj=h.hj||function(){{(h.hj.q=h.hj.q||[]).push(arguments)}};
  h._hjSettings={{hjid:{tag_id},hjsv:6}};
  a=o.getElementsByTagName('head')[0];
  r=o.createElement('script');r.async=1;
  r.src=t+h._hjSettings.hjid+j+h._hjSettings.hjsv;
  a.appendChild(r);
}})(window,document,'https://static.hotjar.com/c/hotjar-','.js?sv=');
</script>
""".strip()
    elif provider == "clarity" and tag_id:
        head = f"""
<!-- Microsoft Clarity -->
<script>
(function(c,l,a,r,i,t,y){{
  c[a]=c[a]||function(){{(c[a].q=c[a].q||[]).push(arguments)}};
  t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
  y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
}})(window, document, "clarity", "script", "{tag_id}");
</script>
""".strip()
    return {"head": head, "body": body}


class PixelReq(BaseModel):
    id: Optional[str] = None
    provider: str  # bkz PIXEL_PROVIDERS
    name: Optional[str] = ""
    tag_id: Optional[str] = ""  # GA4 ID, Pixel ID, vb.
    head_snippet: Optional[str] = ""  # özel kod / override
    body_snippet: Optional[str] = ""
    is_active: bool = True
    # ---- CAPI (Server-Side Conversions API) fields ----
    capi_enabled: Optional[bool] = False
    access_token: Optional[str] = ""        # plain (taşıma için; vault'ta saklamak öneriliyor)
    vault_key: Optional[str] = ""           # secrets_vault collection key
    env_token_key: Optional[str] = ""       # env override (örn META_CAPI_TOKEN)
    test_event_code: Optional[str] = ""     # Meta TEST00001, GA4 debug, …
    tenant_id: Optional[str] = None         # multi-tenant (SaaS)
    # Provider'a özel ekstra (Pinterest ad_account_id, Snapchat conversion_event vs)
    extra: Optional[dict] = None


@router.get("/providers")
async def get_providers(current_user: dict = Depends(require_admin)):
    return {"providers": PIXEL_PROVIDERS}


@router.get("")
async def list_pixels(current_user: dict = Depends(require_admin)):
    rows = await db.marketing_pixels.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=200)
    # Token'ları maskele
    for r in rows:
        if r.get("access_token"):
            r["_has_token"] = True
            r["access_token"] = "***"
        else:
            r["_has_token"] = bool(r.get("vault_key") or r.get("env_token_key"))
    return {"items": rows}


@router.post("")
async def upsert_pixel(req: PixelReq, current_user: dict = Depends(require_admin)):
    valid = {p["key"] for p in PIXEL_PROVIDERS}
    if req.provider not in valid:
        raise HTTPException(status_code=400, detail=f"Geçersiz sağlayıcı. Geçerli: {sorted(valid)}")

    # Kullanıcı head_snippet yazmadıysa tag_id üzerinden template'le üret
    head = (req.head_snippet or "").strip()
    body = (req.body_snippet or "").strip()
    if not head and req.tag_id:
        tpl = _template_snippet(req.provider, req.tag_id.strip())
        head = tpl.get("head") or ""
        body = tpl.get("body") or ""

    now_iso = datetime.now(timezone.utc).isoformat()
    data = {
        "provider": req.provider,
        "name": req.name or next((p["name"] for p in PIXEL_PROVIDERS if p["key"] == req.provider), req.provider),
        "tag_id": (req.tag_id or "").strip(),
        "head_snippet": head,
        "body_snippet": body,
        "is_active": req.is_active,
        # CAPI fields
        "capi_enabled": bool(req.capi_enabled),
        "vault_key": (req.vault_key or "").strip() or None,
        "env_token_key": (req.env_token_key or "").strip() or None,
        "test_event_code": (req.test_event_code or "").strip() or None,
        "tenant_id": req.tenant_id,
        "extra": req.extra or {},
        "updated_at": now_iso,
        "updated_by": current_user.get("email", ""),
    }
    # Access token: vault'a şifreli olarak yazılır; plain MongoDB'de tutulmaz
    if req.access_token:
        # Eğer vault_key belirtilmemişse otomatik üret (SaaS-safe)
        if not (req.vault_key or req.env_token_key):
            from hashlib import sha1
            sig = sha1(f"{req.provider}-{(req.tag_id or '').strip()}-{req.tenant_id or 'default'}".encode()).hexdigest()[:10]
            req.vault_key = f"capi_{req.provider}_{sig}"
            data["vault_key"] = req.vault_key
        # Vault'a yaz (env_token_key yoksa)
        if req.vault_key and not req.env_token_key:
            try:
                from security.crypto import encrypt as _vault_encrypt
                enc = _vault_encrypt(req.access_token.strip())
                await db.vault_secrets.update_one(
                    {"key": req.vault_key.strip()},
                    {"$set": {
                        "key": req.vault_key.strip(),
                        "value_enc": enc,
                        "description": f"CAPI {req.provider} token — {req.name or req.tag_id}",
                        "scope": "capi",
                        "updated_by": current_user.get("email"),
                        "updated_at": now_iso,
                    }, "$setOnInsert": {"created_at": now_iso}},
                    upsert=True,
                )
            except Exception as e:
                logger.warning(f"Vault upsert failed: {e}")
        # PLAIN text token'ı MongoDB'de tutma
        data["access_token"] = ""

    if req.id:
        existing = await db.marketing_pixels.find_one({"id": req.id}, {"_id": 0, "id": 1})
        if not existing:
            raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
        await db.marketing_pixels.update_one({"id": req.id}, {"$set": data})
        data["id"] = req.id
    else:
        data["id"] = generate_id()
        data["created_at"] = now_iso
        await db.marketing_pixels.insert_one(data)
    data.pop("_id", None)
    return {"success": True, "pixel": data}


@router.post("/test-connection")
async def test_capi_connection(req: PixelReq, current_user: dict = Depends(require_admin)):
    """CAPI bağlantısını test event göndererek dener.

    Frontend'den ya kayıtlı pixel id'yi referans edebilir ya da form verisini
    doğrudan yollayabilir. test_event_code önerilir (canlı raporu kirletmemek için).
    """
    from datetime import datetime
    from services.capi.orchestrator import _resolve_access_token, PROVIDERS

    provider = req.provider.lower()
    mod = PROVIDERS.get(provider)
    if not mod:
        raise HTTPException(status_code=400,
                            detail=f"Bu sağlayıcı için CAPI desteklenmiyor: {provider}")

    # Resolve token: from form, else from existing record's vault/env
    token = (req.access_token or "").strip()
    if not token and req.id:
        existing = await db.marketing_pixels.find_one({"id": req.id}, {"_id": 0})
        if existing:
            token = await _resolve_access_token(existing) or ""

    pixel_id = (req.tag_id or "").strip()
    if not pixel_id or not token:
        raise HTTPException(status_code=400,
                            detail="Test için pixel_id ve access_token gerekli.")

    res = await mod.test_connection(
        pixel_id=pixel_id, access_token=token,
        test_event_code=(req.test_event_code or "").strip() or None,
    )
    # Persist tester log
    await db.capi_event_logs.insert_one({
        "id": generate_id(),
        "provider": provider, "event_name": "test_connection",
        "tenant_id": req.tenant_id, "ok": bool(res.get("ok")),
        "status": res.get("status"), "response": res.get("response") or {},
        "error": res.get("error"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_test": True,
    })
    return res


@router.get("/{pid}")
async def get_pixel(pid: str, current_user: dict = Depends(require_admin)):
    px = await db.marketing_pixels.find_one({"id": pid}, {"_id": 0})
    if not px:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    # Token'ı maskele
    if px.get("access_token"):
        px["access_token"] = "***"
        px["_has_token"] = True
    return {"pixel": px}


@router.get("/capi/queue/status")
async def capi_queue_status(current_user: dict = Depends(require_admin)):
    """Stuck CAPI eventlerin özet durumu."""
    pending = await db.capi_event_queue.count_documents({"dead": {"$ne": True}})
    dead = await db.capi_event_queue.count_documents({"dead": True})
    total_logs = await db.capi_event_logs.count_documents({})
    last_failed = await db.capi_event_logs.find(
        {"ok": False}, {"_id": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    return {"pending": pending, "dead": dead,
            "total_logs": total_logs, "recent_failures": last_failed}


@router.post("/capi/queue/run-now")
async def capi_queue_run_now(current_user: dict = Depends(require_admin)):
    """Tüm bekleyen kuyruğu hemen tetikle (cron'u beklemeden)."""
    from services.capi.orchestrator import retry_queue_once
    res = await retry_queue_once(db)
    return res


@router.delete("/{pid}")
async def delete_pixel(pid: str, current_user: dict = Depends(require_admin)):
    res = await db.marketing_pixels.delete_one({"id": pid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")
    return {"success": True}


@router.get("/active-public")
async def list_active_public(response: Response):
    """Frontend'in <head> ve <body> sonuna enjekte edeceği kodlar.
    Auth yok — sadece aktif pixel'lerin önceden kaydedilmiş snippet'leri döner.
    60 saniye cache edilir (her sayfa yüklemesinde DB yorma).
    """
    rows = await db.marketing_pixels.find(
        {"is_active": True}, {"_id": 0, "provider": 1, "name": 1, "head_snippet": 1, "body_snippet": 1}
    ).to_list(length=50)
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return {
        "head": "\n".join([r.get("head_snippet") or "" for r in rows if r.get("head_snippet")]),
        "body": "\n".join([r.get("body_snippet") or "" for r in rows if r.get("body_snippet")]),
        "count": len(rows),
    }
