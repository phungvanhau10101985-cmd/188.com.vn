# backend/app/crud/product.py - COMPLETE FIXED VERSION
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.models.product import Product
from app.models.search_mapping import SearchMapping, SearchMappingType
from app.models.search_log import SearchLog
from app.models.category_seo import CategorySeoMeta
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


def get_category_final_mappings(db: Session) -> List[CategoryFinalMapping]:
    return db.query(CategoryFinalMapping).order_by(CategoryFinalMapping.created_at.asc()).all()


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

        # Match đủ 3 cấp
        if n_category == from_c1 and n_subcategory == from_c2 and n_sub_subcategory == from_c3:
            category = _keep_or_value(m.to_category, category)
            subcategory = _keep_or_value(m.to_subcategory, subcategory)
            sub_subcategory = _keep_or_value(m.to_sub_subcategory, sub_subcategory)
            continue

        # Match 2 cấp (wildcard cấp 3)
        if n_category == from_c1 and n_subcategory == from_c2 and from_c3 == "":
            category = _keep_or_value(m.to_category, category)
            subcategory = _keep_or_value(m.to_subcategory, subcategory)
            # giữ nguyên cấp 3 hiện tại nếu mapping không set cấp 3
            sub_subcategory = _keep_or_value(m.to_sub_subcategory, sub_subcategory)

    product_data["category"] = category
    product_data["subcategory"] = subcategory
    product_data["sub_subcategory"] = sub_subcategory
    return product_data

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
    
    if category:
        query = query.filter(Product.category == category)
    if subcategory:
        subcat_group = get_subcategory_group_for_query(category or "", subcategory)
        if subcat_group:
            query = query.filter(Product.subcategory.in_(subcat_group))
        else:
            query = query.filter(Product.subcategory == subcategory)
    if sub_subcategory:
        query = query.filter(Product.sub_subcategory == sub_subcategory)
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


def get_category_tree_from_products(db: Session, is_active: bool = True) -> List[Dict[str, Any]]:
    """
    Tạo cây danh mục 3 cấp từ sản phẩm:
    - Cấp 1 (AB): Product.category
    - Cấp 2 (AC): Product.subcategory
    - Cấp 3 (AD): Product.sub_subcategory
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
    try:
        mappings = get_category_final_mappings(db)
        for m in mappings:
            from_c1 = _norm_map_name(m.from_category)
            from_c2 = _norm_map_name(m.from_subcategory)
            from_c3 = _norm_map_name(m.from_sub_subcategory)
            key = (from_c1, from_c2, from_c3 if from_c3 else "*")
            mapping_lookup[key] = m
    except Exception:
        mapping_lookup = {}

    tree: Dict[str, Dict[str, Any]] = {}
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
        if c1 not in tree:
            tree[c1] = {"name": c1, "slug": slug_fn(c1), "children": {}}
        if c2:
            c2_key = _norm_map_name(c2)
            if c2_key not in tree[c1]["children"]:
                tree[c1]["children"][c2_key] = {
                    "name": c2,
                    "slug": slug_fn(c2),
                    "children": [],
                    "children_norm": set(),
                }
            if c3:
                c3_key = _norm_map_name(c3)
                if c3_key not in tree[c1]["children"][c2_key]["children_norm"]:
                    tree[c1]["children"][c2_key]["children"].append({"name": c3, "slug": slug_fn(c3)})
                    tree[c1]["children"][c2_key]["children_norm"].add(c3_key)

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
    return result


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
    tree = get_category_tree_from_products(db, is_active=is_active)
    level1_slug = (level1_slug or "").strip().lower()
    level2_slug = (level2_slug or "").strip().lower() if level2_slug else None
    level3_slug = (level3_slug or "").strip().lower() if level3_slug else None

    for c1 in tree:
        slug1 = (c1.get("slug") or slugify_vietnamese(c1.get("name", "")) if SLUG_AVAILABLE else "").lower()
        if slug1 != level1_slug:
            continue
        name1 = c1.get("name", "")
        children2 = c1.get("children") or []
        if not level2_slug:
            count = db.query(Product).filter(
                Product.is_active == is_active,
                Product.category == name1,
            ).count()
            return {
                "level": 1,
                "name": name1,
                "full_name": name1,
                "breadcrumb_names": [name1],
                "product_count": count,
            }
        for c2 in children2:
            slug2 = (c2.get("slug") or (slugify_vietnamese(c2.get("name", "")) if SLUG_AVAILABLE else "")).lower()
            if slug2 != level2_slug:
                continue
            name2 = c2.get("name", "")
            children3 = c2.get("children") or []
            subcat_group = get_subcategory_group_for_query(name1, name2)
            if not level3_slug:
                q = db.query(Product).filter(
                    Product.is_active == is_active,
                    Product.category == name1,
                )
                if subcat_group:
                    q = q.filter(Product.subcategory.in_(subcat_group))
                else:
                    q = q.filter(Product.subcategory == name2)
                count = q.count()
                return {
                    "level": 2,
                    "name": name2,
                    "full_name": f"{name1} - {name2}",
                    "breadcrumb_names": [name1, name2],
                    "product_count": count,
                }
            for c3 in children3:
                name3 = c3.get("name", c3) if isinstance(c3, dict) else c3
                slug3 = (c3.get("slug") if isinstance(c3, dict) else (slugify_vietnamese(name3) if SLUG_AVAILABLE else "")).lower()
                if slug3 != level3_slug:
                    continue
                q = db.query(Product).filter(
                    Product.is_active == is_active,
                    Product.category == name1,
                    Product.sub_subcategory == name3,
                )
                if subcat_group:
                    q = q.filter(Product.subcategory.in_(subcat_group))
                else:
                    q = q.filter(Product.subcategory == name2)
                count = q.count()
                return {
                    "level": 3,
                    "name": name3,
                    "full_name": f"{name1} - {name2} - {name3}",
                    "breadcrumb_names": [name1, name2, name3],
                    "product_count": count,
                }
            break
        break
    return None


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
    level1_slug = (level1_slug or "").strip().lower()
    level2_slug = (level2_slug or "").strip().lower() if level2_slug else None
    level3_slug = (level3_slug or "").strip().lower() if level3_slug else None
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
        query = query.filter(Product.category == name1)
    if len(breadcrumb_names) >= 2:
        name2 = breadcrumb_names[1]
        subcat_group = get_subcategory_group_for_query(name1, name2)
        if subcat_group:
            query = query.filter(Product.subcategory.in_(subcat_group))
        else:
            query = query.filter(Product.subcategory == name2)
    if len(breadcrumb_names) >= 3:
        name3 = breadcrumb_names[2]
        query = query.filter(Product.sub_subcategory == name3)

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
) -> bool:
    """
    Nếu danh mục đã có seo_body thì bỏ qua (return False).
    Nếu chưa có thì gọi Gemini tạo và lưu (return True).
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
    if not data or data.get("seo_body"):
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
    return db_product

def delete_product(db: Session, product_id: int):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product:
        db.delete(db_product)
        db.commit()
    return db_product

# ========== BULK IMPORT FUNCTION ==========

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

    # Tự động đảm bảo seo_body cho các danh mục có trong lô import (đã có thì bỏ qua, chưa có thì sinh bằng Gemini).
    # Luôn thêm cả path cấp 1 (level1, None, None) và cấp 2 (level1, level2, None) để trang danh mục cấp 1/cấp 2 cũng có SEO body.
    unique_paths = set()
    for product_data in products_data:
        c1 = (product_data.get("category") or "").strip()
        c2 = (product_data.get("subcategory") or "").strip()
        c3 = (product_data.get("sub_subcategory") or "").strip()
        path_tuple = _category_path_slugs_from_names(c1, c2 if c2 else None, c3 if c3 else None)
        if path_tuple[0]:
            unique_paths.add(path_tuple)
            # Thêm path cấp 1 và cấp 2 (nếu có) để đảm bảo trang cha cũng có seo_body
            level1, level2, level3 = path_tuple
            unique_paths.add((level1, None, None))
            if level2:
                unique_paths.add((level1, level2, None))
    generated = 0
    paths_list = list(unique_paths)
    n_paths = len(paths_list)

    for path_i, (level1, level2, level3) in enumerate(paths_list):
        try:
            if progress_callback and (path_i % 3 == 0 or path_i == n_paths - 1):
                progress_callback("seo_categories", path_i + 1, n_paths)

            if ensure_category_seo_body(db, level1_slug=level1, level2_slug=level2, level3_slug=level3, is_active=True):
                generated += 1
                logger.info(f"📝 SEO body tự sinh cho danh mục: {level1}" + (f"/{level2}" if level2 else "") + (f"/{level3}" if level3 else ""))
                time.sleep(1.2)
        except Exception as e:
            logger.warning(f"⚠️ Không sinh SEO body cho {level1}/{level2 or ''}/{level3 or ''}: {e}")

    # Calculate success rate
    total_processed = len(products_data)
    success_rate = ((created + updated) / total_processed * 100) if total_processed > 0 else 0
    
    result = {
        "created": created,
        "updated": updated,
        "errors": errors,
        "warnings": warnings,
        "total_processed": total_processed,
        "success_rate": f"{success_rate:.1f}%"
    }
    if generated:
        result["seo_bodies_generated"] = generated
    
    logger.info(f"📦 BULK IMPORT COMPLETE:")
    logger.info(f"   ➕ Created: {created}")
    logger.info(f"   🔄 Updated: {updated}")
    logger.info(f"   ⚠️  Warnings: {len(warnings)}")
    logger.info(f"   ❌ Errors: {len(errors)}")
    logger.info(f"   📈 Success rate: {success_rate:.1f}%")
    
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
