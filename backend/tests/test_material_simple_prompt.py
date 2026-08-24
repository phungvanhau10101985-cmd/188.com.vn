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
        product_name="Túi xách da bò",
        product_type="bag",
    )
    assert "infographic" in prompt.lower()
    assert "MAIN CENTER HERO IMAGE" in prompt
    assert "Top Left Card" in prompt
    assert "CAM KẾT: BAO ĐỔI TRẢ 7 NGÀY" in prompt
    assert "magnifying glass" in prompt.lower()
    assert "Da bò cao cấp" in prompt
    assert "Vân da độc bản tự nhiên" in prompt
    assert "CHẤT LƯỢNG KHẲNG ĐỊNH ĐẲNG CẤP" in prompt
    assert "TÚI XÁCH DA BÒ CAO CẤP" in prompt
    assert "EXACTLY ONE real product photo" in prompt
    assert "1:1 aspect ratio" in prompt
    assert "carrying" in prompt.lower()
    assert "Never write VẬN" in prompt


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
    assert "infographic" in prompt.lower()
    assert "MAIN CENTER HERO IMAGE" in prompt
    assert "Top Left Card" in prompt
    assert "CAM KẾT: BAO ĐỔI TRẢ 7 NGÀY" in prompt
    assert "magnifying glass" in prompt.lower()


def test_material_composition_for_bag():
    from app.services.manual_product_create_service import _material_collage_panel_brief

    brief = _material_collage_panel_brief("bag")
    assert "TOP-LEFT" in brief
    assert "BOTTOM-RIGHT" in brief
    assert "grain" in brief.lower()


def test_material_board_copy_uses_sales_headline():
    from app.services.manual_product_create_service import _material_board_sales_copy

    headline, sub, trust = _material_board_sales_copy(
        product_name="Áo polo dệt kim premium",
        material="dệt kim",
        product_type="apparel",
        gender="Nam",
        benefit_bullets=["Vải mềm mịn", "Thấm hút tuyệt đối", "Giữ phom chuẩn"],
    )
    assert "ÁO POLO DỆT KIM CAO CẤP" in headline
    assert "CHẤT LƯỢNG KHẲNG ĐỊNH ĐẲNG CẤP" in headline
    assert "Vải Mềm Mịn" in sub or "Vải mềm mịn" in sub
    assert "CAM KẾT: BAO ĐỔI TRẢ 7 NGÀY" in trust


def test_simple_prompt_includes_four_captions_and_center_model():
    prompt = _simple_material_prompt(
        material_name="Cotton",
        material_callouts=["Thấm hút vượt trội tự nhiên", "Mềm mại chuẩn cotton nguyên chất", "Thoáng khí suốt ngày dài"],
        product_type="apparel",
        gender="Nam",
        product_name="Áo polo dệt kim",
    )
    assert "model wearing Áo polo dệt kim" in prompt
    assert "magnifying glass" in prompt.lower()
    assert "honeycomb" in prompt.lower()
    assert "PHOM DÁNG HOÀN HẢO" in prompt
    assert "Tôn dáng, mặc lên vừa vặn" in prompt
    assert "CAM KẾT: BAO ĐỔI TRẢ 7 NGÀY" in prompt
    assert "needle icon" in prompt
    assert "do NOT print this full SEO title" in prompt
    assert "EXACTLY ONE" in prompt


def test_b0668_party_dress_fills_locked_template():
    name = (
        "Váy Dạ Tiệc Nữ Dáng Ôm Body Cổ chữ V Lớp Lót Phong Cách Châu Âu Màu Tím"
    )
    prompt = _simple_material_prompt(
        product_name=name,
        product_type="apparel",
        gender="Nữ",
    )
    assert 'Print exactly:\n  "VÁY DẠ TIỆC CAO CẤP — CHẤT LƯỢNG KHẲNG ĐỊNH ĐẲNG CẤP"' in prompt
    assert "Ôm Dáng Sang Trọng • Lót Mềm Êm • Tôn Dáng Nữ Tính" in prompt
    assert f"do NOT print this full SEO title): {name}" in prompt
    assert "VÂN CHẤT LIỆU RÕ NÉT" in prompt
    assert "ĐƯỜNG MAY TINH XẢO" in prompt
    assert "CHI TIẾT TINH TẾ" in prompt
    assert "PHOM DÁNG HOÀN HẢO" in prompt
    assert "Rõ vân, cảm nhận ngay từ ảnh" in prompt
    assert "Tôn dáng, mặc lên vừa vặn" in prompt
    assert "CAM KẾT: BAO ĐỔI TRẢ 7 NGÀY — CHO KIỂM TRA HÀNG" in prompt
    assert "1:1 aspect ratio" in prompt
    assert "Never write VẬN" in prompt
    assert "model wearing Váy Dạ Tiệc Nữ" in prompt


def test_shoes_and_medicine_swap_corner_cards_not_frame():
    shoes = _simple_material_prompt(
        product_name="Giày sneaker nam",
        product_type="shoes",
        gender="Nam",
    )
    med = _simple_material_prompt(
        product_name="Viên uống collagen",
        product_type="medicine",
    )
    assert "[1. HEADER SECTION]" in shoes
    assert "[4. FOOTER TRUST BANNER]" in shoes
    assert "upper material grain" in shoes
    assert "NO human model" in med
    assert "CHI TIẾT CHẤT LƯỢNG" in med
    assert "VÂN CHẤT LIỆU RÕ NÉT" in shoes
    assert "VÂN CHẤT LIỆU RÕ NÉT" not in med
