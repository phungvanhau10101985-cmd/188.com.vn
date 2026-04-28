# backend/app/db/migrations.py
"""
Professional migration system for database schema updates - PostgreSQL / SQLite
"""

import logging
from typing import List, Dict, Any
from sqlalchemy import inspect, text
from app.db.base import Base
from app.models.product import Product
from app.models.order import Order, OrderItem, OrderStatus, DepositType, PaymentMethod, PaymentStatus
from app.models.product_question import ProductQuestion, ProductQuestionUsefulVote
from app.models.product_review import ProductReview, ProductReviewUsefulVote
from app.models.search_mapping import SearchMapping
from app.models.search_log import SearchLog
from app.models.push_subscription import UserPushSubscription
from app.models.email_login_challenge import EmailLoginChallenge
from app.models.email_trusted_device import EmailTrustedDevice
from app.models.bank_account import BankAccount
from app.models.site_embed_code import SiteEmbedCode
from app.models.guest_behavior import GuestProductView, GuestFavorite, GuestSearchHistory
from app.db.session import engine
from app.core.config import settings
import os

logger = logging.getLogger(__name__)
IS_POSTGRESQL = getattr(settings, "IS_POSTGRESQL", False)


class MigrationManager:
    """Manager for database migrations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "..", "..", "app.db")
        
    def check_database_consistency(self) -> Dict[str, Any]:
        """Kiểm tra sự nhất quán giữa model và database"""
        inspector = inspect(engine)
        
        try:
            # Lấy cột hiện có trong database
            existing_columns = inspector.get_columns('products')
            db_columns = [col['name'] for col in existing_columns]
            
            # Lấy cột từ model Product
            model_columns = [col.name for col in Product.__table__.columns]
            
            # Tìm sự khác biệt
            missing_in_db = [col for col in model_columns if col not in db_columns]
            missing_in_model = [col for col in db_columns if col not in model_columns]
            
            return {
                "database_columns": db_columns,
                "model_columns": model_columns,
                "missing_in_database": missing_in_db,
                "missing_in_model": missing_in_model,
                "is_consistent": len(missing_in_db) == 0 and len(missing_in_model) == 0
            }
        except Exception as e:
            logger.error(f"Error checking database consistency: {str(e)}")
            return {"error": str(e)}

    def migrate_users_optional_columns_nullable(self) -> bool:
        """
        PostgreSQL: bỏ NOT NULL ở các cột tùy chọn trên `users` (schema cũ) để khớp model
        (Gmail, email-OTP: phone, email, DOB, … có thể NULL khi tạo user).
        """
        optional = (
            "phone",
            "email",
            "full_name",
            "date_of_birth",
            "gender",
            "address",
            "avatar",
            "last_login",
        )
        try:
            inspector = inspect(engine)
            if "users" not in inspector.get_table_names():
                return True
            if not IS_POSTGRESQL:
                return True
            with engine.connect() as conn:
                for col in optional:
                    r = conn.execute(
                        text(
                            """
                            SELECT is_nullable
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'users'
                              AND column_name = :cname
                            """
                        ),
                        {"cname": col},
                    )
                    row = r.fetchone()
                    if not row:
                        continue
                    if (row[0] or "").upper() == "YES":
                        continue
                    conn.execute(
                        text(f'ALTER TABLE users ALTER COLUMN "{col}" DROP NOT NULL')
                    )
                    conn.commit()
                    logger.info("✅ users.%s: dropped NOT NULL", col)
            return True
        except Exception as e:
            logger.error("❌ migrate_users_optional_columns_nullable: %s", e)
            return False

    def migrate_add_sub_subcategory(self) -> bool:
        """Migration để thêm cột sub_subcategory"""
        try:
            # Kiểm tra cột đã tồn tại chưa
            inspector = inspect(engine)
            existing_columns = inspector.get_columns('products')
            column_names = [col['name'] for col in existing_columns]
            
            if 'sub_subcategory' in column_names:
                logger.info("✅ Column sub_subcategory already exists")
                return True
            
            # Thực hiện migration
            with engine.connect() as conn:
                # Thêm cột mới
                conn.execute(text("ALTER TABLE products ADD COLUMN sub_subcategory TEXT"))
                conn.commit()
                
                # Đặt giá trị mặc định
                conn.execute(text("UPDATE products SET sub_subcategory = '' WHERE sub_subcategory IS NULL"))
                conn.commit()
                
                logger.info("✅ Successfully added sub_subcategory column")
                return True
                
        except Exception as e:
            logger.error(f"❌ Migration failed: {str(e)}")
            return False

    def _dialect_type_for_column(self, col) -> str:
        """Map SQLAlchemy column to database-specific type for ALTER TABLE."""
        from sqlalchemy import Integer, String, Text, Boolean, DateTime, Numeric
        from sqlalchemy.types import Enum as EnumType
        t = type(col.type)
        default_empty = "" if not getattr(col, "nullable", True) else " DEFAULT NULL"
        if t == Integer:
            return "INTEGER DEFAULT 0" if not getattr(col, "nullable", True) else "INTEGER DEFAULT NULL"
        if t == Boolean:
            return "INTEGER DEFAULT 0" if not IS_POSTGRESQL else "BOOLEAN DEFAULT FALSE"
        if t == String:
            length = getattr(col.type, "length", None) or 255
            return f"VARCHAR({length}) DEFAULT ''"
        if t == Text:
            return "TEXT" + default_empty
        if t == DateTime:
            return "DATETIME" + default_empty if not IS_POSTGRESQL else "TIMESTAMP" + default_empty
        if t == Numeric:
            return "REAL DEFAULT 0" if not IS_POSTGRESQL else "DOUBLE PRECISION DEFAULT 0"
        if t == EnumType:
            return "VARCHAR(50)" + default_empty
        return "TEXT" + default_empty

    def migrate_orders_sync_columns(self) -> bool:
        """Thêm mọi cột thiếu của bảng orders theo model Order."""
        try:
            inspector = inspect(engine)
            try:
                existing_columns = inspector.get_columns('orders')
            except Exception:
                logger.info("Table orders does not exist yet, skip orders sync")
                return True
            existing_names = {col['name'] for col in existing_columns}
            with engine.connect() as conn:
                for col in Order.__table__.columns:
                    if col.name in existing_names:
                        continue
                    try:
                        sql_type = self._dialect_type_for_column(col)
                        stmt = text(f"ALTER TABLE orders ADD COLUMN {col.name} {sql_type}")
                        conn.execute(stmt)
                        conn.commit()
                        logger.info(f"  Added column orders.{col.name}")
                    except Exception as e:
                        logger.warning(f"  Skip/add column {col.name}: {e}")
                        conn.rollback()
                # Backfill order_code for existing rows if we just added it
                if 'order_code' not in existing_names:
                    try:
                        conn.execute(text("UPDATE orders SET order_code = 'ORD' || id WHERE order_code = '' OR order_code IS NULL"))
                        conn.commit()
                    except Exception:
                        conn.rollback()
                logger.info("✅ orders table columns synced")
                return True
        except Exception as e:
            logger.error(f"❌ migrate_orders_sync_columns failed: {str(e)}")
            return False

    def migrate_orders_add_order_code(self) -> bool:
        """Migration: thêm cột order_code vào bảng orders nếu chưa có (legacy, kept for back compat)."""
        return self.migrate_orders_sync_columns()

    def _create_table_if_not_exists(self, table_name: str, model_class) -> bool:
        """Tạo bảng từ model nếu chưa tồn tại."""
        try:
            inspector = inspect(engine)
            if table_name in inspector.get_table_names():
                logger.info(f"  Table {table_name} already exists, skip create")
                return True
            model_class.__table__.create(engine, checkfirst=True)
            logger.info(f"  Created table {table_name}")
            return True
        except Exception as e:
            logger.warning(f"  _create_table_if_not_exists({table_name}): {e}")
            return False

    def _sync_table_columns(self, table_name: str, model_class) -> bool:
        """Thêm mọi cột thiếu của bảng theo model (dùng chung cho orders, order_items, ...)."""
        try:
            inspector = inspect(engine)
            try:
                existing_columns = inspector.get_columns(table_name)
            except Exception:
                logger.info(f"Table {table_name} does not exist yet, skip sync")
                return True
            existing_names = {col["name"] for col in existing_columns}
            with engine.connect() as conn:
                for col in model_class.__table__.columns:
                    if col.name in existing_names:
                        continue
                    try:
                        sql_type = self._dialect_type_for_column(col)
                        stmt = text(f"ALTER TABLE {table_name} ADD COLUMN {col.name} {sql_type}")
                        conn.execute(stmt)
                        conn.commit()
                        logger.info(f"  Added column {table_name}.{col.name}")
                    except Exception as e:
                        logger.warning(f"  Skip/add column {table_name}.{col.name}: {e}")
                        conn.rollback()
                logger.info(f"✅ {table_name} columns synced")
                return True
        except Exception as e:
            logger.error(f"❌ _sync_table_columns({table_name}) failed: {str(e)}")
            return False

    def migrate_order_items_sync_columns(self) -> bool:
        """Thêm mọi cột thiếu của bảng order_items theo model OrderItem."""
        return self._sync_table_columns("order_items", OrderItem)

    def migrate_orders_enum_values(self) -> bool:
        """Chuẩn hóa enum trong DB: tên enum (PERCENT_30) -> value (percent_30), legacy (unpaid) -> valid value."""
        name_to_value = {
            "deposit_type": [(e.name, e.value) for e in DepositType],
            "status": [(e.name, e.value) for e in OrderStatus],
            "payment_method": [(e.name, e.value) for e in PaymentMethod],
            "payment_status": [(e.name, e.value) for e in PaymentStatus],
        }
        # Legacy/removed values -> map to current enum value
        legacy_payment_status = [
            ("unpaid", PaymentStatus.PENDING.value),
        ]
        try:
            inspector = inspect(engine)
            for table in ("orders", "payments"):
                try:
                    cols = {c["name"] for c in inspector.get_columns(table)}
                except Exception:
                    continue
                with engine.connect() as conn:
                    if IS_POSTGRESQL:
                        # Ensure postgres enums contain lowercase values before updates
                        for col_name, pairs in name_to_value.items():
                            if col_name not in cols:
                                continue
                            type_row = conn.execute(
                                text(
                                    "SELECT udt_name FROM information_schema.columns "
                                    "WHERE table_name = :table AND column_name = :col"
                                ),
                                {"table": table, "col": col_name},
                            ).fetchone()
                            if not type_row:
                                continue
                            enum_type = type_row[0]
                            existing = conn.execute(
                                text(
                                    "SELECT e.enumlabel FROM pg_enum e "
                                    "JOIN pg_type t ON t.oid = e.enumtypid "
                                    "WHERE t.typname = :type"
                                ),
                                {"type": enum_type},
                            ).fetchall()
                            existing_set = {r[0] for r in existing}
                            for _, enum_value in pairs:
                                if enum_value in existing_set:
                                    continue
                                try:
                                    conn.execute(text(f'ALTER TYPE "{enum_type}" ADD VALUE \'{enum_value}\''))
                                    conn.commit()
                                    existing_set.add(enum_value)
                                except Exception as e:
                                    logger.warning(f"  Enum add value {enum_type}.{enum_value}: {e}")
                                    conn.rollback()

                    for col_name, pairs in name_to_value.items():
                        if col_name not in cols:
                            continue
                        for enum_name, enum_value in pairs:
                            try:
                                if IS_POSTGRESQL:
                                    conn.execute(
                                        text(f"UPDATE {table} SET {col_name} = :val WHERE {col_name}::text = :name"),
                                        {"val": enum_value, "name": enum_name},
                                    )
                                else:
                                    conn.execute(
                                        text(f"UPDATE {table} SET {col_name} = :val WHERE {col_name} = :name"),
                                        {"val": enum_value, "name": enum_name},
                                    )
                                conn.commit()
                            except Exception as e:
                                logger.warning(f"  Enum update {table}.{col_name} {enum_name}: {e}")
                                conn.rollback()
                    # Fix legacy payment_status values
                    if "payment_status" in cols:
                        for old_val, new_val in legacy_payment_status:
                            try:
                                if IS_POSTGRESQL:
                                    conn.execute(
                                        text(
                                            "UPDATE {0} SET payment_status = :val "
                                            "WHERE payment_status::text = :old".format(table)
                                        ),
                                        {"val": new_val, "old": old_val},
                                    )
                                else:
                                    conn.execute(
                                        text(
                                            "UPDATE {0} SET payment_status = :val "
                                            "WHERE payment_status = :old".format(table)
                                        ),
                                        {"val": new_val, "old": old_val},
                                    )
                                conn.commit()
                            except Exception as e:
                                logger.warning(f"  Legacy payment_status {old_val}: {e}")
                                conn.rollback()
            logger.info("✅ orders/payments enum values normalized")
            return True
        except Exception as e:
            logger.error(f"❌ migrate_orders_enum_values failed: {str(e)}")
            return False

    def migrate_category_seo_meta_seo_body(self) -> bool:
        """Thêm cột seo_body (TEXT) vào bảng category_seo_meta nếu chưa có."""
        try:
            inspector = inspect(engine)
            if "category_seo_meta" not in inspector.get_table_names():
                logger.info("Table category_seo_meta chưa tồn tại, bỏ qua migration seo_body")
                return True
            existing = inspector.get_columns("category_seo_meta")
            if any(col["name"] == "seo_body" for col in existing):
                logger.info("Column category_seo_meta.seo_body đã tồn tại")
                return True
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE category_seo_meta ADD COLUMN seo_body TEXT"))
                conn.commit()
            logger.info("✅ Added category_seo_meta.seo_body")
            return True
        except Exception as e:
            logger.error("❌ migrate_category_seo_meta_seo_body failed: %s", e)
            return False

    def migrate_all_tables(self) -> Dict[str, bool]:
        """Chạy tất cả migrations cần thiết"""
        results = {}
        
        # 1. Migration cho sub_subcategory
        results['add_sub_subcategory'] = self.migrate_add_sub_subcategory()
        # 2. Bảng orders
        results['orders_add_order_code'] = self.migrate_orders_add_order_code()
        # 3. Bảng order_items (unit_price, ...)
        results['order_items_sync_columns'] = self.migrate_order_items_sync_columns()
        # 4. Chuẩn hóa enum (tên -> value) để tránh LookupError khi đọc
        results['orders_enum_values'] = self.migrate_orders_enum_values()
        # 5. Bảng product_questions (is_imported, ...)
        results['product_questions_sync_columns'] = self._sync_table_columns("product_questions", ProductQuestion)
        # 6. Bảng product_question_useful_votes (bình chọn hữu ích)
        results['product_question_useful_votes_create'] = self._create_table_if_not_exists(
            "product_question_useful_votes", ProductQuestionUsefulVote
        )
        # 7. Bảng product_reviews (đánh giá sản phẩm)
        results['product_reviews_create'] = self._create_table_if_not_exists(
            "product_reviews", ProductReview
        )
        results['product_review_useful_votes_create'] = self._create_table_if_not_exists(
            "product_review_useful_votes", ProductReviewUsefulVote
        )
        results['product_reviews_sync_columns'] = self._sync_table_columns("product_reviews", ProductReview)
        # 8. Bảng products (thêm cột product_info, ...)
        results['products_sync_columns'] = self._sync_table_columns("products", Product)
        # 9. category_seo_meta.seo_body (đoạn văn SEO 150-300 từ)
        results['category_seo_meta_seo_body'] = self.migrate_category_seo_meta_seo_body()
        # 10. search_mappings
        results['search_mappings_create'] = self._create_table_if_not_exists(
            "search_mappings", SearchMapping
        )
        # 11. search_logs
        results['search_logs_create'] = self._create_table_if_not_exists(
            "search_logs", SearchLog
        )
        # 12. users: bỏ NOT NULL các cột tùy chọn (Gmail, email-OTP) — gộp phone, date_of_birth, …
        results['users_optional_nullable'] = self.migrate_users_optional_columns_nullable()
        # 13. Web Push (PWA)
        results['user_push_subscriptions'] = self._create_table_if_not_exists(
            "user_push_subscriptions", UserPushSubscription
        )
        results['email_login_challenges'] = self._create_table_if_not_exists(
            "email_login_challenges", EmailLoginChallenge
        )
        results['email_trusted_devices'] = self._create_table_if_not_exists(
            "email_trusted_devices", EmailTrustedDevice
        )
        # 14. bank_accounts: mã NH + URL mẫu QR SePay/VietQR
        results['bank_accounts_sync_columns'] = self._sync_table_columns("bank_accounts", BankAccount)
        # 15. Hành vi khách (phiên trình duyệt), gộp vào user khi đăng nhập
        results['guest_product_views'] = self._create_table_if_not_exists("guest_product_views", GuestProductView)
        results['guest_favorites'] = self._create_table_if_not_exists("guest_favorites", GuestFavorite)
        results['guest_search_history'] = self._create_table_if_not_exists("guest_search_history", GuestSearchHistory)
        # 16. Mã nhúng site (GA4, GTM, Pixel, Zalo…)
        results['site_embed_codes'] = self._create_table_if_not_exists("site_embed_codes", SiteEmbedCode)
        results['site_embed_codes_sync'] = self._sync_table_columns("site_embed_codes", SiteEmbedCode)

        return results

    def create_migration_history_table(self):
        """Tạo bảng lịch sử migration nếu chưa có"""
        try:
            with engine.connect() as conn:
                if IS_POSTGRESQL:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS migration_history (
                            id SERIAL PRIMARY KEY,
                            migration_name VARCHAR(255) NOT NULL,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status VARCHAR(50) NOT NULL,
                            details TEXT
                        )
                    """))
                else:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS migration_history (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            migration_name VARCHAR(255) NOT NULL,
                            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            status VARCHAR(50) NOT NULL,
                            details TEXT
                        )
                    """))
                conn.commit()
                logger.info("✅ Migration history table created/verified")
        except Exception as e:
            logger.error(f"Error creating migration table: {str(e)}")

    def log_migration(self, migration_name: str, status: str, details: str = ""):
        """Ghi log migration vào database"""
        try:
            with engine.connect() as conn:
                conn.execute(text("""
                    INSERT INTO migration_history (migration_name, status, details)
                    VALUES (:name, :status, :details)
                """), {
                    "name": migration_name,
                    "status": status,
                    "details": details
                })
                conn.commit()
        except Exception as e:
            logger.error(f"Error logging migration: {str(e)}")

def run_migrations():
    """Chạy tất cả migrations cần thiết"""
    logger.info("🚀 Starting database migrations...")
    
    migration_manager = MigrationManager()
    
    # Tạo bảng lịch sử migration
    migration_manager.create_migration_history_table()
    
    # Kiểm tra sự nhất quán
    consistency_check = migration_manager.check_database_consistency()
    logger.info(f"🔍 Database consistency check: {consistency_check}")
    
    # Chạy migrations
    results = migration_manager.migrate_all_tables()
    
    # Log kết quả
    for migration_name, success in results.items():
        if success:
            migration_manager.log_migration(
                migration_name, 
                "SUCCESS", 
                "Migration completed successfully"
            )
            logger.info(f"✅ {migration_name}: SUCCESS")
        else:
            migration_manager.log_migration(
                migration_name,
                "FAILED",
                "Migration failed"
            )
            logger.error(f"❌ {migration_name}: FAILED")
    
    # Kiểm tra lại sau migration
    final_check = migration_manager.check_database_consistency()
    if final_check.get("is_consistent"):
        logger.info("🎉 All migrations completed successfully!")
    else:
        logger.warning("⚠️  Some inconsistencies remain after migration")
        logger.warning(f"Missing in database: {final_check.get('missing_in_database', [])}")
        logger.warning(f"Missing in model: {final_check.get('missing_in_model', [])}")
    
    return {
        "results": results,
        "initial_check": consistency_check,
        "final_check": final_check
    }

if __name__ == "__main__":
    # Cho phép chạy trực tiếp file này
    import sys
    logging.basicConfig(level=logging.INFO)
    run_migrations()
