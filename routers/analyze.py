"""
POST /api/document-analyze
Handles authentication, dispatches extraction, then calls AI pipeline.
"""

import logging
from fastapi import APIRouter, Header, HTTPException
from models.request import AnalyzeRequest
from models.response import AnalyzeResponse
from services.extractor import extract_text
from services.ai_pipeline import run_analysis

logger = logging.getLogger(__name__)
router = APIRouter()


def _verify_key(x_api_key: str | None):
    import os
    valid = os.getenv("API_KEY", "")
    if not valid:
        logger.warning("API_KEY env var not set – accepting any key for dev")
        return
    if x_api_key != valid:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


@router.post(
    "/document-analyze",
    response_model=AnalyzeResponse,
    summary="Analyze a PDF, DOCX, or image document",
    tags=["Analysis"],
)
async def document_analyze(
    body: AnalyzeRequest,
    x_api_key: str | None = Header(default=None),
):
    _verify_key(x_api_key)

    logger.info(f"Received analysis request | file={body.fileName} | type={body.fileType}")

    # Step 1 – extract raw text
    raw_text = extract_text(body.fileName, body.fileType, body.fileBase64)

    if not raw_text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the document.")

    # Step 2 – AI pipeline (summary + entities + sentiment via Groq + Monte Carlo)
    result = await run_analysis(raw_text, body.fileName)

    return result
