from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class SearchMappingResponse(BaseModel):
    id: int
    keyword_input: str
    keyword_target: str
    type: str
    hit_count: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SearchMappingListResponse(BaseModel):
    items: List[SearchMappingResponse]
    total: int
    page: int
    size: int
    total_pages: int


class SearchMappingCreateRequest(BaseModel):
    keyword_input: str
    keyword_target: str
    type: str
