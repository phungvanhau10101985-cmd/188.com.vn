# backend/app/crud/product.py - COMPLETE FIXED VERSION
from sqlalchemy.orm import Session
from sqlalchemy import and_, cast, func as sql_func, not_, or_, select, String, union_all
from typing import List, Optional, Dict, Any, Set, Tuple
from app.models.product import Product
from app.models.search_mapping import SearchMapping, SearchMappingType
from app.models.search_log import SearchLog
from app.models.category_seo import CategorySeoMeta, CategorySeoGeminiTarget, CategorySeoSettings
from app.models.category_transform_rule import CategoryTransformRule
from app.models.category_final_mapping import CategoryFinalMapping
from app.models.guest_behavior import GuestProductView
from app.models.user import UserProductView
from app.schemas.product import ProductCreate, ProductUpdate
import math
import logging
import json
import copy
import time
import threading
from datetime import datetime
from app.core.config import settings
from app.services.alicdn_urls import normalize_product_data_image_urls_for_db
from app.services.bunny_storage import (
    collect_product_image_urls_for_bunny,
    delete_bunny_assets_for_product,
    delete_bunny_storage_objects_for_urls,
)
from app.services.import_hibox_scraper import canonicalize_hibox_placeholder_product_id
from app.services.product_internal_sku import (
    ensure_unique_internal_product_code,
    internal_sku_exists_on_other_product,
    internal_sku_is_valid_format,
    sync_internal_code_into_product_info,
)
from app.utils.vietnamese import (
    normalize_for_search_no_accent,
    VIETNAMESE_ACCENT_MAP,
    COMMON_WORD_MAPPING,
    remove_vietnamese_accents,
)
from app.db.session import is_sqlite
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import re
import threading

# Import slug function từ slug.py
try:
    from app.utils.slug import create_slug as slugify_vietnamese
    SLUG_AVAILABLE = True
except ImportError:
    SLUG_AVAILABLE = False
    # Fallback function nếu không import được
    import unicodedata
    
    def slugify_vietnamese(text: str) -> str:
        if not text:
            return ""
        text = unicodedata.normalize('NFKD', text)
        text = ''.join([c for c in text if not unicodedata.combining(c)])
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '-', text)
        return text.strip('-')

logger = logging.getLogger(__name__)

# Trường chỉ có trên schema trả API (enrich), không phải cột ORM Product.
_RESPONSE_ONLY_PRODUCT_KEYS = frozenset({"category_level1_slug", "category_level2_slug"})

# product_id kiểu nguồn 1688/Taobao: «…phần_web…» + «a188» + «SKU nội bộ» (vd A920025943011a188B0266)
_PRODUCT_ID_A188_RE = re.compile(r"a188", re.IGNORECASE)


def split_product_id_web_prefix_and_internal_sku(product_id: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Phần id trước «a188» (case-insensitive, giữ casing gốc) + SKU sau đó — dùng chặn trùng offer/id nguồn và trùng SKU.
    Trả dict: prefix (raw), prefix_key (chuẩn so sánh casefold), sku (uppercase).
    """
    if not product_id:
        return None
    raw = str(product_id).strip()
    if not raw:
        return None
    m = _PRODUCT_ID_A188_RE.search(raw)
    if not m:
        return None
    prefix = raw[: m.start()].strip()
    sku_tail = raw[m.end() :].strip().upper()
    if not prefix or not sku_tail:
        return None
    return {"prefix": prefix, "prefix_key": prefix.casefold(), "sku": sku_tail}


def _listing_source_prefix_from_product_id(product_id: Optional[str]) -> Optional[Dict[str, str]]:
    """
    Mã cột A (id Excel) — một offer = một ``prefix_key``:
    - Chỉ prefix: ``a990013135592`` / ``A990013135592``
    - Đủ legacy: ``a990013135592a188f6946`` / ``A990013135592a188K8790``
    Cả hai cùng ``prefix_key`` ``a990013135592`` → một sản phẩm (import chỉ cập nhật).
    """
    raw = str(product_id or "").strip()
    if not raw:
        return None
    seg = split_product_id_web_prefix_and_internal_sku(raw)
    prefix = (seg.get("prefix") if seg else raw).strip()
    if not re.fullmatch(r"(?i)[AT]\d{6,}", prefix):
        return None
    normalized = prefix[0].upper() + prefix[1:]
    return {"prefix": normalized, "prefix_key": normalized.casefold()}


def _compose_listing_product_id(prefix: str, sku: str) -> str:
    return f"{prefix.strip()}a188{sku.strip().upper()}"


def find_conflicting_product_id_for_same_listing_source(
    db: Session,
    candidate_product_id: str,
    *,
    exclude_product_pk_ids: Optional[Set[int]] = None,
) -> Optional[str]:
    """
    Trùng mã nguồn 1688/Taobao (cột A): cùng prefix A/T trước «a188» hoặc id chỉ có A/T+số.
    Trả `product_id` của bản ghi khác đã chiếm — dùng chặn đăng/import trùng offer/item.
    """
    cand_src = _listing_source_prefix_from_product_id(candidate_product_id)
    if not cand_src:
        return None
    pk = cand_src["prefix_key"]
    ex = exclude_product_pk_ids or set()
    cand_norm = str(candidate_product_id).strip()
    for row_id, pid_str in db.query(Product.id, Product.product_id).filter(Product.product_id.isnot(None)).all():
        if row_id in ex:
            continue
        if str(pid_str).strip() == cand_norm:
            continue
        other_src = _listing_source_prefix_from_product_id(pid_str)
        if other_src and other_src["prefix_key"] == pk:
            return str(pid_str).strip()
    return None


def find_product_by_listing_source_prefix(
    db: Session,
    source_prefix: Dict[str, str],
    *,
    exclude_product_pk_ids: Optional[Set[int]] = None,
) -> Optional[Product]:
    """Tìm một SP đã có cùng mã cột A (prefix_key), kể cả id Excel khác hậu tố a188SKU."""
    pk = (source_prefix or {}).get("prefix_key")
    if not pk:
        return None
    ex = exclude_product_pk_ids or set()
    for row_id, pid_str in db.query(Product.id, Product.product_id).filter(Product.product_id.isnot(None)).all():
        if row_id in ex:
            continue
        other_src = _listing_source_prefix_from_product_id(pid_str)
        if other_src and other_src["prefix_key"] == pk:
            return db.query(Product).filter(Product.id == row_id).first()
    return None


def _bulk_import_maps_remove_product_id(
    product_id_str: str,
    batch_prefix_owner: Dict[str, str],
    db_prefix_owner: Dict[str, str],
    batch_code_owner: Dict[str, str],
    db_code_owner: Dict[str, str],
) -> None:
    """Khi xóa SP trong bulk import — gỡ mọi map prefix/SKU trỏ tới product_id đó (dòng sau có thể tái dùng)."""
    for m in (batch_prefix_owner, db_prefix_owner, batch_code_owner, db_code_owner):
        dead = [k for k, v in m.items() if v == product_id_str]
        for k in dead:
            del m[k]


def _bulk_import_conflict_maps_initial(db: Session) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    prefix_key (A/T + số nguồn; tách từ cả id mới và legacy a188) → product_id sở hữu,
    sku_code upper → product_id sở hữu (theo Product.code trong DB hiện tại).
    """
    pref_own: Dict[str, str] = {}
    code_own: Dict[str, str] = {}
    for pid, code in db.query(Product.product_id, Product.code).all():
        if not pid:
            continue
        src = _listing_source_prefix_from_product_id(pid)
        if src:
            k = src["prefix_key"]
            if k not in pref_own:
                pref_own[k] = pid
        if code:
            u = str(code).strip().upper()
            if u and u not in code_own:
                code_own[u] = pid
    return pref_own, code_own


def _ensure_bulk_import_internal_product_code(
    db: Session,
    proposed: Optional[str],
    *,
    exclude_product_id: Optional[int] = None,
    batch_reserved: Optional[Set[str]] = None,
) -> str:
    """
    Import Excel lên web chỉ chặn SKU đang có trên products; không chặn vì nháp import
    hoặc Google Sheet SKU vì các mã đó chính là pool admin dùng để import.
    """
    reserved = batch_reserved if batch_reserved is not None else set()
    cand = str(proposed or "").strip().upper()
    if internal_sku_is_valid_format(cand):
        if cand not in reserved and not internal_sku_exists_on_other_product(
            db,
            cand,
            exclude_product_id=exclude_product_id,
        ):
            reserved.add(cand)
            return cand

    return ensure_unique_internal_product_code(
        db,
        proposed,
        exclude_product_id=exclude_product_id,
        batch_reserved=reserved,
    )


# Đồng bộ Google Sheet: debounce nhiều thao tác liên tiếp → một lần gọi API (tránh vượt quota).
_gsheets_sync_debounce_timer: Optional[threading.Timer] = None
_gsheets_sync_debounce_lock = threading.Lock()


def _schedule_google_sheets_sku_sync(*, immediate: bool = False) -> None:
    """
    Web/DB là chuẩn: sau khi dữ liệu SP đổi, sheet được cập nhật tương ứng (trong worker nền).

    - immediate=False: gộp các lần gọi trong GOOGLE_SHEETS_SKU_SYNC_DEBOUNCE_SECONDS (mặc định 45s)
      thành một lần đồng bộ — giảm số request tới Google.
    - immediate=True: chạy đồng bộ ngay cho thao tác thủ công/đặc biệt.
    Trong service vẫn diff từng ô với DB trước khi ghi, chỉ cập nhật hàng thực sự thay đổi.
    """
    if not getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_ENABLED", False):
        return

    def _run() -> None:
        global _gsheets_sync_debounce_timer
        with _gsheets_sync_debounce_lock:
            _gsheets_sync_debounce_timer = None
        try:
            from app.db.session import SessionLocal
            from app.services.google_sheets_sku_sync import sync_product_skus_to_google_sheet

            s = SessionLocal()
            try:
                sync_product_skus_to_google_sheet(s)
            finally:
                s.close()
        except Exception as exc:
            logger.warning("Google Sheets SKU sync (nền) lỗi: %s", exc)

    debounce_sec = int(getattr(settings, "GOOGLE_SHEETS_SKU_SYNC_DEBOUNCE_SECONDS", 45) or 0)

    if immediate or debounce_sec <= 0:
        threading.Thread(target=_run, name="gsheets-sku-sync", daemon=True).start()
        return

    global _gsheets_sync_debounce_timer
    with _gsheets_sync_debounce_lock:
        if _gsheets_sync_debounce_timer is not None:
            try:
                _gsheets_sync_debounce_timer.cancel()
            except Exception:
                pass
            _gsheets_sync_debounce_timer = None
        t = threading.Timer(float(debounce_sec), _run)
        t.daemon = True
        _gsheets_sync_debounce_timer = t
        t.start()


# ========== Danh sách SP: sắp xếp (admin / API) ==========


def normalize_product_list_sort(sort: Optional[str]) -> str:
    """Giá trị nội bộ: id_desc | newest | oldest | views_desc | purchases_desc | available_desc | available_asc | id_asc."""
    s = (sort or "").strip().lower().replace("-", "_")
    if s in ("", "default", "id_desc", "id_newest"):
        return "id_desc"
    if s in ("id", "id_asc"):
        return "id_asc"
    if s in ("views_desc", "views", "popular", "most_viewed"):
        return "views_desc"
    if s in ("purchases_desc", "purchases", "bestselling", "best_selling", "sold"):
        return "purchases_desc"
    if s in ("available_desc", "stock_desc", "inventory_desc", "ton_kho_desc"):
        return "available_desc"
    if s in ("available_asc", "stock_asc", "inventory_asc", "ton_kho_asc"):
        return "available_asc"
    if s in ("newest", "new", "created_desc"):
        return "newest"
    if s in ("oldest", "created_asc"):
        return "oldest"
    return "id_desc"


def _product_view_totals_subquery():
    """
    Tổng lượt mở trang chi tiết (guest + đăng nhập), group theo Product.id / product_id FK.
    """
    guest_sq = (
        select(
            GuestProductView.product_id.label("product_id"),
            sql_func.coalesce(sql_func.sum(GuestProductView.view_count), 0).label("v"),
        ).group_by(GuestProductView.product_id)
    )
    user_sq = (
        select(
            UserProductView.product_id.label("product_id"),
            sql_func.coalesce(sql_func.sum(UserProductView.view_count), 0).label("v"),
        ).group_by(UserProductView.product_id)
    )
    parts = union_all(guest_sq, user_sq).subquery("pv_union")
    return (
        select(parts.c.product_id, sql_func.sum(parts.c.v).label("view_total"))
        .group_by(parts.c.product_id)
        .subquery("pv_totals")
    )


def _order_exprs_for_product_list(sort: str, view_totals_subq):
    """Cặp/order_by expressions; view_totals_subq chỉ dùng khi sort == views_desc."""
    if sort == "views_desc" and view_totals_subq is not None:
        cnt = sql_func.coalesce(view_totals_subq.c.view_total, 0)
        return [cnt.desc(), Product.id.desc()]
    if sort == "newest":
        return [Product.created_at.desc().nullslast(), Product.id.desc()]
    if sort == "oldest":
        return [Product.created_at.asc().nullslast(), Product.id.asc()]
    if sort == "purchases_desc":
        return [Product.purchases.desc().nullslast(), Product.id.desc()]
    if sort == "available_desc":
        return [sql_func.coalesce(Product.available, 0).desc(), Product.id.desc()]
    if sort == "available_asc":
        return [sql_func.coalesce(Product.available, 0).asc(), Product.id.asc()]
    if sort == "id_asc":
        return [Product.id.asc()]
    # id_desc: ID hệ thống giảm dần — nhập/import mới lên đầu
    return [Product.id.desc()]


# ========== HELPER FUNCTIONS ==========

_ACCENT_SRC = "".join([k for k in VIETNAMESE_ACCENT_MAP.keys() if k.islower()])
_ACCENT_DST = "".join([VIETNAMESE_ACCENT_MAP[k] for k in VIETNAMESE_ACCENT_MAP.keys() if k.islower()])

def category_field_equals_ci(column, value: Optional[str]):
    """
    So khớp tên danh mục trong DB với chuỗi tham chiếu (tree/API): trim + không phân biệt hoa thường.
    Tránh 0 sản phẩm khi mapping/import lệch casing hoặc khoảng trắng so với breadcrumb.
    """
    if value is None:
        return None
    nv = str(value).strip().lower()
    if not nv:
        return None
    return sql_func.lower(sql_func.trim(column)) == nv


def subcategory_field_in_ci(column, values: Optional[List[str]]):
    """IN trên subcategory sau khi lower(trim(col)); values là danh sách chuỗi tham chiếu."""
    if not values:
        return None
    norms = []
    for v in values:
        nv = str(v).strip().lower() if v is not None else ""
        if nv:
            norms.append(nv)
    if not norms:
        return None
    return sql_func.lower(sql_func.trim(column)).in_(norms)


def _normalize_category_url_slug(segment: Optional[str]) -> Optional[str]:
    """Segment trong URL /danh-muc/... có thể chứa dấu tiếng Việt; chuẩn hoá giống slug trong cây."""
    if segment is None:
        return None
    s = str(segment).strip()
    if not s:
        return None
    if SLUG_AVAILABLE:
        return slugify_vietnamese(s).lower()
    return s.lower()


def _normalize_search_key(raw_query: str) -> str:
    try:
        normalized = (raw_query or "").strip().lower()
        return re.sub(r"\s+", " ", normalized).strip()
    except Exception:
        return ""


def _has_vietnamese_accents(text: str) -> bool:
    try:
        raw = (text or "").strip()
        if not raw:
            return False
        return remove_vietnamese_accents(raw) != raw
    except Exception:
        return False


def _get_search_mapping(db: Session, normalized_key: str) -> Optional[SearchMapping]:
    try:
        if not normalized_key:
            return None
        return db.query(SearchMapping).filter(SearchMapping.keyword_input == normalized_key).first()
    except Exception:
        return None


def _touch_search_mapping(db: Session, mapping: SearchMapping) -> None:
    try:
        mapping.hit_count = (mapping.hit_count or 0) + 1
        db.commit()
    except Exception:
        db.rollback()


def _save_search_mapping(db: Session, normalized_key: str, keyword_target: str, mapping_type: SearchMappingType) -> None:
    try:
        if not normalized_key or not keyword_target:
            return
        mapping = db.query(SearchMapping).filter(SearchMapping.keyword_input == normalized_key).first()
        if mapping:
            mapping.keyword_target = keyword_target
            mapping.type = mapping_type
        else:
            mapping = SearchMapping(
                keyword_input=normalized_key,
                keyword_target=keyword_target,
                type=mapping_type,
            )
            db.add(mapping)
        db.commit()
    except Exception:
        db.rollback()


def _log_search(db: Session, keyword: str, result_count: int, ai_processed: bool) -> None:
    try:
        if not keyword:
            return
        db.add(SearchLog(keyword=keyword, result_count=result_count, ai_processed=ai_processed))
        db.commit()
    except Exception:
        db.rollback()


def _similarity_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _flatten_category_tree(tree: List[dict]) -> List[dict]:
    flat = []
    for level1 in tree or []:
        name1 = (level1.get("name") or "").strip()
        slug1 = (level1.get("slug") or slugify_vietnamese(name1)).strip()
        if name1:
            flat.append({"level": 1, "name": name1, "slug": slug1, "path": f"/danh-muc/{slug1}"})
        for level2 in (level1.get("children") or []):
            name2 = (level2.get("name") or "").strip()
            slug2 = (level2.get("slug") or slugify_vietnamese(name2)).strip()
            if name2:
                flat.append({
                    "level": 2,
                    "name": name2,
                    "slug": slug2,
                    "path": f"/danh-muc/{slug1}/{slug2}",
                    "parent": name1,
                })
            for level3 in (level2.get("children") or []):
                name3 = (level3.get("name") or "").strip()
                slug3 = (level3.get("slug") or slugify_vietnamese(name3)).strip()
                if name3:
                    flat.append({
                        "level": 3,
                        "name": name3,
                        "slug": slug3,
                        "path": f"/danh-muc/{slug1}/{slug2}/{slug3}",
                        "parent": name2,
                    })
    return flat


def _match_category_path(normalized_query: str, tree: List[dict]) -> Optional[dict]:
    if not normalized_query:
        return None
    for item in _flatten_category_tree(tree):
        candidate_name = _normalize_search_key(item.get("name", ""))
        if normalized_query == candidate_name:
            return item
    return None


def _run_ai_call(func, *args, timeout_seconds: int = 3):
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args)
            return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError:
        return None
    except Exception:
        return None

def safe_float(value) -> float:
    """Safely convert to float"""
    try:
        if value is None or str(value).strip() == '':
            return 0.0
        return float(value)
    except:
        return 0.0

def safe_int(value) -> int:
    """Safely convert to integer"""
    try:
        if value is None or str(value).strip() == '':
            return 0
        return int(float(value))
    except:
        return 0

def safe_bool(value) -> bool:
    """Safely convert to boolean"""
    try:
        if value is None or str(value).strip() == '':
            return False
        return bool(int(float(value)))
    except:
        return False


def deposit_require_to_excel_int(raw: Any, *, default: int = 1) -> int:
    """
    Quy chuẩn cột Excel «Cần đặt cọc» / draft JSON: 1 = cần cọc, 0 = không.
    Nhận bool/int/str — khớp file mẫu (số), tránh true/false trong luồng trao đổi file/link.
    """
    if raw is None:
        return default
    if isinstance(raw, float) and math.isnan(raw):
        return default
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s == "":
            return default
        if s in ("0", "false", "no", "off", "f"):
            return 0
        if s in ("1", "true", "yes", "on", "t"):
            return 1
        try:
            return 1 if int(float(s)) != 0 else 0
        except Exception:
            return default
    if raw is False:
        return 0
    if raw is True:
        return 1
    try:
        return 1 if int(float(raw)) != 0 else 0
    except Exception:
        return default


def deposit_require_to_bool(raw: Any, *, default: bool = True) -> bool:
    """Chuyển sang bool cho ORM / ProductCreate."""
    return deposit_require_to_excel_int(raw, default=1 if default else 0) == 1


def deposit_require_from_excel_cell(raw: Any) -> bool:
    """Import Excel: ô trống/NaN → cần cọc; chỉ tắt khi ghi rõ 0/false."""
    return deposit_require_to_bool(raw, default=True)


def listed_from_excel_cell(raw: Any, *, default: int = 1) -> int:
    """
    Cột Excel «listed» / «Trong danh sách»: 1 = thêm mới hoặc cập nhật; 0 = xóa khỏi DB (bulk import).
    Ô trống/NaN → 1 (giữ hành vi cũ).
    """
    return deposit_require_to_excel_int(raw, default=default)


# ---------- Nhóm danh mục cùng ý định SEO (aggregation) ----------
# Khi khách vào danh mục "Giày boot Nam" thì hiển thị tất cả sản phẩm có subcategory
# thuộc nhóm này (không chỉ subcategory đúng tên "Giày boot Nam").
# Key: (category level1, subcategory canonical name), Value: list subcategory names để IN query.
SUBCATEGORY_GROUPS = {
    ("Giày dép Nam", "Giày boot Nam"): [
        "Giày boot Nam",
        "Boot Chelsea Nam",
        "Boot Cổ Cao Nam",
    ],
}

# Listing cấp 1: siết taxonomy + loại subcategory lệch ngành (hai chiều giày ↔ quần áo).
_FOOTWEAR_CATEGORY_L1_NAMES = frozenset({"Giày dép Nam", "Giày dép Nữ"})
_FASHION_CATEGORY_L1_NAMES = frozenset(
    {"Thời trang Nam", "Thời trang Nữ", "Thời trang trẻ em"}
)
_CATEGORY_L1_LISTING_GUARD_NAMES = _FOOTWEAR_CATEGORY_L1_NAMES | _FASHION_CATEGORY_L1_NAMES

_FOOTWEAR_MISCAT_SUBCATEGORY_FRAGMENTS = (
    "áo khoác",
    "ao khoac",
    "áo thun",
    "ao thun",
    "áo sơ mi",
    "ao so mi",
    "áo polo",
    "áo len",
    "áo vest",
    "blazer",
    "cardigan",
    "quần jeans",
    "quan jeans",
    "quần short",
    "quan short",
    "quần jogger",
    "quần tây",
    "váy ",
    "vay ",
    "đầm",
    "dam ",
    "chân váy",
    "chan vay",
    "bikini",
    "đồ ngủ",
    "do ngu",
)
_FASHION_MISCAT_SUBCATEGORY_FRAGMENTS = (
    "giày ",
    "giay ",
    "giày tây",
    "giay tay",
    "giày lười",
    "giay luoi",
    "giày boot",
    "giày sneaker",
    "giày dép",
    "giay dep",
    " dép",
    " dep",
    "sneaker",
    "sandal",
    " loafer",
    "loafer",
    " oxford",
    " derby",
    " mule",
    " boot ",
    " boot nam",
    " boot nữ",
    "cao gót",
    "cao got",
    "búp bê",
    "bup be",
    "monkstrap",
)
_FASHION_NU_EXTRA_MISCAT_FRAGMENTS = (
    "giày dép nam",
    "giay dep nam",
    "giày tây nam",
    "giay tay nam",
    "giày lười nam",
    "giày boot nam",
    "sneaker nam",
    "oxford nam",
    "derby nam",
)
_FASHION_NAM_EXTRA_MISCAT_FRAGMENTS = (
    "giày dép nữ",
    "giay dep nu",
    "giày cao gót",
    "váy ",
    "vay ",
    "đầm",
    "chân váy",
    "chan vay",
    "bikini",
)


def get_subcategory_group_for_query(category: str, subcategory: str) -> Optional[List[str]]:
    """
    Nếu (category, subcategory) thuộc nhóm gộp SEO thì trả về list subcategory để dùng
    Product.subcategory.in_(list). Ngược lại trả về None (dùng filter exact subcategory).
    """
    if not category or not subcategory:
        return None
    key = (str(category).strip(), str(subcategory).strip())
    return SUBCATEGORY_GROUPS.get(key)


def parse_json_field(value: Any) -> List:
    """Parse JSON field from string"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except:
            # Try to fix common JSON issues
            value = value.replace("'", '"').replace('None', 'null').replace('True', 'true').replace('False', 'false')
            try:
                return json.loads(value)
            except:
                return []
    elif isinstance(value, list):
        return value
    else:
        return []


def _parse_product_info(value: Any) -> Optional[Dict]:
    """Parse product_info (cột AK) từ string JSON hoặc dict. Trả về dict hoặc None."""
    if value is None:
        return None
    if isinstance(value, float):
        try:
            import math
            if math.isnan(value):
                return None
        except Exception:
            pass
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() == 'nan':
            return None
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    if isinstance(value, dict):
        return value
    return None


def _merge_product_info_preserve_image_localization(incoming: Any, existing_product_info: Any) -> Any:
    """
    Import Excel thường ghi đè nguyên `product_info`: mất `image_localization` do file AK không chứa
    báo cáo chi tiết (popup admin trống) trong khi `image_localization_status` trên row vẫn «localized».
    Nếu payload import không có khóa `image_localization` và DB đã có báo cáo → giữ lại.
    """
    if not isinstance(incoming, dict):
        return incoming
    if "image_localization" in incoming:
        return incoming
    old = _parse_product_info(existing_product_info)
    if not isinstance(old, dict):
        return incoming
    loc_old = old.get("image_localization")
    if isinstance(loc_old, dict) and (
        loc_old.get("results") or loc_old.get("originals") or loc_old.get("processed_at")
    ):
        out = copy.deepcopy(incoming)
        out["image_localization"] = copy.deepcopy(loc_old)
        return out
    return incoming


def generate_consistent_slug(name: str, product_id: str = "") -> str:
    """
    Tạo slug nhất quán cho cả import và export
    Sử dụng hàm create_slug từ slug.py cho tiếng Việt
    PRODUCT_ID: Giữ nguyên tất cả, chỉ chuyển hoa → thường
    """
    try:
        if not product_id:
            product_id = f"pid{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Mã kho thanh lý (H0723/40/3): không để '/' trong slug — URL Next/FastAPI vỡ.
        if "/" in product_id or "\\" in product_id:
            from app.services.warehouse_clearance import warehouse_safe_slug_token

            product_code = warehouse_safe_slug_token(product_id)
        else:
            product_code = product_id.lower()  # CHỈ chuyển hoa → thường
        logger.debug(f"✅ Product ID: {product_id} → {product_code} (lowercase only)")
        
        # Tạo slug từ tên sử dụng hàm từ slug.py
        if name:
            try:
                # Sử dụng hàm create_slug từ slug.py
                from app.utils.slug import create_slug
                slug_name = create_slug(name)
                logger.debug(f"✅ Used create_slug from slug.py for: {name[:30]}...")
            except ImportError as e:
                # Fallback nếu không import được
                logger.warning(f"Cannot import create_slug from slug.py: {e}")
                
                # Fallback đơn giản
                import unicodedata
                
                def simple_slugify(text: str) -> str:
                    if not text:
                        return ""
                    # Chuyển về unicode decomposition
                    text = unicodedata.normalize('NFKD', text)
                    # Loại bỏ dấu combining characters
                    text = ''.join([c for c in text if not unicodedata.combining(c)])
                    # Chuyển thành chữ thường
                    text = text.lower()
                    # Thay thế ký tự không phải chữ cái, số bằng dấu gạch ngang
                    text = re.sub(r'[^a-z0-9\s-]', '', text)
                    # Thay thế khoảng trắng và dấu gạch ngang liên tiếp
                    text = re.sub(r'[\s-]+', '-', text)
                    # Loại bỏ dấu gạch ngang ở đầu và cuối
                    return text.strip('-')
                
                slug_name = simple_slugify(name)
                logger.debug(f"✅ Used fallback slugify for: {name[:30]}...")
            
            # Kết hợp slug_name với product_code (đã chuyển lowercase)
            result = f"{slug_name}-{product_code}"
            logger.debug(f"✅ Generated slug: {result[:80]}...")
            return result
        else:
            result = f"product-{product_code}"
            logger.debug(f"✅ Generated fallback slug: {result}")
            return result
            
    except Exception as e:
        logger.error(f"❌ Error generating slug: {str(e)}")
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"product-{timestamp}"

# ========== EXCEL IMPORT/EXPORT FUNCTIONS ==========

def get_category_transform_rules(db: Session) -> List[CategoryTransformRule]:
    return db.query(CategoryTransformRule).order_by(CategoryTransformRule.created_at.asc()).all()


def apply_category_transform_rules_to_product(
    product_data: Dict[str, Any],
    rules: List[CategoryTransformRule],
) -> Dict[str, Any]:
    if not product_data:
        return product_data
    category = (product_data.get("category") or "").strip()
    subcategory = (product_data.get("subcategory") or "").strip()
    sub_subcategory = (product_data.get("sub_subcategory") or "").strip()

    for rule in rules:
        r_type = rule.rule_type
        if r_type == "rename_level2":
            if category == (rule.category or "") and subcategory == (rule.subcategory or ""):
                subcategory = rule.target_name or subcategory
        elif r_type == "rename_level3":
            if (
                category == (rule.category or "")
                and subcategory == (rule.subcategory or "")
                and sub_subcategory == (rule.sub_subcategory or "")
            ):
                sub_subcategory = rule.target_name or sub_subcategory
        elif r_type == "merge_level2":
            sources = rule.source_subcategories or []
            if category == (rule.category or "") and subcategory in sources:
                subcategory = rule.target_name or subcategory
        elif r_type == "merge_level3":
            sources = rule.source_subcategories or []
            if (
                category == (rule.category or "")
                and subcategory == (rule.subcategory or "")
                and sub_subcategory in sources
            ):
                sub_subcategory = rule.target_name or sub_subcategory
        elif r_type == "swap_level2_level3":
            if category == (rule.category or "") and subcategory == (rule.subcategory or ""):
                swapped_up = rule.sub_subcategory or subcategory
                old_subcategory = subcategory
                subcategory = swapped_up
                if not sub_subcategory or sub_subcategory == swapped_up:
                    sub_subcategory = old_subcategory
        elif r_type == "move_level2_to_level3":
            if category == (rule.category or "") and subcategory == (rule.subcategory or ""):
                subcategory = rule.target_name or subcategory
                if not sub_subcategory:
                    sub_subcategory = rule.sub_subcategory or sub_subcategory
        elif r_type == "move_level3_to_level2":
            if (
                category == (rule.category or "")
                and subcategory == (rule.subcategory or "")
                and sub_subcategory == (rule.sub_subcategory or "")
            ):
                old_subcategory = subcategory
                subcategory = rule.target_name or subcategory
                if not sub_subcategory or sub_subcategory == (rule.sub_subcategory or ""):
                    sub_subcategory = old_subcategory

    product_data["category"] = category
    product_data["subcategory"] = subcategory
    product_data["sub_subcategory"] = sub_subcategory
    return product_data


def get_category_final_mappings_for_runtime(db: Session) -> List[CategoryFinalMapping]:
    """Chỉ mapping được đánh dấu áp cho import/cây danh mục (hành vi cũ / import JSON)."""
    return (
        db.query(CategoryFinalMapping)
        .filter(CategoryFinalMapping.apply_to_future_imports.is_(True))
        .order_by(CategoryFinalMapping.created_at.asc())
        .all()
    )


def canonical_restrict_product_ids_json(payload: Any) -> Optional[str]:
    """Chuẩn hoá danh sách product_id (API) → JSON string lưu DB; None = không giới hạn."""
    if payload is None:
        return None
    raw: Any = payload
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            raw = json.loads(s)
        except Exception:
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    ids = sorted({str(x).strip() for x in raw if str(x).strip()})
    if not ids:
        return None
    return json.dumps(ids, ensure_ascii=False)


def restrict_product_ids_set_from_value(stored: Any) -> Optional[Set[str]]:
    """Đọc cột DB / chuỗi JSON → tập id, hoặc None nếu không giới hạn."""
    if stored is None:
        return None
    if isinstance(stored, str) and not stored.strip():
        return None
    raw: Any = stored
    if isinstance(stored, str):
        try:
            raw = json.loads(stored)
        except Exception:
            return None
    if not isinstance(raw, (list, tuple)):
        return None
    ids = {str(x).strip() for x in raw if str(x).strip()}
    if not ids:
        return None
    return ids


def final_mapping_has_product_restrict(m: CategoryFinalMapping) -> bool:
    return restrict_product_ids_set_from_value(getattr(m, "restrict_product_ids", None)) is not None


def restrict_product_ids_list_for_api(stored: Any) -> List[str]:
    s = restrict_product_ids_set_from_value(stored)
    if not s:
        return []
    return sorted(s)


def apply_category_final_mapping_to_product(
    product_data: Dict[str, Any],
    mappings: List[CategoryFinalMapping],
) -> Dict[str, Any]:
    if not product_data:
        return product_data
    def _keep_or_value(value: Any, fallback: str) -> str:
        if value is None:
            return fallback
        if isinstance(value, str) and value.strip() == "":
            return fallback
        return str(value).strip()

    def _norm_name(val: Any) -> str:
        text = re.sub(r"\s+", " ", (val or "")).strip().lower()
        if not text:
            return ""
        try:
            return slugify_vietnamese(text)
        except Exception:
            return re.sub(r"\s+", " ", text).strip()

    category = (product_data.get("category") or "").strip()
    subcategory = (product_data.get("subcategory") or "").strip()
    sub_subcategory = (product_data.get("sub_subcategory") or "").strip()

    # Áp mapping theo thứ tự tạo, cho phép mapping nối tiếp (level2 -> level3)
    for m in mappings:
        n_category = _norm_name(category)
        n_subcategory = _norm_name(subcategory)
        n_sub_subcategory = _norm_name(sub_subcategory)
        from_c1 = _norm_name(m.from_category)
        from_c2 = _norm_name(m.from_subcategory)
        from_c3 = _norm_name(m.from_sub_subcategory)

        rset = restrict_product_ids_set_from_value(getattr(m, "restrict_product_ids", None))

        # Match đủ 3 cấp
        if n_category == from_c1 and n_subcategory == from_c2 and n_sub_subcategory == from_c3:
            if rset is not None:
                pid = str(product_data.get("product_id") or "").strip()
                if pid not in rset:
                    continue
            category = _keep_or_value(m.to_category, category)
            subcategory = _keep_or_value(m.to_subcategory, subcategory)
            sub_subcategory = _keep_or_value(m.to_sub_subcategory, sub_subcategory)
            continue

        # Match 2 cấp (wildcard cấp 3)
        if n_category == from_c1 and n_subcategory == from_c2 and from_c3 == "":
            if rset is not None:
                pid = str(product_data.get("product_id") or "").strip()
                if pid not in rset:
                    continue
            category = _keep_or_value(m.to_category, category)
            subcategory = _keep_or_value(m.to_subcategory, subcategory)
            # giữ nguyên cấp 3 hiện tại nếu mapping không set cấp 3
            sub_subcategory = _keep_or_value(m.to_sub_subcategory, sub_subcategory)

    product_data["category"] = category
    product_data["subcategory"] = subcategory
    product_data["sub_subcategory"] = sub_subcategory
    return product_data


def _row_matches_single_final_mapping_source(product_data: Dict[str, Any], m: CategoryFinalMapping) -> bool:
    """Khớp nguồn đủ 3 cấp + restrict (cùng chuẩn hoá slugify như apply_category_final_mapping_to_product)."""
    if not product_data:
        return False

    def _norm(val: Any) -> str:
        text = re.sub(r"\s+", " ", (val or "")).strip().lower()
        if not text:
            return ""
        try:
            return slugify_vietnamese(text)
        except Exception:
            return re.sub(r"\s+", " ", text).strip()

    n1 = _norm(product_data.get("category"))
    n2 = _norm(product_data.get("subcategory"))
    n3 = _norm(product_data.get("sub_subcategory"))
    f1 = _norm(m.from_category)
    f2 = _norm(m.from_subcategory)
    f3 = _norm(m.from_sub_subcategory)
    if n1 != f1 or n2 != f2 or n3 != f3:
        return False
    rset = restrict_product_ids_set_from_value(getattr(m, "restrict_product_ids", None))
    if rset is not None:
        pid = str(product_data.get("product_id") or "").strip()
        if pid not in rset:
            return False
    return True


def _norm_triple_cat_values(c1: Any, c2: Any, c3: Any) -> tuple:
    def _norm(val: Any) -> str:
        text = re.sub(r"\s+", " ", (val or "")).strip().lower()
        if not text:
            return ""
        try:
            return slugify_vietnamese(text)
        except Exception:
            return re.sub(r"\s+", " ", text).strip()

    return (_norm(c1), _norm(c2), _norm(c3))


def _product_in_scope_for_final_mapping_batch(p: Product, m: CategoryFinalMapping) -> bool:
    """
    SP có cần xử lý batch mapping: đang ở nguồn; hoặc raw_* còn nguồn; hoặc (có restrict + pid + đã ở đích).
    """
    cur = {
        "product_id": p.product_id,
        "category": p.category,
        "subcategory": p.subcategory,
        "sub_subcategory": p.sub_subcategory,
    }
    if _row_matches_single_final_mapping_source(cur, m):
        return True
    r1 = (getattr(p, "raw_category", None) or "").strip()
    r2 = (getattr(p, "raw_subcategory", None) or "").strip()
    r3 = (getattr(p, "raw_sub_subcategory", None) or "").strip()
    if r1 and r2 and r3:
        raw_d = {"product_id": p.product_id, "category": r1, "subcategory": r2, "sub_subcategory": r3}
        if _row_matches_single_final_mapping_source(raw_d, m):
            return True
    rset = restrict_product_ids_set_from_value(getattr(m, "restrict_product_ids", None))
    if rset is not None and (p.product_id or "").strip() in rset:
        t_cur = _norm_triple_cat_values(p.category, p.subcategory, p.sub_subcategory)
        t_to = _norm_triple_cat_values(m.to_category, m.to_subcategory, m.to_sub_subcategory)
        if t_cur == t_to:
            return True
    t_cur = _norm_triple_cat_values(p.category, p.subcategory, p.sub_subcategory)
    t_to = _norm_triple_cat_values(m.to_category, m.to_subcategory, m.to_sub_subcategory)
    if t_cur == t_to and p.category_id is None:
        return True
    return False


def _build_cat3_triple_name_lookup(db: Session) -> Dict[str, int]:
    """Tên hiển thị c1\\x1fc2\\x1fc3 (chữ thường) → id Category cấp 3."""
    from app.models.category import Category as _Cat

    rows = db.query(_Cat.id, _Cat.parent_id, _Cat.level, _Cat.name).all()
    by_id = {r.id: r for r in rows}
    out: Dict[str, int] = {}
    for r in rows:
        if r.level != 3:
            continue
        c3n = (r.name or "").strip()
        if not c3n:
            continue
        p2 = by_id.get(r.parent_id)
        if not p2 or p2.level != 2:
            continue
        p1 = by_id.get(p2.parent_id)
        if not p1 or p1.level != 1:
            continue
        c1n = (p1.name or "").strip()
        c2n = (p2.name or "").strip()
        if not c1n or not c2n:
            continue
        out[f"{c1n.lower()}\x1f{c2n.lower()}\x1f{c3n.lower()}"] = r.id
    return out


def _sync_product_category_id_from_taxonomy(
    p: Product,
    triple_idx: Dict[str, int],
    cat3_idx: Dict[str, Dict[str, int]],
) -> None:
    """Gán `product.category_id` theo taxonomy để /c/<cluster> và API cluster đếm đúng."""
    c1 = (p.category or "").strip()
    c2 = (p.subcategory or "").strip()
    c3 = (p.sub_subcategory or "").strip()
    if not c1 or not c2 or not c3:
        p.category_id = None
        return
    key = f"{c1.lower()}\x1f{c2.lower()}\x1f{c3.lower()}"
    cid = triple_idx.get(key)
    if cid is None:
        cid = _resolve_category_id_from_row(
            {"category": p.category, "subcategory": p.subcategory, "sub_subcategory": p.sub_subcategory},
            cat3_idx,
        )
    p.category_id = cid


def batch_apply_final_mapping_to_products(db: Session, mapping: CategoryFinalMapping) -> int:
    """
    Gán trực tiếp category / subcategory / sub_subcategory trên `products` khớp *nguồn* của một CategoryFinalMapping.

    Chỉ áp khi `from_sub_subcategory` không rỗng (đã chọn danh mục cấp 3 nguồn cụ thể).
    Mapping kiểu wildcard cấp 3 rỗng không đụng DB để không gộp nhầm toàn bộ L3 dưới một L2.

    Khớp nguồn dùng cùng logic slug như `apply_category_final_mapping_to_product`.

    Đồng bộ thêm `category_id` (FK → categories cat3) để trang landing `/c/<cluster_slug>` đếm SP đúng —
    API cluster dùng `product.category_id IN cat3_ids`, không quét theo chuỗi 3 cột.
    """
    if not (mapping.from_sub_subcategory or "").strip():
        return 0
    mappings_one = [mapping]
    updated = 0
    restrict = restrict_product_ids_set_from_value(getattr(mapping, "restrict_product_ids", None))
    q = db.query(Product)
    if restrict is not None:
        q = q.filter(Product.product_id.in_(restrict))
    triple_idx = _build_cat3_triple_name_lookup(db)
    cat3_idx = _build_cat3_lookup_indexes(db)
    for p in q.all():
        orig = {
            "product_id": p.product_id,
            "category": p.category,
            "subcategory": p.subcategory,
            "sub_subcategory": p.sub_subcategory,
        }
        if not _product_in_scope_for_final_mapping_batch(p, mapping):
            continue
        new_d = apply_category_final_mapping_to_product(dict(orig), mappings_one)
        str_changed = (
            (orig.get("category") or "").strip() != (new_d.get("category") or "").strip()
            or (orig.get("subcategory") or "").strip() != (new_d.get("subcategory") or "").strip()
            or (orig.get("sub_subcategory") or "").strip() != (new_d.get("sub_subcategory") or "").strip()
        )
        if str_changed:
            p.category = new_d.get("category")
            p.subcategory = new_d.get("subcategory")
            p.sub_subcategory = new_d.get("sub_subcategory")
        old_cid = p.category_id
        _sync_product_category_id_from_taxonomy(p, triple_idx, cat3_idx)
        if str_changed or p.category_id != old_cid:
            updated += 1
    if updated > 0:
        try:
            from app.utils.ttl_cache import cache as ttl_cache

            ttl_cache.invalidate_all()
        except Exception:
            pass
    return updated


def resync_all_product_category_ids_from_display_path(db: Session, is_active_only: bool = True) -> int:
    """
    Gán lại `product.category_id` từ (category, subcategory, sub_subcategory) cho mọi SP.
    Dùng khi đã đúng 3 chuỗi (vd sau mapping) nhưng `/c/<cluster_slug>` vẫn 0 do thiếu/ sai FK.
    """
    triple_idx = _build_cat3_triple_name_lookup(db)
    cat3_idx = _build_cat3_lookup_indexes(db)
    q = db.query(Product)
    if is_active_only:
        q = q.filter(Product.is_active.is_(True))
    n = 0
    for p in q.all():
        old = p.category_id
        _sync_product_category_id_from_taxonomy(p, triple_idx, cat3_idx)
        if p.category_id != old:
            n += 1
    if n > 0:
        try:
            from app.utils.ttl_cache import cache as ttl_cache

            ttl_cache.invalidate_all()
        except Exception:
            pass
    return n


def _excel_str(row: Dict, *keys: str) -> str:
    """Đọc ô Excel theo một trong các tên cột (EN hoặc header tiếng Việt trên file mẫu)."""
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("nan", "none", "null"):
            return s
    return ""


def _clean_excel_text(value: Any, *, max_len: Optional[int] = None) -> str:
    """Chuẩn hóa text từ Excel cho cột String: bỏ NaN/rỗng và cắt theo giới hạn DB."""
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return ""
    if max_len is not None and max_len > 0:
        return s[:max_len]
    return s


def _merge_excel_full_text_into_product_info(product_info: Any, *, color_full: str = "") -> Dict[str, Any]:
    """Giữ giá trị Excel dài trong JSON để cột String DB có thể cắt ngắn mà không mất dữ liệu."""
    pi = product_info if isinstance(product_info, dict) else {}
    variants = pi.get("variants")
    if not isinstance(variants, dict):
        variants = {}
        pi["variants"] = variants
    if color_full:
        variants.setdefault("colors", color_full)
    return pi


def _excel_listed_raw(row: Dict[str, Any]) -> Any:
    """
    Đọc ô «listed» / «Trong danh sách»: khi read_excel dùng hàng 2 làm header, tên cột là tiếng Việt
    (vd. «Trong danh sách (1=import, 0=xóa DB)»), không phải khóa `listed` — khi đó row.get('listed') luôn None
    và hệ thống coi như 1 → chỉ cập nhật. Phải khớp mọi alias + mọi cột có tiền tố «Trong danh sách».
    Giá trị 0 hợp lệ (không được bỏ qua như ô rỗng).
    """
    explicit = (
        "listed",
        "Trong danh sách (1=import, 0=xóa DB)",
        "Trong danh sách (1=cập nhật, 0=gỡ)",
        "Trong danh sách",
        "trong_danh_sach",
        "Trong danh sach",
    )
    for k in explicit:
        if k not in row:
            continue
        v = row[k]
        if v is None:
            continue
        if isinstance(v, float) and math.isnan(v):
            continue
        if isinstance(v, str) and str(v).strip() == "":
            continue
        return v
    for col, v in row.items():
        if col is None:
            continue
        cs = str(col).strip().lower()
        if cs == "listed" or cs.startswith("trong danh sách"):
            if v is None:
                continue
            if isinstance(v, float) and math.isnan(v):
                continue
            if isinstance(v, str) and str(v).strip() == "":
                continue
            return v
    return None


def excel_row_to_product(row: Dict) -> Dict:
    """
    Convert Excel row (~40 cột: tới `chinese_name`, `shop_name_chinese`, `listed`) to product dictionary.
    Cột «listed» 0: bulk_import xóa bản ghi Product khỏi DB (nếu tồn tại); không tạo SP mới.
    """
    try:
        # Lấy các giá trị cơ bản
        product_id = _clean_excel_text(row.get('id'), max_len=255)
        product_name = _clean_excel_text(row.get('name'), max_len=500)
        
        # Cột A (id): a990013135592 hoặc a990013135592a188F6946 — cùng prefix = một SP (import chỉ cập nhật).
        # VALIDATION: Product ID là bắt buộc
        if not product_id or product_id.lower() == 'nan':
            logger.warning(f"Missing product_id in row: {row.get('name', 'No name')}")
            return {}
        
        # VALIDATION: Tên sản phẩm là bắt buộc
        if not product_name or product_name.lower() == 'nan':
            logger.warning(f"Missing product name for ID: {product_id}")
            product_name = f"Sản phẩm {product_id}"
        
        # Tạo slug từ tên sản phẩm và product_id
        slug_value = generate_consistent_slug(product_name, product_id)

        listed_cell = listed_from_excel_cell(_excel_listed_raw(row), default=1)
        # Nội bộ bulk_import: pop trước khi ORM — không phải cột Product
        excel_import_listed = 1 if listed_cell else 0

        # FIX: Xử lý Features - có thể là string hoặc JSON
        features_value = row.get('Features', '')
        features_list = []
        
        if features_value and str(features_value).strip() != '':
            if isinstance(features_value, str):
                # Nếu là JSON array
                if features_value.startswith('[') and features_value.endswith(']'):
                    try:
                        parsed = json.loads(features_value)
                        if isinstance(parsed, list):
                            features_list = [str(item) for item in parsed]
                        else:
                            features_list = [str(features_value)]
                    except json.JSONDecodeError:
                        # Nếu không parse được JSON, xử lý như text thường
                        items = [item.strip() for item in features_value.split(',') if item.strip()]
                        features_list = items
                else:
                    # Nếu là text thường, tách bằng dấu phẩy
                    items = [item.strip() for item in features_value.split(',') if item.strip()]
                    features_list = items
            elif isinstance(features_value, list):
                features_list = [str(item) for item in features_value]
        
        # 36 CỘT EXCEL MAPPING - ĐÃ FIX
        # Cột Shop id (I) đồng bộ với cột Style (AI): nguồn là ô Style.
        style_cell = _clean_excel_text(row.get('Style'), max_len=100)
        color_full = _clean_excel_text(row.get('Color'))
        product_info_value = _parse_product_info(
            row.get('product_info')
            or row.get('Thông tin sản phẩm')
            or row.get('thong_tin_san_pham')
            or row.get('Thong tin san pham')
        )
        product_info_value = _merge_excel_full_text_into_product_info(
            product_info_value,
            color_full=color_full,
        )
        product_data = {
            'product_id': product_id,
            'code': _clean_excel_text(row.get('sku'), max_len=100),
            'origin': _clean_excel_text(row.get('origin'), max_len=100),
            'brand_name': _clean_excel_text(row.get('brand'), max_len=200),
            'name': product_name,
            'description': _clean_excel_text(row.get('pro_content')),
            'price': safe_float(row.get('price', 0)),
            'shop_name': _clean_excel_text(row.get('shop_name'), max_len=200),
            'shop_id': style_cell,
            'pro_lower_price': _clean_excel_text(row.get('pro_lower_price'), max_len=255),
            'pro_high_price': _clean_excel_text(row.get('pro_high_price'), max_len=255),
            'group_rating': safe_int(row.get('rating_group_id', 0)),
            'group_question': safe_int(row.get('question_group_id', 0)),
            'sizes': parse_json_field(row.get('sizes', '[]')),
            'colors': parse_json_field(row.get('Variant', '[]')),
            'images': parse_json_field(row.get('gallery_images', '[]')),
            'gallery': parse_json_field(row.get('detail_images', '[]')),
            'link_default': _clean_excel_text(row.get('product_url'), max_len=500),
            'video_link': _clean_excel_text(row.get('video_url'), max_len=500),
            'main_image': _clean_excel_text(row.get('main_image'), max_len=500),
            'likes': safe_int(row.get('likes_count', 0)),
            'purchases': safe_int(row.get('purchases_count', 0)),
            'rating_total': safe_int(row.get('reviews_count', 0)),
            'question_total': safe_int(row.get('questions_count', 0)),
            'rating_point': safe_float(row.get('rating_score', 0.0)),
            'available': safe_int(row.get('stock_quantity', 500)),
            'deposit_require': deposit_require_from_excel_cell(row.get("deposit_required")),
            'category': _clean_excel_text(row.get('Main Category'), max_len=100),
            'subcategory': _clean_excel_text(row.get('Subcategory'), max_len=100),
            'sub_subcategory': _clean_excel_text(row.get('Sub-subcategory'), max_len=100),
            'raw_category': _clean_excel_text(row.get('Main Category'), max_len=100),
            'raw_subcategory': _clean_excel_text(row.get('Subcategory'), max_len=100),
            'raw_sub_subcategory': _clean_excel_text(row.get('Sub-subcategory'), max_len=100),
            'material': _clean_excel_text(row.get('Material'), max_len=100),
            'style': style_cell,
            # FIX: Cột Color -> color (đúng mapping)
            'color': _clean_excel_text(color_full, max_len=100),
            # FIX: Cột Occasion -> occasion (đúng mapping)
            'occasion': _clean_excel_text(row.get('Occasion'), max_len=100),
            # FIX: Features xử lý đúng
            'features': features_list,
            'weight': _clean_excel_text(row.get('Weight'), max_len=100),
            # Cột AK: Thông tin sản phẩm (JSON) - thử nhiều tên cột
            'product_info': product_info_value,
            'chinese_name': _excel_str(
                row,
                'chinese_name',
                'al chinese_name',
                'AL chinese_name',
                'Chinese name',
                'chinese name',
                'Tên tiếng trung',
                'Tên tiếng Trung',
            ),
            'shop_name_chinese': _clean_excel_text(_excel_str(row, 'shop_name_chinese', 'Shop Trung Quốc'), max_len=200),
            'slug': slug_value,
            'excel_import_listed': excel_import_listed,
            'is_active': bool(excel_import_listed),
            'created_at': datetime.now()
        }

        normalize_product_data_image_urls_for_db(product_data)

        from app.services.warehouse_clearance import parse_warehouse_product_id

        wh_parsed = parse_warehouse_product_id(product_id)
        if wh_parsed:
            product_data['is_warehouse_clearance'] = True
            product_data['base_sku'] = wh_parsed['base_sku']
            if not str(product_data.get('code') or '').strip():
                product_data['code'] = wh_parsed['base_sku']
        
        # Debug log để kiểm tra
        logger.debug(f"✅ Converted: {product_id}")
        logger.debug(f"   Color: '{product_data['color']}'")
        logger.debug(f"   Occasion: '{product_data['occasion']}'")
        logger.debug(f"   Features: {product_data['features']}")
        
        return product_data
        
    except Exception as e:
        logger.error(f"❌ Error converting Excel row: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

def product_to_excel_row(product: Product) -> Dict:
    """Convert Product to Excel row — product_info (AK), chinese_name, shop_name_chinese, Slug."""
    try:
        # Đảm bảo có slug
        slug_value = product.slug
        if not slug_value:
            slug_value = generate_consistent_slug(product.name, product.product_id)
        
        # FIX: Xử lý Features cho export
        features_export = ""
        if product.features:
            if isinstance(product.features, list):
                # Nếu là list, chuyển thành string với dấu phẩy
                features_export = ", ".join([str(item) for item in product.features])
            elif isinstance(product.features, str):
                features_export = product.features
            else:
                try:
                    features_export = json.dumps(product.features, ensure_ascii=False)
                except:
                    features_export = str(product.features)
        
        # 37 CỘT EXPORT MAPPING - ĐÃ FIX
        # H–K (shop_name, shop_id, pro_lower_price, pro_high_price): để trống trên file Excel xuất ra.
        _style_out = (product.style or "").strip() if isinstance(product.style, str) else (str(product.style).strip() if product.style is not None else "")
        excel_row = {
            'id': product.product_id or '',
            'sku': product.code or '',
            'origin': '',
            'brand': '',
            'name': product.name or '',
            'pro_content': product.description or '',
            'price': product.price or 0,
            'shop_name': '',
            'shop_id': '',
            'pro_lower_price': '',
            'pro_high_price': '',
            'rating_group_id': product.group_rating or 0,
            'question_group_id': product.group_question or 0,
            'sizes': json.dumps(product.sizes or [], ensure_ascii=False),
            'Variant': json.dumps(product.colors or [], ensure_ascii=False),
            'gallery_images': json.dumps(product.images or [], ensure_ascii=False),
            'detail_images': json.dumps(product.gallery or [], ensure_ascii=False),
            'product_url': product.link_default or '',
            'video_url': product.video_link or '',
            'main_image': product.main_image or '',
            'likes_count': product.likes or 0,
            'purchases_count': product.purchases or 0,
            'reviews_count': product.rating_total or 0,
            'questions_count': product.question_total or 0,
            'rating_score': product.rating_point or 0.0,
            'stock_quantity': product.available or 0,
            'deposit_required': deposit_require_to_excel_int(product.deposit_require, default=0),
            'Main Category': product.category or '',
            'Subcategory': product.subcategory or '',
            'Sub-subcategory': product.sub_subcategory or '',
            'Material': product.material or '',
            'Style': _style_out,
            # FIX: Cột 33: Color -> Color (đúng vị trí)
            'Color': product.color or '',
            # FIX: Cột 34: Occasion -> Occasion (đúng vị trí)
            'Occasion': product.occasion or '',
            # FIX: Cột 35: Features -> Text thường (không phải JSON)
            'Features': features_export,
            'Weight': product.weight or '',
            # Cột AK: Thông tin sản phẩm (JSON)
            'product_info': json.dumps(product.product_info, ensure_ascii=False) if getattr(product, 'product_info', None) else '',
            'chinese_name': getattr(product, 'chinese_name', None) or '',
            'shop_name_chinese': getattr(product, 'shop_name_chinese', None) or '',
            # Slug (sau hai cột tiếng Trung — file đầy đủ có thể 40 cột)
            'Slug': slug_value,
            # 1 = đang hiển thị; 0 = đã ẩn (export trước khi xóa)
            'listed': deposit_require_to_excel_int(getattr(product, "is_active", True), default=1),
        }
        
        # Debug log
        logger.debug(f"✅ Exporting: {product.product_id}")
        logger.debug(f"   Color export: '{excel_row['Color']}'")
        logger.debug(f"   Occasion export: '{excel_row['Occasion']}'")
        logger.debug(f"   Features export: '{excel_row['Features'][:50]}...'")
        
        return excel_row
        
    except Exception as e:
        logger.error(f"❌ Error converting product to Excel row: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {}

# ========== CRUD FUNCTIONS ==========

def get_product(db: Session, product_id: int):
    return db.query(Product).filter(Product.id == product_id).first()

def get_product_by_product_id(db: Session, product_id: str):
    return db.query(Product).filter(Product.product_id == product_id).first()


def get_product_by_code(db: Session, code: str) -> Optional[Product]:
    c = (code or "").strip()
    if not c:
        return None
    try:
        return db.query(Product).filter(sql_func.lower(Product.code) == c.lower()).first()
    except Exception as e:
        logger.error(f"Database error get_product_by_code: {str(e)}")
        return None


def resolve_product_by_sku(db: Session, sku: str) -> Optional[Product]:
    """Tra SP theo product_id, slug hoặc mã code (SKU nội bộ / NanoAI)."""
    s = (sku or "").strip()
    if not s:
        return None
    product = get_product_by_product_id(db, product_id=s)
    if product is not None:
        return product
    product = get_product_by_slug(db, slug=s)
    if product is not None:
        return product
    return get_product_by_code(db, code=s)

_LISTING_PARSER_AT_NUMERIC_ONLY = re.compile(r"^[AT]\d+$", re.IGNORECASE)


def normalize_listing_parser_external_id(raw: Optional[str]) -> str:
    """
    Chuỗi id từ parse HTML listing: A/T + chỉ chữ số → chuẩn hoa A/T; còn lại chỉ strip.
    """
    t = (raw or "").strip()
    if not t:
        return ""
    if len(t) >= 2 and t[1:].isdigit():
        prefix = (t[0] or "").upper()
        if prefix in ("A", "T"):
            return f"{prefix}{t[1:]}"
    return t


def listing_parser_ids_existing_in_products(
    db: Session, candidate_external_ids: List[str], *, active_only: bool = False
) -> Set[str]:
    """
    Đánh dấu id listing (vd A945… sau chuẩn hoa) là đã có trong bảng ``products`` nếu:
    - `products.product_id` trùng chính xác, hoặc
    - `product_id` bắt đầu bằng `{id}a188…` (mã nội bộ nhập Hibox/1688 kèm SKU).

    ``active_only=True``: chỉ các SP đang ``is_active`` (đang lên web catalog).
    """
    out: Set[str] = set()
    normalized_unique: Dict[str, str] = {}  # key chuẩn → canonical (duplicate input gộp 1 khóa)
    for raw in candidate_external_ids:
        n = normalize_listing_parser_external_id(raw)
        if not n:
            continue
        normalized_unique.setdefault(n, n)

    cands = list(normalized_unique.keys())
    if not cands:
        return out

    q_exact = db.query(Product.product_id).filter(Product.product_id.in_(cands))
    if active_only:
        q_exact = q_exact.filter(Product.is_active.is_(True))
    found_exact_rows = q_exact.all()
    exact_db = {r[0] for r in found_exact_rows}
    need_prefix_scan: List[str] = []

    for c in cands:
        if c in exact_db:
            out.add(normalized_unique[c])
        else:
            need_prefix_scan.append(c)

    like_patterns = sorted({f"{c}a188%" for c in need_prefix_scan if _LISTING_PARSER_AT_NUMERIC_ONLY.fullmatch(c)})
    if not like_patterns:
        return out

    q_like = db.query(Product.product_id).filter(or_(*[Product.product_id.like(p) for p in like_patterns]))
    if active_only:
        q_like = q_like.filter(Product.is_active.is_(True))
    hit_rows = q_like.all()
    hit_ids = [r[0] for r in hit_rows]

    for c in need_prefix_scan:
        if not _LISTING_PARSER_AT_NUMERIC_ONLY.fullmatch(c):
            continue
        needle = f"{c}a188"
        if any((pid or "").startswith(needle) for pid in hit_ids):
            out.add(normalized_unique[c])

    return out


def _build_product_id_or_code_filter(term: str):
    """
    Lọc admin/storefront theo ID Excel, prefix nguồn (A/T + số), SKU nội bộ hoặc khớp một phần.
    Vd. «A1045143359347» hoặc chỉ «1045143359347» → «A1045143359347a188K0842»; «K0842» → code / a188SKU.
    """
    t = (term or "").strip()
    if not t:
        return None

    clauses = []
    tu = t.upper()
    digits_only = t.isdigit()

    clauses.extend(
        [
            Product.product_id == t,
            Product.code == t,
            sql_func.upper(sql_func.trim(Product.code)) == tu,
            Product.base_sku == t,
            sql_func.upper(sql_func.trim(Product.base_sku)) == tu,
        ]
    )

    norm_listing = normalize_listing_parser_external_id(t)
    if norm_listing:
        clauses.append(Product.product_id == norm_listing)
        if _LISTING_PARSER_AT_NUMERIC_ONLY.fullmatch(norm_listing):
            clauses.append(Product.product_id.ilike(f"{norm_listing}a188%"))
            clauses.append(Product.product_id.ilike(f"{norm_listing}%"))

    # Chỉ dãy số (không có A/T): coi là mã nguồn 1688/Taobao — thử A… và T…
    if digits_only and len(t) >= 4:
        for pfx in ("A", "T"):
            prefixed = f"{pfx}{t}"
            clauses.append(Product.product_id == prefixed)
            clauses.append(Product.product_id.ilike(f"{prefixed}a188%"))
            clauses.append(Product.product_id.ilike(f"{prefixed}%"))
        clauses.append(Product.product_id.ilike(f"%{t}%"))

    try:
        from app.services.product_internal_sku import internal_sku_is_valid_format

        if internal_sku_is_valid_format(t):
            clauses.append(sql_func.upper(sql_func.trim(Product.code)) == tu)
            clauses.append(Product.product_id.ilike(f"%a188{tu}%"))
    except Exception:
        pass

    seg = split_product_id_web_prefix_and_internal_sku(t)
    if seg and seg.get("sku"):
        clauses.append(sql_func.upper(sql_func.trim(Product.code)) == seg["sku"])
        clauses.append(Product.product_id.ilike(f"%a188{seg['sku']}%"))

    if _PRODUCT_ID_A188_RE.search(t):
        clauses.append(Product.product_id.ilike(f"%{t}%"))

    if digits_only:
        try:
            pk = int(t)
            if 0 < pk <= 2_147_483_647:
                clauses.append(Product.id == pk)
        except ValueError:
            pass
    elif len(t) >= 3:
        like = f"%{t}%"
        clauses.extend(
            [
                Product.product_id.ilike(like),
                Product.code.ilike(like),
                Product.base_sku.ilike(like),
            ]
        )

    return or_(*clauses)


def listing_parser_ids_with_done_drafts(db: Session, candidate_external_ids: List[str]) -> Set[str]:
    """
    Id listing (A|T + chữ số sau chuẩn hóa) đã có bản nháp import crawl xong:
    ``status == done``, ``product_data`` có dữ liệu — dù chưa đăng lên ``products``.
    Khớp ``source_offer_id`` (1688 = chỉ số offer; Hibox = ``abb-<số>`` hoặc slug số Taobao).
    """
    from app.models.product_import_draft import ProductImportDraft

    normalized_unique: Dict[str, str] = {}
    a_digits: Set[str] = set()
    t_digits: Set[str] = set()
    for raw in candidate_external_ids:
        n = normalize_listing_parser_external_id(raw)
        if not n:
            continue
        normalized_unique.setdefault(n, n)
        if not _LISTING_PARSER_AT_NUMERIC_ONLY.fullmatch(n):
            continue
        prefix = (n[0] or "").upper()
        body = n[1:]
        if not body.isdigit():
            continue
        if prefix == "A":
            a_digits.add(body)
        elif prefix == "T":
            t_digits.add(body)

    if not a_digits and not t_digits:
        return set()

    hibox_offer_ids: Set[str] = set(t_digits)
    hibox_offer_ids.update(f"abb-{d}" for d in a_digits)

    clauses = []
    if a_digits:
        clauses.append(
            and_(ProductImportDraft.source == "1688", ProductImportDraft.source_offer_id.in_(sorted(a_digits)))
        )
    if hibox_offer_ids:
        clauses.append(
            and_(
                ProductImportDraft.source == "hibox",
                ProductImportDraft.source_offer_id.in_(sorted(hibox_offer_ids)),
            )
        )
    if not clauses:
        return set()

    rows = (
        db.query(ProductImportDraft.source, ProductImportDraft.source_offer_id, ProductImportDraft.product_data)
        .filter(
            ProductImportDraft.status == "done",
            ProductImportDraft.product_data.isnot(None),
            or_(*clauses),
        )
        .all()
    )

    matched_norm: Set[str] = set()
    for src, oid, pdata in rows:
        if pdata is None or (isinstance(pdata, dict) and len(pdata) == 0):
            continue
        oid_s = str(oid or "").strip()
        if not oid_s:
            continue
        src_l = (src or "").strip().lower()
        if src_l == "1688" and oid_s.isdigit() and oid_s in a_digits:
            matched_norm.add(f"A{oid_s}")
        elif src_l == "hibox":
            mabb = re.match(r"(?i)^abb-(\d+)$", oid_s)
            if mabb:
                d = mabb.group(1)
                if d in a_digits:
                    matched_norm.add(f"A{d}")
            elif oid_s.isdigit():
                if oid_s in t_digits:
                    matched_norm.add(f"T{oid_s}")

    out: Set[str] = set()
    for n_key, canon in normalized_unique.items():
        if n_key in matched_norm:
            out.add(canon)
    return out


def normalize_search_query(q: str) -> str:
    """
    Chuẩn tắc cụm từ tìm kiếm: trim, fix case (Cao lông nam đế).
    Ví dụ: " Cao Lông nam Đế" -> "Cao lông nam đế" (chữ đầu câu viết hoa, còn lại thường)
    """
    if not q or not isinstance(q, str):
        return ""
    s = q.strip().lower()
    if not s:
        return ""
    words = s.split()
    if not words:
        return ""
    normalized = [words[0].capitalize()] + [w for w in words[1:] if w]
    return " ".join(normalized)


def _infer_gender_context(
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    q: Optional[str],
) -> Optional[str]:
    """Suy luận giới tính/đối tượng từ context để gợi ý AI."""
    text = " ".join([s for s in [category, subcategory, sub_subcategory, q] if s])
    if not text:
        return None
    s = text.lower()
    has_nam = re.search(r"\bnam\b", s) is not None
    has_nu = re.search(r"\b(nu|nữ)\b", s) is not None
    has_kid = re.search(r"\b(be|bé|tre em|trẻ em|kid|kids)\b", s) is not None
    if has_kid:
        return "trẻ em"
    if has_nam and not has_nu:
        return "nam"
    if has_nu and not has_nam:
        return "nữ"
    return None


def _apply_word_mapping(words: List[str]) -> List[str]:
    """Áp dụng mapping từ phổ biến (thiếu dấu -> đúng)."""
    result = []
    for w in words:
        w_lower = w.lower()
        result.append(COMMON_WORD_MAPPING.get(w_lower, w))
    return result


def _search_products_sale_keyword(
    db: Session,
    query,
    limit: int,
    skip: int,
    *,
    sort: str = "id_desc",
):
    """
    Từ khóa «sale» / kho thanh lý: tên hoặc slug chứa sale, hoặc SP gốc còn biến thể kho thanh lý.
    """
    sale_pat = "%sale%"
    search_concat = sql_func.concat(
        sql_func.coalesce(Product.name, ""), " ",
        sql_func.coalesce(Product.slug, ""), " ",
        sql_func.coalesce(Product.code, ""), " ",
        sql_func.coalesce(Product.category, ""), " ",
        sql_func.coalesce(Product.subcategory, ""), " ",
        sql_func.coalesce(Product.sub_subcategory, ""), " ",
        sql_func.coalesce(Product.material, ""), " ",
        sql_func.coalesce(Product.style, ""), " ",
        sql_func.coalesce(Product.color, ""), " ",
        sql_func.coalesce(Product.occasion, ""), " ",
        sql_func.coalesce(cast(Product.features, String), ""), " ",
        sql_func.coalesce(cast(Product.sizes, String), ""), " ",
        sql_func.coalesce(cast(Product.product_info, String), ""),
    )
    search_concat_norm = sql_func.lower(search_concat)

    wh_rows = (
        db.query(Product.base_sku, Product.product_id)
        .filter(
            Product.is_warehouse_clearance == True,  # noqa: E712
            Product.is_active == True,  # noqa: E712
            Product.available > 0,
        )
        .all()
    )
    parent_keys: set[str] = set()
    for base_sku, product_id in wh_rows:
        sku = str(base_sku or "").strip()
        if sku:
            parent_keys.add(sku)
        pid = str(product_id or "").strip()
        if "/" in pid:
            parent_keys.add(pid.split("/")[0].strip())

    parent_match = []
    if parent_keys:
        parent_match.append(Product.code.in_(list(parent_keys)))
        parent_match.append(Product.product_id.in_(list(parent_keys)))

    sale_match = [search_concat_norm.ilike(sale_pat)]
    if parent_match:
        sale_match.append(
            and_(
                or_(Product.is_warehouse_clearance == False, Product.is_warehouse_clearance.is_(None)),  # noqa: E712
                or_(*parent_match),
            )
        )

    q2 = query.filter(or_(*sale_match))
    vt_sub = None
    if sort == "views_desc":
        vt_sub = _product_view_totals_subquery()
        q2 = q2.outerjoin(vt_sub, Product.id == vt_sub.c.product_id)
    total = _count_products_query(q2)
    order_exprs = _order_exprs_for_product_list(sort, vt_sub)
    products = q2.order_by(*order_exprs).offset(skip).limit(limit).all()
    return total, products


def _search_products_by_words(
    db: Session,
    query,
    words: List[str],
    limit: int,
    skip: int,
    *,
    sort: str = "id_desc",
):
    """
    Tìm sản phẩm khi chuỗi tổng hợp chứa TẤT CẢ các từ (ilike).
    Chuỗi tổng hợp bao gồm: tên, mã, danh mục 1/2/3, chất liệu, kiểu dáng, màu sắc,
    dịp, tính năng, size, và cột AK (product_info - Thông tin sản phẩm).
    KHÔNG tìm kiếm trong mô tả sản phẩm.
    """
    query = apply_product_search_word_filters(query, words)
    vt_sub = None
    if sort == "views_desc":
        vt_sub = _product_view_totals_subquery()
        query = query.outerjoin(vt_sub, Product.id == vt_sub.c.product_id)
    total = _count_products_query(query)
    order_exprs = _order_exprs_for_product_list(sort, vt_sub)
    products = query.order_by(*order_exprs).offset(skip).limit(limit).all()
    return total, products


def apply_product_search_word_filters(query, words: List[str]):
    """
    Áp lọc «tất cả từ khớp ilike» trên chuỗi tổng hợp (giống _search_products_by_words).
    """
    from sqlalchemy.sql import func
    from sqlalchemy import cast, String

    search_concat = func.concat(
        func.coalesce(Product.name, ""), " ",
        func.coalesce(Product.slug, ""), " ",
        func.coalesce(Product.code, ""), " ",
        func.coalesce(Product.category, ""), " ",
        func.coalesce(Product.subcategory, ""), " ",
        func.coalesce(Product.sub_subcategory, ""), " ",
        func.coalesce(Product.material, ""), " ",
        func.coalesce(Product.style, ""), " ",
        func.coalesce(Product.color, ""), " ",
        func.coalesce(Product.occasion, ""), " ",
        func.coalesce(cast(Product.features, String), ""), " ",
        func.coalesce(cast(Product.sizes, String), ""), " ",
        func.coalesce(cast(Product.product_info, String), "")
    )
    search_concat_norm = func.lower(search_concat)
    for w in words:
        w_norm = (w or "").strip().lower()
        if not w_norm:
            continue
        query = query.filter(search_concat_norm.ilike(f"%{w_norm}%"))
    return query


def _count_products_query(query) -> int:
    """
    Đếm nhanh trên tập Product:
    - bỏ ORDER BY để planner không phải sort vô ích khi count.
    - tắt eager load/options không cần thiết cho truy vấn đếm.
    - dùng COUNT(products.id) thay vì query.count() dạng subquery full-column.
    """
    base = query.enable_eagerloads(False).order_by(None)
    try:
        return int(base.with_entities(sql_func.count(Product.id)).scalar() or 0)
    except Exception:
        try:
            # Fallback nhẹ: chỉ subquery Product.id thay vì full cột Product.
            id_subq = base.with_entities(Product.id).subquery()
            return int(query.session.query(sql_func.count()).select_from(id_subq).scalar() or 0)
        except Exception:
            # Last resort cho trường hợp query cực đặc biệt.
            return int(base.count() or 0)


_PRODUCT_SLUG_ID_SUFFIX_RE = re.compile(
    r"-(?:a|b)(\d{6,}a188[a-z0-9]+)$",
    flags=re.IGNORECASE,
)


def _maybe_repair_warehouse_slug(db: Session, row: Product) -> Product:
    """Slug cũ có '/' → cập nhật dạng ...-h0723-40-3 để URL PDP mở được."""
    if not row or "/" not in (row.slug or ""):
        return row
    new_slug = generate_consistent_slug(row.name or "", row.product_id or "")
    if not new_slug or new_slug == row.slug:
        return row
    try:
        row.slug = new_slug
        db.commit()
        db.refresh(row)
    except Exception as exc:
        logger.warning("repair warehouse slug failed for %s: %s", row.product_id, exc)
        db.rollback()
    return row


def _product_slug_lookup_variants(slug: str) -> List[str]:
    """Các biến thể slug từ URL (encode %2F, gạch ngang thay /)."""
    from urllib.parse import unquote

    from app.services.warehouse_clearance import warehouse_safe_slug_token

    out: List[str] = []

    def _add(v: str) -> None:
        v = (v or "").strip()
        if v and v not in out:
            out.append(v)

    _add(slug)
    try:
        _add(unquote(slug))
    except Exception:
        pass
    for base in list(out):
        _add(base.replace("%2F", "/").replace("%2f", "/"))
        _add(re.sub(r"[/\\]+", "-", base))
    # Slug marketing ...-khh0723-40-3 ↔ product_id khH0723/40/3
    for base in list(out):
        tail = base.split("-")[-3:]
        if len(tail) >= 2 and tail[-1].isdigit():
            guess = "/".join(tail)
            _add(guess)
            _add(guess.upper())
        safe = warehouse_safe_slug_token(base.split("-")[-1] if "/" in base else "")
        if safe:
            _add(safe)
    return out


def get_product_by_slug(db: Session, slug: str) -> Optional[Product]:
    """Tra SP theo slug; dòng kho thanh lý trả SP gốc (PDP nhóm) hoặc chính nó nếu không có gốc."""
    s = (slug or "").strip()
    if not s:
        return None
    try:
        from app.services.warehouse_clearance import (
            find_parent_product_by_base_sku,
            is_warehouse_clearance_product_id,
            parse_warehouse_product_id,
        )

        def _parent_for_warehouse_row(row: Product) -> Optional[Product]:
            if not (
                getattr(row, "is_warehouse_clearance", False)
                or is_warehouse_clearance_product_id(getattr(row, "product_id", None))
            ):
                return row
            parsed = parse_warehouse_product_id(getattr(row, "product_id", None))
            base = (parsed or {}).get("base_sku") or (getattr(row, "base_sku", None) or row.code or "")
            parent = find_parent_product_by_base_sku(db, str(base).strip())
            return parent if parent is not None else row

        row = None
        for cand in _product_slug_lookup_variants(s):
            row = db.query(Product).filter(Product.slug == cand).first()
            if row is not None:
                break
        if row is None and is_warehouse_clearance_product_id(s):
            row = get_product_by_product_id(db, product_id=s)
        if row is not None:
            row = _maybe_repair_warehouse_slug(db, row)
            return _parent_for_warehouse_row(row)

        # Slug marketing có suffix mã (vd. ...-a606864241417a188m7147) — thử tra product_id nhúng cuối slug
        m = _PRODUCT_SLUG_ID_SUFFIX_RE.search(s)
        if m:
            embedded = (m.group(0) or "").lstrip("-")
            if embedded:
                by_pid = get_product_by_product_id(db, product_id=embedded)
                if by_pid is not None:
                    return _parent_for_warehouse_row(by_pid)
                by_pid2 = get_product_by_product_id(db, product_id=embedded.upper())
                if by_pid2 is not None:
                    return _parent_for_warehouse_row(by_pid2)

        # URL marketing / index.php: ...-1141545 (số cuối = PK hoặc product_id Excel)
        m_tail = re.search(r"-(\d{5,})$", s)
        if m_tail:
            tail = (m_tail.group(1) or "").strip()
            if tail:
                try:
                    pk = int(tail)
                    if pk > 0:
                        row = get_product(db, product_id=pk)
                        if row is not None:
                            return _parent_for_warehouse_row(row)
                except (TypeError, ValueError):
                    pass
                by_pid = get_product_by_product_id(db, product_id=tail)
                if by_pid is not None:
                    return _parent_for_warehouse_row(by_pid)
                by_code = get_product_by_code(db, code=tail)
                if by_code is not None:
                    return _parent_for_warehouse_row(by_code)
        return None
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return None


# URL marketing một segment: /moi-ma-...-gia-1520k-giay-da-nam-...-g03-... (mã biến thể -g0x)
_LEGACY_MARKETING_PATH_RE = re.compile(r"(?:^|-)moi-ma-", re.IGNORECASE)
_LEGACY_GIA_PRICE_SEG_RE = re.compile(r"^\d{2,6}k$", re.IGNORECASE)
# Dừng trước segment mã biến thể: g03, g04, g05, g06, ... (không chỉ g06)
_LEGACY_VARIANT_SEG_RE = re.compile(r"^g0\d{1,2}$", re.IGNORECASE)
_LEGACY_TAIL_NOISE_SEGMENTS = frozenset(
    {
        "san",
        "pham",
        "moi",
        "mien",
        "phi",
        "van",
        "chuyen",
        "toan",
        "quoc",
        "hang",
        "sale",
        "hot",
        "free",
        "ship",
        "freeship",
        "km",
        "tang",
        "qua",
        "uu",
        "dai",
        "giam",
        "gia",
    }
)

# Ngưỡng giống slug nhóm (PDP hết hàng → chuyển sang biến thể / slug nhóm gần nhất).
PRODUCT_OOS_GROUP_SLUG_MIN_SIMILARITY = 0.8
# Số segment đầu của tên slug dùng làm pool ILIKE (vd ``ao-khoac-da-nam-da-bo-...`` → ``ao-khoac-da-nam%``).
PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS = 4
PRODUCT_OOS_GROUP_SLUG_POOL_CANDIDATE_LIMIT = 600
# URL marketing một segment (không phải slug PDP): nếu không đạt 80%, chọn SP gần nhất trong pool.
PRODUCT_OOS_LEGACY_PATH_FALLBACK_MIN_SIMILARITY = 0.42


def normalize_legacy_source_slug(source_slug: str) -> str:
    """Bỏ prefix index.php (URL cũ WordPress / marketing)."""
    s = (source_slug or "").strip().lower()
    if not s:
        return ""
    if "index.php/" in s:
        s = s.split("index.php/", 1)[-1]
    elif s.startswith("index.php"):
        s = re.sub(r"^index\.php/?", "", s, count=1)
    return s.strip("/ ").strip("-")


def is_legacy_marketing_product_path(path: str) -> bool:
    """Path một segment kiểu /moi-ma-l1249-gia-20240k-giay-da-nam-...-1156126."""
    s = normalize_legacy_source_slug(path)
    if not s:
        return False
    if _LEGACY_MARKETING_PATH_RE.search(s):
        return True
    return "-gia-" in s and bool(re.search(r"gia-\d{2,6}k", s))


def is_legacy_index_php_product_path(path: str) -> bool:
    """URL cũ /index.php/vay-dam-lien-than-du-tiec-nu-1172882."""
    s = normalize_legacy_source_slug(path)
    if not s or is_legacy_marketing_product_path(s):
        return False
    return bool(re.match(r"^.+-\d{5,}$", s))


def extract_legacy_index_php_name_prefix(source_slug: str) -> str:
    """
    Tách tên SP từ URL index.php: ``vay-dam-lien-than-du-tiec-nu-1172882`` →
    ``vay-dam-lien-than-du-tiec-nu``.
    """
    s = normalize_legacy_source_slug(source_slug)
    if not s or not is_legacy_index_php_product_path(s):
        return ""
    m = re.match(r"^(.+)-(\d{5,})$", s)
    if not m:
        return ""
    prefix = (m.group(1) or "").strip("-")
    return prefix if len(prefix) >= 6 else ""


def extract_legacy_url_name_prefix(source_slug: str) -> str:
    """Pool tên SP từ URL marketing (moi-ma-…) hoặc index.php (slug-id)."""
    s = normalize_legacy_source_slug(source_slug)
    if not s:
        return ""
    marketing = extract_legacy_marketing_name_prefix(s)
    if marketing:
        return marketing
    return extract_legacy_index_php_name_prefix(s)


def extract_legacy_marketing_name_prefix(source_slug: str) -> str:
    """
    Tách tên SP từ URL marketing: sau ``gia-20240k`` → trước mã biến thể ``-g0x`` (g03, g04, …).
    Vd: ...-giay-da-nam-gutdu-giay-dep-nam-chat-lieu-da-bo-g05-san-pham-moi-... →
    ``giay-da-nam-gutdu-giay-dep-nam-chat-lieu-da-bo``.
    """
    s = normalize_legacy_source_slug(source_slug)
    if not s or not is_legacy_marketing_product_path(s):
        return ""
    parts = [x for x in s.split("-") if x]
    if not parts:
        return ""

    start = 0
    for i, p in enumerate(parts):
        if p == "gia" and i + 1 < len(parts) and _LEGACY_GIA_PRICE_SEG_RE.match(parts[i + 1]):
            start = i + 2
            break
        if _LEGACY_GIA_PRICE_SEG_RE.match(p):
            start = i + 1
            break

    if start == 0 and parts[0] == "moi-ma":
        for i, p in enumerate(parts[1:], start=1):
            if p == "gia" and i + 1 < len(parts) and _LEGACY_GIA_PRICE_SEG_RE.match(parts[i + 1]):
                start = i + 2
                break

    collected: List[str] = []
    for p in parts[start:]:
        if _LEGACY_VARIANT_SEG_RE.match(p):
            break
        if p.isdigit() and len(p) >= 5:
            break
        if p in _LEGACY_TAIL_NOISE_SEGMENTS:
            break
        collected.append(p)

    while collected and collected[-1] in _LEGACY_TAIL_NOISE_SEGMENTS:
        collected.pop()

    prefix = "-".join(collected).strip("-")
    return prefix if len(prefix) >= 6 else ""


def product_slug_name_prefix(slug: str, product_id: Optional[str] = None) -> str:
    """Phần tên trong slug (bỏ mã product_id ở cuối), dùng gom nhóm biến thể."""
    s = (slug or "").strip()
    if not s:
        return ""
    pid = (product_id or "").strip().lower()
    if pid:
        suffix = f"-{pid}"
        if s.lower().endswith(suffix):
            return s[: -len(suffix)].rstrip("-")
    m = _PRODUCT_SLUG_ID_SUFFIX_RE.search(s)
    if m:
        return s[: m.start()].rstrip("-")
    return s.rstrip("-")


# Gợi ý nhóm phổ biến (thêm vào ứng viên pool, không thay thế quét DB).
_OOS_POOL_HINT_MARKERS: Tuple[str, ...] = (
    "ao-khoac-da-nam",
    "ao-khoac-nam",
    "ao-khoac-nu",
    "ao-thun-nam",
    "ao-thun-nu",
    "ao-so-mi-nam",
    "ao-so-mi-nu",
    "quan-jean-nam",
    "quan-jean-nu",
    "quan-nam",
    "quan-nu",
    "vay-dam-nu",
    "vay-nu",
    "giay-nam",
    "giay-nu",
    "tui-xach-nu",
    "tui-nam",
)
MIN_OOS_POOL_PRODUCT_COUNT = 3

# Cache đường dẫn listing nhóm (slug/SP) — giảm latency redirect OOS.
_OOS_GROUP_LISTING_PATH_CACHE: Dict[str, Tuple[float, str]] = {}
_OOS_GROUP_LISTING_CACHE_TTL_SEC = 600
_OOS_GROUP_LISTING_CACHE_MAX = 2500


def _count_active_products_with_slug_prefix(db: Session, prefix: str) -> int:
    p = (prefix or "").strip().lower()
    if len(p) < 6:
        return 0
    q = db.query(Product.id).filter(
        Product.slug.isnot(None),
        Product.slug != "",
        Product.slug.ilike(f"{p}%"),
    )
    if hasattr(Product, "is_active"):
        q = q.filter(Product.is_active.is_(True))
    return int(q.count())


def _iter_oos_pool_prefix_candidates(name_prefix: str, source_slug: str) -> List[str]:
    """Sinh ứng viên pool từ PDP (N segment đầu) + cửa sổ trượt trên URL marketing."""
    seen: Set[str] = set()
    out: List[str] = []

    def add(raw: str) -> None:
        p = (raw or "").strip("-").lower()
        if len(p) < 6 or p in seen:
            return
        seen.add(p)
        out.append(p)

    name = (name_prefix or "").strip("-")
    source = (source_slug or name_prefix or "").strip("-")
    legacy_name = extract_legacy_url_name_prefix(source)
    if legacy_name:
        add(legacy_name)

    name_parts = [x for x in name.split("-") if x]
    source_parts = [x for x in source.split("-") if x]

    for n in (
        PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS,
        max(3, PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS - 1),
    ):
        if len(name_parts) >= n:
            add("-".join(name_parts[:n]))

    for window in (5, 4, 3):
        if len(source_parts) < window:
            continue
        for i in range(0, len(source_parts) - window + 1):
            add("-".join(source_parts[i : i + window]))

    haystack = f"{source} {name}".lower()
    for marker in _OOS_POOL_HINT_MARKERS:
        if marker in haystack:
            add(marker)

    return out


def product_slug_oos_search_pool_prefix(
    db: Session,
    name_prefix: str,
    segments: int = PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS,
    *,
    source_slug: Optional[str] = None,
) -> str:
    """
    Chọn pool ILIKE theo DB: cụm segment nào khớp nhiều slug SP nhất (>= MIN_OOS_POOL_PRODUCT_COUNT).
    Áp dụng mọi nhóm (quần, váy, giày, áo, …), không chỉ áo khoác nam.
    """
    _ = segments  # giữ tham số tương thích; cỡ cửa sổ cố định trong _iter_oos_pool_prefix_candidates
    name = (name_prefix or "").strip()
    source = (source_slug or name).strip()
    best_prefix = ""
    best_count = -1
    for cand in _iter_oos_pool_prefix_candidates(name, source):
        cnt = _count_active_products_with_slug_prefix(db, cand)
        if cnt > best_count:
            best_count = cnt
            best_prefix = cand
    if best_prefix and best_count >= MIN_OOS_POOL_PRODUCT_COUNT:
        return best_prefix
    name_parts = [x for x in name.split("-") if x]
    if name_parts:
        fallback = "-".join(name_parts[: min(PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS, len(name_parts))])
        if len(fallback) >= 6:
            return fallback
    return best_prefix


def product_slug_oos_pool_prefix_fast(
    name_prefix: str,
    *,
    source_slug: Optional[str] = None,
) -> str:
    """
    Pool prefix cho redirect listing — không COUNT DB từng ứng viên (nhanh hơn ``product_slug_oos_search_pool_prefix``).
    """
    name = (name_prefix or "").strip()
    source = (source_slug or name).strip()
    legacy_name = extract_legacy_url_name_prefix(source)
    if legacy_name:
        return legacy_name

    haystack = f"{source} {name}".lower()
    for marker in _OOS_POOL_HINT_MARKERS:
        if marker in haystack:
            return marker

    marketing_noise = ("moi-ma", "gia-", "sale-", "hot-", "new-")
    for cand in sorted(
        _iter_oos_pool_prefix_candidates(name, source),
        key=len,
        reverse=True,
    ):
        if len(cand) < 6:
            continue
        if any(cand.startswith(p) for p in marketing_noise):
            continue
        return cand

    for cand in _iter_oos_pool_prefix_candidates(name, source):
        if len(cand) >= 6:
            return cand
    name_parts = [x for x in name.split("-") if x]
    if len(name_parts) >= PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS:
        return "-".join(name_parts[:PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS])
    if name_parts:
        return "-".join(name_parts)
    return name


def score_product_slug_oos_similarity(
    source_slug: str,
    candidate_slug: str,
    name_prefix: str,
) -> float:
    """Độ giống slug PDP nguồn ↔ ứng viên (SequenceMatcher + boost prefix / slug nhóm)."""
    source = (source_slug or "").strip()
    cand = (candidate_slug or "").strip()
    prefix = (name_prefix or "").strip()
    if not source or not cand:
        return 0.0
    sim = _similarity_score(source, cand)
    if prefix:
        canonical = f"{prefix}-"
        if cand == canonical:
            sim = max(sim, 0.95)
        elif cand.startswith(prefix):
            sim = max(sim, _similarity_score(prefix, cand))
    return sim


def _seo_cluster_listing_path(cluster: Any) -> str:
    path = (getattr(cluster, "canonical_path", None) or "").strip()
    if path.startswith("/"):
        return path
    slug = (getattr(cluster, "slug", None) or "").strip()
    return f"/c/{slug}" if slug else "/"


def _cluster_listing_path_for_product(db: Session, product: Product) -> Optional[str]:
    """Ưu tiên SEO cluster của cat3; không có thì /danh-muc theo taxonomy."""
    from app.models.category import Category
    from app.models.seo_cluster import SeoCluster

    cid = getattr(product, "category_id", None)
    if cid:
        row = (
            db.query(Category, SeoCluster)
            .outerjoin(SeoCluster, Category.seo_cluster_id == SeoCluster.id)
            .filter(Category.id == cid)
            .first()
        )
        if row:
            cat, cluster = row
            if cluster:
                return _seo_cluster_listing_path(cluster)
            fs = (cat.full_slug or "").strip().strip("/")
            if fs:
                return f"/danh-muc/{fs}"

    c1 = (getattr(product, "category", None) or "").strip()
    if not c1:
        return None
    s1 = _normalize_category_url_slug(slugify_vietnamese(c1)) or slugify_vietnamese(c1)
    c2 = (getattr(product, "subcategory", None) or "").strip()
    c3 = (getattr(product, "sub_subcategory", None) or "").strip()
    s2 = _normalize_category_url_slug(slugify_vietnamese(c2)) if c2 else None
    s3 = _normalize_category_url_slug(slugify_vietnamese(c3)) if c3 else None
    if s3 and s2:
        cat3 = (
            db.query(Category)
            .filter(
                Category.level == 3,
                Category.full_slug.ilike(f"%/{s2}/{s3}"),
            )
            .first()
        )
        if cat3 and cat3.seo_cluster_id:
            cluster = (
                db.query(SeoCluster)
                .filter(SeoCluster.id == cat3.seo_cluster_id)
                .first()
            )
            if cluster:
                return _seo_cluster_listing_path(cluster)
        return f"/danh-muc/{s1}/{s2}/{s3}"
    if s2:
        return f"/danh-muc/{s1}/{s2}"
    return f"/danh-muc/{s1}"


def _cluster_listing_path_from_pool_prefix(db: Session, pool: str) -> Optional[str]:
    """Suy ra landing nhóm từ pool slug (vd ao-khoac-da-nam) — không chọn PDP khác."""
    from app.models.category import Category
    from app.models.seo_cluster import SeoCluster

    pool_l = (pool or "").strip().lower()
    if len(pool_l) < 4:
        return None

    row = db.query(SeoCluster).filter(SeoCluster.slug == pool_l).first()
    if row:
        return _seo_cluster_listing_path(row)

    row = (
        db.query(SeoCluster)
        .filter(SeoCluster.slug.ilike(f"{pool_l}%"))
        .order_by(SeoCluster.slug.desc())
        .first()
    )
    if row:
        return _seo_cluster_listing_path(row)

    cands = [c for c in _iter_oos_pool_prefix_candidates(pool_l, pool_l) if len(c) >= 6]
    if cands:
        rows = (
            db.query(SeoCluster)
            .filter(SeoCluster.slug.in_(cands[:30]))
            .all()
        )
        by_slug = {(r.slug or "").lower(): r for r in rows}
        for cand in sorted(cands, key=len, reverse=True):
            hit = by_slug.get(cand)
            if hit:
                return _seo_cluster_listing_path(hit)

    if len(pool_l) >= 10:
        dominant = (
            db.query(SeoCluster, sql_func.count(Product.id).label("cnt"))
            .join(Category, Category.seo_cluster_id == SeoCluster.id)
            .join(Product, Product.category_id == Category.id)
            .filter(
                Product.is_active.is_(True),
                Product.slug.isnot(None),
                Product.slug != "",
                Product.slug.ilike(f"{pool_l}%"),
            )
            .group_by(SeoCluster.id)
            .order_by(sql_func.count(Product.id).desc())
            .first()
        )
        if dominant and dominant[1] >= 1:
            return _seo_cluster_listing_path(dominant[0])

    return None


def _cluster_listing_path_from_source_slug(db: Session, source_slug: str) -> Optional[str]:
    """Khớp slug cluster trong URL — chỉ query ứng viên / SQL strpos, không load toàn bảng."""
    from app.models.seo_cluster import SeoCluster

    source_l = (source_slug or "").strip().lower()
    if len(source_l) < 8:
        return None

    cands: List[str] = []
    seen: Set[str] = set()
    for c in _iter_oos_pool_prefix_candidates("", source_l):
        if len(c) >= 6 and c not in seen:
            seen.add(c)
            cands.append(c)
    if cands:
        rows = (
            db.query(SeoCluster)
            .filter(SeoCluster.slug.in_(cands[:30]))
            .all()
        )
        by_slug = {(r.slug or "").lower(): r for r in rows}
        for cand in sorted(cands, key=len, reverse=True):
            hit = by_slug.get(cand)
            if hit:
                return _seo_cluster_listing_path(hit)

    if not is_sqlite:
        row = (
            db.query(SeoCluster)
            .filter(
                sql_func.length(SeoCluster.slug) >= 6,
                sql_func.strpos(source_l, SeoCluster.slug) > 0,
            )
            .order_by(sql_func.length(SeoCluster.slug).desc())
            .first()
        )
        if row:
            return _seo_cluster_listing_path(row)

    best: Optional[Any] = None
    best_len = 0
    for cand in sorted(cands, key=len, reverse=True)[:12]:
        if cand in source_l and len(cand) > best_len:
            row = db.query(SeoCluster).filter(SeoCluster.slug == cand).first()
            if row:
                best_len = len(cand)
                best = row
    if best:
        return _seo_cluster_listing_path(best)
    return None


def _home_search_listing_path(pool_or_query: str) -> str:
    from urllib.parse import quote

    q = (pool_or_query or "").replace("-", " ").strip()
    return f"/?q={quote(q)}" if q else "/"


def _resolve_missing_product_listing_path(
    db: Session,
    *,
    source_slug: str,
    product_id: Optional[str] = None,
) -> str:
    """
    SP không còn trong DB: DeepSeek → ``/?q=``; fallback parse URL (không quét pool 600 slug).
    """
    from app.services.legacy_oos_deepseek_keywords import deepseek_legacy_oos_search_query

    source = normalize_legacy_source_slug(source_slug or "")
    if not source:
        return "/"

    ai_q = deepseek_legacy_oos_search_query(source)
    if ai_q:
        return _home_search_listing_path(ai_q)

    legacy_pool = extract_legacy_url_name_prefix(source)
    if legacy_pool:
        short_pool = product_slug_oos_pool_prefix_fast(legacy_pool, source_slug=source)
        search_path = _oos_home_search_fallback(short_pool or legacy_pool)
        if search_path:
            return search_path
        q = legacy_pool.replace("-", " ").strip()
        if q:
            return _home_search_listing_path(q)

    path = _cluster_listing_path_from_source_slug(db, source)
    if path:
        return path

    name_prefix = product_slug_name_prefix(source, product_id)
    pool = product_slug_oos_pool_prefix_fast(name_prefix, source_slug=source) or (
        name_prefix or ""
    ).strip().lower()
    search_path = _oos_home_search_fallback(pool)
    if search_path:
        return search_path
    return "/"


def _oos_home_search_fallback(pool: str) -> Optional[str]:
    """Chỉ fallback ``/?q=`` với pool ngắn (≤ N segment) — không search cả slug marketing."""
    p = (pool or "").strip().lower()
    if len(p) < 4:
        return None
    parts = [x for x in p.split("-") if x]
    if len(parts) > PRODUCT_OOS_GROUP_SLUG_POOL_SEGMENTS:
        return None
    return _home_search_listing_path(p)


def _cluster_listing_path_from_slug_group_pool(
    db: Session,
    *,
    source_slug: str,
    name_prefix: str,
    product_id: Optional[str] = None,
    pool_prefix: Optional[str] = None,
    legacy_marketing: bool = False,
) -> Optional[str]:
    """
    Suy listing nhóm từ pool slug ILIKE + độ giống (không full-text ``/?q=``).
    URL marketing: trong pool vẫn chọn SP đại diện để lấy /c/ hoặc /danh-muc/.
    """
    source = (source_slug or "").strip()
    name = (name_prefix or product_slug_name_prefix(source, product_id) or "").strip()
    compare_slug = source or name
    if not compare_slug:
        return None

    pool = (pool_prefix or "").strip().lower()
    if len(pool) < 6:
        pool = product_slug_oos_search_pool_prefix(db, name, source_slug=source or name)
    if len(pool) < 6 or _count_active_products_with_slug_prefix(db, pool) < 1:
        return None

    q = db.query(Product).filter(
        Product.slug.isnot(None),
        Product.slug != "",
        Product.slug.ilike(f"{pool}%"),
    )
    if hasattr(Product, "is_active"):
        q = q.filter(Product.is_active.is_(True))

    candidates = (
        q.order_by(
            Product.available.desc(),
            Product.purchases.desc(),
            Product.id.asc(),
        )
        .limit(PRODUCT_OOS_GROUP_SLUG_POOL_CANDIDATE_LIMIT)
        .all()
    )
    if not candidates:
        return None

    min_sim = (
        PRODUCT_OOS_LEGACY_PATH_FALLBACK_MIN_SIMILARITY
        if legacy_marketing
        else PRODUCT_OOS_GROUP_SLUG_MIN_SIMILARITY
    )
    best_product: Optional[Product] = None
    best_key: Tuple[int, float, int] = (-1, -1.0, -1)
    loose_product: Optional[Product] = None
    loose_key: Tuple[int, float, int] = (-1, -1.0, -1)

    for p in candidates:
        cand_slug = (p.slug or "").strip()
        if not cand_slug:
            continue
        sim = score_product_slug_oos_similarity(compare_slug, cand_slug, name)
        in_stock = 1 if int(p.available or 0) > 0 else 0
        key = (in_stock, sim, int(p.purchases or 0))
        if sim >= min_sim and key > best_key:
            best_key = key
            best_product = p
        if legacy_marketing and key > loose_key:
            loose_key = key
            loose_product = p

    pick = best_product or (loose_product if legacy_marketing else None)
    if pick is not None:
        return _cluster_listing_path_for_product(db, pick)
    return None


def _resolve_listing_via_slug_pools(
    db: Session,
    *,
    source_slug: str,
    name_prefix: str,
    product_id: Optional[str] = None,
    legacy_marketing: bool = False,
) -> Optional[str]:
    """Thử pool slug (DB + ứng viên) → cluster SEO / danh mục từ SP trong pool."""
    source = (source_slug or "").strip()
    name = (name_prefix or "").strip()
    if not name and not source:
        return None

    pools: List[str] = []
    seen: Set[str] = set()

    def add_pool(raw: str) -> None:
        pl = (raw or "").strip().lower()
        if len(pl) >= 6 and pl not in seen:
            seen.add(pl)
            pools.append(pl)

    add_pool(product_slug_oos_search_pool_prefix(db, name, source_slug=source or name))
    for cand in _iter_oos_pool_prefix_candidates(name, source or name):
        add_pool(cand)

    for pool in pools:
        path = _cluster_listing_path_from_pool_prefix(db, pool)
        if path:
            return path

    for pool in pools:
        path = _cluster_listing_path_from_slug_group_pool(
            db,
            source_slug=source,
            name_prefix=name,
            product_id=product_id,
            pool_prefix=pool,
            legacy_marketing=legacy_marketing,
        )
        if path:
            return path
    return None


def _resolve_product_group_listing_path_uncached(
    db: Session,
    *,
    source_slug: str,
    product: Optional[Product] = None,
    product_id: Optional[str] = None,
) -> str:
    """
    Đường dẫn listing nhóm khi SP hết hàng / không tồn tại — không mở PDP sản phẩm khác.
    Thứ tự: cluster từ SP → pool slug ILIKE + nhóm SP → cluster trong URL → ``/?q=`` pool ngắn.
    """
    from app.services.warehouse_clearance import WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH

    if product is not None and getattr(product, "is_warehouse_clearance", False):
        return WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH

    if product is not None:
        path = _cluster_listing_path_for_product(db, product)
        if path:
            return path

    source = normalize_legacy_source_slug(source_slug or "")
    pid = product_id or (getattr(product, "product_id", None) if product else None)

    if product is None:
        return _resolve_missing_product_listing_path(
            db, source_slug=source, product_id=pid
        )

    legacy_pool = extract_legacy_url_name_prefix(source)
    if legacy_pool:
        path = _resolve_listing_via_slug_pools(
            db,
            source_slug=source,
            name_prefix=legacy_pool,
            product_id=pid,
            legacy_marketing=True,
        )
        if path:
            return path
        short_pool = product_slug_oos_search_pool_prefix(
            db, legacy_pool, source_slug=source
        )
        if short_pool:
            search_path = _oos_home_search_fallback(short_pool)
            if search_path:
                return search_path
        return "/"

    if source:
        path = _cluster_listing_path_from_source_slug(db, source)
        if path:
            return path

    name_prefix = product_slug_name_prefix(source, pid)
    path = _resolve_listing_via_slug_pools(
        db,
        source_slug=source,
        name_prefix=name_prefix or source,
        product_id=pid,
        legacy_marketing=False,
    )
    if path:
        return path

    pool = product_slug_oos_search_pool_prefix(
        db, name_prefix or source, source_slug=source
    ) or product_slug_oos_pool_prefix_fast(name_prefix, source_slug=source)
    if pool:
        search_path = _oos_home_search_fallback(pool)
        if search_path:
            return search_path
    return "/"


def resolve_product_group_listing_path(
    db: Session,
    *,
    source_slug: str,
    product: Optional[Product] = None,
    product_id: Optional[str] = None,
) -> str:
    """Có cache TTL — dùng cho redirect OOS / API nhẹ."""
    source = (source_slug or "").strip()
    pid = product_id or (getattr(product, "product_id", None) if product else None)
    cid = getattr(product, "category_id", None) if product is not None else None
    cache_key = f"{cid or 0}:{pid or ''}:{source}"
    now = time.time()
    hit = _OOS_GROUP_LISTING_PATH_CACHE.get(cache_key)
    if hit and (now - hit[0]) < _OOS_GROUP_LISTING_CACHE_TTL_SEC:
        return hit[1]

    path = _resolve_product_group_listing_path_uncached(
        db,
        source_slug=source,
        product=product,
        product_id=pid,
    )
    if len(_OOS_GROUP_LISTING_PATH_CACHE) >= _OOS_GROUP_LISTING_CACHE_MAX:
        _OOS_GROUP_LISTING_PATH_CACHE.clear()
    _OOS_GROUP_LISTING_PATH_CACHE[cache_key] = (now, path)
    return path


def find_similar_product_slug_for_oos_redirect(
    db: Session,
    *,
    slug: str,
    min_similarity: float = PRODUCT_OOS_GROUP_SLUG_MIN_SIMILARITY,
    product_id: Optional[str] = None,
    pool_best_fallback_min: Optional[float] = None,
) -> Optional[str]:
    """
    Tìm slug PDP thay thế khi SP hết hàng: pool ``{4 segment đầu}%`` (vd ao-khoac-da-nam%),
    độ giống >= min_similarity (mặc định 0.8).
    Ưu tiên: còn hàng → slug nhóm ``{prefix}-`` → độ giống cao → lượt mua.
    """
    source = (slug or "").strip()
    if not source:
        return None
    name_prefix = product_slug_name_prefix(source, product_id)
    pool_prefix = product_slug_oos_search_pool_prefix(db, name_prefix, source_slug=source)
    if len(pool_prefix) < 6:
        return None
    if _count_active_products_with_slug_prefix(db, pool_prefix) < 1:
        return None

    canonical_group_slug = f"{name_prefix}-" if name_prefix else ""

    q = (
        db.query(Product)
        .filter(
            Product.slug.isnot(None),
            Product.slug != "",
            Product.slug != source,
            Product.slug.ilike(f"{pool_prefix}%"),
        )
    )
    if hasattr(Product, "is_active"):
        q = q.filter(Product.is_active.is_(True))

    candidates = (
        q.order_by(
            Product.available.desc(),
            Product.purchases.desc(),
            Product.id.asc(),
        )
        .limit(PRODUCT_OOS_GROUP_SLUG_POOL_CANDIDATE_LIMIT)
        .all()
    )
    if not candidates:
        return None

    min_sim = max(0.0, min(1.0, float(min_similarity)))
    fallback_min = (
        max(0.0, min(1.0, float(pool_best_fallback_min)))
        if pool_best_fallback_min is not None
        else None
    )
    best_slug: Optional[str] = None
    best_key: Tuple[int, float, int, int] = (-1, -1.0, -1, -1)
    fallback_slug: Optional[str] = None
    fallback_key: Tuple[int, float, int, int] = (-1, -1.0, -1, -1)

    for p in candidates:
        cand = (p.slug or "").strip()
        if not cand or cand == source:
            continue
        sim = score_product_slug_oos_similarity(source, cand, name_prefix)
        in_stock = 1 if int(p.available or 0) > 0 else 0
        is_canonical = 1 if cand == canonical_group_slug else 0
        key = (in_stock, sim, is_canonical, int(p.purchases or 0))
        if sim >= min_sim and key > best_key:
            best_key = key
            best_slug = cand
        elif fallback_min is not None and sim >= fallback_min and key > fallback_key:
            fallback_key = key
            fallback_slug = cand

    if best_slug:
        return best_slug
    return fallback_slug


def get_product_sitemap_slugs(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 5000,
    is_active: Optional[bool] = True,
) -> dict:
    """Chỉ slug + updated_at — payload nhẹ cho sitemap Next.js (tránh giới hạn cache 2MB)."""
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    query = db.query(Product.slug, Product.updated_at, Product.id)
    query = query.filter(Product.slug.isnot(None), Product.slug != "")
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    query = apply_catalog_visibility_filter(query)
    total = int(
        query.enable_eagerloads(False)
        .order_by(None)
        .with_entities(sql_func.count(Product.id))
        .scalar()
        or 0
    )
    rows = (
        query.order_by(Product.id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    products = [
        {
            "slug": row.slug,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
        if row.slug
    ]
    return {"total": total, "skip": skip, "limit": limit, "products": products}


# Gợi ý màu từ tên SP (ưu tiên cụm dài trước) — không accent khi so khớp.
_NAME_COLOR_HINTS_ORDERED: List[str] = [
    "xanh navy",
    "xanh dương",
    "xanh lá",
    "xanh rêu",
    "xanh ngọc",
    "xanh da trời",
    "xanh than",
    "xanh",
    "đen tuyền",
    "đen",
    "trắng ngà",
    "trắng kem",
    "trắng",
    "nâu đậm",
    "nâu nhạt",
    "nâu",
    "xám",
    "be",
    "kem",
    "đỏ đô",
    "đỏ",
    "hồng",
    "tím",
    "vàng",
    "cam",
    "bạc",
    "đồng",
    "champagne",
    "mận",
    "rêu",
    "denim",
]

_CANONICAL_COLOR_HINTS: List[Tuple[str, str]] = [
    ("xanh navy", "Xanh"),
    ("xanh dương", "Xanh"),
    ("xanh lam", "Xanh"),
    ("xanh lá", "Xanh"),
    ("xanh rêu", "Xanh"),
    ("xanh ngọc", "Xanh"),
    ("xanh da trời", "Xanh"),
    ("xanh than", "Xanh"),
    ("xanh", "Xanh"),
    ("đen tuyền", "Đen"),
    ("đen", "Đen"),
    ("trắng ngà", "Trắng"),
    ("trắng kem", "Trắng"),
    ("trắng", "Trắng"),
    ("nâu đậm", "Nâu"),
    ("nâu nhạt", "Nâu"),
    ("đỏ đô", "Đỏ"),
    ("đỏ", "Đỏ"),
    ("nâu", "Nâu"),
    ("xám", "Xám"),
    ("ghi", "Xám"),
    ("be", "Be"),
    ("kem", "Kem"),
    ("cát", "Be"),
    ("hồng", "Hồng"),
    ("tím", "Tím"),
    ("vàng", "Vàng"),
    ("cam", "Cam"),
    ("bạc", "Bạc"),
    ("đồng", "Đồng"),
    ("champagne", "Champagne"),
    ("mận", "Mận"),
    ("rêu", "Xanh"),
    ("denim", "Xanh"),
]

_CLOTHING_SIZE_ORDER: Dict[str, int] = {
    "XS": 10,
    "S": 20,
    "M": 30,
    "L": 40,
    "XL": 50,
    "XXL": 60,
    "2XL": 60,
    "XXXL": 70,
    "3XL": 70,
    "4XL": 80,
    "5XL": 90,
    "6XL": 100,
    "7XL": 110,
    "8XL": 120,
    "FREESIZE": 130,
}
_CLOTHING_SIZE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:FREE\s*SIZE|FREESIZE|[2-8]\s*XL|XXXL|XXL|XL|XS|S|M|L)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_NUMERIC_SIZE_RE = re.compile(r"(?<!\d)(\d{2}(?:[.,]5)?)(?!\d)")

_STYLE_TAG_ALIASES: Dict[str, List[str]] = {
    "Váy": ["váy", "đầm", "dress"],
    "Đuôi cá": ["đuôi cá", "duoi ca", "mermaid"],
    "Xòe": ["xòe", "xoe", "flare", "flared"],
    "Ôm body": ["body", "ôm body", "om body", "bodycon"],
    "Suông": ["suông", "suong"],
    "Maxi": ["maxi"],
    "Midi": ["midi"],
    "Hai dây": ["hai dây", "2 dây", "spaghetti strap"],
    "Cổ V": ["cổ v", "co v", "v-neck"],
    "Cổ cao": ["cổ cao", "co cao", "turtleneck"],
    "Kẻ caro": ["kẻ caro", "ke caro", "caro", "plaid", "checkered"],
    "Kẻ sọc": ["kẻ sọc", "ke soc", "sọc", "soc", "striped"],
    "Hoa nhí": ["hoa nhí", "hoa nhi", "floral"],
    "Áo thun": ["áo thun", "ao thun", "t-shirt", "tee"],
    "Áo sơ mi": ["áo sơ mi", "ao so mi", "shirt"],
    "Áo khoác": ["áo khoác", "ao khoac", "jacket"],
    "Polo": ["polo"],
    "Oversize": ["oversize", "over size"],
    "Slim fit": ["slim fit"],
    "Quần jeans": ["quần jeans", "quan jeans", "jean", "denim"],
    "Quần short": ["quần short", "quan short", "shorts"],
    "Jogger": ["jogger"],
    "Cargo": ["cargo"],
    "Chân váy": ["chân váy", "chan vay", "skirt"],
    "Giày lười": ["giày lười", "giay luoi", "loafer", "slip-on", "slip on"],
    "Sneaker": ["sneaker", "giày thể thao", "giay the thao"],
    "Sandal": ["sandal", "xăng đan", "xang dan"],
    "Cao gót": ["cao gót", "cao got", "high heel"],
    "Boot": ["boot", "bốt", "bốt cổ", "boot cổ"],
    "Búp bê": ["búp bê", "bup be", "mary jane"],
    "Oxford": ["oxford"],
    "Derby": ["derby"],
    "Mule": ["mule", "sục", "clog"],
}
_STYLE_TAG_ORDER: Dict[str, int] = {label: idx for idx, label in enumerate(_STYLE_TAG_ALIASES.keys())}
# Dropdown «Kiểu» — ẩn tag có ít hơn N sản phẩm trong tập facets hiện tại.
_MIN_STYLE_TAG_FACET_PRODUCTS = 3
_APPAREL_ONLY_STYLE_TAGS = frozenset(
    {
        "Váy",
        "Đuôi cá",
        "Xòe",
        "Ôm body",
        "Suông",
        "Maxi",
        "Midi",
        "Hai dây",
        "Cổ V",
        "Kẻ caro",
        "Kẻ sọc",
        "Hoa nhí",
        "Áo thun",
        "Áo sơ mi",
        "Áo khoác",
        "Polo",
        "Oversize",
        "Slim fit",
        "Quần jeans",
        "Quần short",
        "Jogger",
        "Cargo",
        "Chân váy",
    }
)
_FOOTWEAR_STYLE_TAGS = frozenset(_STYLE_TAG_ALIASES.keys()) - _APPAREL_ONLY_STYLE_TAGS
_FASHION_STYLE_TAGS = _APPAREL_ONLY_STYLE_TAGS | frozenset({"Cổ cao"})


def _canonical_size_label(raw: Any) -> str:
    t = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not t or t.lower() in ("nan", "none", "null"):
        return ""

    m = _CLOTHING_SIZE_RE.search(t)
    if m:
        label = re.sub(r"\s+", "", m.group(0)).upper()
        if label == "FREESIZE":
            return "Freesize"
        if label == "XXL":
            return "2XL"
        if label == "XXXL":
            return "3XL"
        return label

    m = _NUMERIC_SIZE_RE.search(t)
    if not m:
        return ""
    num_raw = m.group(1).replace(",", ".")
    try:
        value = float(num_raw)
    except ValueError:
        return ""
    # Bỏ mã SKU/số mẫu như 2825; giữ các size giày/quần áo phổ biến.
    if value < 16 or value > 60:
        return ""
    return str(int(value)) if value == int(value) else str(value).rstrip("0").rstrip(".")


def _canonical_color_label(raw: Any) -> str:
    t = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not t or t.lower() in ("nan", "none", "null"):
        return ""
    # Bỏ mã đầu dòng/SKU thường gặp: "2825 Màu Đen" -> "Màu Đen".
    t = re.sub(r"^[A-Za-z]?\d+[A-Za-z0-9_-]*\s+", "", t).strip()
    t_norm = remove_vietnamese_accents(t.lower())
    for hint, label in _CANONICAL_COLOR_HINTS:
        needle = remove_vietnamese_accents(hint.lower())
        if re.search(rf"(^|[^a-z0-9]){re.escape(needle)}([^a-z0-9]|$)", t_norm):
            return label
    return ""


def _text_for_style_tags(*values: Any) -> str:
    parts: List[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            try:
                parts.append(json.dumps(value, ensure_ascii=False))
            except Exception:
                parts.append(str(value))
        else:
            parts.append(str(value))
    return remove_vietnamese_accents(" ".join(parts).lower())


def style_tags_from_product_row(*values: Any) -> Set[str]:
    text = _text_for_style_tags(*values)
    out: Set[str] = set()
    if not text:
        return out
    for label, aliases in _STYLE_TAG_ALIASES.items():
        for alias in aliases:
            needle = remove_vietnamese_accents(alias.lower())
            if re.search(rf"(^|[^a-z0-9]){re.escape(needle)}([^a-z0-9]|$)", text):
                out.add(label)
                break
    return out


def _pretty_color_label(s: str) -> str:
    t = (s or "").strip()
    if not t:
        return ""
    parts = t.split()
    if not parts:
        return ""
    return " ".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts)


def _flatten_sizes_json(sizes_val: Any) -> List[str]:
    out: List[str] = []
    if sizes_val is None:
        return out
    if isinstance(sizes_val, list):
        for x in sizes_val:
            if x is None:
                continue
            for part in re.split(r"[,;/|]", str(x)):
                s = _canonical_size_label(part)
                if s:
                    out.append(s)
        return out
    if isinstance(sizes_val, str) and sizes_val.strip():
        try:
            parsed = json.loads(sizes_val)
            if isinstance(parsed, list):
                return _flatten_sizes_json(parsed)
        except Exception:
            pass
        for part in re.split(r"[,;/|]", sizes_val):
            p = _canonical_size_label(part)
            if p:
                out.append(p)
    return out


def color_labels_from_product_row(
    name: Optional[str], color_col: Optional[str], colors_json: Any
) -> Set[str]:
    out: Set[str] = set()
    if colors_json is not None:
        if isinstance(colors_json, list):
            for c in colors_json:
                if isinstance(c, str) and c.strip():
                    lab = _canonical_color_label(c)
                    if lab:
                        out.add(lab)
                elif isinstance(c, dict):
                    raw = (c.get("name") or c.get("value") or "").strip()
                    if raw:
                        lab = _canonical_color_label(raw)
                        if lab:
                            out.add(lab)
        elif isinstance(colors_json, str) and colors_json.strip():
            try:
                parsed = json.loads(colors_json)
                if isinstance(parsed, list):
                    return color_labels_from_product_row(name, color_col, parsed)
            except Exception:
                pass
    cc = (color_col or "").strip()
    if cc and cc.lower() != "nan":
        for part in re.split(r"[,;/|]", cc):
            lab = _canonical_color_label(part)
            if lab:
                out.add(lab)
    nm = name or ""
    nn = remove_vietnamese_accents(nm.lower())
    for hint in _NAME_COLOR_HINTS_ORDERED:
        needle = remove_vietnamese_accents(hint.lower())
        if len(needle) >= 2 and needle in nn:
            lab = _canonical_color_label(hint)
            if lab:
                out.add(lab)
    return out


_CATEGORY_L3_UNDER_L1_TTL_SEC = 300.0


def _build_cat3_ids_under_category_l1(db: Session, l1_name: str) -> Set[int]:
    """Mọi category_id cấp 3 thuộc cây taxonomy cấp 1 (vd Giày dép Nam)."""
    from app.models.category import Category as Cat

    l1_row = (
        db.query(Cat.id)
        .filter(Cat.level == 1, sql_func.lower(Cat.name) == l1_name.strip().lower())
        .first()
    )
    if not l1_row:
        return set()
    l2_ids = [
        r.id
        for r in db.query(Cat.id).filter(Cat.parent_id == l1_row.id, Cat.level == 2).all()
    ]
    if not l2_ids:
        return set()
    return {
        r.id
        for r in db.query(Cat.id).filter(Cat.parent_id.in_(l2_ids), Cat.level == 3).all()
    }


def get_cached_cat3_ids_under_category_l1(db: Session, l1_name: str) -> Set[int]:
    """Cache 5 phút — listing guard gọi mỗi request danh mục Giày dép / Thời trang."""
    from app.utils.ttl_cache import cache as ttl_cache

    key = f"cat3_under_l1:{l1_name.strip().lower()}"
    return ttl_cache.get_or_fetch(
        key,
        _CATEGORY_L3_UNDER_L1_TTL_SEC,
        lambda: _build_cat3_ids_under_category_l1(db, l1_name),
    )


def _miscat_subcategory_predicate(fragments: Tuple[str, ...]):
    """Khớp subcategory / sub_subcategory chứa mảnh gợi ý sai ngành."""
    parts = []
    for frag in fragments:
        pat = f"%{frag}%"
        parts.append(Product.subcategory.ilike(pat))
        parts.append(Product.sub_subcategory.ilike(pat))
    return or_(*parts) if parts else None


def _listing_guard_miscat_fragments_for_l1(l1_name: str) -> Tuple[str, ...]:
    if l1_name in _FOOTWEAR_CATEGORY_L1_NAMES:
        return _FOOTWEAR_MISCAT_SUBCATEGORY_FRAGMENTS
    if l1_name in _FASHION_CATEGORY_L1_NAMES:
        frags = list(_FASHION_MISCAT_SUBCATEGORY_FRAGMENTS)
        if l1_name == "Thời trang Nữ":
            frags.extend(_FASHION_NU_EXTRA_MISCAT_FRAGMENTS)
        elif l1_name == "Thời trang Nam":
            frags.extend(_FASHION_NAM_EXTRA_MISCAT_FRAGMENTS)
        return tuple(frags)
    return ()


def apply_category_l1_listing_guard(query, db: Session, category: Optional[str]):
    """
    Siết listing cấp 1 cho giày dép và thời trang:
    - Giữ SP có category_id thuộc cây taxonomy đúng cấp 1, hoặc
    - category_id NULL + cột category khớp + subcategory không gợi ý sai ngành/giới.
    Loại SP có FK cat3 thuộc nhánh khác (map nhầm Excel).
    """
    cat_s = (category or "").strip()
    if cat_s not in _CATEGORY_L1_LISTING_GUARD_NAMES:
        return query
    allowed_cat3 = get_cached_cat3_ids_under_category_l1(db, cat_s)
    miscat_frags = _listing_guard_miscat_fragments_for_l1(cat_s)
    miscat = _miscat_subcategory_predicate(miscat_frags) if miscat_frags else None
    ce = category_field_equals_ci(Product.category, cat_s)
    branches = []
    if allowed_cat3:
        branches.append(Product.category_id.in_(allowed_cat3))
    if ce is not None:
        null_branch = and_(Product.category_id.is_(None), ce)
        if miscat is not None:
            null_branch = and_(null_branch, not_(miscat))
        branches.append(null_branch)
    if not branches:
        return query
    return query.filter(or_(*branches))


def apply_product_category_filters(
    query,
    db: Session,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
):
    """Cùng logic lọc 3 cấp như get_products (gồm category_id + nhóm subcategory)."""
    cat_s = (category or "").strip() if category else ""
    sub_s = (subcategory or "").strip() if subcategory else ""
    subsub_s = (sub_subcategory or "").strip() if sub_subcategory else ""

    triple_combined = False
    if cat_s and sub_s and subsub_s:
        ce = category_field_equals_ci(Product.category, cat_s)
        subcat_group = get_subcategory_group_for_query(cat_s, sub_s)
        if subcat_group:
            se = subcategory_field_in_ci(Product.subcategory, subcat_group)
        else:
            se = category_field_equals_ci(Product.subcategory, sub_s)
        sse = category_field_equals_ci(Product.sub_subcategory, subsub_s)
        if ce is not None and se is not None and sse is not None:
            triple_idx = _build_cat3_triple_name_lookup(db)
            tkey = f"{cat_s.lower()}\x1f{sub_s.lower()}\x1f{subsub_s.lower()}"
            tid = triple_idx.get(tkey)
            if tid is not None:
                text_ok = and_(ce, se, sse)
                query = query.filter(
                    or_(Product.category_id == tid, and_(Product.category_id.is_(None), text_ok))
                )
            else:
                query = query.filter(ce).filter(se).filter(sse)
            triple_combined = True

    if not triple_combined:
        if cat_s:
            ce = category_field_equals_ci(Product.category, cat_s)
            if ce is not None:
                query = query.filter(ce)
        if sub_s:
            subcat_group = get_subcategory_group_for_query(cat_s or "", sub_s)
            if subcat_group:
                ine = subcategory_field_in_ci(Product.subcategory, subcat_group)
                if ine is not None:
                    query = query.filter(ine)
            else:
                se = category_field_equals_ci(Product.subcategory, sub_s)
                if se is not None:
                    query = query.filter(se)
        if subsub_s:
            sse = category_field_equals_ci(Product.sub_subcategory, subsub_s)
            if sse is not None:
                query = query.filter(sse)
    return apply_category_l1_listing_guard(query, db, cat_s)


def _size_filter_candidates(size: str) -> List[str]:
    raw = str(size or "").strip()
    if not raw:
        return []
    candidates = [raw]
    num = raw.replace(",", ".").replace(" ", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", num):
        try:
            fv = float(num)
            normalized = str(int(fv)) if fv == int(fv) else str(fv)
            candidates.append(normalized)
        except Exception:
            pass
    seen: Set[str] = set()
    out: List[str] = []
    for c in candidates:
        key = c.lower()
        if c and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def apply_product_size_filter(query, size: Optional[str]):
    """
    Lọc SP có size trong cột JSON `sizes`.

    Ngoài `@> contains` chuẩn, bổ sung khớp «mảng/ghi dạng text» (vd. [41, 42], \"35/36/42\",
    một phần tử chứa chuỗi nhiều size) — cùng họ dữ liệu mà `_flatten_sizes_json` dùng cho facets,
    tránh trường hợp UI có \"42\" nhưng contains([\"42\"]) không khớp DB.
    """
    if not size or not str(size).strip():
        return query
    candidates = _size_filter_candidates(str(size))
    if not candidates:
        return query
    s_raw = candidates[0]

    parts: List = []
    st = cast(Product.sizes, String)
    if is_sqlite:
        for candidate in candidates:
            parts.append(Product.sizes.contains([candidate]))
        num = s_raw.replace(",", ".").replace(" ", "")
        if re.fullmatch(r"\d+(?:\.\d+)?", num):
            try:
                fv = float(num)
                if fv == int(fv):
                    parts.append(Product.sizes.contains([int(fv)]))
                else:
                    parts.append(Product.sizes.contains([fv]))
            except Exception:
                pass

        sqlite_likes = []
        for candidate in candidates:
            esc = candidate.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sqlite_likes.extend([
                st.like(f'%"{esc}"%', escape="\\"),
                st.like(f'%[{esc}]%', escape="\\"),
                st.like(f'%[{esc},%', escape="\\"),
                st.like(f'%, {esc},%', escape="\\"),
                st.like(f'%,{esc},%', escape="\\"),
                st.like(f'%, {esc}]%', escape="\\"),
                st.like(f'%,{esc}]%', escape="\\"),
                st.like(f'%/{esc}/%', escape="\\"),
                st.like(f'%{esc}/%', escape="\\"),
                st.like(f'%/{esc}%', escape="\\"),
            ])
        parts.append(or_(*sqlite_likes))
    else:
        regex_parts = []
        for candidate in candidates:
            candidate_num = candidate.replace(",", ".").replace(" ", "")
            if re.fullmatch(r"\d+(?:\.\d+)?", candidate_num):
                regex_parts.append(st.op("~*")(rf"(^|[^0-9.]){re.escape(candidate)}([^0-9.]|$)"))
            else:
                regex_parts.append(st.op("~*")(rf"(^|[^A-Za-z0-9]){re.escape(candidate)}([^A-Za-z0-9]|$)"))
        parts.append(or_(*regex_parts))

    return query.filter(or_(*parts))


def apply_product_color_filter(query, color: Optional[str]):
    """Khớp màu đã chọn: tên SP, cột color, JSON colors (cùng logic gợi ý facets)."""
    if not color or not str(color).strip():
        return query
    c = str(color).strip()
    like = f"%{c}%"
    return query.filter(
        or_(
            Product.name.ilike(like),
            Product.color.ilike(like),
            cast(Product.colors, String).ilike(like),
        )
    )


def apply_product_style_tag_filter(query, style_tag: Optional[str]):
    """Lọc theo tag kiểu phổ thông tự rút từ tên / style / features / product_info."""
    label = (style_tag or "").strip()
    if not label:
        return query
    aliases = _STYLE_TAG_ALIASES.get(label, [label])
    search_concat = sql_func.concat(
        sql_func.coalesce(Product.name, ""), " ",
        sql_func.coalesce(Product.category, ""), " ",
        sql_func.coalesce(Product.subcategory, ""), " ",
        sql_func.coalesce(Product.sub_subcategory, ""), " ",
        sql_func.coalesce(Product.style, ""), " ",
        sql_func.coalesce(Product.material, ""), " ",
        sql_func.coalesce(cast(Product.features, String), ""), " ",
        sql_func.coalesce(cast(Product.product_info, String), "")
    )
    text_col = sql_func.lower(search_concat)
    conditions = []
    for alias in aliases:
        a = str(alias).strip()
        if a:
            conditions.append(text_col.ilike(f"%{a.lower()}%"))
    return query.filter(or_(*conditions)) if conditions else query


def _facet_str_nonempty(val: Optional[str]) -> bool:
    s = (val or "").strip()
    return bool(s and s.lower() != "nan")


def _facet_listing_dimensions_present(
    *,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
) -> bool:
    """Ít nhất một chiều lọc (không chỉ q) để facets listing `/` không q — tránh scan cả DB."""
    if _facet_str_nonempty(style):
        return True
    if any(_facet_str_nonempty(x) for x in (category, subcategory, sub_subcategory)):
        return True
    if _facet_str_nonempty(shop_id):
        return True
    if _facet_str_nonempty(shop_name):
        return True
    if _facet_str_nonempty(shop_name_chinese):
        return True
    if _facet_str_nonempty(chinese_name):
        return True
    if _facet_str_nonempty(pro_lower_price):
        return True
    if _facet_str_nonempty(pro_high_price):
        return True
    return False


def _aggregate_product_facet_rows(rows) -> Dict[str, Any]:
    sizes_acc: Set[str] = set()
    colors_acc: Set[str] = set()
    style_tags_acc: Set[str] = set()
    prices: List[float] = []
    for row in rows:
        sizes_val, colors_val, color_col, name, price = row[:5]
        for sz in _flatten_sizes_json(sizes_val):
            sizes_acc.add(sz)
        for lab in color_labels_from_product_row(name, color_col, colors_val):
            colors_acc.add(lab)
        if len(row) > 5:
            for tag in style_tags_from_product_row(name, *row[5:]):
                style_tags_acc.add(tag)
        try:
            if price is not None:
                prices.append(float(price))
        except (TypeError, ValueError):
            pass

    def _size_sort_key(x: str) -> tuple:
        try:
            return (0, float(str(x).replace(",", ".")))
        except Exception:
            key = str(x).upper()
            return (1, _CLOTHING_SIZE_ORDER.get(key, 999), key.lower())

    return {
        "sizes": sorted(sizes_acc, key=_size_sort_key),
        "colors": sorted(colors_acc, key=lambda x: x.lower()),
        "style_tags": sorted(style_tags_acc, key=lambda x: (_STYLE_TAG_ORDER.get(x, 999), x.lower())),
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
    }


def _filter_facet_sizes_with_product_results(base_query, sizes: List[str]) -> List[str]:
    """
    Dropdown size chỉ hiển thị option mà khi áp vào cùng query listing vẫn còn sản phẩm.
    Tránh facet lấy được từ dữ liệu thô nhưng predicate lọc thực tế trả 0 kết quả.
    """
    valid: List[str] = []
    for size in sizes:
        try:
            hit = (
                apply_product_size_filter(base_query, size)
                .with_entities(Product.id)
                .limit(1)
                .first()
            )
            if hit is not None:
                valid.append(size)
        except Exception:
            try:
                base_query.session.rollback()
            except Exception:
                pass
            # Nếu DB dialect có lỗi ngoài ý muốn, giữ option thay vì làm mất toàn bộ bộ lọc.
            valid.append(size)
    return valid


def _filter_facet_colors_with_product_results(base_query, colors: List[str]) -> List[str]:
    """Chỉ giữ màu mà khi áp vào cùng query listing vẫn còn sản phẩm."""
    valid: List[str] = []
    for color in colors:
        try:
            hit = (
                apply_product_color_filter(base_query, color)
                .with_entities(Product.id)
                .limit(1)
                .first()
            )
            if hit is not None:
                valid.append(color)
        except Exception:
            try:
                base_query.session.rollback()
            except Exception:
                pass
            valid.append(color)
    return valid


def _style_tag_search_text_from_facet_row(name: Any, row_tail: Tuple[Any, ...]) -> str:
    """Cùng trường concat như `apply_product_style_tag_filter` (ilike trên chuỗi lower)."""
    parts = [str(name or "")]
    for value in row_tail:
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            try:
                parts.append(json.dumps(value, ensure_ascii=False))
            except Exception:
                parts.append(str(value))
        else:
            parts.append(str(value))
    return " ".join(parts).lower()


def _facet_row_matches_style_tag(name: Any, row_tail: Tuple[Any, ...], label: str) -> bool:
    text = _style_tag_search_text_from_facet_row(name, row_tail)
    for alias in _STYLE_TAG_ALIASES.get(label, [label]):
        a = str(alias).strip().lower()
        if a and a in text:
            return True
    return False


def _facet_style_tags_from_rows(
    rows,
    *,
    min_count: int = _MIN_STYLE_TAG_FACET_PRODUCTS,
    allowed_labels: Optional[Set[str]] = None,
) -> List[str]:
    """
    Đếm tag kiểu trên một lần quét hàng facet — khớp ilike của `apply_product_style_tag_filter`,
    tránh N query COUNT riêng cho từng tag.
    """
    counts: Dict[str, int] = {}
    labels = allowed_labels if allowed_labels is not None else set(_STYLE_TAG_ALIASES.keys())
    for row in rows:
        if not row or len(row) < 5:
            continue
        name = row[3]
        tail = row[5:] if len(row) > 5 else ()
        for label in labels:
            if _facet_row_matches_style_tag(name, tail, label):
                counts[label] = counts.get(label, 0) + 1
    valid = [lab for lab, cnt in counts.items() if cnt >= min_count]
    return sorted(valid, key=lambda x: (_STYLE_TAG_ORDER.get(x, 999), x.lower()))


def _facet_style_tags_with_min_products(
    base_query,
    *,
    min_count: int = _MIN_STYLE_TAG_FACET_PRODUCTS,
    allowed_labels: Optional[Set[str]] = None,
) -> List[str]:
    """Một query lấy cột facet rồi đếm in-memory."""
    facet_columns = (
        Product.sizes, Product.colors, Product.color, Product.name, Product.price,
        Product.style, Product.material, Product.features, Product.product_info,
        Product.category, Product.subcategory, Product.sub_subcategory
    )
    rows = base_query.with_entities(*facet_columns).all()
    return _facet_style_tags_from_rows(
        rows, min_count=min_count, allowed_labels=allowed_labels
    )


def _style_facet_base_query(
    query,
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
):
    """Query dùng đếm option kiểu — cùng phạm vi size/màu/giá, không lọc style_tag đang chọn."""
    style_query = query
    if filter_size:
        style_query = apply_product_size_filter(style_query, filter_size)
    if filter_color:
        style_query = apply_product_color_filter(style_query, filter_color)
    return _apply_product_price_filters(style_query, min_price, max_price)


def _apply_product_price_filters(query, min_price: Optional[float], max_price: Optional[float]):
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    return query


def build_dependent_product_facets(
    query,
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    listing_category_l1: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Facets phụ thuộc nhau cho một base query bất kỳ:
    - size theo màu + giá
    - màu theo size + giá
    - khoảng giá theo size + màu
    """
    facet_columns = (
        Product.sizes, Product.colors, Product.color, Product.name, Product.price,
        Product.style, Product.material, Product.features, Product.product_info,
        Product.category, Product.subcategory, Product.sub_subcategory
    )
    style_query = _style_facet_base_query(
        query,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
    )
    l1 = (listing_category_l1 or "").strip()
    if l1 in _FOOTWEAR_CATEGORY_L1_NAMES:
        style_allowed: Optional[Set[str]] = _FOOTWEAR_STYLE_TAGS
    elif l1 in _FASHION_CATEGORY_L1_NAMES:
        style_allowed = _FASHION_STYLE_TAGS
    else:
        style_allowed = None
    has_dependent_filters = any(
        [min_price is not None, max_price is not None, filter_size, filter_color, filter_style_tag]
    )

    if not has_dependent_filters:
        rows = query.with_entities(*facet_columns).all()
        facets = _aggregate_product_facet_rows(rows)
        style_tags = _facet_style_tags_from_rows(rows, allowed_labels=style_allowed)
        return {
            "sizes": facets["sizes"],
            "colors": facets["colors"],
            "style_tags": style_tags,
            "price_min": facets["price_min"],
            "price_max": facets["price_max"],
        }

    style_rows = style_query.with_entities(*facet_columns).all()
    style_tags = _facet_style_tags_from_rows(style_rows, allowed_labels=style_allowed)

    size_query = query
    if filter_color:
        size_query = apply_product_color_filter(size_query, filter_color)
    if filter_style_tag:
        size_query = apply_product_style_tag_filter(size_query, filter_style_tag)
    size_query = _apply_product_price_filters(size_query, min_price, max_price)
    size_rows = size_query.with_entities(*facet_columns).all()
    size_facets = _aggregate_product_facet_rows(size_rows)

    color_query = query
    if filter_size:
        color_query = apply_product_size_filter(color_query, filter_size)
    if filter_style_tag:
        color_query = apply_product_style_tag_filter(color_query, filter_style_tag)
    color_query = _apply_product_price_filters(color_query, min_price, max_price)
    color_rows = color_query.with_entities(*facet_columns).all()
    color_facets = _aggregate_product_facet_rows(color_rows)

    price_query = query
    if filter_size:
        price_query = apply_product_size_filter(price_query, filter_size)
    if filter_color:
        price_query = apply_product_color_filter(price_query, filter_color)
    if filter_style_tag:
        price_query = apply_product_style_tag_filter(price_query, filter_style_tag)
    price_rows = price_query.with_entities(*facet_columns).all()
    price_facets = _aggregate_product_facet_rows(price_rows)

    return {
        "sizes": size_facets["sizes"],
        "colors": color_facets["colors"],
        "style_tags": style_tags,
        "price_min": price_facets["price_min"],
        "price_max": price_facets["price_max"],
    }


def get_category_product_facets(
    db: Session,
    category: Optional[str],
    subcategory: Optional[str],
    sub_subcategory: Optional[str],
    *,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
) -> Dict[str, Any]:
    """sizes / colors distinct trong phạm vi danh mục; giá min–max (sản phẩm đang active)."""
    return get_product_listing_facets(
        db,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
        is_active=True,
    )


def get_product_listing_facets(
    db: Session,
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    is_active: Optional[bool] = True,
    warehouse_clearance_only: bool = False,
    skip_cache: bool = False,
) -> Dict[str, Any]:
    """
    Size/màu/giá cho listing `GET /products/` — khớp các chiều danh mục, shop, style, nhóm Excel…
    Không áp size/màu/min_price/max_price; khi có `q` áp lọc từ giống danh sách.
    Không `q` thì cần _facet_listing_dimensions_present (tránh facets toàn cửa hàng).
    """
    empty: Dict[str, Any] = {"sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}
    raw_q = (q or "").strip()
    words: Optional[List[str]] = None
    if raw_q:
        normalized = normalize_search_query(raw_q)
        words = [w.strip() for w in normalized.split() if w.strip()]
        if not words:
            return empty
    elif not warehouse_clearance_only and not _facet_listing_dimensions_present(
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
    ):
        return empty

    listing_kwargs = dict(
        q=q,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
    )
    try:
        from app.services import listing_facet_cache as lfc_service

        if not skip_cache:
            cached = lfc_service.try_read_cached_listing_facets(db, **listing_kwargs)
            if cached is not None:
                return cached
    except Exception:
        pass

    query = db.query(Product)
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    query = apply_catalog_visibility_filter(
        query,
        warehouse_clearance_only=warehouse_clearance_only,
        has_text_search=bool(words),
    )
    query = apply_product_category_filters(query, db, category, subcategory, sub_subcategory)
    if shop_name:
        query = query.filter(Product.shop_name.ilike(f"%{shop_name.strip()}%"))
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)
    if style:
        st = style.strip()
        if st and st.lower() != "nan":
            query = query.filter(
                Product.style.isnot(None),
                sql_func.lower(sql_func.trim(Product.style)) == st.lower(),
            )
    if shop_name_chinese:
        sc = shop_name_chinese.strip()
        if sc and sc.lower() != "nan":
            query = query.filter(
                Product.shop_name_chinese.isnot(None),
                sql_func.lower(sql_func.trim(Product.shop_name_chinese)) == sc.lower(),
            )
    if chinese_name:
        cn = chinese_name.strip()
        if cn and cn.lower() != "nan":
            query = query.filter(
                Product.chinese_name.isnot(None),
                sql_func.lower(sql_func.trim(Product.chinese_name)) == cn.lower(),
            )
    if pro_lower_price:
        val = pro_lower_price.strip()
        if val and val.lower() != "nan":
            query = query.filter(Product.pro_lower_price.ilike(f"%{val}%"))
    if pro_high_price:
        val = pro_high_price.strip()
        if val and val.lower() != "nan":
            query = query.filter(Product.pro_high_price.ilike(f"%{val}%"))
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if words is not None:
        query = apply_product_search_word_filters(query, words)

    result = build_dependent_product_facets(
        query,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
        listing_category_l1=(category or "").strip() or None,
    )
    try:
        from app.services import listing_facet_cache as lfc_service

        if not skip_cache:
            lfc_service.maybe_cache_listing_facets(db, facets=result, **listing_kwargs)
    except Exception:
        pass
    return result


def get_search_product_facets(
    db: Session,
    q: Optional[str],
    *,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    is_active: Optional[bool] = True,
) -> Dict[str, Any]:
    """
    Size/màu/khoảng giá trên tập SP khớp `q` (cùng logic từ rời như list tìm kiếm),
    không áp size/màu/min/max — dùng bộ lọc trên trang chủ `/?q=`.
    """
    raw = (q or "").strip()
    if not raw:
        return {"sizes": [], "colors": [], "style_tags": [], "price_min": None, "price_max": None}
    return get_product_listing_facets(
        db,
        q=q,
        category=category,
        subcategory=subcategory,
        sub_subcategory=sub_subcategory,
        shop_name=shop_name,
        shop_id=shop_id,
        style=style,
        shop_name_chinese=shop_name_chinese,
        chinese_name=chinese_name,
        pro_lower_price=pro_lower_price,
        pro_high_price=pro_high_price,
        min_price=min_price,
        max_price=max_price,
        filter_size=filter_size,
        filter_color=filter_color,
        filter_style_tag=filter_style_tag,
        is_active=is_active,
    )


def get_products(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    style: Optional[str] = None,
    shop_name_chinese: Optional[str] = None,
    chinese_name: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_active: Optional[bool] = None,
    q: Optional[str] = None,
    product_id: Optional[str] = None,
    *,
    sort: Optional[str] = None,
    order_random: bool = False,
    filter_size: Optional[str] = None,
    filter_color: Optional[str] = None,
    filter_style_tag: Optional[str] = None,
    skip_total: bool = False,
    include_warehouse_products: bool = False,
    warehouse_clearance_only: bool = False,
    admin_list_query: bool = False,
):
    query = db.query(Product)
    if admin_list_query:
        from sqlalchemy.orm import load_only, noload

        _admin_cols = (
            Product.id,
            Product.product_id,
            Product.code,
            Product.name,
            Product.price,
            Product.slug,
            Product.brand_name,
            Product.category,
            Product.subcategory,
            Product.sub_subcategory,
            Product.main_image,
            Product.images,
            Product.gallery,
            Product.available,
            Product.is_active,
            Product.link_default,
            Product.source_stock_status,
            Product.source_stock_checked_at,
            Product.source_stock_next_check_at,
            Product.source_stock_error,
            Product.admin_source_batch_scanned_at,
            Product.image_localization_status,
            Product.image_localization_language,
            Product.image_localized_at,
            Product.image_localization_error,
            Product.is_warehouse_clearance,
            Product.base_sku,
            Product.colors,
            Product.sizes,
            Product.shop_name,
            Product.shop_id,
            Product.created_at,
            Product.updated_at,
            Product.deposit_require,
            Product.material,
            Product.style,
            Product.color,
            Product.origin,
            Product.chinese_name,
            Product.shop_name_chinese,
        )
        query = query.options(load_only(*_admin_cols), noload(Product.category_rel))
    has_q = bool(q and str(q).strip())
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    query = apply_catalog_visibility_filter(
        query,
        include_warehouse_products=include_warehouse_products,
        warehouse_clearance_only=warehouse_clearance_only,
        has_text_search=has_q,
    )
    sort_norm = normalize_product_list_sort(sort)
    use_random_order = bool(order_random and not has_q)
    if use_random_order:
        sort_norm = "id_desc"

    query = apply_product_category_filters(query, db, category, subcategory, sub_subcategory)
    query = apply_product_size_filter(query, filter_size)
    query = apply_product_color_filter(query, filter_color)
    query = apply_product_style_tag_filter(query, filter_style_tag)
    if shop_name:
        query = query.filter(Product.shop_name.ilike(f"%{shop_name.strip()}%"))
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)
    if style:
        st = style.strip()
        if st and st.lower() != "nan":
            query = query.filter(
                Product.style.isnot(None),
                sql_func.lower(sql_func.trim(Product.style)) == st.lower(),
            )
    if shop_name_chinese:
        sc = shop_name_chinese.strip()
        if sc and sc.lower() != "nan":
            query = query.filter(
                Product.shop_name_chinese.isnot(None),
                sql_func.lower(sql_func.trim(Product.shop_name_chinese)) == sc.lower(),
            )
    if chinese_name:
        cn = chinese_name.strip()
        if cn and cn.lower() != "nan":
            query = query.filter(
                Product.chinese_name.isnot(None),
                sql_func.lower(sql_func.trim(Product.chinese_name)) == cn.lower(),
            )
    if pro_lower_price:
        val = pro_lower_price.strip()
        if val and val.lower() != "nan":
            query = query.filter(Product.pro_lower_price.ilike(f"%{val}%"))
    if pro_high_price:
        val = pro_high_price.strip()
        if val and val.lower() != "nan":
            query = query.filter(Product.pro_high_price.ilike(f"%{val}%"))
    if min_price is not None:
        query = query.filter(Product.price >= min_price)
    if max_price is not None:
        query = query.filter(Product.price <= max_price)
    if is_active is not None:
        query = query.filter(Product.is_active == is_active)
    if product_id:
        pid_filter = _build_product_id_or_code_filter(product_id)
        if pid_filter is not None:
            query = query.filter(pid_filter)
    total = 0
    products = []
    applied_query = None
    suggested_queries = []
    suggested_categories = []
    redirect_path = None
    ai_processed = False
    normalized_query = normalize_search_query(q) if q and q.strip() else None
    if q and q.strip():
        raw_query = q.strip()
        from app.services.warehouse_clearance import (
            WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH,
            is_sale_listing_search_query,
        )

        sale_keyword_search = is_sale_listing_search_query(raw_query)

        if sale_keyword_search:
            total, products = _search_products_sale_keyword(
                db, query, limit, skip, sort=sort_norm,
            )
            if total > 0:
                applied_query = normalize_search_query(raw_query)
                _log_search(db, raw_query, total, ai_processed=False)

        normalized_key = _normalize_search_key(raw_query)
        has_accents = _has_vietnamese_accents(raw_query)

        mapped_query = None
        mapping = None if sale_keyword_search else _get_search_mapping(db, normalized_key)

        try:
            category_tree = get_category_tree_from_products(db, is_active=is_active if is_active is not None else True)
        except Exception:
            category_tree = []

        if total == 0 and has_accents and mapping and mapping.keyword_target:
            mapping_key = _normalize_search_key(mapping.keyword_target)
            matched_from_mapping = _match_category_path(mapping_key, category_tree) if mapping_key else None
            if not matched_from_mapping and mapping.type == SearchMappingType.category_redirect:
                matched_from_mapping = _get_category_by_path(mapping.keyword_target, category_tree)
            if matched_from_mapping and matched_from_mapping.get("path"):
                _touch_search_mapping(db, mapping)
                _log_search(db, raw_query, 0, ai_processed=False)
                return {
                    "total": 0,
                    "products": [],
                    "page": skip // limit + 1 if limit > 0 else 1,
                    "size": limit,
                    "total_pages": 0,
                    "applied_query": applied_query,
                    "normalized_query": normalized_query,
                    "suggested_queries": suggested_queries,
                    "suggested_categories": suggested_categories,
                    "redirect_path": matched_from_mapping["path"],
                    "ai_processed": False,
                }
            mapped_query = mapping.keyword_target.strip()

        # Ưu tiên tìm theo mapping nếu có
        if mapped_query:
            mapped_normalized = normalize_search_query(mapped_query)
            mapped_words = [w.strip() for w in mapped_normalized.split() if w.strip()]
            if mapped_words:
                total, products = _search_products_by_words(
                    db, query, mapped_words, limit, skip, sort=sort_norm,
                )
                if total > 0:
                    applied_query = mapped_normalized
                    _touch_search_mapping(db, mapping)

        # Nếu mapping không có kết quả thì tìm theo từ khóa gốc
        if total == 0:
            normalized = normalize_search_query(raw_query)
            words = [w.strip() for w in normalized.split() if w.strip()]
            if words:
                total, products = _search_products_by_words(db, query, words, limit, skip, sort=sort_norm)
                if total > 0:
                    applied_query = normalized
        if total > 0:
            _log_search(db, raw_query, total, ai_processed=False)
        if total == 0 and not sale_keyword_search:
            try:
                from app.services.search_query_corrector import correct_search_query_via_ai, suggest_category_matches_via_ai
                gender_context = _infer_gender_context(category, subcategory, sub_subcategory, raw_query)
                ai_processed = True
                corrected = _run_ai_call(correct_search_query_via_ai, raw_query, timeout_seconds=3)
                if corrected and corrected.strip() and corrected.strip() != raw_query:
                    corrected_key = _normalize_search_key(corrected)
                    matched_ai_category = _match_category_path(corrected_key, category_tree) if corrected_key else None
                    if matched_ai_category and matched_ai_category.get("path"):
                        _save_search_mapping(db, normalized_key, corrected.strip(), SearchMappingType.category_redirect)
                        _log_search(db, raw_query, 0, ai_processed=True)
                        return {
                            "total": 0,
                            "products": [],
                            "page": skip // limit + 1 if limit > 0 else 1,
                            "size": limit,
                            "total_pages": 0,
                            "applied_query": applied_query,
                            "normalized_query": normalized_query,
                            "suggested_queries": suggested_queries,
                            "suggested_categories": suggested_categories,
                            "redirect_path": matched_ai_category["path"],
                            "ai_processed": True,
                        }
                    norm2 = normalize_search_query(corrected)
                    words2 = [w.strip() for w in norm2.split() if w.strip()]
                    if words2:
                        total, products = _search_products_by_words(
                            db, query, words2, limit, skip, sort=sort_norm,
                        )
                        if total > 0:
                            if total >= 20:
                                applied_query = norm2
                                _save_search_mapping(db, normalized_key, corrected.strip(), SearchMappingType.product_search)
                            else:
                                applied_query = None
                if total == 0:
                    flat = _flatten_category_tree(category_tree)
                    if flat:
                        scored = []
                        for c in flat:
                            score = _similarity_score(
                                _normalize_search_key(raw_query),
                                _normalize_search_key(c.get("name", ""))
                            )
                            scored.append((score, c))
                        scored.sort(key=lambda x: x[0], reverse=True)
                        for _, c in scored[:5]:
                            suggested_categories.append({"name": c.get("name"), "path": c.get("path")})
            except Exception as e:
                logger.debug("AI correct search skipped: %s", e)
            if total == 0 and sale_keyword_search:
                redirect_path = WAREHOUSE_CLEARANCE_GROUP_LISTING_PATH
            _log_search(db, raw_query, total, ai_processed=ai_processed)
    if not (q and q.strip()):
        if skip_total:
            total = -1
        else:
            total = _count_products_query(query)
        if use_random_order:
            products = query.order_by(sql_func.random()).offset(skip).limit(limit).all()
        elif sort_norm == "views_desc":
            vt_sub = _product_view_totals_subquery()
            q2 = query.outerjoin(vt_sub, Product.id == vt_sub.c.product_id)
            products = q2.order_by(*_order_exprs_for_product_list(sort_norm, vt_sub)).offset(skip).limit(limit).all()
        else:
            products = query.order_by(*_order_exprs_for_product_list(sort_norm, None)).offset(skip).limit(limit).all()
    
    page_num = skip // limit + 1 if limit > 0 else 1
    if total < 0:
        total_pages = page_num + (1 if len(products) >= limit and limit > 0 else 0)
    else:
        total_pages = math.ceil(total / limit) if limit > 0 else 1
    return {
        "total": total,
        "products": products,
        "page": page_num,
        "size": limit,
        "total_pages": total_pages,
        "applied_query": applied_query,
        "normalized_query": normalized_query,
        "suggested_queries": suggested_queries,
        "suggested_categories": suggested_categories,
        "redirect_path": redirect_path,
        "ai_processed": ai_processed,
    }


def get_product_category_branch_keys(db: Session, is_active: bool = True) -> Dict[str, List[str]]:
    """
    Nhánh có ít nhất một sản phẩm (chuỗi khớp cột category / subcategory / sub_subcategory).
    - level2_keys: "c1\\x1fc2"
    - level3_keys: "c1\\x1fc2\\x1fc3" (chỉ khi cấp 3 không rỗng)
    """
    sep = "\x1f"
    q = db.query(Product.category, Product.subcategory, Product.sub_subcategory)
    if is_active:
        q = q.filter(Product.is_active.is_(True))
    q = q.filter(
        Product.category.isnot(None),
        sql_func.trim(Product.category) != "",
    )
    level2: Set[str] = set()
    level3: Set[str] = set()
    for cat, sub, subsub in q.distinct().all():
        c1 = (cat or "").strip()
        c2 = (sub or "").strip()
        c3 = (subsub or "").strip()
        if not c1 or not c2:
            continue
        level2.add(f"{c1}{sep}{c2}")
        if c3:
            level3.add(f"{c1}{sep}{c2}{sep}{c3}")
    return {"level2_keys": sorted(level2), "level3_keys": sorted(level3)}


def _build_storefront_active_category_id_counts(db: Session) -> Dict[int, int]:
    """Một query GROUP BY — dùng cho prune menu thay vì COUNT từng nhánh L3."""
    from app.services.warehouse_clearance import apply_catalog_visibility_filter

    q = db.query(Product.category_id, sql_func.count(Product.id))
    q = q.filter(Product.is_active.is_(True), Product.category_id.isnot(None))
    q = apply_catalog_visibility_filter(q)
    return {
        int(cid): int(cnt)
        for cid, cnt in q.group_by(Product.category_id).all()
        if cid is not None
    }


def count_products_for_category_path(
    db: Session,
    name1: str,
    name2: Optional[str] = None,
    name3: Optional[str] = None,
    is_active: bool = True,
    *,
    cat3_by_triple: Optional[Dict[str, int]] = None,
    cat_counts_by_id: Optional[Dict[int, int]] = None,
    storefront_visible: bool = False,
) -> int:
    """
    Đếm sản phẩm active khớp đường danh mục (cùng logic filter với get_category_by_path).
    name2/name3 None hoặc rỗng = không siết thêm cấp đó (đếm phạm vi rộng hơn).
    """
    name1 = (name1 or "").strip()
    if not name1:
        return 0

    def _apply_storefront_filters(q):
        if not storefront_visible:
            return q
        from app.services.warehouse_clearance import apply_catalog_visibility_filter

        return apply_catalog_visibility_filter(q)

    filt_l1 = [Product.is_active == is_active]
    _e = category_field_equals_ci(Product.category, name1)
    if _e is not None:
        filt_l1.append(_e)
    if not name2 or not str(name2).strip():
        return _count_products_query(_apply_storefront_filters(db.query(Product).filter(*filt_l1)))
    name2 = str(name2).strip()
    subcat_group = get_subcategory_group_for_query(name1, name2)
    q = db.query(Product).filter(Product.is_active == is_active)
    _e1 = category_field_equals_ci(Product.category, name1)
    if _e1 is not None:
        q = q.filter(_e1)
    if not name3 or not str(name3).strip():
        if subcat_group:
            _ins = subcategory_field_in_ci(Product.subcategory, subcat_group)
            if _ins is not None:
                q = q.filter(_ins)
        else:
            _e2 = category_field_equals_ci(Product.subcategory, name2)
            if _e2 is not None:
                q = q.filter(_e2)
        return _count_products_query(_apply_storefront_filters(q))
    name3 = str(name3).strip()
    _ca = category_field_equals_ci(Product.category, name1)
    _ss = category_field_equals_ci(Product.sub_subcategory, name3)
    _sb = None
    _inq = None
    if subcat_group:
        _inq = subcategory_field_in_ci(Product.subcategory, subcat_group)
    else:
        _sb = category_field_equals_ci(Product.subcategory, name2)

    sub_pred = _inq if subcat_group else _sb
    text_parts = [p for p in (_ca, sub_pred, _ss) if p is not None]

    idx = cat3_by_triple if cat3_by_triple is not None else _build_cat3_triple_name_lookup(db)
    key = f"{name1.lower()}\x1f{name2.lower()}\x1f{name3.lower()}"
    cid = idx.get(key)

    # Có taxonomy cat3: FK là nguồn sự thật (giống `/c/`). Text chỉ áp khi category_id NULL.
    # → Nhánh nguồn sau map (SP đã đổi FK) không còn bị đếm nhờ text cũ; nhánh đích vẫn nhận SP lệch chữ.
    if cid is not None and cat_counts_by_id is not None:
        base_count = int(cat_counts_by_id.get(int(cid), 0))
        if not text_parts:
            return base_count
        text_match = and_(*text_parts)
        extra = _count_products_query(_apply_storefront_filters(
            db.query(Product).filter(
                Product.is_active == is_active,
                Product.category_id.is_(None),
                text_match,
            )
        ))
        return base_count + extra
    if cid is not None and text_parts:
        text_match = and_(*text_parts)
        return _count_products_query(_apply_storefront_filters(
            db.query(Product)
            .filter(
                Product.is_active == is_active,
                or_(Product.category_id == cid, and_(Product.category_id.is_(None), text_match)),
            )
        ))
    if cid is not None:
        return _count_products_query(_apply_storefront_filters(
            db.query(Product)
            .filter(Product.is_active == is_active, Product.category_id == cid)
        ))
    q = db.query(Product).filter(Product.is_active == is_active)
    for p in text_parts:
        q = q.filter(p)
    return _count_products_query(_apply_storefront_filters(q))


_SIZE_ONLY_LEVEL1_RE = re.compile(
    r"^(?:xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|\d{1,2}(?:\.\d)?|\d{2,3})$",
    re.IGNORECASE,
)
_JUNK_LEVEL1_MENU_RES = (
    re.compile(r"^(?:chỉ|chi|only)\s+size\b", re.IGNORECASE),
    re.compile(
        r"^size\s+(?:xxs|xs|s|m|l|xl|xxl|xxxl|2xl|3xl|4xl|5xl|\d+)\s*$",
        re.IGNORECASE,
    ),
    _SIZE_ONLY_LEVEL1_RE,
)


def _is_junk_level1_menu_category(name: str) -> bool:
    """Ẩn danh mục cấp 1 kiểu «Chỉ size XL» — size/marketing không phải ngành hàng."""
    text = re.sub(r"\s+", " ", (name or "")).strip()
    if not text:
        return True
    for pat in _JUNK_LEVEL1_MENU_RES:
        if pat.search(text):
            return True
    return False


def prune_category_tree_empty_branches(
    db: Session,
    tree: List[Dict[str, Any]],
    is_active: bool,
) -> List[Dict[str, Any]]:
    """Ẩn nhánh theo số SP active: cấp 3 đạt ngưỡng CATEGORY_MENU_MIN_PRODUCT_COUNT mới giữ; cấp 2 chỉ giữ khi còn ít nhất một cấp 3 đạt ngưỡng (không giữ L2 chỉ vì tổng SP cả L2 lớn)."""
    try:
        min_kept = max(0, int(getattr(settings, "CATEGORY_MENU_MIN_PRODUCT_COUNT", 0)))
    except (TypeError, ValueError):
        min_kept = 0
    slug_fn = slugify_vietnamese if SLUG_AVAILABLE else (lambda x: (x or "").lower().replace(" ", "-"))

    def _l3_meets_menu_min(count: int) -> bool:
        if min_kept <= 0:
            return count > 0
        return count >= min_kept

    def _l3_sig(c3: Any) -> str:
        """Chữ ký dedupe trong một cột cấp 2 (trùng tên cấp 3 do lỗi merge)."""
        if isinstance(c3, dict):
            n = (c3.get("name") or "").strip()
            sl = (c3.get("slug") or slug_fn(n)).strip().lower()
            nl = re.sub(r"\s+", " ", n.lower()).strip()
            return f"{nl}|{sl}"
        s = str(c3).strip()
        return f"{s.lower()}|{slug_fn(s).lower()}"

    out: List[Dict[str, Any]] = []
    triple_idx = _build_cat3_triple_name_lookup(db)
    cat_counts_by_id = _build_storefront_active_category_id_counts(db)
    for c1 in tree:
        name1 = (c1.get("name") or "").strip()
        if not name1 or _is_junk_level1_menu_category(name1):
            continue
        children2_in = c1.get("children") or []
        pruned_l2: List[Dict[str, Any]] = []
        for c2 in children2_in:
            name2 = (c2.get("name") or "").strip()
            if not name2:
                continue
            children3_in = c2.get("children") or []
            pruned_l3: List[Any] = []
            for c3 in children3_in:
                n3 = c3.get("name", c3) if isinstance(c3, dict) else c3
                n3s = (str(n3) if n3 is not None else "").strip()
                if not n3s:
                    continue
                cnt = count_products_for_category_path(
                    db,
                    name1,
                    name2,
                    n3s,
                    is_active,
                    cat3_by_triple=triple_idx,
                    cat_counts_by_id=cat_counts_by_id,
                    storefront_visible=True,
                )
                if _l3_meets_menu_min(cnt):
                    pruned_l3.append(c3)
            seen_l3: Set[str] = set()
            dedup_l3: List[Any] = []
            for c3 in pruned_l3:
                sig = _l3_sig(c3)
                if sig in seen_l3:
                    continue
                seen_l3.add(sig)
                dedup_l3.append(c3)
            pruned_l3 = dedup_l3
            keep_l2 = bool(pruned_l3)
            if keep_l2:
                pruned_l2.append({**c2, "children": pruned_l3})
        keep_l1 = bool(pruned_l2)
        if keep_l1:
            out.append({**c1, "children": pruned_l2})
    return out


def resolve_category_breadcrumb_names_from_tree(
    tree: List[Dict[str, Any]],
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
) -> Optional[List[str]]:
    """
    Khớp slug URL với một cây danh mục đã có (không query DB).
    Trả về [cấp1], [cấp1,cấp2] hoặc [cấp1,cấp2,cấp3] tên hiển thị; không khớp → None.
    """
    level1_slug = _normalize_category_url_slug(level1_slug) or ""
    level2_slug = _normalize_category_url_slug(level2_slug)
    level3_slug = _normalize_category_url_slug(level3_slug)
    for c1 in tree:
        slug1 = (c1.get("slug") or slugify_vietnamese(c1.get("name", "")) if SLUG_AVAILABLE else "").lower()
        if slug1 != level1_slug:
            continue
        name1 = c1.get("name", "")
        children2 = c1.get("children") or []
        if not level2_slug:
            return [name1]
        for c2 in children2:
            slug2 = (c2.get("slug") or (slugify_vietnamese(c2.get("name", "")) if SLUG_AVAILABLE else "")).lower()
            if slug2 != level2_slug:
                continue
            name2 = c2.get("name", "")
            children3 = c2.get("children") or []
            if not level3_slug:
                return [name1, name2]
            for c3 in children3:
                name3 = c3.get("name", c3) if isinstance(c3, dict) else c3
                slug3 = (c3.get("slug") if isinstance(c3, dict) else (slugify_vietnamese(name3) if SLUG_AVAILABLE else "")).lower()
                if slug3 != level3_slug:
                    continue
                return [name1, name2, name3 if isinstance(name3, str) else str(name3)]
            break
        break
    return None


def get_category_tree_from_products(
    db: Session,
    is_active: bool = True,
    hide_empty_branches: bool = True,
) -> List[Dict[str, Any]]:
    """
    Tạo cây danh mục 3 cấp từ sản phẩm:
    - Cấp 1 (AB): Product.category
    - Cấp 2 (AC): Product.subcategory
    - Cấp 3 (AD): Product.sub_subcategory
    Đồng thời áp category_final_mappings để hiển thị nhánh đích; và merge các nhánh đích đủ 3 cấp
    từ bảng mapping vào cây (để menu có đường dẫn đích đã khai báo).
    Nếu hide_empty_branches=True: menu web chỉ giữ cấp 3 có đủ SP active (mặc định
    CATEGORY_MENU_MIN_PRODUCT_COUNT=10 → cần ≥10 SP trên đúng nhánh L3); cấp 2 / 1 chỉ hiện
    khi còn ít nhất một nhánh con đạt ngưỡng — không giữ L2 “trơ” chỉ vì tổng SP cả cấp 2 lớn.
    hide_empty_branches=False: dùng cho dọn DB / resolve đường đầy đủ trước khi đếm SP.
    Trả về danh sách nested: [{ name, slug, children: [{ name, slug, children: [{ name, slug }] }] }]
    """
    query = db.query(
        Product.category,
        Product.subcategory,
        Product.sub_subcategory,
    ).filter(Product.is_active == is_active)
    query = query.filter(
        Product.category.isnot(None),
        Product.category != "",
    )
    rows = query.distinct().order_by(
        Product.category,
        Product.subcategory,
        Product.sub_subcategory,
    ).all()

    slug_fn = slugify_vietnamese if SLUG_AVAILABLE else (lambda x: (x or "").lower().replace(" ", "-"))

    def _norm_map_name(val: Any) -> str:
        text = re.sub(r"\s+", " ", (val or "")).strip().lower()
        if not text:
            return ""
        try:
            return slugify_vietnamese(text)
        except Exception:
            return re.sub(r"\s+", " ", text).strip()

    def _keep_or_value(value: Any, fallback: str) -> str:
        if value is None:
            return fallback
        if isinstance(value, str) and value.strip() == "":
            return fallback
        return str(value).strip()

    mapping_lookup: Dict[tuple, CategoryFinalMapping] = {}
    final_mappings: List[CategoryFinalMapping] = []
    try:
        final_mappings = list(get_category_final_mappings_for_runtime(db))
        for m in final_mappings:
            if final_mapping_has_product_restrict(m):
                continue
            from_c1 = _norm_map_name(m.from_category)
            from_c2 = _norm_map_name(m.from_subcategory)
            from_c3 = _norm_map_name(m.from_sub_subcategory)
            key = (from_c1, from_c2, from_c3 if from_c3 else "*")
            mapping_lookup[key] = m
    except Exception:
        mapping_lookup = {}
        final_mappings = []

    tree: Dict[str, Dict[str, Any]] = {}

    def _merge_distinct_row_into_tree(c1: str, c2: str, c3: str) -> None:
        """Gộp một bộ (cấp1, cấp2, cấp3) vào cây hiển thị."""
        if not c1:
            return
        if c1 not in tree:
            tree[c1] = {"name": c1, "slug": slug_fn(c1), "children": {}}
        if not c2:
            return
        c2_key = _norm_map_name(c2)
        if c2_key not in tree[c1]["children"]:
            tree[c1]["children"][c2_key] = {
                "name": c2,
                "slug": slug_fn(c2),
                "children": [],
                "children_norm": set(),
            }
        if not c3:
            return
        c3_key = _norm_map_name(c3)
        if c3_key not in tree[c1]["children"][c2_key]["children_norm"]:
            tree[c1]["children"][c2_key]["children"].append({"name": c3, "slug": slug_fn(c3)})
            tree[c1]["children"][c2_key]["children_norm"].add(c3_key)

    for cat, subcat, subsub in rows:
        c1 = (cat or "").strip()
        c2 = (subcat or "").strip() if subcat else ""
        c3 = (subsub or "").strip() if subsub else ""
        mapped = mapping_lookup.get((_norm_map_name(c1), _norm_map_name(c2), _norm_map_name(c3)))
        if mapped:
            c1 = _keep_or_value(mapped.to_category, c1)
            c2 = _keep_or_value(mapped.to_subcategory, c2)
            c3 = _keep_or_value(mapped.to_sub_subcategory, c3)
        else:
            wildcard = mapping_lookup.get((_norm_map_name(c1), _norm_map_name(c2), "*"))
            if wildcard:
                c1 = _keep_or_value(wildcard.to_category, c1)
                c2 = _keep_or_value(wildcard.to_subcategory, c2)
        if not c1:
            continue
        _merge_distinct_row_into_tree(c1, c2, c3)

    # Luôn hiển thị nhánh đích đã khai báo trong mapping (đủ 3 cấp), kể cả khi tổ hợp DISTINCT từ SP
    # không khớp chuẩn hoá hoặc chưa có SP đích trong DB — tránh menu thiếu danh mục đích.
    for m in final_mappings:
        tc = (m.to_category or "").strip()
        ts = (m.to_subcategory or "").strip()
        tss = (m.to_sub_subcategory or "").strip()
        if tc and ts and tss:
            _merge_distinct_row_into_tree(tc, ts, tss)

    # Nhánh taxonomy theo FK: SP có category_id đúng cat3 nhưng cột AB/AC/AD chưa khớp → menu /danh-muc vẫn có link.
    try:
        from app.models.category import Category as _CatModel

        cat_by_id = {r.id: r for r in db.query(_CatModel).all()}
        fk_rows = (
            db.query(Product.category_id)
            .filter(
                Product.category_id.isnot(None),
                Product.is_active == is_active,
            )
            .distinct()
            .all()
        )
        for (cid,) in fk_rows:
            if not cid:
                continue
            c3 = cat_by_id.get(cid)
            if not c3 or c3.level != 3:
                continue
            c2 = cat_by_id.get(c3.parent_id)
            if not c2 or c2.level != 2:
                continue
            c1 = cat_by_id.get(c2.parent_id)
            if not c1 or c1.level != 1:
                continue
            n1 = (c1.name or "").strip()
            n2 = (c2.name or "").strip()
            n3 = (c3.name or "").strip()
            if n1 and n2 and n3:
                _merge_distinct_row_into_tree(n1, n2, n3)
    except Exception:
        pass

    result: List[Dict[str, Any]] = []
    for name, node in sorted(tree.items(), key=lambda x: x[0]):
        children_dict = node["children"]
        children_list = []
        for k, v in sorted(children_dict.items(), key=lambda x: x[0]):
            sub_children = v.get("children") or []
            if isinstance(sub_children, list):
                def _norm_c3(s: Any) -> Dict[str, Any]:
                    if isinstance(s, dict):
                        name = s.get("name", "")
                        return {"name": name, "slug": s.get("slug") or slug_fn(name)}
                    return {"name": str(s), "slug": slug_fn(str(s))}
                sub_children = [_norm_c3(s) for s in sub_children] if sub_children else []
            else:
                sub_children = [{"name": s, "slug": slug_fn(s)} for s in (v.get("children") or [])]
            children_list.append({"name": v["name"], "slug": v.get("slug", slug_fn(v["name"])), "children": sub_children})
        result.append({"name": name, "slug": node.get("slug", slug_fn(name)), "children": children_list})
    if hide_empty_branches:
        return prune_category_tree_empty_branches(db, result, is_active)
    return result


# Cùng key/TTL với GET /categories/from-products — by-path phải dùng đúng cây menu đã cache,
# tránh lệch (menu còn mà trang /danh-muc/... báo không tồn tại).
def _category_menu_tree_ttl_sec() -> float:
    try:
        return max(30.0, float(getattr(settings, "CATEGORY_MENU_TREE_TTL_SECONDS", 300)))
    except (TypeError, ValueError):
        return 300.0


_CATEGORY_MENU_TREE_KEY_ACTIVE = "category_tree_v1:from_products:active=true"
_CATEGORY_MENU_TREE_KEY_ALL = "category_tree_v1:from_products:active=false"


def _build_menu_tree_session(is_active: bool) -> List[Dict[str, Any]]:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        try:
            return get_category_tree_from_products(db, is_active=is_active, hide_empty_branches=True)
        except Exception:
            # Prune/đếm SP từng nhánh có thể lỗi với dữ liệu lạ; trả cây chưa prune vẫn hơn 500.
            return get_category_tree_from_products(db, is_active=is_active, hide_empty_branches=False)
    except Exception:
        return []
    finally:
        db.close()


def get_cached_menu_category_tree(is_active: bool = True) -> List[Dict[str, Any]]:
    """Cây danh mục trên menu (đã lọc theo CATEGORY_MENU_MIN_PRODUCT_COUNT). Cache in-process (mặc định 300s)."""
    from app.utils.ttl_cache import cache as ttl_cache
    key = _CATEGORY_MENU_TREE_KEY_ACTIVE if is_active else _CATEGORY_MENU_TREE_KEY_ALL
    return ttl_cache.get_or_fetch(key, _category_menu_tree_ttl_sec(), lambda: _build_menu_tree_session(is_active))


def get_category_by_path(
    db: Session,
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
    is_active: bool = True,
) -> Optional[Dict[str, Any]]:
    """
    Resolve path slugs (level1, level2?, level3?) thành thông tin danh mục cho SEO.
    Trả về: { level: 1|2|3, name, full_name, breadcrumb_names: [c1, c2?, c3?], product_count }
    """
    level1_slug = _normalize_category_url_slug(level1_slug) or ""
    level2_slug = _normalize_category_url_slug(level2_slug)
    level3_slug = _normalize_category_url_slug(level3_slug)

    tree = get_cached_menu_category_tree(is_active)
    bc = resolve_category_breadcrumb_names_from_tree(tree, level1_slug, level2_slug, level3_slug)
    if not bc:
        return None
    n = len(bc)
    if n == 1:
        count = count_products_for_category_path(db, bc[0], None, None, is_active)
        return {
            "level": 1,
            "name": bc[0],
            "full_name": bc[0],
            "breadcrumb_names": [bc[0]],
            "product_count": count,
        }
    if n == 2:
        count = count_products_for_category_path(db, bc[0], bc[1], None, is_active)
        return {
            "level": 2,
            "name": bc[1],
            "full_name": f"{bc[0]} - {bc[1]}",
            "breadcrumb_names": [bc[0], bc[1]],
            "product_count": count,
        }
    count = count_products_for_category_path(db, bc[0], bc[1], bc[2], is_active)
    return {
        "level": 3,
        "name": bc[2],
        "full_name": f"{bc[0]} - {bc[1]} - {bc[2]}",
        "breadcrumb_names": [bc[0], bc[1], bc[2]],
        "product_count": count,
    }


def get_category_sibling_names(
    db: Session,
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
    is_active: bool = True,
) -> List[str]:
    """
    Trả về danh sách tên hiển thị (name) của các danh mục anh/chị em cùng cấp.
    Dùng để đưa vào prompt Gemini, giúp đoạn văn SEO nhắc tên danh mục con → dễ gắn internal link.
    """
    tree = get_category_tree_from_products(db, is_active=is_active)
    level1_slug = _normalize_category_url_slug(level1_slug) or ""
    level2_slug = _normalize_category_url_slug(level2_slug)
    level3_slug = _normalize_category_url_slug(level3_slug)
    out: List[str] = []

    for c1 in tree:
        slug1 = (c1.get("slug") or slugify_vietnamese(c1.get("name", "")) if SLUG_AVAILABLE else "").lower()
        if slug1 != level1_slug:
            continue
        children2 = c1.get("children") or []
        if not level2_slug:
            for other in tree:
                s = (other.get("slug") or slugify_vietnamese(other.get("name", "")) if SLUG_AVAILABLE else "").lower()
                if s == level1_slug:
                    continue
                out.append(other.get("name", ""))
            return [n for n in out if n]

        for c2 in children2:
            slug2 = (c2.get("slug") or (slugify_vietnamese(c2.get("name", "")) if SLUG_AVAILABLE else "")).lower()
            if slug2 != level2_slug:
                continue
            children3 = c2.get("children") or []
            if not level3_slug:
                for other in children2:
                    if (other.get("slug") or (slugify_vietnamese(other.get("name", "")) if SLUG_AVAILABLE else "")).lower() == level2_slug:
                        continue
                    out.append(other.get("name", ""))
                return [n for n in out if n]
            for c3 in children3:
                name3 = c3.get("name", c3) if isinstance(c3, dict) else c3
                slug3 = (c3.get("slug") if isinstance(c3, dict) else (slugify_vietnamese(name3) if SLUG_AVAILABLE else "")).lower()
                if slug3 == level3_slug:
                    continue
                out.append(name3 if isinstance(name3, str) else str(name3))
            return [n for n in out if n]
        break
    return out


def path_to_breadcrumb_names(
    db: Session,
    path: str,
    is_active: bool = True,
) -> Optional[List[str]]:
    """
    Chuyển category path (slug, VD: 'giay-dep-nam/boot-nam') thành list tên danh mục [name1, name2?, name3?].
    Dùng để filter/cập nhật sản phẩm theo danh mục.
    """
    if not path or not path.strip():
        return None
    parts = [p.strip().lower() for p in path.split("/") if p.strip()]
    if not parts:
        return None
    info = get_category_by_path(
        db,
        level1_slug=parts[0],
        level2_slug=parts[1] if len(parts) > 1 else None,
        level3_slug=parts[2] if len(parts) > 2 else None,
        is_active=is_active,
    )
    if not info:
        return None
    return info.get("breadcrumb_names")


def get_category_seo_data(
    db: Session,
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
    is_active: bool = True,
    image_limit: int = 4,
) -> Optional[Dict[str, Any]]:
    """
    Lấy dữ liệu SEO cho danh mục: thông tin cơ bản + 4 ảnh + mô tả.
    Ưu tiên đọc từ bảng category_seo_meta (4 ảnh và mô tả cố định, không query sản phẩm mỗi lần).
    Nếu chưa có trong meta thì fallback: query products lấy ảnh, và trả sample_product_names để API gọi AI viết mô tả.
    Trả về: {
        level, name, full_name, breadcrumb_names, product_count,
        images: [url1, url2, ...],
        sample_product_names: [name1, ...]  # Chỉ có khi lấy từ products (fallback)
        seo_description: str | None  # Có khi đọc từ meta
    }
    """
    base_info = get_category_by_path(db, level1_slug, level2_slug, level3_slug, is_active)
    if not base_info:
        return None

    # Path danh mục (slug) để tra category_seo_meta — chuẩn hóa lowercase để khớp URL
    path_parts = [level1_slug]
    if level2_slug:
        path_parts.append(level2_slug)
    if level3_slug:
        path_parts.append(level3_slug)
    category_path = "/".join((p or "").strip().lower() for p in path_parts)

    # Ưu tiên: đọc 4 ảnh + mô tả từ DB (cố định cho mọi lần mở)
    meta = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == category_path).first()
    if meta and (meta.image_1 or meta.image_2 or meta.image_3 or meta.image_4):
        images = [meta.image_1, meta.image_2, meta.image_3, meta.image_4]
        images = [u for u in images if u]
        return {
            **base_info,
            "images": images,
            "sample_product_names": [],
            "seo_description": meta.seo_description if meta.seo_description else None,
            "seo_body": getattr(meta, "seo_body", None) or None,
        }

    # Fallback: chưa có meta (hoặc meta không có ảnh) → query products lấy ảnh + tên mẫu
    # Nếu có meta.seo_description thì vẫn dùng, tránh bỏ qua mô tả đã lưu
    saved_seo_description = meta.seo_description if meta and meta.seo_description else None

    # Fallback: query products lấy ảnh + tên mẫu (để API gọi AI viết mô tả khi chưa có saved_seo_description)
    breadcrumb_names = base_info.get("breadcrumb_names", [])
    query = db.query(Product).filter(Product.is_active == is_active)
    if len(breadcrumb_names) >= 1:
        name1 = breadcrumb_names[0]
        _e = category_field_equals_ci(Product.category, name1)
        if _e is not None:
            query = query.filter(_e)
    if len(breadcrumb_names) >= 2:
        name2 = breadcrumb_names[1]
        subcat_group = get_subcategory_group_for_query(name1, name2)
        if subcat_group:
            _inq = subcategory_field_in_ci(Product.subcategory, subcat_group)
            if _inq is not None:
                query = query.filter(_inq)
        else:
            _e2 = category_field_equals_ci(Product.subcategory, name2)
            if _e2 is not None:
                query = query.filter(_e2)
    if len(breadcrumb_names) >= 3:
        name3 = breadcrumb_names[2]
        _e3 = category_field_equals_ci(Product.sub_subcategory, name3)
        if _e3 is not None:
            query = query.filter(_e3)

    products = query.filter(
        Product.main_image.isnot(None),
        Product.main_image != ""
    ).order_by(Product.rating_point.desc()).limit(max(image_limit, 5)).all()

    images = []
    sample_names = []
    for p in products:
        if p.main_image and len(images) < image_limit:
            images.append(p.main_image)
        if p.name and len(sample_names) < 5:
            sample_names.append(p.name)

    seo_body = getattr(meta, "seo_body", None) if meta else None
    return {
        **base_info,
        "images": images,
        "sample_product_names": sample_names,
        "seo_description": saved_seo_description,
        "seo_body": seo_body,
    }


def set_category_seo_body(
    db: Session,
    category_path: str,
    seo_body: str,
) -> None:
    """Tạo hoặc cập nhật seo_body cho category_seo_meta (chỉ cần category_path). Lưu path lowercase."""
    category_path = (category_path or "").strip().lower()
    meta = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == category_path).first()
    if meta:
        meta.seo_body = seo_body
    else:
        meta = CategorySeoMeta(category_path=category_path, seo_body=seo_body)
        db.add(meta)
    db.commit()


def set_category_seo_description(
    db: Session,
    category_path: str,
    seo_description: str,
) -> None:
    """Tạo hoặc cập nhật seo_description cho category_seo_meta (category_path lowercase)."""
    category_path = (category_path or "").strip().lower()
    text = (seo_description or "").strip()
    meta = db.query(CategorySeoMeta).filter(CategorySeoMeta.category_path == category_path).first()
    if meta:
        meta.seo_description = text
    else:
        meta = CategorySeoMeta(category_path=category_path, seo_description=text)
        db.add(meta)
    db.commit()


def ensure_category_seo_description(
    db: Session,
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
    is_active: bool = True,
    force: bool = False,
) -> bool:
    """
    Nếu đã có seo_description trong meta thì bỏ qua (trừ khi force=True).
    Chỉ chạy khi danh mục resolve được và có ít nhất 1 SP active.
    Trả True nếu đã sinh/lưu mới.
    """
    from app.services.category_seo_service import generate_category_seo_description

    data = get_category_seo_data(
        db,
        level1_slug=level1_slug,
        level2_slug=level2_slug,
        level3_slug=level3_slug,
        is_active=is_active,
        image_limit=4,
    )
    if not data:
        return False
    if (data.get("product_count") or 0) < 1:
        return False
    if data.get("seo_description") and not force:
        return False

    breadcrumb_names = list(data.get("breadcrumb_names") or [])
    leaf_name = breadcrumb_names[-1] if breadcrumb_names else data.get("full_name") or ""
    sample = list(data.get("sample_product_names") or [])
    desc = generate_category_seo_description(
        category_name=str(leaf_name or data.get("name") or ""),
        breadcrumb_names=breadcrumb_names,
        product_count=int(data.get("product_count") or 0),
        sample_product_names=sample if sample else None,
    )
    if not desc:
        return False
    path_parts = [level1_slug]
    if level2_slug:
        path_parts.append(level2_slug)
    if level3_slug:
        path_parts.append(level3_slug)
    category_path = "/".join((p or "").strip().lower() for p in path_parts)
    set_category_seo_description(db, category_path=category_path, seo_description=desc)
    return True


def _category_path_slugs_from_names(
    c1_name: Optional[str],
    c2_name: Optional[str] = None,
    c3_name: Optional[str] = None,
) -> tuple:
    """
    Từ tên danh mục (category, subcategory, sub_subcategory) trả về (level1_slug, level2_slug?, level3_slug?)
    dùng cùng slug logic với get_category_tree_from_products.
    """
    slug_fn = slugify_vietnamese if SLUG_AVAILABLE else (lambda x: (x or "").lower().replace(" ", "-"))
    c1 = (c1_name or "").strip()
    if not c1:
        return (None, None, None)
    s1 = (slug_fn(c1) or "").lower()
    s2 = None
    s3 = None
    if (c2_name or "").strip():
        s2 = (slug_fn((c2_name or "").strip()) or "").lower()
        if (c3_name or "").strip():
            s3 = (slug_fn((c3_name or "").strip()) or "").lower()
    return (s1, s2, s3)


def ensure_category_seo_body(
    db: Session,
    level1_slug: str,
    level2_slug: Optional[str] = None,
    level3_slug: Optional[str] = None,
    is_active: bool = True,
    force: bool = False,
) -> bool:
    """
    Nếu danh mục đã có seo_body thì bỏ qua (return False), trừ khi force=True.
    Chỉ chạy khi có ít nhất 1 SP trong path (ưu tiên Gemini có ví dụ tên SP).
    Nếu chưa có seo_body thì gọi Gemini tạo và lưu (return True).
    Trả về True nếu đã sinh mới, False nếu bỏ qua hoặc path không tồn tại.
    """
    data = get_category_seo_data(
        db,
        level1_slug=level1_slug,
        level2_slug=level2_slug,
        level3_slug=level3_slug,
        is_active=is_active,
        image_limit=4,
    )
    if not data:
        return False
    if not force and data.get("seo_body"):
        return False
    if (data.get("product_count") or 0) < 1:
        return False
    from app.services.category_seo_service import generate_category_seo_body
    sibling_names = get_category_sibling_names(
        db, level1_slug=level1_slug, level2_slug=level2_slug, level3_slug=level3_slug, is_active=is_active
    )
    body = generate_category_seo_body(
        category_name=data.get("full_name", ""),
        breadcrumb_names=data.get("breadcrumb_names", []),
        product_count=data.get("product_count", 0),
        sample_product_names=data.get("sample_product_names") or [],
        related_category_names=sibling_names if sibling_names else None,
    )
    if not body:
        return False
    path_parts = [level1_slug]
    if level2_slug:
        path_parts.append(level2_slug)
    if level3_slug:
        path_parts.append(level3_slug)
    category_path = "/".join((p or "").strip().lower() for p in path_parts)
    set_category_seo_body(db, category_path=category_path, seo_body=body)
    return True


def create_product(db: Session, product: ProductCreate):
    data = product.model_dump() if hasattr(product, "model_dump") else product.dict()
    pid_raw = (data.get("product_id") or "").strip()
    if pid_raw:
        hit = find_conflicting_product_id_for_same_listing_source(db, pid_raw)
        if hit:
            raise ValueError(
                f"Mã cột A (prefix trước a188) đã tồn tại — sản phẩm {hit}. "
                "Chỉ cập nhật, không tạo mới."
            )
    normalize_product_data_image_urls_for_db(data)
    batch_reserved: Set[str] = set()
    data["code"] = ensure_unique_internal_product_code(
        db,
        data.get("code"),
        exclude_product_id=None,
        batch_reserved=batch_reserved,
    )
    data["product_info"] = sync_internal_code_into_product_info(data.get("product_info"), data["code"])
    canonicalize_hibox_placeholder_product_id(data)
    if not data.get("slug"):
        data["slug"] = generate_consistent_slug(data["name"], data["product_id"])

    for k in _RESPONSE_ONLY_PRODUCT_KEYS:
        data.pop(k, None)

    db_product = Product(**data)
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    _maybe_schedule_category_gemini_for_product(db, db_product)
    _schedule_google_sheets_sku_sync()
    try:
        from app.services.listing_facet_cache import refresh_caches_after_product_change

        refresh_caches_after_product_change(db, db_product)
    except Exception:
        pass
    return db_product

def update_product(db: Session, product_id: int, product_update: ProductUpdate):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product:
        old_category = db_product.category
        old_subcategory = db_product.subcategory
        old_sub_subcategory = db_product.sub_subcategory
        old_category_id = db_product.category_id
        from app.services.listing_facet_cache import snapshot_product_for_facet_refresh

        previous_product = snapshot_product_for_facet_refresh(db_product)
        update_data = (
            product_update.model_dump(exclude_unset=True)
            if hasattr(product_update, "model_dump")
            else product_update.dict(exclude_unset=True)
        )
        normalize_product_data_image_urls_for_db(update_data)

        if 'name' in update_data and 'slug' not in update_data:
            update_data['slug'] = generate_consistent_slug(update_data['name'], db_product.product_id)

        if "code" in update_data:
            batch_reserved: Set[str] = set()
            update_data["code"] = ensure_unique_internal_product_code(
                db,
                update_data.get("code"),
                exclude_product_id=db_product.id,
                batch_reserved=batch_reserved,
            )
            pi_src = update_data["product_info"] if "product_info" in update_data else db_product.product_info
            update_data["product_info"] = sync_internal_code_into_product_info(
                pi_src, update_data["code"]
            )
            probe = {
                "product_id": (
                    update_data["product_id"]
                    if "product_id" in update_data
                    else db_product.product_id
                ),
                "code": update_data["code"],
            }
            before_pid = probe["product_id"]
            canonicalize_hibox_placeholder_product_id(probe)
            if probe["product_id"] != before_pid:
                update_data["product_id"] = probe["product_id"]

        for field, value in update_data.items():
            if hasattr(db_product, field):
                setattr(db_product, field, value)
        
        db.commit()
        db.refresh(db_product)
        _maybe_schedule_category_gemini_for_product(db, db_product)
        if "code" in update_data or "product_id" in update_data:
            _schedule_google_sheets_sku_sync()
        try:
            from app.services.listing_facet_cache import refresh_caches_after_product_change

            refresh_caches_after_product_change(
                db,
                db_product,
                old_category=old_category,
                old_subcategory=old_subcategory,
                old_sub_subcategory=old_sub_subcategory,
                old_category_id=old_category_id,
                previous_product=previous_product,
            )
        except Exception:
            pass
    return db_product

def _delete_product_orm_only(db: Session, db_product: Product) -> None:
    """Xóa SP trong session (Bunny best-effort + db.delete); không commit — dùng bulk import batch."""
    delete_bunny_assets_for_product(db_product)
    db.delete(db_product)


def delete_product(db: Session, product_id: int, *, admin_force: bool = False):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product:
        from app.services.listing_facet_cache import (
            refresh_caches_after_product_change,
            snapshot_product_for_facet_refresh,
        )
        from app.services import warehouse_clearance as wh_clearance_svc

        wh_clearance_svc.assert_product_deletion_allowed(db, db_product, admin_force=admin_force)
        snapshot = snapshot_product_for_facet_refresh(db_product)
        _delete_product_orm_only(db, db_product)
        db.commit()
        _schedule_google_sheets_sku_sync()
        try:
            refresh_caches_after_product_change(db, snapshot)
        except Exception:
            pass
    return db_product


def _schedule_bunny_cleanup_for_deleted_products(products: List[Product]) -> None:
    """Dọn object Bunny sau bulk xóa — chạy nền để tránh timeout gateway trên lô lớn."""
    if not settings.BUNNY_DELETE_ON_PRODUCT_DELETE or not products:
        return

    all_urls: List[str] = []
    seen: Set[str] = set()
    for product in products:
        for url in collect_product_image_urls_for_bunny(product):
            if url not in seen:
                seen.add(url)
                all_urls.append(url)
    if not all_urls:
        return

    def _run() -> None:
        try:
            n = delete_bunny_storage_objects_for_urls(all_urls)
            if n:
                logger.info("Bulk xóa SP: đã dọn %s object Bunny (nền)", n)
        except Exception as exc:
            logger.warning("Bulk xóa SP — dọn Bunny nền lỗi (DB đã xóa): %s", exc)

    threading.Thread(target=_run, name="bulk-bunny-delete", daemon=True).start()


def _schedule_facet_cache_refresh_after_bulk_delete(snapshots: List[Any]) -> None:
    """Làm mới cache facet sau bulk xóa — nền để tránh 504 gateway trên lô lớn."""
    if not snapshots:
        return
    snap_copy = list(snapshots)

    def _run() -> None:
        from app.db.session import SessionLocal
        from app.services.listing_facet_cache import refresh_caches_after_products_change

        db_bg = SessionLocal()
        try:
            refresh_caches_after_products_change(db_bg, snap_copy)
            logger.info(
                "Bulk xóa SP: đã làm mới cache facet (nền), %s snapshot",
                len(snap_copy),
            )
        except Exception as exc:
            logger.warning("Bulk xóa SP — làm mới cache facet nền lỗi: %s", exc)
        finally:
            db_bg.close()

    threading.Thread(target=_run, name="bulk-facet-cache-refresh", daemon=True).start()


def bulk_delete_products_by_db_ids(db: Session, db_ids: List[int]) -> Tuple[List[int], List[int]]:
    """
    Xóa nhiều SP theo ``products.id`` trong một transaction; Bunny CDN dọn nền.
    Trả (deleted_db_ids, not_found_db_ids) — thứ tự ``deleted`` khớp tham số đầu vào.
    """
    if not db_ids:
        return [], []

    ordered_unique: List[int] = []
    seen: Set[int] = set()
    for raw in db_ids:
        try:
            pk = int(raw)
        except (TypeError, ValueError):
            continue
        if pk <= 0 or pk in seen:
            continue
        seen.add(pk)
        ordered_unique.append(pk)

    if not ordered_unique:
        return [], []

    rows = db.query(Product).filter(Product.id.in_(ordered_unique)).all()
    by_id = {row.id: row for row in rows}
    deleted: List[int] = []
    bunny_rows: List[Product] = []
    deleted_snapshots: List[Any] = []

    from app.services.listing_facet_cache import snapshot_product_for_facet_refresh
    from app.services import warehouse_clearance as wh_clearance_svc

    blocked: List[int] = []
    for pk in ordered_unique:
        row = by_id.get(pk)
        if row is None:
            continue
        try:
            wh_clearance_svc.assert_product_deletion_allowed(db, row)
        except ValueError:
            blocked.append(pk)
            continue
        deleted_snapshots.append(snapshot_product_for_facet_refresh(row))
        bunny_rows.append(row)
        db.delete(row)
        deleted.append(pk)

    if deleted:
        db.commit()
        _schedule_google_sheets_sku_sync()
        _schedule_bunny_cleanup_for_deleted_products(bunny_rows)
        _schedule_facet_cache_refresh_after_bulk_delete(deleted_snapshots)

    not_found = [pk for pk in ordered_unique if pk not in by_id]
    return deleted, not_found


def bulk_delete_products_by_excel_product_ids(
    db: Session,
    product_ids: List[str],
    *,
    admin_force: bool = True,
) -> Tuple[List[str], List[dict]]:
    """
    Xóa nhiều SP theo product_id Excel trong một transaction.
    Bunny + facet cache chạy một lần — nhanh hơn gọi delete_product lặp.
    """
    from urllib.parse import unquote
    from app.services import warehouse_clearance as wh_clearance_svc
    from app.services.listing_facet_cache import snapshot_product_for_facet_refresh

    deleted_pids: List[str] = []
    errors: List[dict] = []
    bunny_rows: List[Product] = []
    snapshots: List[Any] = []
    seen: Set[str] = set()

    for raw in product_ids:
        pid = unquote((raw or "").strip())
        if not pid or pid in seen:
            continue
        seen.add(pid)

        row = get_product_by_product_id(db, product_id=pid)
        if row is None:
            row = resolve_product_by_sku(db, sku=pid)
        if row is None:
            errors.append({"product_id": pid, "status": 404, "detail": "Product not found"})
            continue
        try:
            wh_clearance_svc.assert_product_deletion_allowed(db, row, admin_force=admin_force)
        except ValueError as exc:
            errors.append({"product_id": pid, "status": 400, "detail": str(exc)})
            continue

        snapshots.append(snapshot_product_for_facet_refresh(row))
        bunny_rows.append(row)
        db.delete(row)
        deleted_pids.append(pid)

    if deleted_pids:
        db.commit()
        _schedule_google_sheets_sku_sync()
        _schedule_bunny_cleanup_for_deleted_products(bunny_rows)
        _schedule_facet_cache_refresh_after_bulk_delete(snapshots)

    return deleted_pids, errors


def get_category_gemini_auto_settings_snapshot(db: Session) -> Dict[str, Any]:
    """Trả trạng thái chế độ auto Gemini SEO danh mục cho trang admin."""
    env_ok = bool(getattr(settings, "CATEGORY_GEMINI_SEO_AUTO_ENABLED", False))
    row = db.query(CategorySeoSettings).filter(CategorySeoSettings.id == 1).first()
    admin_flag = bool(row.gemini_auto_enabled) if row is not None else False
    return {
        "gemini_auto_enabled_admin": admin_flag,
        "env_allows_gemini_auto": env_ok,
        "gemini_auto_effective": env_ok and admin_flag,
        "gemini_whitelist_only_env": bool(getattr(settings, "CATEGORY_GEMINI_SEO_WHITELIST_ONLY", False)),
    }


def category_gemini_auto_is_effective(db: Session) -> bool:
    """True khi .env đã cho phép (VPS) và admin bật trong bảng category_seo_settings."""
    if not getattr(settings, "CATEGORY_GEMINI_SEO_AUTO_ENABLED", False):
        return False
    row = db.query(CategorySeoSettings).filter(CategorySeoSettings.id == 1).first()
    if row is None:
        return False
    return bool(row.gemini_auto_enabled)


def _should_run_auto_category_gemini_after_import(db: Session, rows_in_batch: int) -> bool:
    """Import Excel: chỉ spawn Gemini nền khi admin + env bật auto; né batch quá lớn."""
    if not category_gemini_auto_is_effective(db):
        return False
    thr = int(getattr(settings, "EXCEL_IMPORT_AUTO_SKIP_CATEGORY_SEO_MIN_ROWS", 0) or 0)
    if thr > 0 and rows_in_batch >= thr:
        logger.info(
            "EXCEL_IMPORT: Bỏ qua Gemini SEO danh mục (nền) — %s dòng ≥ ngưỡng %s "
            "(đặt EXCEL_IMPORT_AUTO_SKIP_CATEGORY_SEO_MIN_ROWS=0 để vẫn chạy)",
            rows_in_batch,
            thr,
        )
        return False
    return True


def _is_warehouse_row_in_import_batch(product_data: Dict) -> bool:
    from app.services.warehouse_clearance import parse_warehouse_product_id

    pid = str(product_data.get("product_id") or "").strip()
    return parse_warehouse_product_id(pid) is not None


def _collect_unique_category_paths_for_import(products_data: List[Dict]) -> List[tuple]:
    """Từ dữ liệu SP import, gom path slug danh mục (cấp 1 / 1+2 / đủ 3) cho SEO body."""
    unique_paths = set()
    for product_data in products_data:
        if _is_warehouse_row_in_import_batch(product_data):
            continue
        c1 = (product_data.get("category") or "").strip()
        c2 = (product_data.get("subcategory") or "").strip()
        c3 = (product_data.get("sub_subcategory") or "").strip()
        path_tuple = _category_path_slugs_from_names(c1, c2 if c2 else None, c3 if c3 else None)
        if path_tuple[0]:
            unique_paths.add(path_tuple)
            level1, level2, level3 = path_tuple
            unique_paths.add((level1, None, None))
            if level2:
                unique_paths.add((level1, level2, None))
    return list(unique_paths)


def _category_path_string_from_slugs(
    level1: str,
    level2: Optional[str] = None,
    level3: Optional[str] = None,
) -> str:
    parts = [str(level1 or "").strip().lower()]
    if level2:
        parts.append(str(level2).strip().lower())
    if level3:
        parts.append(str(level3).strip().lower())
    return "/".join(p for p in parts if p)


def _filter_paths_needing_gemini_seo(db: Session, paths_list: List[tuple]) -> List[tuple]:
    """Chỉ giữ path thiếu seo_description hoặc seo_body trong category_seo_meta."""
    if not paths_list:
        return []
    path_strs: List[str] = []
    tup_by_path: Dict[str, tuple] = {}
    for tup in paths_list:
        if not tup or not tup[0]:
            continue
        level1, level2, level3 = tup[0], tup[1] if len(tup) > 1 else None, tup[2] if len(tup) > 2 else None
        ps = _category_path_string_from_slugs(level1, level2, level3)
        if len(ps) < 3:
            continue
        if ps not in tup_by_path:
            path_strs.append(ps)
            tup_by_path[ps] = tup
    if not path_strs:
        return []

    rows = (
        db.query(
            CategorySeoMeta.category_path,
            CategorySeoMeta.seo_description,
            CategorySeoMeta.seo_body,
        )
        .filter(CategorySeoMeta.category_path.in_(path_strs))
        .all()
    )
    meta_by_path = {
        (r[0] or "").strip().lower(): (
            (r[1] or "").strip(),
            (r[2] or "").strip(),
        )
        for r in rows
    }
    out: List[tuple] = []
    for ps, tup in tup_by_path.items():
        desc, body = meta_by_path.get(ps, ("", ""))
        if desc and body:
            continue
        out.append(tup)
    return out


def _filter_category_paths_by_gemini_whitelist(db: Session, paths_list: List[tuple]) -> List[tuple]:
    """Khi CATEGORY_GEMINI_SEO_WHITELIST_ONLY: chỉ giữ path có trong category_seo_gemini_targets."""
    if not getattr(settings, "CATEGORY_GEMINI_SEO_WHITELIST_ONLY", False):
        return paths_list
    if not paths_list:
        return paths_list
    rows = db.query(CategorySeoGeminiTarget.category_path).all()
    targets = {(r[0] or "").strip().lower() for r in rows if r[0]}
    if not targets:
        return []
    out: List[tuple] = []
    for tup in paths_list:
        path_str = "/".join((x or "").strip().lower() for x in tup if x)
        if path_str in targets:
            out.append(tup)
    return out


def _run_category_gemini_seo_loop_for_paths(
    db: Session,
    paths_list: List[tuple],
    progress_callback,
) -> tuple:
    """Sinh seo_description + seo_body (Gemini) cho từng path; sleep khi có thay đổi. Trả (n_desc, n_body)."""
    n_paths = len(paths_list)
    if n_paths == 0:
        return (0, 0)
    n_desc = 0
    n_body = 0
    for path_i, (level1, level2, level3) in enumerate(paths_list):
        try:
            if progress_callback and (path_i % 3 == 0 or path_i == n_paths - 1):
                progress_callback("seo_categories", path_i + 1, n_paths)
            touched = False
            if ensure_category_seo_description(
                db,
                level1_slug=str(level1),
                level2_slug=str(level2) if level2 else None,
                level3_slug=str(level3) if level3 else None,
                is_active=True,
            ):
                n_desc += 1
                touched = True
            if ensure_category_seo_body(
                db,
                level1_slug=str(level1),
                level2_slug=str(level2) if level2 else None,
                level3_slug=str(level3) if level3 else None,
                is_active=True,
            ):
                n_body += 1
                touched = True
            if touched:
                logger.info(
                    "GEMINI_CATEGORY_SEO path %s%s%s — description/body đã cập nhật (hoặc một phần)",
                    level1,
                    f"/{level2}" if level2 else "",
                    f"/{level3}" if level3 else "",
                )
                time.sleep(1.2)
        except Exception as e:
            logger.warning("⚠️ Gemini SEO danh mục lỗi %s/%s/%s: %s", level1, level2, level3, e)
    return (n_desc, n_body)


def _spawn_category_gemini_background(paths_snapshot: List[tuple]) -> None:
    """Thread daemon: CATEGORY_GEMINI_SEO_AUTO — sinh seo_description + seo_body theo các path slug."""
    if not paths_snapshot:
        return

    snap = list(paths_snapshot)

    def _defer_gemini_categories() -> None:
        from app.db.session import SessionLocal

        db2 = SessionLocal()
        try:
            snap_f = _filter_category_paths_by_gemini_whitelist(db2, snap)
            if getattr(settings, "CATEGORY_GEMINI_SEO_WHITELIST_ONLY", False) and not snap_f:
                logger.info(
                    "CATEGORY_GEMINI [nền] Bỏ qua — CATEGORY_GEMINI_SEO_WHITELIST_ONLY và không có path trong whitelist (%s ban đầu)",
                    len(snap),
                )
                return
            snap_need = _filter_paths_needing_gemini_seo(db2, snap_f)
            if not snap_need:
                logger.info(
                    "CATEGORY_GEMINI [nền] Bỏ qua — %s path đã có đủ seo_description + seo_body",
                    len(snap_f),
                )
                return
            logger.info(
                "CATEGORY_GEMINI [nền] Bắt đầu — %s path thiếu SEO (đã kiểm tra %s path)",
                len(snap_need),
                len(snap_f),
            )
            nd, nb = _run_category_gemini_seo_loop_for_paths(db2, snap_need, None)
            logger.info(
                "CATEGORY_GEMINI [nền] Xong — meta description mới: %s, body mới: %s",
                nd,
                nb,
            )
        except Exception as exc:
            logger.exception("CATEGORY_GEMINI [nền] Lỗi: %s", exc)
        finally:
            db2.close()

    threading.Thread(target=_defer_gemini_categories, daemon=True).start()


def _maybe_schedule_category_gemini_for_product(db: Session, product: Optional[Product]) -> None:
    """API tạo/sửa SP: nếu auto hiệu lực (env + DB) và SP active có nhánh DM — Gemini SEO (nền) cho path đó."""
    if not category_gemini_auto_is_effective(db):
        return
    if product is None:
        return
    if not bool(getattr(product, "is_active", True)):
        return
    c1 = (getattr(product, "category", None) or "").strip()
    if not c1:
        return
    c2 = (getattr(product, "subcategory", None) or "").strip()
    c3 = (getattr(product, "sub_subcategory", None) or "").strip()
    path_tuple = _category_path_slugs_from_names(c1, c2 or None if c2 else None, c3 or None if c3 else None)
    if not path_tuple[0]:
        return
    if getattr(settings, "CATEGORY_GEMINI_SEO_WHITELIST_ONLY", False):
        path_str = "/".join((p or "").strip().lower() for p in path_tuple if p)
        if not db.query(CategorySeoGeminiTarget).filter(CategorySeoGeminiTarget.category_path == path_str).first():
            return
    _spawn_category_gemini_background([path_tuple])


# ========== BULK IMPORT FUNCTION ==========

def _build_cat3_lookup_indexes(db: Session) -> Dict[str, Dict[str, int]]:
    """
    Trả 3 dict tra cứu cat3 → category_id (level=3).
    Dùng trong bulk_import_products để map sản phẩm theo slug/full_slug/name (O(1) thay vì query DB từng row).
    """
    from app.models.category import Category as _Cat
    by_full_slug: Dict[str, int] = {}
    by_slug: Dict[str, int] = {}
    by_name: Dict[str, int] = {}
    rows = (
        db.query(_Cat.id, _Cat.full_slug, _Cat.slug, _Cat.name)
        .filter(_Cat.level == 3)
        .all()
    )
    for r in rows:
        if r.full_slug:
            by_full_slug[r.full_slug.strip().lower()] = r.id
        if r.slug:
            by_slug.setdefault(r.slug.strip().lower(), r.id)
        if r.name:
            by_name.setdefault(r.name.strip().lower(), r.id)
    return {"by_full_slug": by_full_slug, "by_slug": by_slug, "by_name": by_name}


def _resolve_category_id_from_row(
    product_data: Dict[str, Any], idx: Dict[str, Dict[str, int]]
) -> Optional[int]:
    """
    Tra cat3.id theo thứ tự ưu tiên:
      1) full_slug (vd `giay-dep-nam/sneaker-giay-chay-nam/giay-chay-trail-nam`)
         - lấy từ `slug_seo` hoặc `cat3_full_slug` (nếu Excel có), hoặc ghép từ category/sub/sub-sub.
      2) slug đơn (cat3_slug hoặc `slug_seo` chưa có dấu /)
      3) tên cat3 (`sub_subcategory`)
    Trả None nếu không match được — admin xử lý sau qua /admin/taxonomy.
    """
    cat = (product_data.get("category") or "").strip()
    sub = (product_data.get("subcategory") or "").strip()
    subsub = (product_data.get("sub_subcategory") or "").strip()

    candidates_full: List[str] = []
    for k in ("cat3_full_slug", "slug_seo", "full_slug"):
        v = (product_data.get(k) or "").strip()
        if "/" in v:
            candidates_full.append(v.lower())

    # Ghép từ category/sub/sub-sub nếu các trường đã được slug-hoá (không dùng nếu là tên VN có dấu)
    if cat and sub and subsub and all("/" not in s for s in (cat, sub, subsub)):
        candidates_full.append(f"{cat}/{sub}/{subsub}".lower())

    for fs in candidates_full:
        cid = idx["by_full_slug"].get(fs)
        if cid:
            return cid

    # Slug đơn của cat3
    for k in ("cat3_slug", "slug_seo"):
        v = (product_data.get(k) or "").strip()
        if v and "/" not in v:
            cid = idx["by_slug"].get(v.lower())
            if cid:
                return cid

    # Tên cat3
    if subsub:
        cid = idx["by_name"].get(subsub.lower())
        if cid:
            return cid
    return None


def bulk_import_products(
    db: Session,
    products_data: List[Dict],
    progress_callback=None,
):
    """Import multiple products from Excel data. progress_callback(phase, current, total) optional."""
    created = 0
    updated = 0
    deleted = 0
    errors = []
    warnings = []
    skipped: List[str] = []
    warehouse_import_rows = 0
    regular_import_rows = 0

    batch_size = max(
        1,
        min(
            int(getattr(settings, "EXCEL_IMPORT_COMMIT_BATCH_SIZE", 250) or 250),
            500,
        ),
    )

    n_products = len(products_data)
    db_tick = max(50, batch_size)

    if progress_callback and n_products:
        progress_callback("database", 0, n_products)

    # Cache cat3 lookup 1 lần (tránh query DB N lần). Nếu admin chưa import taxonomy, các dict rỗng.
    cat3_idx = _build_cat3_lookup_indexes(db)
    unmatched_cat3: List[str] = []

    sku_batch_reserved: Set[str] = set()

    db_prefix_owner, db_code_owner = _bulk_import_conflict_maps_initial(db)
    batch_prefix_owner: Dict[str, str] = {}
    batch_code_owner: Dict[str, str] = {}

    prefix_counts: Dict[str, int] = {}
    prefix_sample: Dict[str, str] = {}
    for pid_row in db.query(Product.product_id).filter(Product.product_id.isnot(None)).all():
        pid_s = (pid_row[0] or "").strip()
        src0 = _listing_source_prefix_from_product_id(pid_s)
        if not src0:
            continue
        pk0 = src0["prefix_key"]
        prefix_counts[pk0] = prefix_counts.get(pk0, 0) + 1
        prefix_sample.setdefault(pk0, src0["prefix"])
    for pk0, cnt in prefix_counts.items():
        if cnt > 1:
            warnings.append(
                f"Mã cột A «{prefix_sample.get(pk0, pk0)}» đang có {cnt} sản phẩm trên web — "
                "import chỉ cập nhật một bản, không tạo thêm trùng offer."
            )

    def _missing_required_category_labels(data: Dict, *, warehouse_row: bool = False) -> List[str]:
        if warehouse_row:
            # Kho thanh lý độc lập: chỉ bắt buộc danh mục cấp 1 (còn thiếu field khác vẫn import).
            labels = (("category", "danh mục cấp 1"),)
        else:
            labels = (
                ("category", "danh mục cấp 1"),
                ("subcategory", "danh mục cấp 2"),
                ("sub_subcategory", "danh mục cấp 3"),
            )
        missing: List[str] = []
        for key, label in labels:
            value = str(data.get(key) or "").strip()
            if not value or value.lower() == "nan":
                missing.append(label)
        return missing

    def _bulk_import_one_warehouse_row(idx: int, product_data: Dict) -> Optional[str]:
        """Import dòng kho thanh lý (id có /). Trả 'deleted'|'created'|'updated'|'skip'|'error' nếu đã xử lý."""
        from app.services import warehouse_clearance as wh_svc

        product_id = str(product_data.get("product_id") or "").strip()
        parsed = wh_svc.parse_warehouse_product_id(product_id)
        if not parsed:
            return None

        excel_listed = listed_from_excel_cell(product_data.pop("excel_import_listed", 1), default=1)
        if excel_listed == 0:
            existing_del = db.query(Product).filter(Product.product_id == product_id).first()
            if existing_del:
                try:
                    wh_svc.assert_product_deletion_allowed(db, existing_del)
                    with db.begin_nested():
                        _delete_product_orm_only(db, existing_del)
                    return "deleted"
                except ValueError as exc:
                    errors.append(f"Dòng {idx + 1} ({product_id}): {exc}")
                    return "error"
                except Exception as e:
                    errors.append(f"Dòng {idx + 1} ({product_id}): Không thể xóa khỏi DB — {e}")
                    return "error"
            skipped.append(
                f"Dòng {idx + 1} ({product_id}): listed=0 nhưng chưa có sản phẩm kho trong DB — bỏ qua."
            )
            return "skip"

        parent = wh_svc.find_parent_product_by_base_sku(db, parsed["base_sku"])
        if parent is not None:
            wh_svc.merge_clone_from_parent(parent, product_data, parsed)
            product_data["category_id"] = product_data.get("category_id") or parent.category_id
        else:
            missing = _missing_required_category_labels(product_data, warehouse_row=True)
            if missing:
                errors.append(
                    f"Dòng {idx + 1} ({product_id}): Thiếu {', '.join(missing)} — "
                    f"chưa có SP gốc «{parsed['base_sku']}», cần ít nhất danh mục cấp 1 trong file."
                )
                return "error"
            wh_svc.apply_warehouse_import_from_row(product_data, parsed)
            product_data["category_id"] = _resolve_category_id_from_row(product_data, cat3_idx)
            warnings.append(
                f"Dòng {idx + 1} ({product_id}): Chưa có SP gốc «{parsed['base_sku']}» — "
                "đã tạo/cập nhật dòng kho thanh lý từ file (không sinh SEO). "
                f"Tìm trong admin theo ID «{product_id}»."
            )

        product_data["slug"] = generate_consistent_slug(product_data.get("name", ""), product_id)
        normalize_product_data_image_urls_for_db(product_data)

        existing_wh = db.query(Product).filter(Product.product_id == product_id).first()
        try:
            with db.begin_nested():
                if existing_wh:
                    for key, value in product_data.items():
                        if hasattr(existing_wh, key) and key not in ["id", "created_at"]:
                            setattr(existing_wh, key, value)
                    existing_wh.updated_at = datetime.now()
                    return "updated"
                db.add(Product(**product_data))
                return "created"
        except Exception as e:
            errors.append(f"Dòng {idx + 1} ({product_id}): Lỗi import kho — {e}")
            return "error"

    for idx, product_data in enumerate(products_data):
        wh_action = _bulk_import_one_warehouse_row(idx, product_data)
        if wh_action is not None:
            if wh_action in ("created", "updated", "deleted"):
                warehouse_import_rows += 1
            if wh_action == "deleted":
                deleted += 1
            elif wh_action == "created":
                created += 1
            elif wh_action == "updated":
                updated += 1
            if (idx + 1) % batch_size == 0:
                db.commit()
            if progress_callback and ((idx + 1) % db_tick == 0 or (idx + 1) == n_products):
                progress_callback("database", idx + 1, n_products)
            continue

        product_id = product_data.get("product_id")
        if not product_id:
            errors.append(f"Dòng {idx + 1}: Thiếu product_id")
            continue
        source_prefix = _listing_source_prefix_from_product_id(product_id)
        if not source_prefix:
            errors.append(
                f"Dòng {idx + 1} ({product_id}): ID sản phẩm phải có dạng A<số> hoặc T<số> "
                "(có thể kèm legacy a188SKU)."
            )
            continue

        excel_listed = listed_from_excel_cell(product_data.pop("excel_import_listed", 1), default=1)
        if excel_listed == 0:
            delete_candidates = [product_id]
            prefix_owner = batch_prefix_owner.get(source_prefix["prefix_key"]) or db_prefix_owner.get(
                source_prefix["prefix_key"]
            )
            if prefix_owner and prefix_owner not in delete_candidates:
                delete_candidates.append(prefix_owner)
            existing_del = (
                db.query(Product)
                .filter(Product.product_id.in_(delete_candidates))
                .order_by(Product.id.asc())
                .first()
            )
            if existing_del:
                try:
                    from app.services import warehouse_clearance as wh_clearance_svc

                    wh_clearance_svc.assert_product_deletion_allowed(db, existing_del)
                    product_id = existing_del.product_id
                    code_upper = str(existing_del.code or "").strip().upper()
                    with db.begin_nested():
                        _delete_product_orm_only(db, existing_del)
                    _bulk_import_maps_remove_product_id(
                        product_id,
                        batch_prefix_owner,
                        db_prefix_owner,
                        batch_code_owner,
                        db_code_owner,
                    )
                    if code_upper and internal_sku_is_valid_format(code_upper):
                        sku_batch_reserved.discard(code_upper)
                    deleted += 1
                except ValueError as exc:
                    errors.append(f"Dòng {idx + 1} ({product_id}): {exc}")
                except Exception as e:
                    errors.append(f"Dòng {idx + 1} ({product_id}): Không thể xóa khỏi DB — {e}")
                    logger.error("❌ Delete-from-excel row %s: %s", idx + 1, e)
            else:
                skipped.append(
                    f"Dòng {idx + 1} ({product_id}): listed=0 nhưng chưa có sản phẩm trong DB — bỏ qua."
                )

            if (idx + 1) % batch_size == 0:
                db.commit()
                logger.info("💾 Batch commit: %s rows (kể cả xóa SP)", idx + 1)

            if progress_callback and ((idx + 1) % db_tick == 0 or (idx + 1) == n_products):
                progress_callback("database", idx + 1, n_products)
            continue

        missing_categories = _missing_required_category_labels(product_data)
        if missing_categories:
            errors.append(
                f"Dòng {idx + 1} ({product_id}): Thiếu {', '.join(missing_categories)} — không import."
            )
            continue

        pk = source_prefix["prefix_key"]
        prefix_label = source_prefix.get("prefix") or product_id
        existing: Optional[Product] = None
        owner_pid = batch_prefix_owner.get(pk) or db_prefix_owner.get(pk)
        if owner_pid:
            existing = db.query(Product).filter(Product.product_id == owner_pid).first()
        if existing is None:
            existing = db.query(Product).filter(Product.product_id == product_id).first()
        if existing is None:
            conflict_pid = find_conflicting_product_id_for_same_listing_source(db, product_id)
            if conflict_pid:
                existing = db.query(Product).filter(Product.product_id == conflict_pid).first()
        if existing is None:
            existing = find_product_by_listing_source_prefix(db, source_prefix)
        ex_pid_early = existing.id if existing else None
        proposed_raw = product_data.get("code")
        proposed_u = str(proposed_raw or "").strip().upper()
        if proposed_raw is not None and str(proposed_raw).strip():
            if internal_sku_is_valid_format(proposed_u):
                if proposed_u in sku_batch_reserved:
                    skipped.append(
                        f"Dòng {idx + 1} ({product_id}): Bỏ qua — mã SKU «{proposed_u}» "
                        "trùng trong cùng file import."
                    )
                    continue
                if internal_sku_exists_on_other_product(db, proposed_u, exclude_product_id=ex_pid_early):
                    skipped.append(
                        f"Dòng {idx + 1} ({product_id}): Bỏ qua — mã SKU «{proposed_u}» "
                        "đã có trên sản phẩm khác trên web."
                    )
                    continue
            else:
                proposed_u = ""

        try:
            row_slug_warning: Optional[str] = None
            resolved_cat_id: Optional[int] = None
            with db.begin_nested():
                existing_code_u = str(getattr(existing, "code", "") or "").strip().upper() if existing else ""
                if proposed_u:
                    final_sku = _ensure_bulk_import_internal_product_code(
                        db,
                        proposed_u,
                        exclude_product_id=existing.id if existing else None,
                        batch_reserved=sku_batch_reserved,
                    )
                elif existing and internal_sku_is_valid_format(existing_code_u):
                    final_sku = existing_code_u
                    sku_batch_reserved.add(final_sku)
                else:
                    final_sku = _ensure_bulk_import_internal_product_code(
                        db,
                        "",
                        exclude_product_id=existing.id if existing else None,
                        batch_reserved=sku_batch_reserved,
                    )
                final_product_id = _compose_listing_product_id(source_prefix["prefix"], final_sku)
                product_data["product_id"] = final_product_id
                product_id = final_product_id
                product_data["slug"] = generate_consistent_slug(product_data.get("name", ""), product_id)

                slug_value = product_data.get("slug", "")
                if slug_value:
                    existing_slug = db.query(Product).filter(Product.slug == slug_value).first()
                    if existing_slug and existing_slug.product_id != product_id:
                        new_slug = generate_consistent_slug(product_data.get("name", ""), product_id)
                        product_data["slug"] = new_slug
                        row_slug_warning = (
                            f"Dòng {idx + 1}: Slug '{slug_value}' bị trùng, đã đổi thành '{new_slug}'"
                        )

                resolved_cat_id = _resolve_category_id_from_row(product_data, cat3_idx)
                product_data["category_id"] = resolved_cat_id

                product_data["code"] = final_sku
                product_data["product_info"] = sync_internal_code_into_product_info(
                    product_data.get("product_info"),
                    product_data["code"],
                )
                normalize_product_data_image_urls_for_db(product_data)
                if not existing:
                    late = find_product_by_listing_source_prefix(db, source_prefix)
                    if late is None:
                        late_pid = find_conflicting_product_id_for_same_listing_source(
                            db, product_id
                        )
                        if late_pid:
                            late = (
                                db.query(Product)
                                .filter(Product.product_id == late_pid)
                                .first()
                            )
                    if late is not None:
                        existing = late
                        warnings.append(
                            f"Dòng {idx + 1}: Mã cột A «{prefix_label}» đã có "
                            f"(«{existing.product_id}») — cập nhật, không thêm mới."
                        )

                if existing:
                    old_product_id = existing.product_id
                    product_data["product_info"] = _merge_product_info_preserve_image_localization(
                        product_data.get("product_info"),
                        existing.product_info,
                    )
                    if old_product_id and old_product_id != product_id:
                        _bulk_import_maps_remove_product_id(
                            old_product_id,
                            batch_prefix_owner,
                            db_prefix_owner,
                            batch_code_owner,
                            db_code_owner,
                        )
                    for key, value in product_data.items():
                        if hasattr(existing, key) and key not in ["id", "created_at"]:
                            setattr(existing, key, value)
                    existing.updated_at = datetime.now()
                    row_was_update = True
                    logger.debug("🔄 Updated product: %s", product_id)
                else:
                    for k in _RESPONSE_ONLY_PRODUCT_KEYS:
                        product_data.pop(k, None)
                    db.add(Product(**product_data))
                    row_was_update = False
                    logger.debug("➕ Created product (pending flush): %s", product_id)

            if row_was_update:
                updated += 1
            else:
                created += 1
            regular_import_rows += 1

            if row_slug_warning:
                warnings.append(row_slug_warning)
            if resolved_cat_id is None and (
                product_data.get("category") or product_data.get("sub_subcategory")
            ):
                unmatched_cat3.append(
                    f"{product_id}: {product_data.get('category', '')}/"
                    f"{product_data.get('subcategory', '')}/"
                    f"{product_data.get('sub_subcategory', '')}"
                )

            batch_prefix_owner.setdefault(pk, product_id)
            db_prefix_owner[pk] = product_id
            code_only = str(product_data.get("code") or "").strip().upper()
            if internal_sku_is_valid_format(code_only):
                batch_code_owner.setdefault(code_only, product_id)
                db_code_owner[code_only] = product_id

        except Exception as e:
            errors.append(f"Dòng {idx + 1}: {str(e)}")
            logger.error("❌ Row %s error: %s", idx + 1, e)
            continue

        if (idx + 1) % batch_size == 0:
            db.commit()
            logger.info("💾 Batch commit: %s products", idx + 1)

        if progress_callback and ((idx + 1) % db_tick == 0 or (idx + 1) == n_products):
            progress_callback("database", idx + 1, n_products)

    # Final commit
    try:
        db.commit()
        logger.info(f"💾 Final commit: {created + updated + deleted} products processed")
        # Import Excel phải hoàn tất và trả trạng thái ổn định trước; Google Sheet sync
        # chạy nền/debounce để lỗi quota/mạng Google không làm hỏng luồng import.
        _schedule_google_sheets_sku_sync()
    except Exception as e:
        errors.append(f"Commit error: {str(e)}")
        db.rollback()
        logger.error(f"❌ Final commit error: {e}")
        total_processed = len(products_data)
        success_rate = (
            ((created + updated + deleted) / total_processed * 100) if total_processed > 0 else 0
        )
        return {
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "errors": errors,
            "warnings": warnings,
            "skipped": skipped,
            "skipped_count": len(skipped),
            "total_processed": total_processed,
            "success_rate": f"{success_rate:.1f}%",
        }

    # Cảnh báo SP không match được cat3 trong taxonomy (chỉ summary, không spam log)
    if unmatched_cat3:
        unmatched_count = len(unmatched_cat3)
        sample = unmatched_cat3[:10]
        warnings.append(
            f"Có {unmatched_count} sản phẩm không tìm được cat3 trong taxonomy "
            f"(category_id = NULL). Mẫu 10 SP đầu: {sample}. "
            "Kiểm tra /admin/taxonomy đã import chưa hoặc cập nhật slug_seo/cat3_slug trong file."
        )
        logger.warning("⚠️  %d products unmatched cat3 — first 10: %s", unmatched_count, sample)

    # CATEGORY_GEMINI_SEO_AUTO: sinh seo_description + seo_body (Gemini, nền) cho path DM có trong batch — né batch cực lớn.
    total_processed = len(products_data)
    success_rate_pct = (
        ((created + updated + deleted) / total_processed * 100) if total_processed > 0 else 0
    )

    only_warehouse_import = warehouse_import_rows > 0 and regular_import_rows == 0

    run_cat_gemini = (
        not only_warehouse_import
        and _should_run_auto_category_gemini_after_import(db, regular_import_rows or total_processed)
    )
    paths_need_n = 0
    if run_cat_gemini:
        paths = _filter_category_paths_by_gemini_whitelist(
            db, _collect_unique_category_paths_for_import(products_data)
        )
        paths_need = _filter_paths_needing_gemini_seo(db, paths)
        paths_need_n = len(paths_need)
        if paths_need:
            warnings.append(
                f"Gemini SEO danh mục (nền): {paths_need_n} path thiếu mô tả/body "
                f"(đã kiểm tra {len(paths)} path trong file; xem pm2 logs CATEGORY_GEMINI)."
            )
            _spawn_category_gemini_background(paths_need)
        elif paths:
            warnings.append(
                "Gemini SEO danh mục: các path trong file import đã có đủ mô tả + body — không gọi lại Gemini."
            )

    if progress_callback:
        progress_callback("seo_categories", 0, paths_need_n if run_cat_gemini else 0)

    # Calculate success rate
    success_rate = f"{success_rate_pct:.1f}%"

    result = {
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "errors": errors,
        "warnings": warnings,
        "skipped": skipped,
        "skipped_count": len(skipped),
        "total_processed": total_processed,
        "success_rate": success_rate,
        "only_warehouse_import": only_warehouse_import,
        "warehouse_import_rows": warehouse_import_rows,
        "regular_import_rows": regular_import_rows,
    }

    logger.info(f"📦 BULK IMPORT COMPLETE:")
    logger.info(f"   ➕ Created: {created}")
    logger.info(f"   🔄 Updated: {updated}")
    logger.info(f"   🗑 Xóa khỏi DB (listed=0): {deleted}")
    logger.info(f"   ⏭ Skipped (trùng a188/SKU): {len(skipped)}")
    logger.info(f"   ⚠️  Warnings: {len(warnings)}")
    logger.info(f"   ❌ Errors: {len(errors)}")
    logger.info(f"   📈 Success rate: {success_rate}")

    if created or updated or deleted:
        if only_warehouse_import:
            warnings.append(
                "Import kho thanh lý: không sinh SEO danh mục / không làm mới cache facet toàn catalog "
                "(chỉ áp dụng khi import sản phẩm thường)."
            )
        else:
            if progress_callback:
                progress_callback("cache_refresh", 0, None)

            def _refresh_caches_background() -> None:
                from app.db.session import SessionLocal
                from app.services.listing_facet_cache import refresh_caches_after_bulk_import

                db_bg = SessionLocal()
                try:
                    refresh_caches_after_bulk_import(db_bg)
                    logger.info("Background cache refresh after bulk import completed")
                except Exception as exc:
                    logger.warning("Background cache refresh after bulk import failed: %s", exc)
                finally:
                    db_bg.close()

            threading.Thread(target=_refresh_caches_background, daemon=True).start()
            warnings.append(
                "Đang làm mới cache bộ lọc danh mục/tìm kiếm/SEO cluster trên nền "
                "(catalog lớn có thể vài phút — không chặn kết thúc import)."
            )

    return result

# ========== EXPORT FUNCTIONS ==========

def get_all_products_for_export(db: Session) -> List[Dict]:
    """Get all products in Excel format (37 columns) — đọc theo lô để giảm RAM và timeout DB."""
    excel_rows: List[Dict] = []
    try:
        query = db.query(Product).order_by(Product.id.asc()).yield_per(300)
        for product in query:
            excel_row = product_to_excel_row(product)
            if excel_row:
                excel_rows.append(excel_row)
        logger.info(f"📤 Prepared {len(excel_rows)} products for export")
        return excel_rows
    except Exception as e:
        logger.error(f"❌ Error getting products for export: {str(e)}")
        raise

# ========== UTILITY FUNCTIONS ==========

def fix_all_slugs(db: Session) -> Dict[str, Any]:
    """Hàm tiện ích: Sửa tất cả slug cho sản phẩm hiện có"""
    try:
        products = db.query(Product).all()
        fixed = 0
        errors = []
        
        for product in products:
            try:
                if not product.slug or product.slug == '':
                    new_slug = generate_consistent_slug(product.name, product.product_id)
                    product.slug = new_slug
                    fixed += 1
                    
                    if fixed % 100 == 0:
                        db.commit()
                        logger.info(f"💾 Fixed {fixed} slugs...")
            except Exception as e:
                errors.append(f"Product {product.product_id}: {str(e)}")
        
        db.commit()
        
        result = {
            "total_products": len(products),
            "fixed_slugs": fixed,
            "errors": errors
        }
        
        logger.info(f"✅ Fixed {fixed} slugs for {len(products)} products")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error fixing slugs: {str(e)}")
        return {"error": str(e)}

# ========== VALIDATION FUNCTIONS ==========

def validate_product_data(product_data: Dict) -> List[str]:
    """Validate product data before import"""
    errors = []
    
    # Check required fields
    if not product_data.get('product_id'):
        errors.append("Missing product_id")
    
    if not product_data.get('name'):
        errors.append("Missing product name")
    
    # Check price
    price = product_data.get('price', 0)
    if not isinstance(price, (int, float)) or price < 0:
        errors.append(f"Invalid price: {price}")
    
    # Check JSON fields
    json_fields = ['sizes', 'colors', 'images', 'gallery', 'features']
    for field in json_fields:
        value = product_data.get(field)
        if value and isinstance(value, str):
            try:
                json.loads(value)
            except:
                errors.append(f"Invalid JSON in {field}: {value[:50]}")
    
    return errors
