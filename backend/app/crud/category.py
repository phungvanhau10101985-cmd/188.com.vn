"""
backend/app/crud/category.py - Category CRUD operations
Tạo file này nếu chưa có để tránh ImportError
"""

from sqlalchemy.orm import Session
from typing import List, Optional
from app.models.category import Category
from app.models.product import Product

print("✅ Loading category CRUD module...")

def get_category(db: Session, category_id: int) -> Optional[Category]:
    """Lấy category bằng ID"""
    return db.query(Category).filter(Category.id == category_id).first()


def get_category_by_slug(db: Session, slug: str) -> Optional[Category]:
    """Lấy category bằng slug"""
    return db.query(Category).filter(Category.slug == slug).first()


def get_categories(db: Session, skip: int = 0, limit: int = 100, is_active: bool = True) -> List[Category]:
    """Lấy danh sách category"""
    query = db.query(Category)
    if is_active:
        query = query.filter(Category.is_active == True)
    return query.order_by(Category.sort_order).offset(skip).limit(limit).all()


def create_category(db: Session, category_data: dict) -> Category:
    """Tạo category mới"""
    db_category = Category(**category_data)
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


def update_category(db: Session, category_id: int, category_data: dict) -> Optional[Category]:
    """Cập nhật category"""
    db_category = get_category(db, category_id)
    if not db_category:
        return None
    
    for key, value in category_data.items():
        setattr(db_category, key, value)
    
    db.commit()
    db.refresh(db_category)
    return db_category


def delete_category(db: Session, category_id: int) -> bool:
    """Xóa category"""
    db_category = get_category(db, category_id)
    if not db_category:
        return False
    
    db.delete(db_category)
    db.commit()
    return True


def get_category_products(db: Session, category_id: int, skip: int = 0, limit: int = 50) -> List[Product]:
    """Lấy danh sách sản phẩm trong category"""
    return db.query(Product).filter(
        Product.category_id == category_id,
        Product.is_active == True
    ).offset(skip).limit(limit).all()


def get_category_count(db: Session, is_active: bool = True) -> int:
    """Đếm số lượng category"""
    query = db.query(Category)
    if is_active:
        query = query.filter(Category.is_active == True)
    return query.count()


print("✅ Category CRUD module loaded successfully")