#!/usr/bin/env python3
"""
FIX ALL COLUMNS: Thêm cả image và updated_at vào bảng categories
Chạy: python backend/database_migrations/fix_all_columns.py
"""

import sqlite3
import os
import sys
import shutil
from datetime import datetime

def print_header(text):
    print("\n" + "="*60)
    print(f"📌 {text}")
    print("="*60)

def print_success(text):
    print(f"✅ {text}")

def print_error(text):
    print(f"❌ {text}")

def backup_database(db_path):
    """Tạo backup database"""
    if not os.path.exists(db_path):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_all_fix_{timestamp}"
    
    try:
        shutil.copy2(db_path, backup_path)
        print_success(f"Đã backup database: {backup_path}")
        return backup_path
    except Exception as e:
        print_error(f"Không thể backup database: {e}")
        return None

def check_column_exists(cursor, table_name, column_name):
    """Kiểm tra cột có tồn tại không"""
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns

def fix_categories_table():
    """Sửa bảng categories - thêm cả image và updated_at nếu thiếu"""
    
    # Đường dẫn database
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    db_path = os.path.join(backend_dir, 'app.db')
    
    print_header("FIX BẢNG CATEGORIES - THÊM CỘT THIẾU")
    print(f"🗄️  Database path: {db_path}")
    
    if not os.path.exists(db_path):
        print_error(f"Không tìm thấy database: {db_path}")
        return False
    
    # Backup
    backup_file = backup_database(db_path)
    
    # Kết nối database
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        print_success("Kết nối database thành công")
    except Exception as e:
        print_error(f"Lỗi kết nối database: {e}")
        return False
    
    try:
        # ==================================================
        # 1. KIỂM TRA CẤU TRÚC HIỆN TẠI
        # ==================================================
        print_header("1. KIỂM TRA CẤU TRÚC HIỆN TẠI")
        
        cursor.execute("PRAGMA table_info(categories);")
        columns = cursor.fetchall()
        
        print("📊 CẤU TRÚC BẢNG CATEGORIES:")
        column_names = []
        for col in columns:
            col_id, col_name, col_type, not_null, default_val, is_pk = col
            nullable = "NOT NULL" if not_null else "NULL"
            default_str = f"DEFAULT {default_val}" if default_val else ""
            pk_str = "PRIMARY KEY" if is_pk else ""
            print(f"   [{col_id}] {col_name:20} {col_type:15} {nullable:10} {default_str:15} {pk_str}")
            column_names.append(col_name)
        
        # ==================================================
        # 2. THÊM CÁC CỘT THIẾU
        # ==================================================
        print_header("2. THÊM CÁC CỘT THIẾU")
        
        columns_to_add = []
        
        # Kiểm tra và thêm cột image nếu chưa có
        if "image" not in column_names:
            columns_to_add.append(("image", "VARCHAR(500)"))
        
        # Kiểm tra và thêm cột updated_at nếu chưa có
        if "updated_at" not in column_names:
            columns_to_add.append(("updated_at", "DATETIME"))
        
        if not columns_to_add:
            print_success("Tất cả cột đã có sẵn, không cần thêm")
            return True
        
        print(f"➕ Cần thêm {len(columns_to_add)} cột:")
        for col_name, col_type in columns_to_add:
            print(f"   - {col_name} ({col_type})")
        
        # Thêm từng cột
        for col_name, col_type in columns_to_add:
            try:
                print(f"\n🔧 Đang thêm cột '{col_name}'...")
                cursor.execute(f"ALTER TABLE categories ADD COLUMN {col_name} {col_type};")
                
                # Cập nhật giá trị mặc định nếu cần
                if col_name == "image":
                    cursor.execute("UPDATE categories SET image = '' WHERE image IS NULL;")
                    print_success(f"Đã thêm cột '{col_name}' và cập nhật giá trị mặc định")
                elif col_name == "updated_at":
                    # updated_at có thể để NULL, sẽ tự động cập nhật khi có thay đổi
                    print_success(f"Đã thêm cột '{col_name}' (giá trị mặc định: NULL)")
                
            except sqlite3.Error as e:
                print_error(f"Lỗi khi thêm cột '{col_name}': {e}")
                # Tiếp tục với cột khác
        
        conn.commit()
        
        # ==================================================
        # 3. KIỂM TRA KẾT QUẢ
        # ==================================================
        print_header("3. KIỂM TRA KẾT QUẢ")
        
        cursor.execute("PRAGMA table_info(categories);")
        columns = cursor.fetchall()
        
        print("📊 CẤU TRÚC BẢNG SAU KHI FIX:")
        required_columns = ["id", "name", "slug", "description", "level", "image", 
                          "is_active", "sort_order", "created_at", "updated_at"]
        
        all_ok = True
        for req_col in required_columns:
            found = any(col[1] == req_col for col in columns)
            status = "✅ CÓ" if found else "❌ THIẾU"
            print(f"   {req_col:20} {status}")
            if not found:
                all_ok = False
        
        # Hiển thị dữ liệu mẫu
        print("\n📋 DỮ LIỆU MẪU:")
        try:
            cursor.execute("SELECT id, name, image, updated_at FROM categories LIMIT 3;")
            rows = cursor.fetchall()
            if rows:
                print("   ID  | Tên danh mục          | Image  | Updated At")
                print("   " + "-"*60)
                for row in rows:
                    id, name, image, updated_at = row
                    img_display = f"'{image}'" if image else "NULL"
                    updated_display = f"'{updated_at}'" if updated_at else "NULL"
                    print(f"   {id:4} | {name:22} | {img_display:7} | {updated_display}")
            else:
                print("   (Không có dữ liệu)")
        except Exception as e:
            print(f"   Lỗi khi lấy dữ liệu: {e}")
        
        # ==================================================
        # 4. KIỂM TRA MODEL TƯƠNG THÍCH
        # ==================================================
        print_header("4. KIỂM TRA MODEL TƯƠNG THÍCH")
        
        # Kiểm tra xem model có query được không
        test_queries = [
            "SELECT COUNT(*) FROM categories;",
            "SELECT id, name FROM categories WHERE is_active = 1 LIMIT 1;",
            "SELECT id, name, image FROM categories WHERE image IS NOT NULL OR image = '' LIMIT 1;"
        ]
        
        for i, query in enumerate(test_queries, 1):
            try:
                cursor.execute(query)
                result = cursor.fetchone()
                print_success(f"Test {i}: Query thành công - {query[:50]}...")
            except Exception as e:
                print_error(f"Test {i}: Lỗi query - {e}")
        
        if all_ok:
            print_success("\n🎉 FIX HOÀN TẤT! Bảng categories đã đầy đủ cột")
        else:
            print_error("\n⚠️  VẪN CÒN THIẾU CỘT, cần kiểm tra lại")
        
        return all_ok
        
    except Exception as e:
        print_error(f"Lỗi tổng quát: {e}")
        return False
    finally:
        conn.close()

def main():
    """Hàm chính"""
    print_header("FIX DATABASE - THÊM CỘT THIẾU CHO CATEGORIES")
    
    # Chạy fix
    success = fix_categories_table()
    
    if success:
        print_header("HƯỚNG DẪN TIẾP THEO")
        print("""
        ✅ ĐÃ FIX XONG! Tiếp theo:
        
        1. KHỞI ĐỘNG LẠI SERVER:
           cd backend
           python -m uvicorn main:app --reload --port 8000
        
        2. TEST ENDPOINT:
           curl http://localhost:8000/api/v1/categories/
           Hoặc mở: http://localhost:8000/api/v1/categories/
        
        3. KIỂM TRA SWAGGER:
           http://localhost:8000/docs
        
        4. NẾU VẪN LỖI:
           - Kiểm tra log server
           - Kiểm tra lại model và database
        """)
        return 0
    else:
        print_header("FIX THẤT BẠI")
        print("""
        ❌ FIX KHÔNG THÀNH CÔNG! Cần:
        
        1. RESTORE TỪ BACKUP:
           cp backend/app.db.backup_all_fix_* backend/app.db
        
        2. KIỂM TRA THỦ CÔNG:
           sqlite3 backend/app.db
           .tables
           PRAGMA table_info(categories);
        
        3. LIÊN HỆ HỖ TRỢ:
           Gửi log lỗi chi tiết
        """)
        return 1

if __name__ == "__main__":
    sys.exit(main())