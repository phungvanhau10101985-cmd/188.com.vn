"""Hành vi bản địa hóa khớp nanoai: engine, prompt, classifier, kho sheet, hậu kiểm."""

import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "app" / "services" / "image_localization_tool"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

import importlib.util

from nano_rules import (  # noqa: E402
    chinese_blocks_to_redraw,
    classify_image,
    convert_jin_weight_text,
    has_size_table_context,
    image_loc_gpt_verify_attempts,
    apparel_sheet_kinds,
    image_loc_sheet_kinds,
    language_prompt,
    local_blocks_need_draw,
    localized_image_fix,
    localized_image_problem,
    parse_ink_bleed_verdict,
    remaining_chinese_on_localized_image,
    resolve_stored_image_loc_sheet,
    select_localization_engine,
)
from app.services.image_localization_service import (  # noqa: E402
    ImageLocalizationGptStopError,
    is_image_localization_gpt_stop_error,
)


def test_images_narrower_than_350_are_dropped():
    path = _TOOL / "config.py"
    spec = importlib.util.spec_from_file_location("image_loc_tool_config_width", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.MIN_IMAGE_WIDTH == 350


def test_url_size_suffix_under_350_is_junk():
    import image_merger

    merger = image_merger.ImageMerger()
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_220x220.jpg") is True
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_100x100.jpg") is True
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_349x349.jpg") is True
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_350x350.jpg") is False
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_384x1024.jpg") is False
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_790x1000.jpg") is False
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a.jpg_.search.jpg") is True
    assert merger.is_junk_thumbnail("https://img.alicdn.com/bao/a_sum.jpg") is True


def test_ai_off_is_local_and_ai_on_is_gpt_for_every_image():
    assert (
        select_localization_engine(
            classification="gemini",
            allows_ai=False,
            gemini_mode="api",
            has_size_or_laundry=False,
        )
        == "local"
    )
    assert (
        select_localization_engine(
            classification="local",
            allows_ai=False,
            has_size_or_laundry=True,
        )
        == "local"
    )
    assert (
        select_localization_engine(
            classification="gemini",
            allows_ai=False,
            gemini_mode="openai",
            has_size_or_laundry=True,
            force_ai=True,
        )
        == "local"
    )
    assert (
        select_localization_engine(
            classification="local",
            allows_ai=True,
            has_size_or_laundry=False,
        )
        == "ai"
    )
    assert (
        select_localization_engine(
            classification="gemini",
            allows_ai=True,
            has_size_or_laundry=True,
        )
        == "ai"
    )
    assert select_localization_engine(classification="delete", allows_ai=True) == "delete"
    assert select_localization_engine(classification="keep", allows_ai=True) == "keep"


def test_size_chart_prompt_removes_the_model():
    plain = language_prompt("vi")
    size = language_prompt("vi", remove_model=True)
    assert "Erase only the fashion model photograph" not in plain
    assert "Erase only the fashion model photograph" in size
    assert "Do not keep the original Chinese" in size
    assert "Do not add a second copy of any line" in size
    assert "1 斤 = 0.5 kg" in plain
    assert "94 斤 becomes 47 kg" in plain
    assert "Still convert 斤 body weight to kilograms" in size


def test_gpt_failure_stops_the_job():
    err = ImageLocalizationGptStopError("OpenAI images/edits lỗi HTTP 500: boom")
    assert is_image_localization_gpt_stop_error(err) is True
    assert is_image_localization_gpt_stop_error(RuntimeError("vẽ local lỗi")) is False
    assert image_loc_gpt_verify_attempts() == 2


def test_verify_policy_matches_nanoai():
    assert remaining_chinese_on_localized_image(["Ngực 82 cm", "S", ""]) == []
    assert localized_image_problem(bleed=False, chinese=[]) == ""
    left = remaining_chinese_on_localized_image(["胸围 82", "Giặt tay"])
    assert left == ["胸围 82"]
    assert "胸围" in localized_image_problem(bleed=False, chinese=["胸围 82", "洗涤说明"])
    assert localized_image_fix(bleed=True, chinese_count=2) == "gpt"
    assert localized_image_fix(bleed=False, chinese_count=1) == "deepseek"
    assert localized_image_fix(bleed=False, chinese_count=0) == "ok"
    assert parse_ink_bleed_verdict('{"bleed":true,"where":"size table"}')["bleed"] is True
    assert parse_ink_bleed_verdict('{"bleed":false,"where":""}')["bleed"] is False
    assert parse_ink_bleed_verdict("not json") is None
    redraw = chinese_blocks_to_redraw(
        [
            {"text": "胸围", "bbox": [0, 0, 10, 10]},
            {"text": "82 cm", "bbox": [12, 0, 30, 10]},
        ]
    )
    assert [block["text"] for block in redraw] == ["胸围"]
    assert "mực loang" in localized_image_problem(bleed=True, where="bảng size", chinese=["胸围"])


def test_classifier_delete_keep_overlap_and_return_cluster():
    deleted = classify_image([{"text": "热荐爆款", "bbox": [0, 0, 10, 10]}], [], "https://example.com/a.jpg")
    assert deleted["type"] == "delete"
    assert deleted["details"]["detected_keyword"] == "荐"
    kept = classify_image([{"text": "SKU 12345", "bbox": [0, 0, 10, 10]}], [], "https://example.com/a.jpg")
    assert kept["type"] == "keep"
    blocks = [
        {"text": "尺码表", "bbox": [0, 0, 20, 10]},
        {"text": "胸围", "bbox": [0, 12, 20, 20]},
        {"text": "S", "bbox": [22, 12, 30, 20]},
        {"text": "M", "bbox": [32, 12, 40, 20]},
        {"text": "L", "bbox": [42, 12, 50, 20]},
        {"text": "50cm", "bbox": [0, 22, 20, 30]},
    ]
    assert has_size_table_context(blocks) is True
    assert convert_jin_weight_text("约 2 斤") == "约 1 kg"
    assert convert_jin_weight_text("1.5斤") == "0.75 kg"
    overlap = classify_image(
        [
            {"text": "显瘦显高", "bbox": [0, 0, 120, 60]},
            {"text": "轻盈舒适", "bbox": [20, 10, 80, 40]},
        ],
        [],
        "https://example.com/shoe.jpg",
    )
    assert overlap["type"] == "gemini"
    assert overlap["details"]["overlap_ratio"] > 0.05


def test_local_draw_keeps_size_laundry_and_erases_return_and_factory():
    size = local_blocks_need_draw(
        [
            {"text": "尺码表", "bbox": [0, 0, 40, 12]},
            {"text": "S", "bbox": [0, 14, 8, 22]},
            {"text": "M", "bbox": [10, 14, 18, 22]},
            {"text": "L", "bbox": [20, 14, 28, 22]},
            {"text": "50cm", "bbox": [0, 24, 20, 32]},
        ]
    )
    assert size["action"] == "draw"
    assert any(block["text"] == "尺码表" for block in size["blocks"])
    laundry = local_blocks_need_draw(
        [
            {"text": "洗涤说明", "bbox": [0, 0, 80, 16]},
            {"text": "手洗", "bbox": [0, 20, 40, 32]},
        ]
    )
    assert laundry["action"] == "draw"
    urgent = local_blocks_need_draw(
        [
            {"text": "新款女装", "bbox": [0, 0, 80, 20]},
            {"text": "荐", "bbox": [90, 0, 100, 20]},
        ]
    )
    assert urgent["action"] == "deleted"
    draw = local_blocks_need_draw(
        [
            {"text": "新款女装", "bbox": [0, 0, 80, 20]},
            {"text": "春", "bbox": [90, 0, 100, 20]},
        ]
    )
    assert draw["action"] == "draw"
    assert [block["text"] for block in draw["blocks"]] == ["新款女装"]
    returned = local_blocks_need_draw(
        [
            {"text": "商品信息", "bbox": [0, 0, 40, 12]},
            {"text": "特殊靴子订制都不退换", "bbox": [200, 40, 320, 52]},
            {"text": "鞋面材质:漆皮", "bbox": [0, 80, 120, 96]},
        ]
    )
    assert returned["action"] == "draw"
    assert next(block for block in returned["blocks"] if block["bbox"][1] == 40)["text"] == ""
    factory = local_blocks_need_draw(
        [
            {"text": "源头工厂", "bbox": [10, 20, 90, 40]},
            {"text": "不易起球", "bbox": [10, 80, 90, 100]},
            {"text": "杰仕西服源头工厂", "bbox": [10, 120, 140, 140]},
        ]
    )
    assert factory["action"] == "draw"
    assert next(block for block in factory["blocks"] if block["bbox"][1] == 20)["text"] == ""
    assert next(block for block in factory["blocks"] if block["text"] == "不易起球")["text"] == "不易起球"
    assert next(block for block in factory["blocks"] if block["bbox"][1] == 120)["text"] == "杰仕西服"


def test_sheet_reuse_needs_every_kind_on_the_same_url():
    assert resolve_stored_image_loc_sheet(["size"], {"size": "https://cdn.example/size.jpg"}) == "https://cdn.example/size.jpg"
    assert resolve_stored_image_loc_sheet(["laundry"], {"size": "https://cdn.example/size.jpg"}) is None
    assert (
        resolve_stored_image_loc_sheet(
            ["size", "laundry"],
            {"size": "https://cdn.example/both.jpg", "laundry": "https://cdn.example/both.jpg"},
        )
        == "https://cdn.example/both.jpg"
    )
    assert resolve_stored_image_loc_sheet(["size", "laundry"], {"size": "https://cdn.example/size.jpg"}) is None
    assert image_loc_sheet_kinds(
        [
            {"text": "尺码表", "bbox": [0, 0, 40, 12]},
            {"text": "胸围", "bbox": [0, 20, 40, 32]},
            {"text": "S", "bbox": [50, 20, 70, 32]},
            {"text": "M", "bbox": [80, 20, 100, 32]},
            {"text": "L", "bbox": [110, 20, 130, 32]},
            {"text": "88cm", "bbox": [0, 40, 40, 52]},
        ]
    ) == ["size"]
    assert apparel_sheet_kinds([{"text": "洗涤", "bbox": [0, 0, 20, 10]}]) == []
    assert image_loc_sheet_kinds([{"text": "洗涤", "bbox": [0, 0, 20, 10]}]) == ["laundry"]
    assert "Also erase product photographs" in language_prompt("vi", strip_photos=True)
