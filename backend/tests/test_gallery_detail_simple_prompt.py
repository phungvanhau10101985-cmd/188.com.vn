"""Gallery/chi tiết dùng prompt cố định — chỉ đổi góc ảnh."""

from app.services.manual_product_create_service import (
    _default_studio_admin_intent,
    _resolve_studio_admin_intent,
    _simple_gallery_detail_prompt,
)


def test_gallery_detail_prompt_is_fixed():
    gallery = _simple_gallery_detail_prompt("gallery")
    detail = _simple_gallery_detail_prompt("detail")
    assert "different camera angle" in gallery.lower()
    assert "different angle" in detail.lower()
    assert gallery == _default_studio_admin_intent({}, kind="gallery")
    assert detail == _resolve_studio_admin_intent({}, kind="detail")
