#!/usr/bin/env python3
"""
MIGRATION SCRIPT: Thêm cột image vào bảng categories
====================================================

Cách sử dụng:
1. Chắc chắn server đã dừng (Ctrl+C nếu đang chạy)
2. Chạy: python backend/database_migrations/run_migration.py
3. Kiểm tra kết quả
4. Khởi động lại server

Lưu ý:
- Backup database tự động trước khi migration
- Kiểm tra an toàn trước khi thay đổi
- Log chi tiết quá trình thực thi
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime

def print_header(text):
    """In tiêu đề đẹp"""
    print("\n" + "="*60)
    print(f"📌 {text}")
    print("="*60)

def print_success(text):
    """In thông báo thành công"""
    print(f"✅ {text}")

def print_warning(text):
    """In cảnh báo"""
    print(f"⚠️  {text}")

def print_error(text):
    """In lỗi"""
    print(f"❌ {text}")

def backup_database(db_path):
    """Tạo backup database trước khi migration"""
    if not os.path.exists(db_path):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    
    try:
        shutil.copy2(db_path, backup_path)
        print_success(f"Đã backup database: {backup_path}")
        return backup_path
    except Exception as e:
        print_warning(f"Không thể backup database: {e}")
        return None

def check_table_exists(cursor, table_name):
    """Kiểm tra bảng có tồn tại không"""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", 
        (table_name,)
    )
    return cursor.fetchone() is not None

def check_column_exists(cursor, table_name, column_name):
    """Kiểm tra cột có tồn tại không"""
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def get_table_info(cursor, table_name):
    """Lấy thông tin cấu trúc bảng"""
    cursor.execute(f"PRAGMA table_info({table_name});")
    return cursor.fetchall()

def run_migration():
    """Thực thi migration chính"""
    
    # ==================================================
    # 1. THIẾT LẬP ĐƯỜNG DẪN
    # ==================================================
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    db_path = os.path.join(backend_dir, 'app.db')
    
    print_header("MIGRATION: THÊM CỘT IMAGE VÀO BẢNG CATEGORIES")
    print(f"📁 Thư mục hiện tại: {current_dir}")
    print(f"🗄️  Database path: {db_path}")
    
    if not os.path.exists(db_path):
        print_error(f"Không tìm thấy database: {db_path}")
        print("Vui lòng kiểm tra đường dẫn database")
        return False
    
    # ==================================================
    # 2. BACKUP DATABASE
    # ==================================================
    print_header("1. BACKUP DATABASE")
    backup_file = backup_database(db_path)
    
    # ==================================================
    # 3. KẾT NỐI DATABASE
    # ==================================================
    print_header("2. KẾT NỐI DATABASE")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")  # Bật foreign keys
        cursor = conn.cursor()
        print_success("Kết nối database thành công")
    except Exception as e:
        print_error(f"Lỗi kết nối database: {e}")
        return False
    
    try:
        # ==================================================
        # 4. KIỂM TRA BẢNG CATEGORIES
        # ==================================================
        print_header("3. KIỂM TRA BẢNG CATEGORIES")
        
        if not check_table_exists(cursor, "categories"):
            print_error("Bảng 'categories' không tồn tại trong database!")
            print("Có thể cần khởi tạo database trước:")
            print("  cd backend && python -c \"from app.db.init_db import init_db; init_db()\"")
            return False
        
        print_success("Bảng 'categories' tồn tại")
        
        # Hiển thị cấu trúc hiện tại
        print("\n📊 CẤU TRÚC BẢNG HIỆN TẠI:")
        columns = get_table_info(cursor, "categories")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            nullable = "NOT NULL" if not_null else "NULL"
            default_str = f"DEFAULT {default_val}" if default_val else ""
            pk_str = "PRIMARY KEY" if is_pk else ""
            print(f"   [{col_id}] {col_name:20} {col_type:15} {nullable:10} {default_str:15} {pk_str}")
        
        # ==================================================
        # 5. KIỂM TRA CỘT IMAGE ĐÃ CÓ CHƯA
        # ==================================================
        print_header("4. KIỂM TRA CỘT IMAGE")
        
        if check_column_exists(cursor, "categories", "image"):
            print_success("Cột 'image' đã tồn tại, không cần migration")
            print("Quá trình migration hoàn tất (không có thay đổi)")
            
            # Hiển thị sample data
            print("\n📋 DỮ LIỆU MẪU:")
            cursor.execute("SELECT id, name, slug, image FROM categories LIMIT 5;")
            rows = cursor.fetchall()
            for row in rows:
                id, name, slug, image = row
                image_display = f"'{image}'" if image else "NULL"
                print(f"   ID:{id:3} | {name:30} | {slug:20} | Image: {image_display}")
            
            conn.close()
            return True
        
        print_warning("Cột 'image' chưa tồn tại, bắt đầu migration...")
        
        # ==================================================
        # 6. THỰC HIỆN MIGRATION
        # ==================================================
        print_header("5. THỰC HIỆN MIGRATION")
        
        # Thêm cột image
        print("➕ Thêm cột 'image' (VARCHAR 500)...")
        cursor.execute("ALTER TABLE categories ADD COLUMN image VARCHAR(500);")
        
        # Cập nhật giá trị mặc định
        print("🔄 Cập nhật giá trị mặc định...")
        cursor.execute("UPDATE categories SET image = '' WHERE image IS NULL;")
        
        # Commit thay đổi
        conn.commit()
        print_success("Migration thành công!")
        
        # ==================================================
        # 7. KIỂM TRA KẾT QUẢ
        # ==================================================
        print_header("6. KIỂM TRA KẾT QUẢ")
        
        # Hiển thị cấu trúc mới
        print("\n📊 CẤU TRÚC BẢNG SAU MIGRATION:")
        columns = get_table_info(cursor, "categories")
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            nullable = "NOT NULL" if not_null else "NULL"
            default_str = f"DEFAULT {default_val}" if default_val else ""
            pk_str = "PRIMARY KEY" if is_pk else ""
            print(f"   [{col_id}] {col_name:20} {col_type:15} {nullable:10} {default_str:15} {pk_str}")
        
        # Hiển thị số lượng bản ghi
        cursor.execute("SELECT COUNT(*) as total FROM categories;")
        total = cursor.fetchone()[0]
        print(f"\n📈 Tổng số danh mục: {total}")
        
        # Hiển thị sample data
        print("\n📋 DỮ LIỆU MẪU (5 bản ghi đầu):")
        cursor.execute("SELECT id, name, slug, image FROM categories LIMIT 5;")
        rows = cursor.fetchall()
        
        if rows:
            print("   ID  | Tên danh mục                  | Slug                | Image")
            print("   " + "-"*70)
            for row in rows:
                id, name, slug, image = row
                image_display = f"'{image}'" if image else "NULL"
                print(f"   {id:4} | {name:30} | {slug:20} | {image_display}")
        else:
            print("   (Không có dữ liệu trong bảng categories)")
        
        # ==================================================
        # 8. KIỂM TRA TÍNH TƯƠNG THÍCH
        # ==================================================
        print_header("7. KIỂM TRA TÍNH TƯƠNG THÍCH")
        
        # Kiểm tra xem model có thể query được không
        try:
            cursor.execute("SELECT id, name FROM categories WHERE image IS NOT NULL OR image = '' LIMIT 1;")
            test_result = cursor.fetchone()
            if test_result:
                print_success("Query test thành công - cột 'image' hoạt động tốt")
            else:
                print_warning("Không có dữ liệu test, nhưng cấu trúc đã OK")
        except Exception as e:
            print_error(f"Lỗi khi test query: {e}")
        
        print_success("Migration hoàn tất thành công! ✅")
        
        # ==================================================
        # 9. HƯỚNG DẪN TIẾP THEO
        # ==================================================
        print_header("8. HƯỚNG DẪN TIẾP THEO")
        print("""
        ĐÃ HOÀN THÀNH MIGRATION! Tiếp theo:
        
        1. KHỞI ĐỘNG LẠI SERVER:
           cd backend
           python -m uvicorn main:app --reload --port 8000
        
        2. KIỂM TRA ENDPOINT:
           Mở trình duyệt: http://localhost:8000/api/v1/categories/
           Hoặc dùng curl: curl http://localhost:8000/api/v1/categories/
        
        3. KIỂM TRA FRONTEND:
           Truy cập frontend và kiểm tra danh mục sản phẩm
        
        4. NẾU CÓ LỖI:
           - Kiểm tra log server
           - Kiểm tra lại migration
           - Restore từ backup nếu cần
        """)
        
        return True
        
    except sqlite3.Error as e:
        print_error(f"Lỗi SQLite: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print_error(f"Lỗi không xác định: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    # Kiểm tra Python version
    if sys.version_info < (3, 7):
        print_error("Yêu cầu Python 3.7 hoặc cao hơn")
        sys.exit(1)
    
    # Chạy migration
    success = run_migration()
    
    # Trả về exit code
    if success:
        print("\n" + "="*60)
        print("🎉 MIGRATION HOÀN TẤT - SẴN SÀNG KHỞI ĐỘNG SERVER")
        print("="*60)
        sys.exit(0)
    else:
        print("\n" + "="*60)
        print("💥 MIGRATION THẤT BẠI - KIỂM TRA LỖI VÀ THỬ LẠI")
        print("="*60)
        sys.exit(1)