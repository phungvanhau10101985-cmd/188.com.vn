"""
backend/app/services/category_seo_analyzer.py

Phiên bản rút gọn theo yêu cầu mới:
- GỠ BỎ toàn bộ phần phân tích ý định SEO bằng AI (Gemini/DeepSeek) và rule-based.
- GỠ BỎ logic gộp sản phẩm theo intent SEO.

Giữ lại những gì vẫn cần cho hệ thống:
- Đọc trạng thái SEO của một path (dựa trên bảng category_seo_mappings do admin tự cấu hình).
- Lấy danh sách redirects đã được approve.
- Trả ra danh sách path danh mục (nếu cần thống kê).
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging

from app.models.category_seo import CategorySeoMapping, CategorySeoDictionary  # noqa: F401  (dictionary dùng ở chỗ khác)
from app.models.product import Product

logger = logging.getLogger(__name__)


# ========== DEFAULT_SYNONYMS (GIỮ LẠI CHO TƯƠNG THÍCH, KHÔNG CÒN DÙNG CHO AI) ==========
# Một số từ khóa đồng nghĩa, trước đây dùng để hỗ trợ rule-based.
DEFAULT_SYNONYMS = {
    "boot": ["giày boot", "boots", "bốt", "giầy boot"],
    "sneaker": ["giày thể thao", "giầy thể thao", "sneakers"],
    "loafer": ["giày lười", "giầy lười", "loafers"],
    "oxford": ["giày oxford", "giầy oxford"],
    "derby": ["giày derby", "giầy derby"],
    "chelsea": ["chelsea boot", "giày chelsea", "boot chelsea", "giày chelsea boot", "giay chelsea boot"],
    "da": ["giày da", "giầy da"],
    "jacket": ["áo khoác", "áo jacket"],
    "hoodie": ["áo hoodie", "áo nỉ", "áo nỉ hoodie"],
    "blazer": ["áo blazer", "áo vest"],
    "polo": ["áo polo", "áo thun polo"],
    "jean": ["quần jean", "quần jeans", "quần bò"],
    "short": ["quần short", "quần đùi", "quần ngắn"],
    "trouser": ["quần tây", "quần âu", "quần trousers"],
}


# ========== CÁC HÀM PHÂN TÍCH Ý ĐỊNH SEO TỰ ĐỘNG - ĐÃ TẮT ==========

def analyze_category_with_ai(
    category_name: str,
    category_path: str,
    existing_categories: List[Dict[str, str]],
) -> Optional[Dict[str, Any]]:
    """
    [ĐÃ TẮT] Trước đây dùng AI để phân tích danh mục trùng ý định SEO.
    Theo yêu cầu mới: KHÔNG còn tự động phân tích/chọn canonical bằng AI hay rule-based.

    Hàm này luôn trả về None.
    """
    logger.info(
        "analyze_category_with_ai disabled: skip automatic intent analysis for '%s' (%s)",
        category_name,
        category_path,
    )
    return None


def scan_and_create_mappings(db: Session, force_rescan: bool = False) -> Dict[str, Any]:
    """
    [ĐÃ TẮT] Trước đây scan tất cả danh mục và dùng AI/rule-based để tạo/cập nhật SEO mappings.
    Yêu cầu mới: KHÔNG tự động phân tích ý định SEO hay tạo mapping nữa, mọi thứ do admin chỉnh tay.

    Hàm này chỉ log và trả về thống kê rỗng, không đọc/ghi DB nặng.
    """
    logger.info(
        "scan_and_create_mappings disabled (force_rescan=%s) - no automatic SEO intent analysis.",
        force_rescan,
    )
    return {
        "total_categories": 0,
        "new_categories": 0,
        "new_mappings": 0,
        "duplicates_found": 0,
        "auto_approved": 0,
        "skipped_existing": 0,
        "details": [],
    }


# ========== CÁC HÀM VẪN DÙNG ĐỂ ĐỌC TRẠNG THÁI SEO ========== 

def get_all_category_paths(db: Session) -> List[Dict[str, Any]]:
    """
    Lấy danh sách đơn giản tất cả path danh mục sinh từ sản phẩm.
    Dùng cho thống kê ở trang /category-seo/categories và /category-seo/summary.

    Output: [{ "path": "giay-dep-nam/giay-boot-nam", "level": 2 }, ...]
    """
    results: List[Dict[str, Any]] = []

    # Lấy từng cấp riêng để tránh trùng lặp phức tạp; đây là bản rút gọn, đủ cho thống kê.
    # Cấp 1
    q1 = (
        db.query(func.trim(Product.category).label("c1"))
        .filter(Product.is_active == True)  # noqa: E712
        .distinct()
    )
    for row in q1:
        name1 = (row.c1 or "").strip()
        if not name1:
            continue
        slug1 = _slugify(name1)
        results.append(
            {
                "level": 1,
                "name": name1,
                "slug": slug1,
                "path": slug1,
            }
        )

    # Cấp 2
    q2 = (
        db.query(func.trim(Product.category).label("c1"), func.trim(Product.subcategory).label("c2"))
        .filter(Product.is_active == True)  # noqa: E712
        .filter(Product.subcategory.isnot(None))
        .distinct()
    )
    for row in q2:
        name1 = (row.c1 or "").strip()
        name2 = (row.c2 or "").strip()
        if not name1 or not name2:
            continue
        slug1 = _slugify(name1)
        slug2 = _slugify(name2)
        path = f"{slug1}/{slug2}"
        results.append(
            {
                "level": 2,
                "name": name2,
                "slug": slug2,
                "path": path,
                "parent": name1,
            }
        )

    # Cấp 3
    q3 = (
        db.query(
            func.trim(Product.category).label("c1"),
            func.trim(Product.subcategory).label("c2"),
            func.trim(Product.sub_subcategory).label("c3"),
        )
        .filter(Product.is_active == True)  # noqa: E712
        .filter(Product.subcategory.isnot(None))
        .filter(Product.sub_subcategory.isnot(None))
        .distinct()
    )
    for row in q3:
        name1 = (row.c1 or "").strip()
        name2 = (row.c2 or "").strip()
        name3 = (row.c3 or "").strip()
        if not name1 or not name2 or not name3:
            continue
        slug1 = _slugify(name1)
        slug2 = _slugify(name2)
        slug3 = _slugify(name3)
        path = f"{slug1}/{slug2}/{slug3}"
        results.append(
            {
                "level": 3,
                "name": name3,
                "slug": slug3,
                "path": path,
                "parent": name2,
            }
        )

    return results


def _slugify(name: str) -> str:
    """Slug đơn giản: lower + thay khoảng trắng bằng dấu gạch ngang."""
    return "-".join(name.strip().lower().split())


def get_category_seo_status(db: Session, category_path: str) -> Dict[str, Any]:
    """
    TRẠNG THÁI SEO ĐƠN GIẢN (ĐÃ BỎ CHUYỂN HƯỚNG):
    - Theo yêu cầu mới: tất cả trang danh mục đều được SEO (indexable).
    - Không còn dùng mapping để 301 redirect hay noindex.
    - Hàm này luôn trả về: không redirect, được SEO.
    """
    logger.info("get_category_seo_status simplified: no redirect, always SEO indexable for %s", category_path)
    return {
        "should_redirect": False,
        "redirect_to": None,
        "seo_indexable": True,
        "canonical_url": None,
    }


def should_redirect_category(db: Session, category_path: str) -> Optional[str]:
    """
    Hàm tiện ích (giữ cho tương thích): trả về URL cần redirect nếu có, ngược lại None.
    """
    status = get_category_seo_status(db, category_path)
    return status.get("redirect_to")


def get_all_approved_redirects(db: Session) -> List[Dict[str, str]]:
    """
    Lấy danh sách redirects đã được approve.
    ĐÃ BỎ CHUYỂN HƯỚNG Ý ĐỊNH SEO → luôn trả về danh sách rỗng để không còn hiển thị “→ 301 …”.
    """
    logger.info("get_all_approved_redirects simplified: returning empty list (redirects disabled).")
    return []


def merge_non_seo_categories_to_canonical(db: Session) -> Dict[str, Any]:
    """
    [ĐÃ TẮT] Trước đây gộp sản phẩm từ danh mục không SEO (redirect/noindex) sang danh mục canonical.
    Theo yêu cầu mới: KHÔNG tự động gộp hay thay đổi category/subcategory/sub_subcategory của sản phẩm nữa.

    Hàm này chỉ log và trả về số liệu 0.
    """
    logger.info("merge_non_seo_categories_to_canonical disabled: no automatic product moving between categories.")
    return {
        "merged_mappings": 0,
        "products_updated": 0,
        "details": [],
    }

