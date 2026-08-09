"""Ảnh màu #1: ref mới thay thế — không ghép attach + ref cũ."""

from app.services.manual_product_create_service import _merge_color_slot_refs


def test_color_first_attach_ignores_old_picked():
    studio = {"colors": []}
    merged = _merge_color_slot_refs(
        studio,
        ["https://cdn/old-ref.jpg", "https://cdn/another.jpg"],
        attach_url="https://cdn/new-upload.jpg",
        color_index=0,
    )
    assert merged == ["https://cdn/new-upload.jpg"]


def test_color_first_picked_single_no_attach():
    studio = {"colors": [{"name": "Đen", "img": "https://cdn/color1.jpg"}]}
    merged = _merge_color_slot_refs(
        studio,
        ["https://cdn/new-pick.jpg", "https://cdn/color1.jpg"],
        attach_url="",
        color_index=0,
    )
    assert merged == ["https://cdn/new-pick.jpg"]
