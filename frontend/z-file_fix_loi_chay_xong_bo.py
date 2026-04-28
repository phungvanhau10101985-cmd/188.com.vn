# backend/force_recreate_db.py
import os
import sys
import sqlite3

print("=" * 60)
print("🔄 FORCE RECREATE DATABASE - CẤP TỐC")
print("=" * 60)

# 1. Xác định đường dẫn database
db_path = "app.db"
db_backup_path = "app.db.backup.force"

print(f"📁 Database hiện tại: {db_path}")
print(f"📁 Backup sẽ tạo tại: {db_backup_path}")

# 2. Backup database cũ (nếu có)
if os.path.exists(db_path):
    import shutil
    shutil.copy2(db_path, db_backup_path)
    print(f"✅ Đã backup database cũ: {os.path.getsize(db_backup_path)} bytes")
else:
    print("ℹ️  Không có database cũ để backup")

# 3. Xóa database cũ
if os.path.exists(db_path):
    os.remove(db_path)
    print("🗑️  Đã xóa database cũ")

# 4. Tạo database mới bằng SQLAlchemy
print("\n🔄 Đang tạo database mới với schema đầy đủ...")

# Thêm path để import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.db.session import engine
    from app.db.base import Base
    
    # Tạo tất cả bảng
    Base.metadata.create_all(bind=engine)
    print("✅ Đã tạo tất cả bảng với schema mới")
    
    # Kiểm tra cột sub_subcategory
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Lấy thông tin cột của bảng products
    cursor.execute("PRAGMA table_info(products)")
    columns = cursor.fetchall()
    
    print(f"\n🔍 KIỂM TRA CẤU TRÚC BẢNG 'products':")
    column_names = [col[1] for col in columns]
    
    print(f"   Tổng số cột: {len(columns)}")
    
    # Kiểm tra cột quan trọng
    important_columns = ['sub_subcategory', 'category', 'subcategory', 'name', 'price']
    for col in important_columns:
        if col in column_names:
            print(f"   ✅ '{col}': CÓ")
        else:
            print(f"   ❌ '{col}': KHÔNG CÓ")
    
    conn.close()
    
except Exception as e:
    print(f"❌ Lỗi khi tạo database: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("🎉 HOÀN THÀNH!")
print("=" * 60)
print("📋 HƯỚNG DẪN TIẾP THEO:")
print("   1. Khởi động lại backend: python main.py")
print("   2. Kiểm tra Swagger UI: http://localhost:8000/docs")
print("   3. Test endpoint: GET /api/v1/products/")
print("\n⚠️  LƯU Ý: Tất cả dữ liệu cũ đã bị xóa")
print("   Database backup được lưu tại: app.db.backup.force")
print("=" * 60)