"""Response schema for /api/document-analyze"""

from pydantic import BaseModel
from typing import Literal
from models.entities import EntitiesModel


class AnalyzeResponse(BaseModel):
    status: Literal["success", "error"] = "success"
    fileName: str
    summary: str
    entities: EntitiesModel
    sentiment: Literal["positive", "neutral", "negative"]
