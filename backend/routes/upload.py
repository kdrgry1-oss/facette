from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response, RedirectResponse
from datetime import datetime, timezone
import base64
import uuid
import os

from .deps import db, get_current_user, logger
from services import r2_storage as r2

router = APIRouter(prefix="/upload", tags=["upload"])
# Geriye dönük uyumluluk: bazı kayıtlarda görsel URL'si /api/files/... olarak saklandı
files_router = APIRouter(prefix="/files", tags=["upload"])

APP_NAME = "facette"
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Yeni yüklemeler Cloudflare R2'ye (S3 uyumlu) gider ve doğrudan R2 CDN'den
# sunulur. Bu, MongoDB'yi base64 görsel yükünden kurtarır ve yüklemeyi hızlandırır.
# R2 yapılandırılmamışsa eski davranışa (MongoDB + disk) düşer.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Görseli Cloudflare R2'ye yükler; R2 kapalıysa MongoDB+disk'e düşer."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları yüklenebilir")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Dosya çok büyük (maks 10MB)")

    ext = file.filename.split(".")[-1].lower() if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"

    # 1) Cloudflare R2 (tercih edilen)
    if r2.is_enabled():
        key = f"uploads/{filename}"
        try:
            public_url = r2.put_object(key, data, file.content_type)
            await db.files.insert_one({
                "id": str(uuid.uuid4()),
                "storage_path": filename,
                "r2_key": key,
                "r2_url": public_url,
                "original_filename": file.filename,
                "content_type": file.content_type,
                "size": len(data),
                "is_deleted": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            return {"success": True, "path": filename, "url": public_url}
        except Exception as e:
            logger.error(f"R2 upload failed, falling back to db/disk: {e}")

    # 2) Fallback: MongoDB (kalıcı) + disk (önbellek)
    try:
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
            f.write(data)
    except Exception as e:
        logger.warning(f"upload disk write failed: {e}")

    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": filename,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    return {
        "success": True,
        "path": filename,
        "url": f"/api/upload/files/{filename}",
    }


async def _serve(path: str, w: int = 0, q: int = 90):
    record = await db.files.find_one({"storage_path": path, "is_deleted": False})

    # 0) R2'ye taşınmış/yüklenmişse → R2 public URL'ine yönlendir (CDN servis eder).
    #    SADECE mutlak http(s) URL'e yönlendir; eski/bozuk relatif r2_url ("/uploads/..")
    #    varsa GÖZ ARDI et ve DB/disk içeriğinden servis et (görsel kaybolmasın).
    _r2 = (record or {}).get("r2_url") or ""
    if _r2 and str(_r2).lower().startswith("http"):
        return RedirectResponse(url=_r2, status_code=302)

    content = None
    ctype = (record or {}).get("content_type", "image/jpeg")
    # 1) MongoDB içeriği (eski yüklemeler için güvenilir kaynak)
    if record and record.get("data_b64"):
        try:
            content = base64.b64decode(record["data_b64"])
        except Exception as e:
            logger.warning(f"serve db decode failed for {path}: {e}")
    # 2) Disk önbelleği (fallback)
    if content is None:
        file_path = os.path.join(UPLOAD_DIR, path)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                content = f.read()
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")

    # İçerik-adresli (uuid) dosyalar değişmez → 1 yıl immutable cache (PageSpeed + tekrar ziyaret)
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}

    # On-the-fly optimize/resize — yalnızca ?w= verildiyse ve raster görselse.
    if w and w > 0 and ctype.startswith("image/") and "svg" not in ctype:
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(content))
            if im.width > w:
                ratio = w / float(im.width)
                im = im.resize((w, max(1, int(im.height * ratio))), Image.LANCZOS)
            if im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            out = io.BytesIO()
            im.save(out, format="WEBP", quality=max(40, min(int(q), 95)), method=4)
            return Response(content=out.getvalue(), media_type="image/webp", headers=headers)
        except Exception as e:
            logger.warning(f"resize failed {path}: {e}")
    return Response(content=content, media_type=ctype, headers=headers)


@router.get("/files/{path:path}")
async def get_file(path: str, w: int = 0, q: int = 90):
    return await _serve(path, w, q)


@files_router.get("/{path:path}")
async def get_file_legacy(path: str, w: int = 0, q: int = 90):
    """Eski kayıtlardaki /api/files/... URL'lerini de servis et (resize destekli)."""
    return await _serve(path, w, q)
