# backend/app/crud/product.py - COMPLETE FIXED VERSION
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from typing import List, Optional, Dict, Any, Set
from app.models.product import Product
from app.models.search_mapping import SearchMapping, SearchMappingType
from app.models.search_log import SearchLog
from app.models.category_seo import CategorySeoMeta, CategorySeoGeminiTarget, CategorySeoSettings
from app.models.category_transform_rule import CategoryTransformRule
from app.models.category_final_mapping import CategoryFinalMapping
from app.schemas.product import ProductCreate, ProductUpdate
import math
import logging
import json
import time
from datetime import datetime
from app.core.config import settings
from app.utils.vietnamese import (
    normalize_for_search_no_accent,
    VIETNAMESE_ACCENT_MAP,
    COMMON_WORD_MAPPING,
    remove_vietnamese_accents,
)
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

def generate_consistent_slug(name: str, product_id: str = "") -> str:
    """
    Tạo slug nhất quán cho cả import và export
    Sử dụng hàm create_slug từ slug.py cho tiếng Việt
    PRODUCT_ID: Giữ nguyên tất cả, chỉ chuyển hoa → thường
    """
    try:
        if not product_id:
            product_id = f"pid{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # FIX: PRODUCT_ID giữ NGUYÊN TẤT CẢ ký tự
        # Chỉ chuyển CHỮ HOA thành CHỮ THƯỜNG
        # Ví dụ: "A863862166833a188b0196" → "a863862166833a188b0196"
        # Không bỏ 'A' đầu, không cắt xén, giữ NGUYÊN
        
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


def excel_row_to_product(row: Dict) -> Dict:
    """
    Convert Excel row (36 columns A-AJ) to product dictionary
    FIX: Đúng mapping các cột Color, Occasion, Features
    """
    try:
        # Lấy các giá trị cơ bản
        product_id = str(row.get('id', '')).strip()
        product_name = str(row.get('name', '')).strip()
        
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
        product_data = {
            'product_id': product_id,
            'code': str(row.get('sku', '')).strip(),
            'origin': str(row.get('origin', '')).strip(),
            'brand_name': str(row.get('brand', '')).strip(),
            'name': product_name,
            'description': str(row.get('pro_content', '')).strip(),
            'price': safe_float(row.get('price', 0)),
            'shop_name': str(row.get('shop_name', '')).strip(),
            'shop_id': str(row.get('shop_id', '')).strip(),
            'pro_lower_price': str(row.get('pro_lower_price', '')).strip(),
            'pro_high_price': str(row.get('pro_high_price', '')).strip(),
            'group_rating': safe_int(row.get('rating_group_id', 0)),
            'group_question': safe_int(row.get('question_group_id', 0)),
            'sizes': parse_json_field(row.get('sizes', '[]')),
            'colors': parse_json_field(row.get('Variant', '[]')),
            'images': parse_json_field(row.get('gallery_images', '[]')),
            'gallery': parse_json_field(row.get('detail_images', '[]')),
            'link_default': str(row.get('product_url', '')).strip(),
            'video_link': str(row.get('video_url', '')).strip(),
            'main_image': str(row.get('main_image', '')).strip(),
            'likes': safe_int(row.get('likes_count', 0)),
            'purchases': safe_int(row.get('purchases_count', 0)),
            'rating_total': safe_int(row.get('reviews_count', 0)),
            'question_total': safe_int(row.get('questions_count', 0)),
            'rating_point': safe_float(row.get('rating_score', 0.0)),
            'available': safe_int(row.get('stock_quantity', 0)),
            'deposit_require': safe_bool(row.get('deposit_required', 0)),
            'category': str(row.get('Main Category', '')).strip(),
            'subcategory': str(row.get('Subcategory', '')).strip(),
            'sub_subcategory': str(row.get('Sub-subcategory', '')).strip(),
            'raw_category': str(row.get('Main Category', '')).strip(),
            'raw_subcategory': str(row.get('Subcategory', '')).strip(),
            'raw_sub_subcategory': str(row.get('Sub-subcategory', '')).strip(),
            'material': str(row.get('Material', '')).strip(),
            'style': str(row.get('Style', '')).strip(),
            # FIX: Cột Color -> color (đúng mapping)
            'color': str(row.get('Color', '')).strip(),
            # FIX: Cột Occasion -> occasion (đúng mapping)
            'occasion': str(row.get('Occasion', '')).strip(),
            # FIX: Features xử lý đúng
            'features': features_list,
            'weight': str(row.get('Weight', '')).strip(),
            # Cột AK: Thông tin sản phẩm (JSON) - thử nhiều tên cột
            'product_info': _parse_product_info(
                row.get('product_info')
                or row.get('Thông tin sản phẩm')
                or row.get('thong_tin_san_pham')
                or row.get('Thong tin san pham')
            ),
            'slug': slug_value,
            'is_active': True,
            'created_at': datetime.now()
        }
        
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
    """Convert Product to Excel row - 37 columns A-AK (with Slug as last column)"""
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
        excel_row = {
            'id': product.product_id or '',
            'sku': product.code or '',
            'origin': product.origin or '',
            'brand': product.brand_name or '',
            'name': product.name or '',
            'pro_content': product.description or '',
            'price': product.price or 0,
            'shop_name': product.shop_name or '',
            'shop_id': product.shop_id or '',
            'pro_lower_price': product.pro_lower_price or '',
            'pro_high_price': product.pro_high_price or '',
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
            'deposit_required': 1 if product.deposit_require else 0,
            'Main Category': product.category or '',
            'Subcategory': product.subcategory or '',
            'Sub-subcategory': product.sub_subcategory or '',
            'Material': product.material or '',
            'Style': product.style or '',
            # FIX: Cột 33: Color -> Color (đúng vị trí)
            'Color': product.color or '',
            # FIX: Cột 34: Occasion -> Occasion (đúng vị trí)
            'Occasion': product.occasion or '',
            # FIX: Cột 35: Features -> Text thường (không phải JSON)
            'Features': features_export,
            'Weight': product.weight or '',
            # Cột AK (37): Thông tin sản phẩm (JSON)
            'product_info': json.dumps(product.product_info, ensure_ascii=False) if getattr(product, 'product_info', None) else '',
            # Cột AL (38): Slug
            'Slug': slug_value
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


def _search_products_by_words(db: Session, query, words: List[str], limit: int, skip: int):
    """
    Tìm sản phẩm khi chuỗi tổng hợp chứa TẤT CẢ các từ (ilike).
    Chuỗi tổng hợp bao gồm: tên, mã, danh mục 1/2/3, chất liệu, kiểu dáng, màu sắc,
    dịp, tính năng, size, và cột AK (product_info - Thông tin sản phẩm).
    KHÔNG tìm kiếm trong mô tả sản phẩm.
    """
    from sqlalchemy.sql import func
    from sqlalchemy import cast, String
    
    # Tạo chuỗi tổng hợp từ các trường cần tìm kiếm
    # Sử dụng COALESCE để xử lý NULL và CAST để chuyển JSON thành text
    search_concat = func.concat(
        func.coalesce(Product.name, ""), " ",
        func.coalesce(Product.code, ""), " ",
        func.coalesce(Product.category, ""), " ",
        func.coalesce(Product.subcategory, ""), " ",
        func.coalesce(Product.sub_subcategory, ""), " ",
        func.coalesce(Product.material, ""), " ",
        func.coalesce(Product.style, ""), " ",
        func.coalesce(Product.color, ""), " ",
        func.coalesce(Product.occasion, ""), " ",
        # Features và sizes là JSON array, cast thành text
        func.coalesce(cast(Product.features, String), ""), " ",
        func.coalesce(cast(Product.sizes, String), ""), " ",
        # Cột AK: Thông tin sản phẩm (JSON) - tìm trong toàn bộ nội dung
        func.coalesce(cast(Product.product_info, String), "")
    )
    search_concat_norm = func.lower(search_concat)

    for w in words:
        w_norm = (w or "").strip().lower()
        if not w_norm:
            continue
        query = query.filter(search_concat_norm.ilike(f"%{w_norm}%"))
    total = query.count()
    products = query.order_by(Product.id).offset(skip).limit(limit).all()
    return total, products


def get_product_by_slug(db: Session, slug: str) -> Optional[Product]:
    try:
        return db.query(Product).filter(Product.slug == slug).first()
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return None

def get_products(
    db: Session, 
    skip: int = 0, 
    limit: int = 100,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    sub_subcategory: Optional[str] = None,
    shop_name: Optional[str] = None,
    shop_id: Optional[str] = None,
    pro_lower_price: Optional[str] = None,
    pro_high_price: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    is_active: Optional[bool] = None,
    q: Optional[str] = None,
    product_id: Optional[str] = None
):
    query = db.query(Product)
    
    if category and str(category).strip():
        ce = category_field_equals_ci(Product.category, category)
        if ce is not None:
            query = query.filter(ce)
    if subcategory and str(subcategory).strip():
        subcat_group = get_subcategory_group_for_query(category or "", subcategory)
        if subcat_group:
            ine = subcategory_field_in_ci(Product.subcategory, subcat_group)
            if ine is not None:
                query = query.filter(ine)
        else:
            se = category_field_equals_ci(Product.subcategory, subcategory)
            if se is not None:
                query = query.filter(se)
    if sub_subcategory and str(sub_subcategory).strip():
        sse = category_field_equals_ci(Product.sub_subcategory, sub_subcategory)
        if sse is not None:
            query = query.filter(sse)
    if shop_name:
        query = query.filter(Product.shop_name.ilike(f"%{shop_name.strip()}%"))
    if shop_id:
        query = query.filter(Product.shop_id == shop_id)
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
        query = query.filter(Product.product_id == product_id.strip())
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
        normalized_key = _normalize_search_key(raw_query)
        has_accents = _has_vietnamese_accents(raw_query)

        mapped_query = None
        mapping = _get_search_mapping(db, normalized_key)

        try:
            category_tree = get_category_tree_from_products(db, is_active=is_active if is_active is not None else True)
        except Exception:
            category_tree = []

        if has_accents and mapping and mapping.keyword_target:
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
                total, products = _search_products_by_words(db, query, mapped_words, limit, skip)
                if total > 0:
                    applied_query = mapped_normalized
                    _touch_search_mapping(db, mapping)

        # Nếu mapping không có kết quả thì tìm theo từ khóa gốc
        if total == 0:
            normalized = normalize_search_query(raw_query)
            words = [w.strip() for w in normalized.split() if w.strip()]
            if words:
                total, products = _search_products_by_words(db, query, words, limit, skip)
                if total > 0:
                    applied_query = normalized
        if total > 0:
            _log_search(db, raw_query, total, ai_processed=False)
        if total == 0:
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
                        total, products = _search_products_by_words(db, query, words2, limit, skip)
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
            _log_search(db, raw_query, total, ai_processed=ai_processed)
    if not (q and q.strip()):
        total = query.count()
        products = query.order_by(Product.id).offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "products": products,
        "page": skip // limit + 1 if limit > 0 else 1,
        "size": limit,
        "total_pages": math.ceil(total / limit) if limit > 0 else 1,
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


def count_products_for_category_path(
    db: Session,
    name1: str,
    name2: Optional[str] = None,
    name3: Optional[str] = None,
    is_active: bool = True,
) -> int:
    """
    Đếm sản phẩm active khớp đường danh mục (cùng logic filter với get_category_by_path).
    name2/name3 None hoặc rỗng = không siết thêm cấp đó (đếm phạm vi rộng hơn).
    """
    name1 = (name1 or "").strip()
    if not name1:
        return 0
    filt_l1 = [Product.is_active == is_active]
    _e = category_field_equals_ci(Product.category, name1)
    if _e is not None:
        filt_l1.append(_e)
    if not name2 or not str(name2).strip():
        return db.query(Product).filter(*filt_l1).count()
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
        return q.count()
    name3 = str(name3).strip()
    q = db.query(Product).filter(Product.is_active == is_active)
    _ca = category_field_equals_ci(Product.category, name1)
    _ss = category_field_equals_ci(Product.sub_subcategory, name3)
    if _ca is not None:
        q = q.filter(_ca)
    if _ss is not None:
        q = q.filter(_ss)
    if subcat_group:
        _inq = subcategory_field_in_ci(Product.subcategory, subcat_group)
        if _inq is not None:
            q = q.filter(_inq)
    else:
        _sb = category_field_equals_ci(Product.subcategory, name2)
        if _sb is not None:
            q = q.filter(_sb)
    return q.count()


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
    for c1 in tree:
        name1 = (c1.get("name") or "").strip()
        if not name1:
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
                cnt = count_products_for_category_path(db, name1, name2, n3s, is_active)
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
_CATEGORY_MENU_TREE_TTL_SEC = 60.0
_CATEGORY_MENU_TREE_KEY_ACTIVE = "category_tree_v1:from_products:active=true"
_CATEGORY_MENU_TREE_KEY_ALL = "category_tree_v1:from_products:active=false"


def _build_menu_tree_session(is_active: bool) -> List[Dict[str, Any]]:
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        return get_category_tree_from_products(db, is_active=is_active, hide_empty_branches=True)
    finally:
        db.close()


def get_cached_menu_category_tree(is_active: bool = True) -> List[Dict[str, Any]]:
    """Cây danh mục trên menu (đã lọc theo CATEGORY_MENU_MIN_PRODUCT_COUNT). Cache process 60s, đồng bộ với from-products."""
    from app.utils.ttl_cache import cache as ttl_cache
    key = _CATEGORY_MENU_TREE_KEY_ACTIVE if is_active else _CATEGORY_MENU_TREE_KEY_ALL
    return ttl_cache.get_or_fetch(key, _CATEGORY_MENU_TREE_TTL_SEC, lambda: _build_menu_tree_session(is_active))


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
    # Đảm bảo có slug
    if not product.slug:
        product.slug = generate_consistent_slug(product.name, product.product_id)
    
    db_product = Product(**product.dict())
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    _maybe_schedule_category_gemini_for_product(db, db_product)
    return db_product

def update_product(db: Session, product_id: int, product_update: ProductUpdate):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product:
        update_data = product_update.dict(exclude_unset=True)
        
        if 'name' in update_data and 'slug' not in update_data:
            update_data['slug'] = generate_consistent_slug(update_data['name'], db_product.product_id)
        
        for field, value in update_data.items():
            if hasattr(db_product, field):
                setattr(db_product, field, value)
        
        db.commit()
        db.refresh(db_product)
        _maybe_schedule_category_gemini_for_product(db, db_product)
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product

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


def _collect_unique_category_paths_for_import(products_data: List[Dict]) -> List[tuple]:
    """Từ dữ liệu SP import, gom path slug danh mục (cấp 1 / 1+2 / đủ 3) cho SEO body."""
    unique_paths = set()
    for product_data in products_data:
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
            logger.info("CATEGORY_GEMINI [nền] Bắt đầu — %s path", len(snap_f))
            nd, nb = _run_category_gemini_seo_loop_for_paths(db2, snap_f, None)
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
    errors = []
    warnings = []

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

    for idx, product_data in enumerate(products_data):
        try:
            product_id = product_data.get('product_id')
            if not product_id:
                errors.append(f"Dòng {idx+1}: Thiếu product_id")
                continue
            
            # Kiểm tra trùng slug
            slug_value = product_data.get('slug', '')
            if slug_value:
                existing_slug = db.query(Product).filter(Product.slug == slug_value).first()
                if existing_slug and existing_slug.product_id != product_id:
                    new_slug = generate_consistent_slug(product_data.get('name', ''), product_id)
                    product_data['slug'] = new_slug
                    warnings.append(f"Dòng {idx+1}: Slug '{slug_value}' bị trùng, đã đổi thành '{new_slug}'")
            
            # Tra `category_id` (cat3.id) theo slug/full_slug/name. Không match → để None,
            # log để admin biết cần bổ sung taxonomy hoặc đồng bộ tên Excel.
            resolved_cat_id = _resolve_category_id_from_row(product_data, cat3_idx)
            product_data["category_id"] = resolved_cat_id
            if resolved_cat_id is None and (
                product_data.get("category") or product_data.get("sub_subcategory")
            ):
                unmatched_cat3.append(
                    f"{product_id}: {product_data.get('category', '')}/"
                    f"{product_data.get('subcategory', '')}/"
                    f"{product_data.get('sub_subcategory', '')}"
                )

            existing = db.query(Product).filter(Product.product_id == product_id).first()
            
            if existing:
                # Update existing product
                for key, value in product_data.items():
                    if hasattr(existing, key) and key not in ['id', 'created_at']:
                        setattr(existing, key, value)
                existing.updated_at = datetime.now()
                updated += 1
                logger.debug(f"🔄 Updated product: {product_id}")
            else:
                # Create new product
                db_product = Product(**product_data)
                db.add(db_product)
                created += 1
                logger.debug(f"➕ Created product: {product_id}")
            
            # Batch commit (lô lớn hơn khi import ~30k dòng để giảm số transaction)
            if (idx + 1) % batch_size == 0:
                db.commit()
                logger.info(f"💾 Batch commit: {idx + 1} products")

            if progress_callback and (
                (idx + 1) % db_tick == 0 or (idx + 1) == n_products
            ):
                progress_callback("database", idx + 1, n_products)

        except Exception as e:
            error_msg = f"Dòng {idx+1}: {str(e)}"
            errors.append(error_msg)
            db.rollback()
            logger.error(f"❌ Row {idx+1} error: {e}")
    
    # Final commit
    try:
        db.commit()
        logger.info(f"💾 Final commit: {created + updated} products processed")
    except Exception as e:
        errors.append(f"Commit error: {str(e)}")
        db.rollback()
        logger.error(f"❌ Final commit error: {e}")
        total_processed = len(products_data)
        success_rate = ((created + updated) / total_processed * 100) if total_processed > 0 else 0
        return {
            "created": created,
            "updated": updated,
            "errors": errors,
            "warnings": warnings,
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
    success_rate_pct = ((created + updated) / total_processed * 100) if total_processed > 0 else 0

    if _should_run_auto_category_gemini_after_import(db, total_processed):
        paths = _collect_unique_category_paths_for_import(products_data)
        if paths:
            warnings.append(
                "Đã bật Gemini SEO danh mục — đang chạy nền cho các path trong file import "
                "(xem pm2 logs CATEGORY_GEMINI)."
            )
            _spawn_category_gemini_background(paths)

    if progress_callback:
        progress_callback("seo_categories", n_products or 1, n_products or 1)

    # Calculate success rate
    success_rate = f"{success_rate_pct:.1f}%"
    
    result = {
        "created": created,
        "updated": updated,
        "errors": errors,
        "warnings": warnings,
        "total_processed": total_processed,
        "success_rate": success_rate,
    }

    logger.info(f"📦 BULK IMPORT COMPLETE:")
    logger.info(f"   ➕ Created: {created}")
    logger.info(f"   🔄 Updated: {updated}")
    logger.info(f"   ⚠️  Warnings: {len(warnings)}")
    logger.info(f"   ❌ Errors: {len(errors)}")
    logger.info(f"   📈 Success rate: {success_rate}")
    
    return result

# ========== EXPORT FUNCTIONS ==========

def get_all_products_for_export(db: Session) -> List[Dict]:
    """Get all products in Excel format (37 columns)"""
    try:
        products = db.query(Product).all()
        excel_rows = []
        
        for product in products:
            excel_row = product_to_excel_row(product)
            if excel_row:
                excel_rows.append(excel_row)
        
        logger.info(f"📤 Prepared {len(excel_rows)} products for export")
        return excel_rows
        
    except Exception as e:
        logger.error(f"❌ Error getting products for export: {str(e)}")
        return []

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
