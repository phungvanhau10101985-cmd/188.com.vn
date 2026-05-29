"""Schema API admin: quản lý cache bộ lọc listing."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ListingFacetCacheRowItem(BaseModel):
    id: int
    scope_type: str
    scope_key: str
    display_label: Optional[str] = None
    product_count: int = 0
    sizes_count: int = 0
    colors_count: int = 0
    style_tags_count: int = 0
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    is_manual: bool = False
    is_enabled: bool = True
    is_stale: bool = False
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ListingFacetCacheListResponse(BaseModel):
    total_rows: int
    counts_by_type: Dict[str, int]
    items: List[ListingFacetCacheRowItem]


class ListingFacetCacheRebuildRequest(BaseModel):
    scope: str = Field(
        "all",
        description='category | search | seo_cluster | all | hoặc "single" kèm scope_type + scope_key',
    )
    scope_type: Optional[str] = None
    scope_key: Optional[str] = None


class ListingFacetCacheRebuildResponse(BaseModel):
    rebuilt: int
    scope: str
    message: str


class ListingFacetCachePinSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=500)


class ListingFacetCacheToggleRequest(BaseModel):
    is_enabled: bool


class ListingFacetCacheClearResponse(BaseModel):
    deleted: int
    scope_type: Optional[str] = None


class ListingFacetCacheDetailResponse(BaseModel):
    id: int
    scope_type: str
    scope_key: str
    display_label: Optional[str] = None
    product_count: int
    facets: Dict[str, Any]
    is_manual: bool
    is_enabled: bool
    is_stale: bool
    updated_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
