# backend/app/services/ladipage_ai_service.py
"""
AI cho Ladipage: viết nội dung bán hàng bằng DeepSeek text (hero, điểm mạnh, chất liệu, FAQ, SEO…)
và sinh ảnh minh họa chất liệu bằng Gemini image. Ảnh hero dùng trực tiếp ảnh đại diện sản phẩm.

QUAN TRỌNG: Module này CHỈ ĐỌC dữ liệu sản phẩm/danh mục thật để làm ngữ cảnh prompt — không bao
giờ ghi ngược vào bảng `products`/`categories`. Danh sách sản phẩm hiển thị luôn resolve live.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.models.ladipage import Ladipage, LadipageSection
from app.models.product import Product
from app.services import bunny_storage
from app.services.category_size_guide_gemini import gemini_generate_image_from_text
from app.services.image_localization_service import (
    _extract_first_image_bytes_from_gemini_generate_response,
    _normalize_gemini_image_size,
    _sanitize_model_id,
)

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_PRODUCTS_LIMIT = 12


def normalize_material_filter(raw: Optional[str]) -> Optional[str]:
    """Chuẩn hoá giá trị lọc chất liệu admin chọn (trim; rỗng → None)."""
    if raw is None:
        return None
    t = str(raw).strip()
    return t[:100] if t else None


def material_filter_match_key(raw: Optional[str]) -> Optional[str]:
    norm = normalize_material_filter(raw)
    return norm.lower() if norm else None

FIXED_SECTION_ORDER: List[str] = [
    "hero",
    "highlights",
    "material",
    "products_grid",
    "trust_cta",
    "faq",
]


# ---------------------------------------------------------------------------
# Resolve dữ liệu thật (live) — không cache/snapshot lâu dài
# ---------------------------------------------------------------------------

def resolve_products_for_ladipage(
    db: Session, ladipage: Ladipage, limit: Optional[int] = None
) -> List[Product]:
    """Danh sách sản phẩm thật hiện tại theo nguồn (category | products). Luôn đọc live từ DB."""
    if ladipage.source_type == "products":
        raw_ids = ladipage.product_ids or []
        ids: List[int] = []
        for x in raw_ids:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        if not ids:
            return []
        rows = db.query(Product).filter(Product.id.in_(ids), Product.is_active.is_(True)).all()
        order = {pid: i for i, pid in enumerate(ids)}
        rows.sort(key=lambda r: order.get(r.id, 999999))
        return rows

    if ladipage.source_type == "category" and ladipage.category_id:
        eff_limit = limit or ladipage.products_limit or DEFAULT_PRODUCTS_LIMIT
        q = db.query(Product).filter(
            Product.category_id == ladipage.category_id,
            Product.is_active.is_(True),
        )
        material_key = material_filter_match_key(getattr(ladipage, "material_filter", None))
        if material_key:
            q = q.filter(
                Product.material.isnot(None),
                func.lower(func.trim(Product.material)) == material_key,
            )
        return q.order_by(Product.purchases.desc(), Product.id.desc()).limit(eff_limit).all()
    return []


def _product_brief(p: Product) -> Dict[str, Any]:
    codes = _product_code_tokens(p)
    return {
        "name": _sanitize_copy_for_ladipage(p.name or "", code_tokens=codes),
        "material": (p.material or "").strip() or None,
        "style": (p.style or "").strip() or None,
        "color": (p.color or "").strip() or None,
        "occasion": (p.occasion or "").strip() or None,
        "features": p.features if isinstance(p.features, list) else [],
        "price": p.price or 0,
    }


def _product_code_tokens(p: Product) -> List[str]:
    """Mã SP/SKU có thể lọc khỏi tên & mô tả trước khi đưa vào prompt ladipage."""
    tokens: List[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        if raw is None:
            return
        t = str(raw).strip()
        if len(t) >= 2 and t not in seen:
            seen.add(t)
            tokens.append(t)

    add(getattr(p, "product_id", None))
    add(getattr(p, "code", None))
    add(getattr(p, "base_sku", None))
    pid = str(getattr(p, "product_id", "") or "")
    m = re.search(r"a188(.+)$", pid, flags=re.I)
    if m:
        add(m.group(1))
    return tokens


def _sanitize_copy_for_ladipage(text: str, *, code_tokens: Optional[List[str]] = None) -> str:
    """Bỏ mã SP/SKU khỏi chuỗi đưa vào AI — tránh copy lại mã trong nội dung marketing."""
    if not text:
        return ""
    out = text
    for tok in sorted({t.strip() for t in (code_tokens or []) if t and len(t.strip()) >= 2}, key=len, reverse=True):
        out = re.sub(re.escape(tok), "", out, flags=re.I)
    out = re.sub(r"\ba188[A-Z0-9]+\b", "", out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s*([\-–|,;])\s*", r"\1 ", out)
    return out.strip(" -–|,;")


def _collect_code_tokens_from_products(products: List[Product]) -> List[str]:
    tokens: List[str] = []
    seen: set[str] = set()
    for p in products:
        for t in _product_code_tokens(p):
            if t not in seen:
                seen.add(t)
                tokens.append(t)
    return tokens


_CATEGORY_STOP_WORDS = frozenset(
    {
        "bo",
        "bộ",
        "suu",
        "sưu",
        "tap",
        "tập",
        "moi",
        "mới",
        "cua",
        "của",
        "va",
        "và",
        "cho",
        "cac",
        "các",
        "the",
        "san",
        "sản",
        "pham",
        "phẩm",
        "hang",
        "hàng",
        "loai",
        "loại",
        "danh",
        "muc",
        "mục",
        "nam",
        "nu",
        "nữ",
        "unisex",
    }
)


def _normalize_vn_token(value: str) -> str:
    import unicodedata

    text = unicodedata.normalize("NFD", (value or "").lower())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _category_keywords(category_name: Optional[str]) -> List[str]:
    if not category_name:
        return []
    tokens: List[str] = []
    for part in re.split(r"[\s/|,–\-+&]+", category_name.strip()):
        token = _normalize_vn_token(part)
        if len(token) >= 3 and token not in _CATEGORY_STOP_WORDS:
            tokens.append(token)
    # Giữ token ngắn nhưng đặc thù (vd loafer, penny)
    for part in re.split(r"[\s/|,–\-+&]+", category_name.strip()):
        token = _normalize_vn_token(part)
        if 2 <= len(token) < 3 and token not in _CATEGORY_STOP_WORDS and token not in tokens:
            tokens.append(token)
    return tokens


def _product_search_text(p: Product) -> str:
    return _normalize_vn_token(
        " ".join(
            filter(
                None,
                [p.name, p.material or "", p.style or "", p.subcategory or "", p.sub_subcategory or ""],
            )
        )
    )


def _product_category_relevance_score(p: Product, keywords: List[str]) -> int:
    if not keywords:
        return 0
    haystack = _product_search_text(p)
    return sum(1 for kw in keywords if kw in haystack)


def _pick_category_aligned_products(products: List[Product], category_name: Optional[str]) -> List[Product]:
    """Sản phẩm khớp tên danh mục — dùng làm ngữ cảnh AI, không lọc lưới hiển thị."""
    if not products or not category_name:
        return products
    keywords = _category_keywords(category_name)
    if not keywords:
        return products
    scored = sorted(
        products,
        key=lambda p: (-_product_category_relevance_score(p, keywords), -(p.purchases or 0), -p.id),
    )
    matched = [p for p in scored if _product_category_relevance_score(p, keywords) > 0]
    return matched if matched else scored


def _collect_product_image_urls(p: Product) -> List[str]:
    """Ảnh đại diện + gallery + chi tiết + màu — thứ tự ưu tiên cho ladipage 1 SP."""
    urls: List[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        if not isinstance(raw, str):
            return
        u = raw.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    add(p.main_image)
    if isinstance(p.images, list):
        for img in p.images:
            add(img)
    if isinstance(p.gallery, list):
        for img in p.gallery:
            add(img)
    if isinstance(p.colors, list):
        for cv in p.colors:
            if isinstance(cv, dict):
                add(cv.get("img") or cv.get("image"))
    return urls


def _is_single_product_ladipage(ladipage: Ladipage) -> bool:
    """Ladipage 1 SP — theo product_ids admin chọn, không phụ thuộc SP còn active hay không."""
    if ladipage.source_type != "products":
        return False
    raw = ladipage.product_ids or []
    if not isinstance(raw, list):
        return False
    ids: List[int] = []
    for x in raw:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return len(ids) == 1


def resolve_material_product_image(
    product: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> Dict[str, str]:
    """Ladipage 1 SP — ảnh chất liệu từ SP (không qua AI)."""
    existing = str(current.get("image_url") or "").strip()
    pos = str(current.get("image_object_position") or "").strip() or "50% 50%"
    if existing:
        return {"image_url": existing, "image_object_position": pos}
    for url in pick_usable_product_image_urls(product):
        return {"image_url": url, "image_object_position": "50% 50%"}
    for url in _collect_product_image_urls_from_dict(product):
        return {"image_url": url, "image_object_position": "50% 50%"}
    raise RuntimeError("Không có ảnh sản phẩm khả dụng cho phần chất liệu.")


def resolve_material_product_image_from_ladipage(
    db: Session,
    ladipage: Ladipage,
    current: Dict[str, Any],
) -> Dict[str, str]:
    """Lấy ảnh chất liệu trực tiếp từ bản ghi Product — không gọi Gemini."""
    existing = str(current.get("image_url") or "").strip()
    pos = str(current.get("image_object_position") or "").strip() or "50% 50%"
    if existing:
        return {"image_url": existing, "image_object_position": pos}
    products = resolve_products_for_ladipage(db, ladipage)
    if not products:
        raise RuntimeError("Không tìm thấy sản phẩm để lấy ảnh chất liệu.")
    for url in _collect_product_image_urls(products[0]):
        return {"image_url": url, "image_object_position": "50% 50%"}
    raise RuntimeError("Không có ảnh sản phẩm cho phần chất liệu.")


def _collect_product_image_urls_from_dict(product: Optional[Dict[str, Any]]) -> List[str]:
    if not product:
        return []
    urls: List[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        if not isinstance(raw, str):
            return
        u = raw.strip()
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    add(product.get("main_image"))
    gallery = product.get("gallery_urls")
    if isinstance(gallery, list):
        for img in gallery:
            add(img)
    elif isinstance(product.get("images"), list):
        for img in product.get("images"):
            add(img)
    if isinstance(product.get("gallery"), list):
        for img in product.get("gallery"):
            add(img)
    colors = product.get("colors") or product.get("color_variants")
    if isinstance(colors, list):
        for cv in colors:
            if isinstance(cv, dict):
                add(cv.get("img") or cv.get("image"))
    color_urls = product.get("color_image_urls")
    if isinstance(color_urls, list):
        for img in color_urls:
            add(img)
    return urls


def _is_usable_reference_image_url(url: str, *, timeout: int = 15) -> bool:
    """Ảnh tham chiếu phải tải được (HTTP 200, content-type image, không quá nhỏ)."""
    headers = {"User-Agent": "188-ladipage-image-check/1.0"}
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True, headers=headers)
        if resp.status_code in (405, 501):
            resp = requests.get(url, timeout=timeout, stream=True, allow_redirects=True, headers=headers)
        if resp.status_code != 200:
            return False
        content_type = (resp.headers.get("Content-Type") or "").lower()
        if content_type and (not content_type.startswith("image/") or "text/html" in content_type):
            return False
        content_length = resp.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) < 256:
                    return False
            except ValueError:
                pass
        elif resp.request.method.upper() == "GET":
            chunk = next(resp.iter_content(512), b"")
            if len(chunk) < 32:
                return False
        return True
    except Exception:
        return False


def pick_usable_product_image_urls(product: Optional[Dict[str, Any]]) -> List[str]:
    """Chỉ trả các URL ảnh SP mở được — dùng làm tham chiếu sinh ảnh chất liệu."""
    out: List[str] = []
    for url in _collect_product_image_urls_from_dict(product):
        if _is_usable_reference_image_url(url):
            out.append(url)
    return out


def _product_image_dict(p: Product) -> Optional[Dict[str, Any]]:
    gallery_urls = _collect_product_image_urls(p)
    if not gallery_urls:
        return None
    return {
        "id": p.id,
        "name": _sanitize_copy_for_ladipage(p.name or "", code_tokens=_product_code_tokens(p)),
        "material": (p.material or "").strip() or None,
        "main_image": gallery_urls[0],
        "gallery_urls": gallery_urls,
        "price": p.price or 0,
        "description": _sanitize_copy_for_ladipage(
            (p.description or "").strip(),
            code_tokens=_product_code_tokens(p),
        ),
    }


def build_context(db: Session, ladipage: Ladipage) -> Dict[str, Any]:
    """Ngữ cảnh cho prompt — tổng hợp từ dữ liệu sản phẩm/danh mục thật + brief admin."""
    products = resolve_products_for_ladipage(db, ladipage)

    category_name = None
    if ladipage.category_id:
        cat = db.query(Category).filter(Category.id == ladipage.category_id).first()
        category_name = cat.name if cat else None

    is_category_landing = ladipage.source_type == "category" and bool(category_name)
    aligned_products = _pick_category_aligned_products(products, category_name) if is_category_landing else products
    context_products = aligned_products if is_category_landing else products

    materials = [(p.material or "").strip() for p in context_products if (p.material or "").strip()]
    material_filter = normalize_material_filter(getattr(ladipage, "material_filter", None))
    if material_filter:
        dominant_material = material_filter
    else:
        dominant_material = max(set(materials), key=materials.count) if materials else None
    brief = (ladipage.admin_brief or "").strip()

    prices = [p.price for p in products if p.price]

    is_single_product = _is_single_product_ladipage(ladipage) and bool(products)
    single_product: Optional[Dict[str, Any]] = None
    category_anchor_product: Optional[Dict[str, Any]] = None

    if is_single_product:
        single_product = _product_image_dict(products[0])
    elif is_category_landing:
        for candidate in aligned_products:
            category_anchor_product = _product_image_dict(candidate)
            if category_anchor_product:
                break

    hero_image_product = single_product or category_anchor_product
    if not hero_image_product:
        for p in products:
            hero_image_product = _product_image_dict(p)
            if hero_image_product:
                break

    code_tokens = _collect_code_tokens_from_products(context_products)

    # Import cục bộ tránh vòng import với ladipage_seo_strategy.
    from app.services.ladipage_seo_strategy import (
        get_category_seo_competitor,
        get_dominant_category_for_products,
    )

    category_competitor: Dict[str, Any] = {}
    if is_category_landing and ladipage.category_id:
        category_competitor = get_category_seo_competitor(db, ladipage.category_id)
    elif ladipage.source_type == "products" and len(products) > 1:
        # Ladipage nhiều SP: nếu đa số SP cùng 1 danh mục, canh SEO/link chéo như ladipage danh mục.
        dominant_category_id = get_dominant_category_for_products(db, [p.id for p in products])
        if dominant_category_id:
            category_competitor = get_category_seo_competitor(db, dominant_category_id)

    category_head_title = category_competitor.get("head_title")
    category_seo_description = category_competitor.get("seo_description")
    category_full_slug = category_competitor.get("full_slug")
    category_seo_path = category_competitor.get("seo_path")
    category_catalog_path = category_competitor.get("catalog_path")
    if not category_name:
        category_name = category_competitor.get("category_name")

    return {
        "title": _sanitize_copy_for_ladipage((ladipage.title or "").strip(), code_tokens=code_tokens),
        "category_name": category_name,
        "admin_brief": brief,
        "product_count": len(products),
        "sample_products": [_product_brief(p) for p in context_products[:8]],
        "dominant_material": dominant_material,
        "material_filter": material_filter,
        "category_head_title": category_head_title,
        "category_seo_description": category_seo_description,
        "category_full_slug": category_full_slug,
        "category_seo_path": category_seo_path,
        "category_catalog_path": category_catalog_path,
        "category_competitor": category_competitor,
        "price_min": min(prices) if prices else None,
        "price_max": max(prices) if prices else None,
        "is_single_product": is_single_product,
        "is_category_landing": is_category_landing,
        "single_product": single_product,
        "category_anchor_product": category_anchor_product,
        "hero_image_product": hero_image_product,
    }


def build_fixed_sections_plan(include_material: bool, include_faq: bool) -> List[str]:
    plan = ["hero", "highlights"]
    if include_material:
        plan.append("material")
    plan.append("products_grid")
    plan.append("trust_cta")
    if include_faq:
        plan.append("faq")
    return plan


# ---------------------------------------------------------------------------
# Gemini text
# ---------------------------------------------------------------------------

_BRAND_VOICE = (
    "Bạn là chuyên gia copywriting bán hàng cho website thời trang 188.com.vn. "
    "Giọng văn thuyết phục, trung thực — CHỈ dùng thông tin có trong dữ liệu sản phẩm bên dưới, "
    "KHÔNG bịa thông số kỹ thuật hay cam kết không có thật. Viết hoàn toàn tiếng Việt, không dùng "
    "ký tự tiếng Trung. "
    "TUYỆT ĐỐI KHÔNG nhắc mã sản phẩm, mã kho, SKU, mã nội bộ hay bất kỳ chuỗi mã kỹ thuật nào "
    "(vd B0266, HN256, a188…) trong headline, mô tả, FAQ, callout — chỉ nói lợi ích và đặc điểm bán hàng."
)


def _call_deepseek_text(prompt: str, *, max_tokens: int = 1000, temperature: float = 0.8) -> Optional[str]:
    api_key = (getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
    if not api_key:
        logger.warning("Ladipage: thiếu DEEPSEEK_API_KEY.")
        return None
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-v4-flash"
    try:
        from app.services.deepseek_http import deepseek_chat_completions

        resp = deepseek_chat_completions(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
                # deepseek-v4-flash mặc định bật thinking — reasoning ăn hết max_tokens, content rỗng.
                "thinking": {"type": "disabled"},
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Bạn trả lời đúng một object JSON theo yêu cầu trong prompt. "
                            "Không bọc markdown, không thêm giải thích."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=60,
        )
        if not resp.ok:
            logger.warning(
                "Ladipage DeepSeek: HTTP %s %s (model=%s)",
                resp.status_code,
                (resp.text or "")[:400],
                model,
            )
            return None
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            logger.warning("Ladipage DeepSeek: không có choices.")
            return None
        text = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not text:
            finish = (choices[0].get("finish_reason") or "").lower()
            logger.warning("Ladipage DeepSeek: content rỗng (finish_reason=%s).", finish)
            return None
        return text
    except Exception as exc:
        logger.warning("Ladipage DeepSeek lỗi: %s", exc)
        return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", text).strip()


def _context_block(context: Dict[str, Any]) -> str:
    lines = [f"Tiêu đề landing page: {context.get('title')}"]
    if context.get("category_name"):
        lines.append(f"Danh mục: {context['category_name']}")
    if context.get("is_category_landing"):
        lines.append(
            "QUAN TRỌNG — LANDING PAGE THEO DANH MỤC: Toàn bộ nội dung (hero, điểm mạnh, chất liệu, FAQ, "
            f"ảnh minh họa) PHẢI xoay quanh đúng chủ đề danh mục «{context['category_name']}». "
            "Danh mục có thể có thêm vài sản phẩm phụ lệch chủ đề ở lưới cuối trang — KHÔNG được viết "
            "marketing về các sản phẩm lệch chủ đề đó (vd danh mục giày thì không viết/vẽ túi xách)."
        )
        lines.append(
            "PHÂN VAI SEO/AI: Trang danh mục/cluster là trang SEO chính (head keyword). "
            "Ladipage này là landing bộ sưu tập / long-tail — KHÔNG copy nguyên tiêu đề hay mô tả trang danh mục. "
            "Phải có góc riêng (chất liệu đã lọc, bộ sưu tập, dịp dùng)."
        )
    elif context.get("category_head_title"):
        lines.append(
            f"Đa số sản phẩm trong ladipage này thuộc danh mục «{context.get('category_name') or context['category_head_title']}» "
            "(trang danh mục/cluster đó là trang SEO chính — head keyword). Ladipage này là landing bộ sưu tập chọn lọc — "
            "KHÔNG copy nguyên tiêu đề hay mô tả trang danh mục đó, phải có góc riêng (bộ sưu tập, USP nổi bật của nhóm SP này)."
        )
    if context.get("material_filter"):
        lines.append(
            f"Lọc chất liệu bắt buộc trên lưới SP: «{context['material_filter']}» — "
            "mọi copy (hero/highlights/chất liệu/FAQ/SEO) phải nêu rõ góc chất liệu này."
        )
    if context.get("category_head_title"):
        lines.append(
            f"Tiêu đề trang SEO chính (TRÁNH trùng): {context['category_head_title']}"
        )
    if context.get("category_seo_description"):
        lines.append(
            f"Mô tả SEO danh mục (TRÁNH viết lại gần giống): {context['category_seo_description'][:220]}"
        )
    if context.get("sample_products"):
        label = "Sản phẩm tiêu biểu đúng chủ đề danh mục" if context.get("is_category_landing") else "Sản phẩm tiêu biểu"
        names = ", ".join(p["name"] for p in context["sample_products"][:6] if p.get("name"))
        if names:
            lines.append(f"{label}: {names}")
    if context.get("dominant_material"):
        lines.append(f"Chất liệu chính (theo sản phẩm đúng chủ đề): {context['dominant_material']}")
    if context.get("price_min") and context.get("price_max"):
        lines.append(
            f"Khoảng giá: {context['price_min']:,.0f}đ - {context['price_max']:,.0f}đ".replace(",", ".")
        )
    if context.get("admin_brief"):
        lines.append(f"Ý tưởng/định hướng nội dung từ admin (ưu tiên bám sát): {context['admin_brief']}")

    if context.get("is_single_product"):
        sp = context.get("single_product") or {}
        lines.append(
            "QUAN TRỌNG: Đây là trang landing page bán hàng dành RIÊNG cho 1 sản phẩm duy nhất — coi như đang "
            "viết lại toàn bộ nội dung bán hàng cho sản phẩm này từ đầu (một phiên bản giới thiệu sản phẩm thứ 2, "
            "thuyết phục hơn). Tập trung 100% vào đúng sản phẩm này, không lan man sang sản phẩm khác."
        )
        real_desc = _strip_html(sp.get("description") or "")
        if real_desc:
            lines.append(
                "Mô tả gốc thật của sản phẩm (đã hiển thị sẵn ở phần khác của trang — KHÔNG được mâu thuẫn với "
                f"thông tin này): {real_desc[:600]}"
            )
    return "\n".join(lines)


def generate_hero_text(context: Dict[str, Any], *, custom_instruction: Optional[str] = None) -> Optional[Dict[str, str]]:
    extra = f"\nYêu cầu thêm từ admin: {custom_instruction}" if custom_instruction else ""
    prompt = f"""{_BRAND_VOICE}

{_context_block(context)}{extra}

Nhiệm vụ: Viết phần HERO mở đầu cho landing page bán hàng.
Trả về đúng JSON: {{"headline": "tiêu đề ngắn gọn gây chú ý (tối đa 12 từ)", "subheadline": "câu mô tả phụ 1-2 câu nêu giá trị nổi bật"}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=300) or "")
    if not data:
        return None
    return {
        "headline": str(data.get("headline") or context.get("title") or "").strip(),
        "subheadline": str(data.get("subheadline") or "").strip(),
    }


def generate_highlights_text(context: Dict[str, Any], *, custom_instruction: Optional[str] = None) -> Optional[Dict[str, Any]]:
    extra = f"\nYêu cầu thêm từ admin: {custom_instruction}" if custom_instruction else ""
    prompt = f"""{_BRAND_VOICE}

{_context_block(context)}{extra}

Nhiệm vụ: Viết 4-6 điểm mạnh / điểm đáng mua nổi bật nhất cho sản phẩm/danh mục này.
Trả về đúng JSON: {{"items": [{{"title": "tên điểm mạnh ngắn (3-6 từ)", "desc": "mô tả 1 câu"}}]}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=800) or "")
    if not data or not isinstance(data.get("items"), list):
        return None
    items = [
        {"title": str(it.get("title") or "").strip(), "desc": str(it.get("desc") or "").strip()}
        for it in data["items"]
        if isinstance(it, dict) and (it.get("title") or it.get("desc"))
    ][:6]
    return {"items": items} if items else None


def generate_material_text(
    context: Dict[str, Any],
    material: str,
    *,
    custom_instruction: Optional[str] = None,
    strict_material_callouts: bool = False,
) -> Optional[Dict[str, Any]]:
    extra = f"\nYêu cầu thêm từ admin: {custom_instruction}" if custom_instruction else ""
    strict_block = ""
    if strict_material_callouts:
        strict_block = f"""

QUAN TRỌNG — callouts (3 nhãn in trên ảnh):
- Mỗi callout PHẢI nói đặc tính riêng CHỈ chất liệu «{material}» mới có — khách đọc phải hiểu ngay đang nói về {material},
  không thể dùng chung cho chất liệu khác.
- Mỗi callout PHẢI toát lên sự CAO CẤP/KHAN HIẾM gắn với chính đặc tính đó (không phải cao cấp chung chung) —
  khiến khách cảm nhận "đúng chất liệu xịn, đáng tiền, chốt đơn ngay", không phải câu marketing sáo rỗng.
- CẤM câu chung chung dùng được cho mọi loại vải/da: «Sang trọng đẳng cấp», «Mềm mại tự nhiên», «Thoáng khí mát lạnh»,
  «Chất lượng cao», «Đáng đồng tiền», «Cao cấp», «Tiện dụng».
- Ví dụ lụa: «Óng ánh chuẩn lụa thật», «Mát lạnh hiếm có tự nhiên», «Càng dùng càng lên màu đẹp».
- Ví dụ da bò: «Vân da độc bản tự nhiên», «Càng dùng càng lên màu», «Bền đẹp theo thời gian dùng».
- Ví dụ cotton 100%: «Thấm hút vượt trội tự nhiên», «Mềm mại chuẩn cotton nguyên chất», «Thoáng khí suốt ngày dài».
- body cũng phải giải thích vì sao {material} đáng mua NGAY — nêu đặc tính độc quyền của {material}, không viết
  chung chung cho mọi loại vải."""
    prompt = f"""{_BRAND_VOICE}

{_context_block(context)}
Chất liệu cần giải thích: {material}{extra}{strict_block}

Nhiệm vụ: Viết đoạn giải thích ngắn (60-90 từ) về chất liệu "{material}" — vì sao đây là điểm đáng mua và đáng
chốt đơn ngay (độ bền, cảm giác mặc/dùng, đặc tính riêng — cao cấp — của {material}, cách bảo quản nếu phù hợp).
Đồng thời liệt kê 3 chú thích ngắn (mỗi cái 3-6 từ, kiểu nhãn callout) sẽ in trực tiếp trên ảnh minh họa — mỗi
nhãn phải gắn với ưu điểm thật + cảm giác cao cấp riêng của {material}.
Trả về đúng JSON: {{"body": "đoạn giải thích", "callouts": ["...", "...", "..."]}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=500) or "")
    if not data:
        return None
    callouts = [str(x).strip() for x in (data.get("callouts") or []) if str(x).strip()][:3]
    return {"body": str(data.get("body") or "").strip(), "callouts": callouts}


def generate_trust_cta_text(context: Dict[str, Any], *, custom_instruction: Optional[str] = None) -> Optional[Dict[str, str]]:
    extra = f"\nYêu cầu thêm từ admin: {custom_instruction}" if custom_instruction else ""
    prompt = f"""{_BRAND_VOICE}

{_context_block(context)}{extra}

Nhiệm vụ: Viết đoạn kêu gọi hành động cuối trang (60-100 từ) nhấn mạnh sự an tâm khi mua tại
188.com.vn (giao hàng, đổi trả, chất lượng) và thúc đẩy hành động mua ngay.
Trả về đúng JSON: {{"body": "đoạn văn", "cta_label": "nhãn nút bấm ngắn (vd: Mua ngay)"}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=400) or "")
    if not data:
        return None
    return {
        "body": str(data.get("body") or "").strip(),
        "cta_label": str(data.get("cta_label") or "Mua ngay").strip(),
    }


def generate_faq_text(context: Dict[str, Any], *, custom_instruction: Optional[str] = None) -> Optional[Dict[str, Any]]:
    extra = f"\nYêu cầu thêm từ admin: {custom_instruction}" if custom_instruction else ""
    prompt = f"""{_BRAND_VOICE}

{_context_block(context)}{extra}

Nhiệm vụ: Viết 3-5 câu hỏi thường gặp (FAQ) và câu trả lời ngắn gọn hữu ích cho khách khi cân nhắc mua.
Trả về đúng JSON: {{"items": [{{"q": "câu hỏi", "a": "câu trả lời"}}]}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=700) or "")
    if not data or not isinstance(data.get("items"), list):
        return None
    items = [
        {"q": str(it.get("q") or "").strip(), "a": str(it.get("a") or "").strip()}
        for it in data["items"]
        if isinstance(it, dict) and (it.get("q") or it.get("a"))
    ][:5]
    return {"items": items} if items else None


def generate_ladipage_seo(
    context: Dict[str, Any],
    *,
    hero_headline: Optional[str] = None,
    hero_subheadline: Optional[str] = None,
) -> Optional[Dict[str, str]]:
    hero_bits: List[str] = []
    if hero_headline:
        hero_bits.append(f"Tiêu đề hero trên trang: {hero_headline}")
    if hero_subheadline:
        hero_bits.append(f"Mô tả phụ hero: {hero_subheadline}")
    hero_block = ("\n" + "\n".join(hero_bits)) if hero_bits else ""

    material_rule = ""
    if context.get("material_filter"):
        material_rule = (
            f"\n- BẮT BUỘC có cụm chất liệu «{context['material_filter']}» trong meta_title "
            "(góc long-tail / bộ sưu tập theo chất liệu)"
        )
    category_rule = ""
    if context.get("category_head_title"):
        category_rule = (
            "\n- KHÔNG viết meta giống trang danh mục/cluster (head keyword). "
            "Ladipage = bộ sưu tập / USP; danh mục mới là trang SEO chính."
        )

    prompt = f"""Bạn là chuyên gia SEO thương mại điện tử cho 188.com.vn. Viết meta title và meta description tiếng Việt.

{_context_block(context)}{hero_block}

Nhiệm vụ: Viết SEO cho landing page `/lp/...` — thu hút click, bám USP trang (không thay trang danh mục), không bịa thông tin.
- KHÔNG nhắc mã sản phẩm, mã kho, SKU hay mã nội bộ trong meta title/description
- meta_title: tối đa 60 ký tự, có từ khóa + USP (chất liệu/góc bộ sưu tập), có thể kết thúc bằng "| 188.com.vn" nếu còn chỗ
- meta_description: 120–160 ký tự, nêu lợi ích góc riêng + kêu gọi mua, tự nhiên
{material_rule}{category_rule}

Trả về đúng JSON: {{"meta_title": "...", "meta_description": "..."}}
Chỉ trả JSON, không thêm chữ nào khác."""
    data = _extract_json(_call_deepseek_text(prompt, max_tokens=400, temperature=0.7) or "")
    if not data:
        return None
    title = str(data.get("meta_title") or context.get("title") or "").strip()
    desc = str(data.get("meta_description") or "").strip()
    if not title:
        return None
    if len(title) > 500:
        title = title[:500].rsplit(" ", 1)[0].strip()
    if len(desc) > 1000:
        desc = desc[:160].rsplit(" ", 1)[0].strip()
    elif len(desc) > 160:
        desc = desc[:160].rsplit(" ", 1)[0].strip()
    if not desc:
        desc = f"{context.get('title') or title}. Mua sắm tại 188.com.vn — Xem là thích, click là mê."[:160]
    return {"meta_title": title, "meta_description": desc}


def generate_and_save_ladipage_seo(
    db: Session,
    ladipage: Ladipage,
    *,
    hero_headline: Optional[str] = None,
    hero_subheadline: Optional[str] = None,
    only_missing: bool = False,
) -> Dict[str, str]:
    from app.services.ladipage_seo_strategy import apply_ladipage_seo_guardrails

    has_title = bool((ladipage.meta_title or "").strip())
    has_desc = bool((ladipage.meta_description or "").strip())
    if only_missing and has_title and has_desc:
        return {
            "meta_title": ladipage.meta_title or "",
            "meta_description": ladipage.meta_description or "",
            "seo_collision_warning": None,
        }

    context = build_context(db, ladipage)
    seo = generate_ladipage_seo(
        context,
        hero_headline=hero_headline,
        hero_subheadline=hero_subheadline,
    )
    if not seo:
        raise RuntimeError("DeepSeek không trả nội dung SEO hợp lệ.")

    warning = None
    competitor = context.get("category_competitor") or {}
    if competitor.get("category_id"):
        seo, warning = apply_ladipage_seo_guardrails(
            seo,
            competitor=competitor,
            material_filter=context.get("material_filter"),
            category_name=context.get("category_name"),
        )

    if only_missing:
        if not has_title:
            ladipage.meta_title = seo["meta_title"]
        if not has_desc:
            ladipage.meta_description = seo["meta_description"]
    else:
        ladipage.meta_title = seo["meta_title"]
        ladipage.meta_description = seo["meta_description"]
    db.commit()
    db.refresh(ladipage)
    return {
        "meta_title": ladipage.meta_title or "",
        "meta_description": ladipage.meta_description or "",
        "seo_collision_warning": warning,
    }


# ---------------------------------------------------------------------------
# Gemini image + upload Bunny
# ---------------------------------------------------------------------------

def _upload_ladipage_image(ladipage_id: int, image_bytes: bytes, *, name_hint: str) -> str:
    zone = settings.BUNNY_STORAGE_ZONE_NAME
    key = settings.BUNNY_STORAGE_ACCESS_KEY
    if not zone or not key:
        raise RuntimeError("Thiếu BUNNY_STORAGE_ZONE_NAME hoặc BUNNY_STORAGE_ACCESS_KEY.")
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", name_hint).strip("-") or "section"
    digest = hashlib.sha1(image_bytes).hexdigest()[:10]
    remote_name = f"{safe}-{int(time.time())}-{digest}.png"
    prefix = (settings.BUNNY_UPLOAD_PATH_PREFIX or "site").strip("/")
    remote_path = f"{prefix}/ladipage/{ladipage_id}/{remote_name}"
    bunny_storage.upload_file_to_zone(
        zone_name=zone, access_key=key, remote_path=remote_path, data=image_bytes, content_type="image/png"
    )
    return bunny_storage.build_public_object_url(settings.BUNNY_CDN_PUBLIC_BASE, remote_path)


def _guess_mime_from_url(url: str, fallback_content_type: Optional[str] = None) -> str:
    u = (url or "").lower()
    if u.endswith(".png"):
        return "image/png"
    if u.endswith(".webp"):
        return "image/webp"
    if fallback_content_type:
        return fallback_content_type.split(";")[0].strip() or "image/jpeg"
    return "image/jpeg"


def _gemini_edit_image_from_url(
    image_url: str,
    prompt: str,
    *,
    image_model: Optional[str] = None,
    image_size: Optional[str] = None,
    timeout_sec: Optional[int] = None,
) -> bytes:
    """Chỉnh sửa ảnh thật (image-to-image, Gemini) — dùng để tạo ảnh chuyên nghiệp từ ảnh sản phẩm thật.

    Theo đúng payload dạng edit đã dùng ở `image_localization_service.py` (text + inline_data ảnh gốc),
    tái sử dụng các hàm phụ trợ sinh ảnh sẵn có (`_sanitize_model_id`, `_normalize_gemini_image_size`,
    `_extract_first_image_bytes_from_gemini_generate_response`) — đúng cách `category_size_guide_gemini.py`
    đã làm.
    """
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        raise RuntimeError("Thiếu GEMINI_API_KEY.")
    img_resp = requests.get(image_url, timeout=30)
    img_resp.raise_for_status()
    image_bytes = img_resp.content
    mime = _guess_mime_from_url(image_url, img_resp.headers.get("Content-Type"))
    b64 = base64.b64encode(image_bytes).decode("ascii")

    dm = (
        (image_model or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "") or "gemini-3-pro-image-preview")
        .strip()
        or "gemini-3-pro-image-preview"
    )
    model = _sanitize_model_id(dm, "gemini-3-pro-image-preview")
    eff_size = (
        _normalize_gemini_image_size(
            image_size or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", "2K")
        )
        or "2K"
    )
    tout = (
        timeout_sec
        if timeout_sec is not None
        else max(60, int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_TIMEOUT_SEC", 300) or 300))
    )

    payload: Dict[str, Any] = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt.strip()},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"], "imageConfig": {"imageSize": eff_size}},
    }
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
    res = requests.post(url, params={"key": api_key}, json=payload, timeout=tout)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {res.status_code}: {(res.text or '')[:400]}")
    body = res.json()
    fb = body.get("promptFeedback") or {}
    br = fb.get("blockReason") or fb.get("block_reason")
    if br:
        raise RuntimeError(f"Gemini từ chối prompt: {br}")
    out = _extract_first_image_bytes_from_gemini_generate_response(body)
    if not out:
        raise RuntimeError("Gemini không trả ảnh chỉnh sửa (kiểm tra model sinh ảnh).")
    return out


def generate_material_image(
    ladipage_id: int,
    material: str,
    callouts: List[str],
    *,
    custom_prompt: Optional[str] = None,
    single_product: Optional[Dict[str, Any]] = None,
    category_name: Optional[str] = None,
) -> Dict[str, str]:
    callout_str = "; ".join(callouts) if callouts else "chất lượng bền đẹp; đáng đồng tiền; dễ bảo quản"
    category_hint = f" thuộc danh mục «{category_name}»" if category_name else ""
    candidate_urls = pick_usable_product_image_urls(single_product) if single_product else []

    if candidate_urls and not custom_prompt:
        prompt = (
            f"Chỉnh sửa ảnh sản phẩm thật đính kèm{category_hint} thành ảnh cận cảnh chất liệu «{material}» "
            "chuyên nghiệp, đẳng cấp cho thương mại điện tử: zoom cận cảnh vào bề mặt/kết cấu chất liệu thật "
            "của đúng loại sản phẩm trong ảnh (phải khớp danh mục/chủ đề), ánh sáng studio đẹp, nền trung tính "
            "sang trọng. GIỮ NGUYÊN CHÍNH XÁC loại sản phẩm, màu sắc/hoạ tiết/kết cấu thật — không đổi thành "
            "sản phẩm khác loại (vd không biến giày/túi thành loại khác). "
            f"Trên ảnh in trực tiếp các chú thích ngắn tiếng Việt dạng nhãn callout đẹp mắt, không che sản phẩm: {callout_str}. "
            "Không watermark, không chữ tiếng Trung, không logo hãng khác. Bố cục vuông, rõ nét, chuyên nghiệp."
        )
        last_exc: Optional[Exception] = None
        for source_photo in candidate_urls:
            try:
                raw = _gemini_edit_image_from_url(source_photo, prompt)
                url = _upload_ladipage_image(ladipage_id, raw, name_hint=f"material-{material}")
                return {"image_url": url, "prompt_used": prompt}
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Ladipage material image: ảnh %s không dùng được (%s), thử ảnh gallery tiếp theo.",
                    source_photo,
                    exc,
                )
        if last_exc is not None:
            logger.warning(
                "Ladipage material image: hết ảnh gallery khả dụng (%s), fallback sang tạo ảnh từ text.",
                last_exc,
            )

    prompt = custom_prompt or (
        f"Ảnh sản phẩm thương mại điện tử cận cảnh chất liệu «{material}»"
        f"{category_hint}, ánh sáng studio đẹp, nền trung tính sang trọng, tông màu ấm phù hợp thời trang. "
        "Chỉ hiển thị đúng loại sản phẩm khớp danh mục/chủ đề — không túi xách nếu chủ đề là giày và ngược lại. "
        f"Trên ảnh in trực tiếp các chú thích ngắn tiếng Việt dạng nhãn callout đẹp mắt, không che sản phẩm: {callout_str}. "
        "Không watermark, không chữ tiếng Trung, không logo hãng khác. Bố cục vuông, rõ nét, chuyên nghiệp."
    )
    raw = gemini_generate_image_from_text(prompt)
    url = _upload_ladipage_image(ladipage_id, raw, name_hint=f"material-{material}")
    return {"image_url": url, "prompt_used": prompt}


def _hero_image_reference(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return (
        context.get("hero_image_product")
        or context.get("single_product")
        or context.get("category_anchor_product")
    )


def resolve_hero_image_url(image_reference: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """Lấy ảnh đại diện sản phẩm làm hero — không qua AI."""
    url = str((image_reference or {}).get("main_image") or "").strip()
    if not url:
        raise RuntimeError("Không có ảnh đại diện sản phẩm để làm hero.")
    return {"image_url": url}


# ---------------------------------------------------------------------------
# Dispatcher — dùng chung cho tạo lần đầu và tạo lại (regenerate)
# ---------------------------------------------------------------------------

def generate_or_regenerate_section(
    db: Session,
    ladipage: Ladipage,
    section: LadipageSection,
    *,
    target: str = "all",
    custom_prompt: Optional[str] = None,
) -> Dict[str, Any]:
    """Sinh (lần đầu) hoặc tạo lại nội dung 1 section. `target`: all | text | image. Trả `data` mới (caller lưu DB)."""
    context = build_context(db, ladipage)
    st = section.section_type
    current: Dict[str, Any] = dict(section.data or {})
    custom_instruction = custom_prompt if target != "image" else None
    image_reference = _hero_image_reference(context) if st == "hero" else (
        context.get("single_product") or context.get("category_anchor_product")
    )
    category_name = context.get("category_name")

    if st == "hero":
        if target in ("all", "text"):
            text = generate_hero_text(context, custom_instruction=custom_instruction)
            if text:
                current.update(text)
            else:
                # Fallback: vẫn có headline từ tên SP để trang không trống khi DeepSeek lỗi tạm
                sp = image_reference or {}
                pname = str(sp.get("name") or context.get("title") or "Sản phẩm").strip()
                current.setdefault("headline", pname[:120] or "Sản phẩm nổi bật")
                current.setdefault(
                    "subheadline",
                    "Chất liệu đẹp, form thời thượng — chọn size/màu và đặt hàng ngay.",
                )
                if target == "text":
                    raise RuntimeError("DeepSeek không trả nội dung hero hợp lệ.")
        if target in ("all", "image"):
            if not image_reference:
                if target == "image":
                    raise RuntimeError("Không có ảnh đại diện sản phẩm để làm hero.")
            else:
                # Luôn gắn ảnh hero từ main_image SP (không phụ thuộc DeepSeek)
                try:
                    current.update(resolve_hero_image_url(image_reference))
                except RuntimeError:
                    # Thử gallery_urls nếu main_image trống
                    gallery = image_reference.get("gallery_urls") or []
                    if isinstance(gallery, list) and gallery:
                        current["image_url"] = str(gallery[0]).strip()
                    elif target == "image":
                        raise
        return current

    if st == "highlights":
        text = generate_highlights_text(context, custom_instruction=custom_prompt)
        if not text:
            raise RuntimeError("DeepSeek không trả điểm mạnh hợp lệ.")
        return text

    if st == "material":
        material = (
            normalize_material_filter(getattr(ladipage, "material_filter", None))
            or normalize_material_filter(str(current.get("material") or ""))
            or context.get("dominant_material")
            or "chất liệu cao cấp"
        )
        single_product_lp = _is_single_product_ladipage(ladipage)
        if single_product_lp:
            image_source = str(current.get("image_source") or "product").strip().lower()
            if image_source not in ("ai", "product"):
                image_source = "product"
        else:
            image_source = "ai"
        if target in ("all", "text"):
            text = generate_material_text(context, material, custom_instruction=custom_instruction)
            if not text:
                raise RuntimeError("DeepSeek không trả nội dung chất liệu hợp lệ.")
            current.update(text)
            current["material"] = material
        if target in ("all", "image"):
            if image_source == "product":
                current.update(resolve_material_product_image_from_ladipage(db, ladipage, current))
                current["image_source"] = "product"
            else:
                image = generate_material_image(
                    ladipage.id,
                    material,
                    current.get("callouts") or [],
                    custom_prompt=custom_prompt if target == "image" else None,
                    single_product=image_reference,
                    category_name=category_name if context.get("is_category_landing") else None,
                )
                current.update(image)
                current["image_source"] = "ai"
        return current

    if st == "trust_cta":
        text = generate_trust_cta_text(context, custom_instruction=custom_prompt)
        if not text:
            raise RuntimeError("DeepSeek không trả nội dung CTA hợp lệ.")
        return text

    if st == "faq":
        text = generate_faq_text(context, custom_instruction=custom_prompt)
        if not text:
            raise RuntimeError("DeepSeek không trả FAQ hợp lệ.")
        return text

    if st == "products_grid":
        # Không phải AI — chỉ đánh dấu ready, dữ liệu sản phẩm luôn resolve live khi render.
        return {}

    raise ValueError(f"Loại section không hỗ trợ: {st}")
