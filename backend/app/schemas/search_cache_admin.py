"""Schema API admin: thống kê từ khóa tìm kiếm & quản lý cache GET /products."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SearchKeywordStatItem(BaseModel):
    keyword: str
    search_count: int = Field(..., description="Số lần ghi nhận tìm kiếm (mỗi request có thể ghi 1 dòng log)")
    avg_result_count: float = Field(..., description="Trung bình số SP trả về trong các lần log đó")
    ai_processed_count: int = Field(
        0, description="Số lần log có bước AI (sửa query / gợi ý danh mục)"
    )


class SearchKeywordStatsResponse(BaseModel):
    days: int
    total_distinct_keywords: int
    items: List[SearchKeywordStatItem]


class ProductSearchCacheRowItem(BaseModel):
    cache_key: str
    expires_at: datetime
    created_at: Optional[datetime] = None
    response_size_bytes: int
    hint_query: Optional[str] = Field(
        None, description="Gợi ý từ JSON cache (normalized_query / applied_query) nếu có"
    )


class ProductSearchCacheListResponse(BaseModel):
    total_rows: int
    active_rows: int
    expired_rows: int
    items: List[ProductSearchCacheRowItem]


class ClearProductSearchCacheResponse(BaseModel):
    deleted: int
    scope: str
