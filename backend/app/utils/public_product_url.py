"""URL trang sản phẩm công khai (canonical) — đồng bộ JSON API với shop."""

from __future__ import annotations

from urllib.parse import quote, unquote, urlparse

from app.core.config import settings


def public_shop_origin() -> str:
    """Origin HTTPS shop (vd. https://188.com.vn), không slash cuối."""
    base = (getattr(settings, "WEBSITE_URL", None) or "").strip().rstrip("/")
    if not base:
        return "https://188.com.vn"
    if not base.lower().startswith(("http://", "https://")):
        base = "https://" + base.lstrip("/")
    return base


def product_public_page_url(slug: str | None) -> str | None:
    """
    URL đầy đủ trang PDP: https://domain/products/<slug>
    Nếu slug đã là URL thì trả nguyên (đã chuẩn); rỗng thì None.
    """
    if slug is None:
        return None
    s = str(slug).strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s
    origin = public_shop_origin()
    return f"{origin}/products/{quote(s, safe='')}"


def slug_path_segment_from_input(v: object | None) -> str | None:
    """
    Chuẩn hoá input (segment hoặc URL đầy đủ) → một segment slug lưu DB.
    """
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        try:
            p = urlparse(s)
            path = p.path.strip("/")
            if path.startswith("products/"):
                rest = path[len("products/") :].strip("/")
                first = rest.split("/")[0] if rest else ""
                return unquote(first) if first else s
        except Exception:
            return s
    return s
