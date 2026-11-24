from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class EntityIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    industry: Literal["Banking", "CreditUnion"]
    jurisdiction: str = Field(min_length=2, max_length=80)

class ObligationIn(BaseModel):
    entity_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=250)
    regulation_reference: str = Field(min_length=2, max_length=150)
    due_date: datetime
