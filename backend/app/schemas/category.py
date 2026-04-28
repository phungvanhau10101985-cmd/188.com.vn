from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = 0

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class CategoryInDBBase(CategoryBase):
    id: int
    slug: str
    level: int
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    image: Optional[str] = None
    is_active: bool
    sort_order: int
    created_at: Optional[datetime] = None  # DB có thể trả None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class Category(CategoryInDBBase):
    pass

class CategoryWithProducts(Category):
    products_count: int = 0
