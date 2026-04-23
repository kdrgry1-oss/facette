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
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from .deps import db, require_admin, generate_id

router = APIRouter(prefix="/marketing-pixels", tags=["marketing-pixels"])


PIXEL_PROVIDERS = [
    {"key": "ga4", "name": "Google Analytics 4"},
    {"key": "meta", "name": "Meta Pixel (Facebook)"},
    {"key": "google_ads", "name": "Google Ads Conversion"},
    {"key": "tiktok", "name": "TikTok Pixel"},
    {"key": "yandex", "name": "Yandex Metrica"},
    {"key": "hotjar", "name": "Hotjar"},
    {"key": "clarity", "name": "Microsoft Clarity"},
    {"key": "custom", "name": "Özel Kod"},
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


@router.get("/providers")
async def get_providers(current_user: dict = Depends(require_admin)):
    return {"providers": PIXEL_PROVIDERS}


@router.get("")
async def list_pixels(current_user: dict = Depends(require_admin)):
    rows = await db.marketing_pixels.find({}, {"_id": 0}).sort("created_at", -1).to_list(length=200)
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
        "updated_at": now_iso,
        "updated_by": current_user.get("email", ""),
    }

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
