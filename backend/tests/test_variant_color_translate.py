"""Kiểm tra nhận diện nhãn màu cần dịch (Hibox / 1688 Latin + SKU)."""
from app.services.variant_color_translate import (
    _needs_translate,
    variant_color_translate_enabled,
)


def test_needs_translate_hibox_size_color_sku():
    assert _needs_translate("15 Black Suede (91536)") is True
    assert _needs_translate("15 Champagne Gold (91536)") is True
    assert _needs_translate("12 Black Suede (18836)") is True


def test_needs_translate_simple_english_color():
    assert _needs_translate("Black Suede") is True
    assert _needs_translate("Champagne Gold") is True


def test_needs_translate_already_vietnamese():
    assert _needs_translate("Đen da lộn") is False
    assert _needs_translate("Màu như ảnh") is False


def test_needs_translate_pure_size_skipped():
    assert _needs_translate("M") is False
    assert _needs_translate("XL") is False


def test_hibox_source_always_enables_translate_when_api_key():
    from unittest.mock import patch
    from app.core import config as config_mod

    with patch.object(config_mod.settings, "DEEPSEEK_API_KEY", "test-key"), patch.object(
        config_mod.settings, "IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED", False
    ), patch.object(config_mod.settings, "EXCEL_VARIANT_COLORS_DEEPSEEK_TRANSLATE", False):
        pd = {"product_info": {"variants": {"source": "hibox"}}}
        assert variant_color_translate_enabled(product_data=pd) is True
        assert variant_color_translate_enabled(import_source="hibox") is True
