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


def test_strip_chinese_guofeng_from_source_context():
    raw = "国风新中式淑女高端连衣裙女国潮小众仙气收腰无袖长裙子 N6074"
    out = sanitize_listing_context_for_ai(raw)
    assert "国风" not in out
    assert "国潮" not in out
    assert "新中式" not in out
    assert "连衣裙" in out


def test_strip_vietnamese_guofeng_style_from_name():
    name = "Váy maxi nữ phong cách quốc gia mới thắt eo không tay dáng dài — Xanh lam"
    out = sanitize_vi_listing_field(name)
    assert "phong cách quốc gia" not in out.casefold()
    assert "Váy maxi nữ" in out
    assert "thắt eo" in out


def test_keep_other_style_phrases():
    name = "Túi đeo hông nam phong cách thể thao ngoài trời"
    assert sanitize_vi_listing_field(name) == name
