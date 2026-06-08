"""
Đọc/ghi cache JSON cây menu danh mục (L1/L2/L3) — build 1 lần, dùng nhiều lần.

Chỉ ảnh hưởng cấu trúc menu navigation; không cache danh sách SP trên trang /danh-muc/
(sort random / sản phẩm mới vẫn query products riêng mỗi lần mở trang danh mục).
"""

from __future__ import annotations

import json
import logging
import threading
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.category_menu_cache import CategoryMenuCache

logger = logging.getLogger(__name__)

CACHE_KEY_ACTIVE = "menu_tree:active=true"
CACHE_KEY_ALL = "menu_tree:active=false"

_MENU_RAM_KEYS = (
    "category_tree_v1:from_products:active=true",
    "category_tree_v1:from_products:active=false",
)

_rebuild_lock = threading.Lock()
_rebuild_in_flight = False


def cache_key_for_is_active(is_active: bool) -> str:
    return CACHE_KEY_ACTIVE if is_active else CACHE_KEY_ALL


def _invalidate_menu_ram_cache() -> None:
    try:
        from app.utils.ttl_cache import cache as ttl_cache

        for key in _MENU_RAM_KEYS:
            ttl_cache.invalidate(key)
    except Exception:
        pass


def _is_missing_cache_table(exc: BaseException) -> bool:
    msg = str(getattr(exc, "orig", exc)).lower()
    return "category_menu_cache" in msg and ("does not exist" in msg or "no such table" in msg)


def read_cached_tree(db: Session, is_active: bool, *, allow_stale: bool = True) -> Optional[List[Dict[str, Any]]]:
    try:
        row = (
            db.query(CategoryMenuCache)
            .filter(CategoryMenuCache.cache_key == cache_key_for_is_active(is_active))
            .first()
        )
    except (ProgrammingError, SQLAlchemyError) as exc:
        if _is_missing_cache_table(exc):
            db.rollback()
            return None
        raise
    if not row:
        return None
    if row.is_stale and not allow_stale:
        return None
    try:
        data = json.loads(row.tree_json)
        if not isinstance(data, list) or len(data) == 0:
            return None
        return data
    except json.JSONDecodeError:
        return None


def write_cached_tree(db: Session, is_active: bool, tree: List[Dict[str, Any]], *, is_stale: bool = False) -> None:
    if not tree:
        return
    key = cache_key_for_is_active(is_active)
    body = json.dumps(tree, ensure_ascii=False, default=str)
    try:
        row = db.query(CategoryMenuCache).filter(CategoryMenuCache.cache_key == key).first()
        if row:
            row.tree_json = body
            row.is_stale = is_stale
        else:
            db.add(
                CategoryMenuCache(
                    cache_key=key,
                    tree_json=body,
                    is_stale=is_stale,
                )
            )
        db.commit()
        _invalidate_menu_ram_cache()
    except (ProgrammingError, SQLAlchemyError) as exc:
        db.rollback()
        if _is_missing_cache_table(exc):
            logger.debug("category menu cache write skipped — table missing")
            return
        raise
    except Exception:
        db.rollback()
        raise


def mark_all_stale(db: Session) -> int:
    try:
        n = (
            db.query(CategoryMenuCache)
            .filter(CategoryMenuCache.is_stale.is_(False))
            .update({CategoryMenuCache.is_stale: True}, synchronize_session=False)
        )
        db.commit()
        _invalidate_menu_ram_cache()
        return int(n or 0)
    except (ProgrammingError, SQLAlchemyError) as exc:
        db.rollback()
        if _is_missing_cache_table(exc):
            return 0
        raise
    except Exception:
        db.rollback()
        return 0


def rebuild_tree_in_session(db: Session, is_active: bool) -> List[Dict[str, Any]]:
    from app.crud.product import get_category_tree_from_products
    from app.db.retry import TransientDbError, is_transient_db_error

    try:
        try:
            tree = get_category_tree_from_products(db, is_active=is_active, hide_empty_branches=True)
        except Exception as prune_exc:
            if is_transient_db_error(prune_exc):
                raise TransientDbError(str(prune_exc)) from prune_exc
            tree = get_category_tree_from_products(db, is_active=is_active, hide_empty_branches=False)
    except TransientDbError:
        raise
    except Exception as exc:
        if is_transient_db_error(exc):
            raise TransientDbError(str(exc)) from exc
        logger.exception("category menu cache rebuild failed (is_active=%s)", is_active)
        return []
    if tree:
        write_cached_tree(db, is_active, tree, is_stale=False)
    return tree


def rebuild_both_trees(db: Session) -> None:
    rebuild_tree_in_session(db, True)
    rebuild_tree_in_session(db, False)


def schedule_rebuild_both_trees() -> None:
    global _rebuild_in_flight

    with _rebuild_lock:
        if _rebuild_in_flight:
            return
        _rebuild_in_flight = True

    def _run() -> None:
        global _rebuild_in_flight
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            rebuild_both_trees(db)
            logger.info("category menu cache: rebuilt both trees (background)")
        except Exception as exc:
            logger.warning("category menu cache background rebuild failed: %s", exc)
        finally:
            db.close()
            with _rebuild_lock:
                _rebuild_in_flight = False

    threading.Thread(target=_run, name="category-menu-cache-rebuild", daemon=True).start()


def invalidate_all_menu_caches() -> None:
    """Sau đổi taxonomy / mapping — xóa RAM + đánh stale DB + rebuild nền."""
    _invalidate_menu_ram_cache()

    def _run() -> None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            mark_all_stale(db)
        except Exception as exc:
            logger.warning("category menu cache mark stale failed: %s", exc)
        finally:
            db.close()
        schedule_rebuild_both_trees()

    threading.Thread(target=_run, name="category-menu-cache-invalidate", daemon=True).start()


def product_change_affects_menu_tree(
    product: Any,
    *,
    previous: Any = None,
    old_category: Optional[str] = None,
    old_subcategory: Optional[str] = None,
    old_sub_subcategory: Optional[str] = None,
    old_category_id: Optional[int] = None,
) -> bool:
    """Chỉ rebuild menu khi nhánh danh mục / trạng thái hiển thị SP đổi — không đụng sort random trang listing."""
    if previous is None:
        return True
    fields = ("category", "subcategory", "sub_subcategory", "category_id", "is_active")
    for field in fields:
        if getattr(product, field, None) != getattr(previous, field, None):
            return True
    if old_category is not None and (
        (old_category or "").strip() != (getattr(product, "category", None) or "").strip()
        or (old_subcategory or "").strip() != (getattr(product, "subcategory", None) or "").strip()
        or (old_sub_subcategory or "").strip() != (getattr(product, "sub_subcategory", None) or "").strip()
    ):
        return True
    if old_category_id is not None and old_category_id != getattr(product, "category_id", None):
        return True
    return False


def schedule_refresh_after_product_changes(
    products: List[Any],
    *,
    previous_products: Optional[List[Any]] = None,
    old_category: Optional[str] = None,
    old_subcategory: Optional[str] = None,
    old_sub_subcategory: Optional[str] = None,
    old_category_id: Optional[int] = None,
) -> None:
    if not products:
        return
    prev_by_id: Dict[Any, Any] = {}
    if previous_products:
        for p in previous_products:
            if p is not None and getattr(p, "id", None) is not None:
                prev_by_id[p.id] = p

    affected = False
    for product in products:
        prev = prev_by_id.get(getattr(product, "id", None))
        if product_change_affects_menu_tree(
            product,
            previous=prev,
            old_category=old_category if prev is None else None,
            old_subcategory=old_subcategory if prev is None else None,
            old_sub_subcategory=old_sub_subcategory if prev is None else None,
            old_category_id=old_category_id if prev is None else None,
        ):
            affected = True
            break

    if not affected:
        return

    def _mark_stale_and_rebuild() -> None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            mark_all_stale(db)
        except Exception as exc:
            logger.warning("category menu cache mark stale failed: %s", exc)
        finally:
            db.close()
        schedule_rebuild_both_trees()

    threading.Thread(target=_mark_stale_and_rebuild, name="category-menu-cache-stale", daemon=True).start()


def snapshot_for_menu_refresh(product: Any) -> SimpleNamespace:
    return SimpleNamespace(
        id=getattr(product, "id", None),
        category=getattr(product, "category", None),
        subcategory=getattr(product, "subcategory", None),
        sub_subcategory=getattr(product, "sub_subcategory", None),
        category_id=getattr(product, "category_id", None),
        is_active=getattr(product, "is_active", None),
    )
