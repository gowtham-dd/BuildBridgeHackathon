"""Entities sub-schema"""

from pydantic import BaseModel
from typing import List


class EntitiesModel(BaseModel):
    names: List[str] = []
    dates: List[str] = []
    organizations: List[str] = []
    amounts: List[str] = []
    locations: List[str] = []
