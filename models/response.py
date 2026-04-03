"""Response schema for /api/document-analyze"""

from pydantic import BaseModel
from typing import Literal, List
from models.entities import EntitiesModel


class AnalyzeResponse(BaseModel):
    status: Literal["success", "error"] = "success"
    fileName: str
    document_type: str = ""          # e.g. Invoice, Resume, Contract, Report
    summary: str
    key_points: List[str] = []       # Bullet-point key findings
    entities: EntitiesModel
    sentiment: Literal["positive", "neutral", "negative"]
    language: str = "English"        # Detected language of the document