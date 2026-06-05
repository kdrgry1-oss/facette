from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from datetime import datetime, timezone
import base64
import uuid
import os

from .deps import db, get_current_user, logger

router = APIRouter(prefix="/upload", tags=["upload"])
# Geriye dönük uyumluluk: bazı kayıtlarda görsel URL'si /api/files/... olarak saklandı
files_router = APIRouter(prefix="/files", tags=["upload"])

APP_NAME = "facette"
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Production'da pod diski kalıcı değil ve birden fazla replica var; bu yüzden
# görsel içeriği MongoDB'de (paylaşımlı + kalıcı) saklanır, disk yalnızca hız önbelleği.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Görseli MongoDB'ye (kalıcı) + diske (önbellek) yükle."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları yüklenebilir")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Dosya çok büyük (maks 10MB)")

    ext = file.filename.split(".")[-1].lower() if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"

    # Diske yaz (best-effort önbellek)
    try:
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
            f.write(data)
    except Exception as e:
        logger.warning(f"upload disk write failed: {e}")

    # MongoDB'ye kalıcı sakla (replica'lar arası erişilebilir)
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


async def _serve(path: str) -> Response:
    record = await db.files.find_one({"storage_path": path, "is_deleted": False})
    # 1) Önce MongoDB içeriği (production'da güvenilir kaynak)
    if record and record.get("data_b64"):
        try:
            content = base64.b64decode(record["data_b64"])
            return Response(content=content, media_type=record.get("content_type", "image/jpeg"))
        except Exception as e:
            logger.warning(f"serve db decode failed for {path}: {e}")
    # 2) Disk önbelleği (fallback)
    file_path = os.path.join(UPLOAD_DIR, path)
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            content = f.read()
        return Response(content=content, media_type=(record or {}).get("content_type", "image/jpeg"))
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/files/{path:path}")
async def get_file(path: str):
    return await _serve(path)


@files_router.get("/{path:path}")
async def get_file_legacy(path: str):
    """Eski kayıtlardaki /api/files/... URL'lerini de servis et."""
    return await _serve(path)
