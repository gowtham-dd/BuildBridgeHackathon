"""
POST /api/document-analyze
Accepts multipart/form-data with a real file upload — no base64 needed.
Testing in Postman: Body → form-data → file field named "file" + header x-api-key.
"""

import logging
import base64
import os
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Header, HTTPException
from models.response import AnalyzeResponse
from services.extractor import extract_text
from services.ai_pipeline import run_analysis

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Supported extensions ───────────────────────────────────────────────────────
EXTENSION_MAP = {
    "pdf":  "pdf",
    "docx": "docx",
    "doc":  "docx",
    "png":  "image",
    "jpg":  "image",
    "jpeg": "image",
    "webp": "image",
    "tiff": "image",
    "tif":  "image",
    "bmp":  "image",
    "gif":  "image",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _verify_key(x_api_key: Optional[str]):
    valid = os.getenv("API_KEY", "")
    if not valid:
        logger.warning("API_KEY env var not set – accepting any key for dev")
        return
    if x_api_key != valid:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _detect_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    file_type = EXTENSION_MAP.get(ext)
    if not file_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext}'. Allowed: pdf, docx, doc, png, jpg, jpeg, webp, tiff, bmp, gif",
        )
    return file_type


@router.post(
    "/document-analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a PDF, DOCX, or image document",
    description=(
        "Upload a file directly as **multipart/form-data** — no base64 encoding needed.\n\n"
        "**Postman setup:**\n"
        "1. Method: `POST`\n"
        "2. Body: `form-data`\n"
        "3. Add key `file` → change type to **File** → select your document\n"
        "4. Add header `x-api-key` → your API key value\n\n"
        "Supported formats: `pdf`, `docx`, `doc`, `png`, `jpg`, `jpeg`, `webp`, `tiff`, `bmp`, `gif`"
    ),
    tags=["Analysis"],
)
async def document_analyze(
    file: UploadFile = File(..., description="Document to analyze (pdf / docx / image)"),
    x_api_key: Optional[str] = Header(default=None),
):
    _verify_key(x_api_key)

    # ── Read & validate ────────────────────────────────────────────────────────
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(file_bytes) > MAX_FILE_SIZE:
        mb = len(file_bytes) // 1024 // 1024
        raise HTTPException(status_code=413, detail=f"File too large ({mb} MB). Max: 20 MB.")

    filename  = file.filename or "upload"
    file_type = _detect_file_type(filename)

    logger.info(f"Upload received | file={filename} | type={file_type} | size={len(file_bytes)} bytes")

    # ── base64 encode internally for extractor ─────────────────────────────────
    file_base64 = base64.b64encode(file_bytes).decode("utf-8")

    # ── Step 1: Extract text ───────────────────────────────────────────────────
    raw_text = extract_text(filename, file_type, file_base64)

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the document.")

    # ── Step 2: AI pipeline ────────────────────────────────────────────────────
    result = await run_analysis(raw_text, filename)

    return result
