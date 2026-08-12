"""Ảnh chất liệu dùng prompt cố định — cận cảnh rõ + ưu điểm đã khai báo."""

from app.services.manual_product_create_service import (
    _build_studio_slot_prompt,
    _callouts_are_too_generic,
    _default_studio_admin_intent,
    _dynamic_material_callouts,
    _fallback_callouts_for_material,
    _is_generic_material_callout,
    _resolve_studio_admin_intent,
    _resolve_studio_material_copy,
    _simple_material_prompt,
)


def test_material_simple_prompt_lists_declared_benefits():
    prompt = _simple_material_prompt(
        material_name="Da bò cao cấp",
        material_callouts=["Vân da độc bản tự nhiên", "Càng dùng càng lên màu", "Bền đẹp theo thời gian dùng"],
    )
    assert "material details collage" in prompt.lower()
    assert "TOP PANEL" in prompt
    assert "Da bò cao cấp" in prompt
    assert "Vân da độc bản tự nhiên" in prompt
    assert "verbatim" in prompt.lower()
    assert "premium" in prompt.lower()


def test_generic_callouts_detected():
    assert _is_generic_material_callout("Sang trọng đẳng cấp")
    assert _is_generic_material_callout("Mềm mại tự nhiên")
    assert _callouts_are_too_generic(["Sang trọng đẳng cấp", "Mềm mại tự nhiên", "Thoáng khí mát lạnh"])
    assert not _callouts_are_too_generic(["Óng ảnh tự nhiên", "Mát nhẹ trên da", "Mịn tay"])


def test_fallback_callouts_match_silk():
    callouts = _fallback_callouts_for_material("Lụa tơ tằm")
    assert "Óng ánh chuẩn lụa thật" in callouts
    assert not _callouts_are_too_generic(callouts)


def test_fallback_callouts_match_leather():
    callouts = _fallback_callouts_for_material("Da bò Nappa")
    assert "Vân da độc bản tự nhiên" in callouts


def test_fallback_callouts_cover_diverse_materials():
    for material in ["Gỗ sồi tự nhiên", "Inox 304", "Ren cao cấp", "Cashmere", "Gấm"]:
        callouts = _fallback_callouts_for_material(material)
        assert not _callouts_are_too_generic(callouts)
        assert len(callouts) == 3


def test_dynamic_callouts_reference_unknown_material():
    material = "Sợi tre thiên nhiên"
    callouts = _dynamic_material_callouts(material)
    assert any("Sợi tre" in c for c in callouts)
    assert not _callouts_are_too_generic(callouts)


def test_fallback_uses_dynamic_when_no_keyword_match():
    callouts = _fallback_callouts_for_material("Vải sợi chuối độc lạ")
    assert any("Vải sợi" in c for c in callouts)
    assert not _callouts_are_too_generic(callouts)


def test_simple_prompt_replaces_generic_callouts():
    prompt = _simple_material_prompt(
        material_name="Lụa",
        material_callouts=["Sang trọng đẳng cấp", "Mềm mại tự nhiên", "Thoáng khí mát lạnh"],
    )
    assert "Sang trọng đẳng cấp" not in prompt
    assert "Óng ánh chuẩn lụa thật" in prompt


def test_resolve_studio_material_copy_rejects_generic(monkeypatch):
    state = {
        "payload": {"material": "Lụa", "product_type": "apparel", "product_name": "Váy"},
        "vision_product_name": "Váy lụa",
    }

    def _fake_generate(*_a, **_k):
        return {
            "body": "Lụa mềm",
            "callouts": ["Sang trọng đẳng cấp", "Mềm mại tự nhiên", "Thoáng khí mát lạnh"],
        }

    monkeypatch.setattr(
        "app.services.manual_product_create_service.generate_material_text",
        _fake_generate,
    )
    copy = _resolve_studio_material_copy(state, "Lụa")
    assert not _callouts_are_too_generic(copy["callouts"])
    assert "Óng ánh chuẩn lụa thật" in copy["callouts"]


def test_material_admin_intent_ignores_custom_prompt():
    state = {
        "payload": {"material": "Cotton 100%", "product_type": "apparel"},
        "studio": {"material_callouts": ["Co giãn tốt", "Thấm hút", "Mềm"]},
    }
    resolved = _resolve_studio_admin_intent(
        state,
        kind="material",
        user_prompt="zoom cực cận vân vải",
    )
    assert resolved == _default_studio_admin_intent(state, kind="material")
    assert "Cotton 100%" in resolved
    assert "Co giãn tốt" in resolved
    assert "zoom cực cận" not in resolved


def test_build_studio_slot_prompt_material_uses_simple_template():
    state = {
        "payload": {
            "material": "Linen",
            "product_type": "apparel",
            "gender": "Nữ",
            "model_presence": "none",
        },
        "studio": {
            "plan": {"shot_style": "studio"},
            "material_callouts": ["Nhẹ", "Thoáng", "Tự nhiên"],
        },
    }
    slot = {"kind": "material", "index": 0, "material_callouts": ["Nhẹ", "Thoáng", "Tự nhiên"]}
    prompt = _build_studio_slot_prompt(state, slot)
    assert "Linen" in prompt
    assert "Nhẹ" in prompt
    assert "material details collage" in prompt.lower()
    assert "TOP PANEL" in prompt
    assert "STRIP" in prompt
    assert "corners" in prompt.lower() or "margins" in prompt.lower()


def test_material_composition_for_bag():
    from app.services.manual_product_create_service import _material_collage_panel_brief

    brief = _material_collage_panel_brief("bag")
    assert "TOP" in brief
    assert "STRIP" in brief
    assert "grain" in brief.lower()
