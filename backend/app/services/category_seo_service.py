# backend/app/services/category_seo_service.py - AI viết mô tả SEO cho danh mục
"""Dùng Gemini (GEMINI_MODEL, mặc định gemini-2.5-flash) để viết mô tả SEO chuẩn cho danh mục sản phẩm."""

import logging
from typing import Optional, List
import hashlib

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache đơn giản trong memory để tránh gọi AI nhiều lần cho cùng danh mục
_description_cache: dict = {}

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def _cache_key(category_name: str) -> str:
    """Tạo cache key từ tên danh mục (không dùng product_count vì thay đổi hàng ngày)."""
    return hashlib.md5(category_name.encode()).hexdigest()


def _call_gemini(prompt: str, max_tokens: int = 200, temperature: float = 0.7) -> Optional[str]:
    """Gọi Gemini API (generateContent), trả về text hoặc None."""
    api_key = getattr(settings, "GEMINI_API_KEY", None) or ""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
    if not api_key or len(api_key) < 10:
        return None
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        },
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return (parts[0].get("text") or "").strip()
    except Exception as e:
        logger.warning("Gemini category SEO request failed: %s", e)
        return None


def generate_category_seo_description(
    category_name: str,
    breadcrumb_names: List[str],
    product_count: int,
    sample_product_names: Optional[List[str]] = None
) -> Optional[str]:
    """
    Gọi Gemini (GEMINI_MODEL, qua _call_gemini) để viết mô tả SEO cho danh mục.
    
    Args:
        category_name: Tên đầy đủ danh mục (vd: "Áo khoác nam")
        breadcrumb_names: Danh sách tên các cấp (vd: ["Thời trang nam", "Áo", "Áo khoác"])
        product_count: Số lượng sản phẩm trong danh mục
        sample_product_names: Tên vài sản phẩm mẫu để AI hiểu context
    
    Returns:
        Mô tả SEO 150-160 ký tự hoặc None nếu lỗi
    """
    if not category_name:
        return None
    
    # Check cache (không dùng product_count để cache ổn định)
    cache_key = _cache_key(category_name)
    if cache_key in _description_cache:
        logger.debug(f"Cache hit for category SEO: {category_name}")
        return _description_cache[cache_key]
    
    # Tạo context từ sản phẩm mẫu
    sample_context = ""
    if sample_product_names and len(sample_product_names) > 0:
        sample_context = f"\nVí dụ sản phẩm trong danh mục: {', '.join(sample_product_names[:5])}"
    
    breadcrumb_str = " > ".join(breadcrumb_names) if breadcrumb_names else category_name
    
    prompt = f"""Bạn là chuyên gia SEO cho website thời trang nam 188.com.vn.
Nhiệm vụ: Viết meta description chuẩn SEO cho trang danh mục sản phẩm.

Thông tin danh mục:
- Tên: {category_name}
- Đường dẫn: {breadcrumb_str}{sample_context}

Yêu cầu:
1. Độ dài: 140-155 ký tự (tối ưu cho Google)
2. Bắt đầu bằng từ khóa chính (tên danh mục)
3. Bao gồm: lợi ích mua hàng (đa dạng mẫu mã, chất lượng). KHÔNG ghi số lượng sản phẩm cụ thể (số thay đổi hàng ngày).
4. Kêu gọi hành động (CTA) nhẹ nhàng
5. Tự nhiên, không spam từ khóa
6. Phù hợp thương hiệu 188.com.vn - "Xem là thích"

Chỉ trả về mô tả, không giải thích, không markdown, không dấu ngoặc kép."""

    content = _call_gemini(prompt, max_tokens=200, temperature=0.7)
    if not content:
        return _generate_fallback_description(category_name)
    
    # Chuẩn hóa: loại bỏ dấu ngoặc kép nếu có
    content = content.strip('"\'')
    
    # Giới hạn 160 ký tự
    if len(content) > 160:
        content = content[:157] + "..."
    
    # Lưu cache
    _description_cache[cache_key] = content
    logger.info(f"Generated SEO description for '{category_name}': {content[:50]}...")
    
    return content


def _generate_fallback_description(category_name: str, _product_count: int = 0) -> str:
    """Mô tả mặc định khi AI không khả dụng. Không ghi số sản phẩm (thay đổi hàng ngày)."""
    templates = [
        f"{category_name} chính hãng, đa dạng mẫu mã. Giá tốt, giao hàng nhanh toàn quốc. Mua ngay tại 188.com.vn!",
        f"Khám phá {category_name.lower()} đa dạng tại 188.com.vn. Chất lượng đảm bảo, giá hợp lý. Xem là thích!",
        f"{category_name} - nhiều sản phẩm đang chờ bạn. Xem ngay bộ sưu tập mới nhất tại 188.com.vn!",
    ]
    # Chọn template dựa trên hash để nhất quán
    idx = hash(category_name) % len(templates)
    desc = templates[idx]
    return desc[:160]


def clear_description_cache():
    """Xóa cache mô tả (dùng khi cần refresh)."""
    global _description_cache
    _description_cache = {}
    logger.info("Cleared category SEO description cache")


# Cache cho seo_body (key = category_path hoặc full_name) để tránh gọi AI lặp
_body_cache: dict = {}


def generate_category_seo_body(
    category_name: str,
    breadcrumb_names: List[str],
    product_count: int,
    sample_product_names: Optional[List[str]] = None,
    related_category_names: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Gọi Gemini để viết đoạn văn SEO 150-300 từ cho cuối trang danh mục.
    Nội dung: tại sao nên mua tại 188, các kiểu dáng/loại phổ biến, cách bảo quản...
    related_category_names: tên các danh mục anh em (cùng cấp) — AI sẽ nhắc 2-3 tên trong đoạn để gắn internal link.
    product_count: vẫn nhận để tương thích API nhưng KHÔNG đưa vào prompt (số thay đổi hàng ngày).
    """
    if not category_name:
        return None

    # Cache không dùng product_count để nội dung ổn định
    cache_key = hashlib.md5(
        f"body:{category_name}:{','.join(related_category_names or [])}".encode()
    ).hexdigest()
    if cache_key in _body_cache:
        return _body_cache[cache_key]

    sample_context = ""
    if sample_product_names and len(sample_product_names) > 0:
        sample_context = f"\nVí dụ sản phẩm: {', '.join(sample_product_names[:5])}."

    related_instruction = ""
    if related_category_names and len(related_category_names) > 0:
        names_str = ", ".join(related_category_names[:8])
        related_instruction = f"""
4. QUAN TRỌNG - Internal link: Hãy nhắc một cách TỰ NHIÊN ít nhất 2-3 trong các danh mục sau (đúng tên để hệ thống gắn link): {names_str}.
   Ví dụ: "Bên cạnh ..., bạn có thể xem thêm [tên 1], [tên 2] để đa dạng tủ đồ." Dùng đúng chính tả tên danh mục như trong list."""

    breadcrumb_str = " > ".join(breadcrumb_names) if breadcrumb_names else category_name

    prompt = f"""Bạn là chuyên gia nội dung SEO cho website thời trang nam 188.com.vn.
Nhiệm vụ: Viết MỘT đoạn văn (paragraph) từ 150 đến 300 từ, dùng cho cuối trang danh mục sản phẩm.

Thông tin danh mục:
- Tên: {category_name}
- Đường dẫn: {breadcrumb_str}.{sample_context}

Yêu cầu nội dung (tự nhiên, không liệt kê số):
- KHÔNG đề cập số lượng sản phẩm cụ thể (số thay đổi hàng ngày). Có thể dùng "đa dạng", "nhiều mẫu mã" nếu cần.
1. Tại sao nên mua {category_name.lower()} tại 188.com.vn (chất lượng, giá, giao hàng).
2. Các kiểu dáng/loại phổ biến phù hợp với danh mục này (ví dụ giày: Oxford, Derby, Loafer; áo: slim, regular...).
3. Gợi ý bảo quản hoặc phối đồ ngắn gọn (1-2 câu).{related_instruction}

Giọng văn: thân thiện, chuyên nghiệp, có CTA nhẹ (xem thêm, mua ngay tại 188). Không spam từ khóa.
Chỉ trả về đoạn văn liền mạch, không tiêu đề con, không markdown, không dấu ngoặc kép."""

    content = _call_gemini(prompt, max_tokens=650, temperature=0.7)
    if not content:
        return None

    content = content.strip('"\' \n')
    # Giới hạn ~2000 ký tự (khoảng 300 từ)
    if len(content) > 2200:
        content = content[:2197] + "..."

    _body_cache[cache_key] = content
    logger.info("Generated SEO body for '%s': %d chars", category_name, len(content))
    return content
