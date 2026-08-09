"""Unit tests for shared color prompt across Studio color slots."""

from app.services.manual_product_create_service import (
    _merge_color_slot_refs,
    _sync_color_user_prompt,
)


def _studio_with_color_one(*, face_url: str = "https://cdn.example/color1.jpg"):
    return {
        "colors": [{"name": "Đen", "img": face_url, "status": "approved"}],
        "ref_pool": [],
        "color_user_prompt": "",
    }


def test_color_one_saves_shared_prompt():
    studio = _studio_with_color_one()
    studio["colors"] = []
    resolved = _sync_color_user_prompt(studio, "cầm túi trên cẳng tay", color_index=0)
    assert resolved == "cầm túi trên cẳng tay"
    assert studio["color_user_prompt"] == "cầm túi trên cẳng tay"


def test_color_two_inherits_saved_prompt():
    studio = _studio_with_color_one()
    studio["color_user_prompt"] = "cầm túi trên cẳng tay"
    resolved = _sync_color_user_prompt(studio, "", color_index=1)
    assert resolved == "cầm túi trên cẳng tay"
    assert studio["color_user_prompt"] == "cầm túi trên cẳng tay"


def test_color_two_refs_product_then_face():
    studio = _studio_with_color_one(face_url="https://cdn.example/face.jpg")
    merged = _merge_color_slot_refs(
        studio,
        [],
        attach_url="https://cdn.example/new-bag.jpg",
        color_index=1,
    )
    assert merged == ["https://cdn.example/new-bag.jpg", "https://cdn.example/face.jpg"]
