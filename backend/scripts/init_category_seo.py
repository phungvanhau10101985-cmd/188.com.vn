# backend/scripts/init_category_seo.py - Script khởi tạo bảng và scan danh mục SEO
"""
Script này:
1. Tạo bảng category_seo_mappings và category_seo_dictionary nếu chưa có
2. Scan tất cả danh mục hiện có
3. Phát hiện và tạo mapping cho danh mục trùng ý nghĩa
"""

import sys
import os

# Thêm path để import được app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from app.db.session import SessionLocal, engine
from app.db.base import Base
from app.models.category_seo import CategorySeoMapping, CategorySeoDictionary
from app.services.category_seo_analyzer import scan_and_create_mappings, DEFAULT_SYNONYMS


def create_tables():
    """Tạo bảng nếu chưa có."""
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    
    tables_to_create = []
    
    if "category_seo_mappings" not in existing_tables:
        tables_to_create.append("category_seo_mappings")
    
    if "category_seo_dictionary" not in existing_tables:
        tables_to_create.append("category_seo_dictionary")
    
    if tables_to_create:
        print(f"📦 Tạo bảng: {', '.join(tables_to_create)}")
        Base.metadata.create_all(bind=engine)
        print("✅ Đã tạo bảng thành công")
    else:
        print("ℹ️  Bảng đã tồn tại")


def init_dictionary(db):
    """Khởi tạo từ điển đồng nghĩa mặc định."""
    count = db.query(CategorySeoDictionary).count()
    if count > 0:
        print(f"ℹ️  Từ điển đã có {count} entries")
        return
    
    print("📚 Khởi tạo từ điển đồng nghĩa...")
    
    for term, synonyms in DEFAULT_SYNONYMS.items():
        # Chọn canonical là từ dài nhất
        all_terms = [term] + synonyms
        canonical = max(all_terms, key=len)
        
        entry = CategorySeoDictionary(
            term=term.lower(),
            synonyms=", ".join(synonyms),
            canonical_term=canonical,
            term_type="category",
            is_active=True
        )
        db.add(entry)
    
    db.commit()
    print(f"✅ Đã thêm {len(DEFAULT_SYNONYMS)} entries vào từ điển")


def main():
    print("=" * 60)
    print("🔧 KHỞI TẠO CATEGORY SEO SYSTEM")
    print("=" * 60)
    
    # 1. Tạo bảng
    print("\n[1/3] Tạo bảng database...")
    create_tables()
    
    # 2. Khởi tạo từ điển
    print("\n[2/3] Khởi tạo từ điển đồng nghĩa...")
    db = SessionLocal()
    try:
        init_dictionary(db)
    finally:
        db.close()
    
    # 3. Scan danh mục
    print("\n[3/3] Scan danh mục và phát hiện trùng lặp...")
    db = SessionLocal()
    try:
        result = scan_and_create_mappings(db, force_rescan=False)
        
        print("\n" + "=" * 60)
        print("📊 KẾT QUẢ SCAN")
        print("=" * 60)
        print(f"   Tổng danh mục: {result['total_categories']}")
        print(f"   Mappings mới: {result['new_mappings']}")
        print(f"   Trùng lặp phát hiện: {result['duplicates_found']}")
        
        if result['duplicates_found'] > 0:
            print("\n⚠️  DANH MỤC TRÙNG LẶP CẦN REVIEW:")
            for detail in result['details']:
                if detail.get('is_duplicate'):
                    print(f"   - {detail['category']} → {detail['canonical']}")
                    print(f"     Action: {detail['action']}, Confidence: {detail['confidence']}")
        
        print("\n" + "=" * 60)
        print("✅ HOÀN THÀNH!")
        print("=" * 60)
        print("\nBước tiếp theo:")
        print("1. Gọi API /api/v1/category-seo/mappings/pending để xem danh sách cần review")
        print("2. Approve/Reject từng mapping qua API hoặc trang admin")
        print("3. Sau khi approve, redirect sẽ tự động hoạt động")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()
