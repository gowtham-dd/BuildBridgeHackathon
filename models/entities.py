"""Entities sub-schema — extended with 10 entity categories"""

from pydantic import BaseModel
from typing import List


class EntitiesModel(BaseModel):
    names: List[str] = []            # Person names
    organizations: List[str] = []    # Companies, institutions
    locations: List[str] = []        # Cities, countries, addresses
    dates: List[str] = []            # Dates, time references
    amounts: List[str] = []          # Monetary values
    emails: List[str] = []           # Email addresses
    phones: List[str] = []           # Phone numbers
    urls: List[str] = []             # Website / URL references
    keywords: List[str] = []         # Key topics / technical terms
    document_type: str = ""          # e.g. "Invoice", "Resume", "Contract"