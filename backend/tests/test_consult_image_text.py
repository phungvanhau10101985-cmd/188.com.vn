"""Lọc chữ OCR cho ngữ cảnh tư vấn NanoAI."""
from app.services.consult_image_text import (
    build_image_consult_context,
    consult_updates_from_results,
    filter_ocr_line,
    filter_ocr_lines,
    merge_consult_image_text,
    translate_consult_lines,
)


class _Res:
    def __init__(self, texts):
        self.consult_ocr_texts = texts


def test_keeps_product_facts_across_categories():
    assert filter_ocr_line("功率 2000W") == "功率 2000W"
    assert filter_ocr_line("电压 220V") == "电压 220V"
    assert filter_ocr_line("胸围88cm") == "胸围88cm"
    assert filter_ocr_line("纯棉") == "纯棉"
    assert filter_ocr_line("洗涤 冷水手洗") == "洗涤 冷水手洗"
    assert "88" in (filter_ocr_line("胸围88cm价") or "")


def test_drops_seller_price_contact_and_short_noise():
    assert filter_ocr_line("批发价25元") is None
    assert filter_ocr_line("25元") is None
    assert filter_ocr_line("¥99") is None
    assert filter_ocr_line("加微信 abcshop") is None
    assert filter_ocr_line("实力工厂") is None
    assert filter_ocr_line("热卖爆款") is None
    assert filter_ocr_line("https://shop.example.com") is None
    assert filter_ocr_line("电话13800138000") is None
    assert filter_ocr_line("的") is None
    assert filter_ocr_line("价") is None
    assert filter_ocr_line("ab") is None


def test_mixed_line_keeps_measurement_only():
    assert filter_ocr_line("胸围88cm 实力工厂") == "胸围88cm"
    assert filter_ocr_line("功率2000W 批发价25元") == "功率2000W"
    assert filter_ocr_line("38") == "38"
    assert filter_ocr_line("XL") == "XL"
    assert filter_ocr_line("2000W") == "2000W"


def test_single_jia_does_not_drop_measurement_sentence():
    kept = filter_ocr_lines(["胸围88cm 价 适合", "价"])
    assert any("胸围88cm" in line for line in kept)
    assert "价" not in kept


def test_empty_after_filter_omits_image_and_rerun_replaces_one_url():
    existing = {
        "https://img/a.jpg": [{"src": "旧", "vi": "cũ"}],
        "https://img/b.jpg": [{"src": "功率2000W", "vi": "Công suất 2000W"}],
    }
    updates = consult_updates_from_results(
        {
            "https://img/a.jpg": _Res(["实力工厂", "的"]),
            "https://img/c.jpg": _Res(None),
        }
    )
    assert updates["https://img/a.jpg"] == []
    assert "https://img/c.jpg" not in updates
    merged = merge_consult_image_text(existing, updates)
    assert "https://img/a.jpg" not in merged
    assert "https://img/b.jpg" in merged

    replaced = merge_consult_image_text(
        merged,
        {
            "https://img/b.jpg": translate_consult_lines(
                filter_ocr_lines(["容量 5L"]),
                translate_batch=lambda lines: [f"VI:{lines[0]}"],
            )
        },
    )
    assert replaced["https://img/b.jpg"] == [{"src": "容量 5L", "vi": "VI:容量 5L"}]
    assert "https://img/a.jpg" not in replaced


def test_translate_mismatch_keeps_source():
    rows = translate_consult_lines(["功率2000W"], translate_batch=lambda _lines: ["một", "hai"])
    assert rows == [{"src": "功率2000W", "vi": "功率2000W"}]


def test_search_document_ignores_consult_column():
    from types import SimpleNamespace

    from app.services.product_search_document import build_product_search_document

    product = SimpleNamespace(
        name="áo",
        slug="",
        code="",
        category="",
        subcategory="",
        sub_subcategory="",
        material="",
        style="",
        color="",
        occasion="",
        features="",
        sizes="",
        product_info={"product_info": {"sku": "A1"}},
        consult_image_text={"https://img/a.jpg": [{"src": "wechat-secret-token", "vi": "x"}]},
    )
    doc = build_product_search_document(product=product)
    assert "wechat-secret-token" not in doc


def test_image_consult_context_shape_and_limits():
    from app.schemas.product import Product as ProductSchema

    stored = {
        "https://cdn.shop/size-chart.jpg": [
            {"src": "胸围88cm 实力工厂", "vi": "Vòng ngực 88cm"},
            {"src": "<b>功率 1500W</b>", "vi": "Công suất 1500W"},
            {"src": "微信 shop123", "vi": "wechat"},
        ],
        "https://cdn.shop/spec.jpg": [
            {"src": "电压 220V", "vi": "Điện áp 220V"},
        ],
    }
    payload = build_image_consult_context(stored)
    assert payload["language"] == "vi"
    assert payload["lines"][0] == {"src": "胸围88cm", "vi": "Vòng ngực 88cm"}
    assert payload["lines"][1]["src"] == "功率 1500W"
    assert all("微信" not in row["src"] for row in payload["lines"])
    assert payload["images"][0]["url"] == "https://cdn.shop/size-chart.jpg"
    assert "product_info" not in payload
    assert build_image_consult_context({}) is None
    assert build_image_consult_context({"https://img/a.jpg": [{"src": "实力工厂", "vi": "xưởng"}]}) is None
    long = {"https://img/a.jpg": [{"src": "棉" * 250, "vi": "v" * 250}]}
    clipped = build_image_consult_context(long)
    assert clipped is not None
    assert len(clipped["lines"][0]["src"]) == 200
    assert len(clipped["lines"][0]["vi"]) == 200
    many = {
        "https://img/a.jpg": [{"src": f"容量 {i}L", "vi": f"{i}L"} for i in range(60)]
    }
    capped = build_image_consult_context(many)
    assert len(capped["lines"]) == 40
    assert "image_consult_context" not in ProductSchema.model_fields
