"""
Documentation download endpoints.
Serves project documentation files (BUILD_SPEC, SYSTEM_DOCS) as downloadable
files via authenticated admin endpoints.
"""
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["Docs"])

DOCS_DIR = Path("/app/docs")

AVAILABLE_DOCS = {
    "build-spec": {
        "filename": "BUILD_SPEC.md",
        "download_name": "FACETTE_Build_Specification.md",
        "title": "Yazılımcıya Verilecek Build Specification",
    },
    "system-docs": {
        "filename": "SYSTEM_DOCS.md",
        "download_name": "FACETTE_System_Documentation.md",
        "title": "Mevcut Sistemin Dokümantasyonu",
    },
}


@router.get("/docs")
async def list_docs():
    """Mevcut dokümanları listele."""
    return {
        "docs": [
            {"id": k, "title": v["title"], "filename": v["download_name"],
             "download_url": f"/api/docs/{k}/download"}
            for k, v in AVAILABLE_DOCS.items()
        ]
    }


@router.get("/docs/{doc_id}/download")
async def download_doc(doc_id: str):
    """Markdown dokümantasyon dosyasını indir."""
    meta = AVAILABLE_DOCS.get(doc_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Doküman bulunamadı")
    path = DOCS_DIR / meta["filename"]
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dosya bulunamadı")
    return FileResponse(
        path=str(path),
        media_type="text/markdown",
        filename=meta["download_name"],
    )
