#!/usr/bin/env python3
"""
MIGRATION SCRIPT: Add SEO columns to products
=============================================

Usage:
1. Stop server
2. Run: python backend/database_migrations/004_add_product_seo_fields.py
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime


def print_header(text: str) -> None:
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_success(text: str) -> None:
    print(f"[OK] {text}")


def print_warning(text: str) -> None:
    print(f"[WARN] {text}")


def print_error(text: str) -> None:
    print(f"[ERROR] {text}")


def backup_database(db_path: str) -> str | None:
    if not os.path.exists(db_path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    try:
        shutil.copy2(db_path, backup_path)
        print_success(f"Database backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print_warning(f"Backup failed: {e}")
        return None


def check_table_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table_name,))
    return cursor.fetchone() is not None


def check_column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [col[1] for col in cursor.fetchall()]
    return column_name in columns


def run_migration() -> bool:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.dirname(current_dir)
    db_path = os.path.join(backend_dir, "app.db")

    print_header("MIGRATION: ADD SEO COLUMNS TO PRODUCTS")
    print(f"Database path: {db_path}")

    if not os.path.exists(db_path):
        print_error(f"Database not found: {db_path}")
        return False

    print_header("1. BACKUP DATABASE")
    backup_database(db_path)

    print_header("2. CONNECT DATABASE")
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        print_success("Database connection OK")
    except Exception as e:
        print_error(f"Database connection error: {e}")
        return False

    try:
        print_header("3. CHECK TABLE PRODUCTS")
        if not check_table_exists(cursor, "products"):
            print_error("Table 'products' does not exist!")
            return False
        print_success("Table 'products' exists")

        print_header("4. ADD SEO COLUMNS (IF MISSING)")
        columns = [
            ("meta_title", "VARCHAR(500)"),
            ("meta_description", "VARCHAR(1000)"),
            ("meta_keywords", "VARCHAR(1000)"),
        ]
        added = 0
        for name, col_type in columns:
            if check_column_exists(cursor, "products", name):
                print_warning(f"Column '{name}' exists, skip")
                continue
            print(f"Add column '{name}' ({col_type})...")
            cursor.execute(f"ALTER TABLE products ADD COLUMN {name} {col_type};")
            added += 1

        conn.commit()
        if added == 0:
            print_success("No changes (columns already exist)")
        else:
            print_success(f"Added {added} SEO columns to products")
        return True
    except sqlite3.Error as e:
        print_error(f"SQLite error: {e}")
        conn.rollback()
        return False
    except Exception as e:
        print_error(f"Unknown error: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    if sys.version_info < (3, 8):
        print_error("Python 3.8+ required")
        sys.exit(1)
    success = run_migration()
    sys.exit(0 if success else 1)
