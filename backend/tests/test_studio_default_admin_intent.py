"""Unit tests for AI Studio compose intent (gallery/detail unique prompts)."""

import pytest

from app.services.manual_product_create_service import (
    _default_studio_admin_intent,
    _pick_unique_compose_intent,
    _record_compose_intent,
    _resolve_studio_admin_intent,
    _validate_unique_compose_intent,
)


def _state(*, product_type="apparel", model_presence="model", vision_product_kind=""):
    return {
        "payload": {
            "product_type": product_type,
            "model_presence": model_presence,
            "material": "Cotton 100%",
        },
        "vision_product_kind": vision_product_kind,
        "studio": {
            "plan": {"model_presence": model_presence},
            "compose_intents_used": {},
        },
    }


def test_material_default_intent_without_admin_input():
    intent = _default_studio_admin_intent(_state(), kind="material")
    assert "material details collage" in intent.lower()
    assert "Cotton 100%" in intent
    assert "TOP PANEL" in intent


def test_resolve_material_ignores_admin_prompt():
    resolved = _resolve_studio_admin_intent(
        _state(),
        kind="material",
        user_prompt="zoom cực cận vân vải",
    )
    assert "zoom cực cận" not in resolved
    assert "Cotton 100%" in resolved


def test_gallery_defaults_differ_by_index():
    state = _state(product_type="apparel", model_presence="model")
    a = _pick_unique_compose_intent(state, kind="gallery", index=0)
    b = _pick_unique_compose_intent(state, kind="gallery", index=1)
    assert a != b


def test_gallery_rejects_duplicate_used_prompt():
    studio = {"compose_intents_used": {"gallery": ["người mẫu đứng 3/4, tư thế thời trang tự nhiên"]}}
    with pytest.raises(ValueError, match="trùng"):
        _validate_unique_compose_intent(
            studio,
            kind="gallery",
            user_prompt="Người mẫu đứng 3/4, tư thế thời trang tự nhiên",
        )


def test_gallery_skips_used_when_picking_next():
    state = _state(product_type="apparel", model_presence="model")
    studio = state["studio"]
    first = _pick_unique_compose_intent(state, kind="gallery", index=0)
    _record_compose_intent(studio, "gallery", first)
    second = _pick_unique_compose_intent(state, kind="gallery", index=1)
    assert first != second


def test_non_wearable_gallery_no_model():
    state = _state(product_type="medicine", model_presence="model")
    intent = _pick_unique_compose_intent(state, kind="gallery", index=0)
    assert "packshot" in intent.lower() or "nhãn" in intent.lower()
