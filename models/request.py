"""Request schema for /api/document-analyze"""

from pydantic import BaseModel, Field
from typing import Literal


class AnalyzeRequest(BaseModel):
    fileName: str = Field(..., description="Original filename with extension")
    fileType: Literal["pdf", "docx", "image"] = Field(
        ..., description="Document type: pdf | docx | image"
    )
    fileBase64: str = Field(..., description="Base64-encoded file content")
