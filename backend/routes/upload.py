from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import Response
from datetime import datetime, timezone
import uuid
import os

from .deps import db, get_current_user, logger

router = APIRouter(prefix="/upload", tags=["upload"])

APP_NAME = "facette"
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/image")
async def upload_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Upload image to local storage"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Sadece resim dosyaları yüklenebilir")
    
    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, filename)
    data = await file.read()
    
    with open(file_path, "wb") as f:
        f.write(data)
    
    # Store reference in DB
    await db.files.insert_one({
        "id": str(uuid.uuid4()),
        "storage_path": filename,
        "original_filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "success": True,
        "path": filename,
        "url": f"/api/upload/files/{filename}"
    }

@router.get("/files/{path:path}")
async def get_file(path: str):
    """Serve files from local storage"""
    file_path = os.path.join(UPLOAD_DIR, path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    record = await db.files.find_one({"storage_path": path, "is_deleted": False})
    
    with open(file_path, "rb") as f:
        data = f.read()
    
    return Response(content=data, media_type=record.get("content_type", "image/jpeg") if record else "image/jpeg")
