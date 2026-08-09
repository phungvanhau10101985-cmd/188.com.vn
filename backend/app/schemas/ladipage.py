# backend/app/schemas/ladipage.py
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

SectionType = Literal["hero", "highlights", "material", "products_grid", "trust_cta", "faq"]
SectionStatus = Literal["pending", "generating", "ready", "error"]
LadipageStatus = Literal["draft", "published"]
LadipageSourceType = Literal["category", "products"]
MaterialImageSource = Literal["ai", "product"]
RegenerateTarget = Literal["all", "text", "image"]


class LadipageSectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    section_type: SectionType
    order_index: int
    status: SectionStatus
    data: Dict[str, Any] = Field(default_factory=dict)
    prompt_used: Optional[str] = None
    error_message: Optional[str] = None
    updated_at: Optional[datetime] = None


class LadipageCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=300)
    source_type: LadipageSourceType
    category_id: Optional[int] = None
    product_ids: Optional[List[int]] = None
    admin_brief: str = Field("", max_length=4000)
    include_material: bool = True
    include_faq: bool = True
    products_limit: int = Field(12, ge=1, le=60)
    material_filter: Optional[str] = Field(
        None,
        max_length=100,
        description="Ladipage danh mục: lọc SP theo chất liệu trong category",
    )
    material_image_source: MaterialImageSource = Field(
        default="product",
        description="Ladipage 1 SP: product = chọn ảnh SP (mặc định); ai = Gemini tạo ảnh chất liệu",
    )


class LadipageUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=300)
    slug: Optional[str] = Field(None, min_length=3, max_length=300)
    status: Optional[LadipageStatus] = None
    admin_brief: Optional[str] = Field(None, max_length=4000)
    meta_title: Optional[str] = Field(None, max_length=500)
    meta_description: Optional[str] = Field(None, max_length=1000)
    products_limit: Optional[int] = Field(None, ge=1, le=60)
    product_ids: Optional[List[int]] = None
    material_filter: Optional[str] = Field(None, max_length=100)


class LadipageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    status: LadipageStatus
    source_type: LadipageSourceType
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    product_ids: List[int] = Field(default_factory=list)
    admin_brief: Optional[str] = None
    include_material: bool
    include_faq: bool
    products_limit: int
    material_filter: Optional[str] = None
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    public_url: Optional[str] = None


class LadipageDetailResponse(LadipageResponse):
    sections: List[LadipageSectionResponse] = Field(default_factory=list)
    resolved_product_ids: List[int] = Field(default_factory=list)
    category_catalog_path: Optional[str] = None
    category_seo_path: Optional[str] = None
    seo_collision_warning: Optional[str] = None


class LadipageListResponse(BaseModel):
    total: int
    items: List[LadipageResponse]


class LadipageAdminStatsResponse(BaseModel):
    kind: str
    active_products_total: Optional[int] = None
    products_with_ladipage: Optional[int] = None
    products_with_published_ladipage: Optional[int] = None
    products_without_ladipage: Optional[int] = None
    category_l3_total: Optional[int] = None
    categories_with_ladipage: Optional[int] = None
    categories_without_ladipage: Optional[int] = None
    products_in_multi_ladipages: Optional[int] = None
    ladipage_pages_total: Optional[int] = None


class SectionRegenerateRequest(BaseModel):
    target: RegenerateTarget = "all"
    custom_prompt: Optional[str] = Field(None, max_length=2000)


class SectionManualUpdateRequest(BaseModel):
    data: Dict[str, Any]


class LadipageSeoResponse(BaseModel):
    meta_title: str
    meta_description: str


class LadipageCategoryMaterialItem(BaseModel):
    material: str
    count: int


class LadipageCategoryMaterialsResponse(BaseModel):
    category_id: int
    items: List[LadipageCategoryMaterialItem] = Field(default_factory=list)


class LadipagePublicResponse(BaseModel):
    id: int
    slug: str
    title: str
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    material_filter: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    category_catalog_path: Optional[str] = None
    category_seo_path: Optional[str] = None
    sections: List[LadipageSectionResponse] = Field(default_factory=list)
    resolved_product_ids: List[int] = Field(default_factory=list)


class LadipageRelatedItem(BaseModel):
    id: int
    slug: str
    title: str
    material_filter: Optional[str] = None
    path: str
    meta_title: Optional[str] = None


class LadipageRelatedResponse(BaseModel):
    items: List[LadipageRelatedItem] = Field(default_factory=list)


class LadipageSitemapItem(BaseModel):
    slug: str
    updated_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


class LadipageSitemapResponse(BaseModel):
    items: List[LadipageSitemapItem] = Field(default_factory=list)


class LadipageProductLinkResponse(BaseModel):
    slug: str
    path: str
