"""Tests for listing year/marketing sanitization."""
from app.services.listing_year_sanitize import (
    apply_listing_year_sanitize_to_product_data,
    sanitize_listing_context_for_ai,
    sanitize_vi_listing_field,
)


def test_strip_chinese_year_season_new():
    raw = "厚底老爹鞋女款2026春季新款水钻时尚内增高女鞋"
    out = sanitize_listing_context_for_ai(raw)
    assert "2026" not in out
    assert "春季" not in out or "新款" not in out
    assert "厚底老爹鞋" in out


def test_strip_vietnamese_year_marketing():
    name = "Giày cao gót nữ model 2026 mới sang trọng"
    out = sanitize_vi_listing_field(name)
    assert "2026" not in out
    assert "Giày cao gót" in out


def test_keep_technical_measurements():
    spec = "Gót khoảng 9 cm, đế bệt 2 cm"
    assert sanitize_vi_listing_field(spec) == spec


def test_product_data_skips_chinese_name():
    pd = {
        "name": "Sandal nữ hở mũi 2025 collection",
        "chinese_name": "2026春季新款凉鞋",
        "description": "Phù hợp mùa hè 2024, năm ra mắt 2023.",
    }
    apply_listing_year_sanitize_to_product_data(pd)
    assert pd["chinese_name"] == "2026春季新款凉鞋"
    assert "2025" not in pd["name"]
    assert "2024" not in pd["description"]
    assert "2023" not in pd["description"]
