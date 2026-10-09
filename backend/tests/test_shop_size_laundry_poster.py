"""Kho ảnh size/giặt và nhánh GPT Image."""

from app.services.image_localization_service import (
    ImageLocalizationFatalDependencyError,
    is_image_localization_fatal_dependency_error,
    parse_gemini_ink_smear,
)
from app.services.shop_size_laundry_poster import (
    category_level2_slug_from_full_slug,
    collapse_repeated_poster_urls,
    explicit_ai_image_requested,
    localization_image_branch,
    normalize_shop_name_chinese,
    size_laundry_nano_prompt,
)


def test_shop_and_cat2_key():
    assert normalize_shop_name_chinese("  Shop   Alpha  ") == "shop alpha"
    assert category_level2_slug_from_full_slug("thoi-trang-nu/ao-nu/ao-thun-nu") == "ao-nu"
    assert category_level2_slug_from_full_slug("thoi-trang-nu") == ""


def test_only_size_and_laundry_use_gpt_image():
    assert (
        localization_image_branch(
            is_size_or_laundry=True,
            has_chinese=True,
            size_laundry_ai_enabled=True,
            explicit_other_ai=False,
            classifier_type="gemini",
        )
        == "gpt"
    )
    assert (
        localization_image_branch(
            is_size_or_laundry=True,
            has_chinese=True,
            size_laundry_ai_enabled=False,
            explicit_other_ai=False,
            classifier_type="gemini",
        )
        == "local"
    )
    assert (
        localization_image_branch(
            is_size_or_laundry=False,
            has_chinese=True,
            size_laundry_ai_enabled=True,
            explicit_other_ai=False,
            classifier_type="gemini",
        )
        == "local"
    )
    assert (
        localization_image_branch(
            is_size_or_laundry=False,
            has_chinese=True,
            size_laundry_ai_enabled=False,
            explicit_other_ai=True,
            classifier_type="gemini",
        )
        == "explicit_gemini"
    )
    assert (
        localization_image_branch(
            is_size_or_laundry=False,
            has_chinese=True,
            size_laundry_ai_enabled=True,
            explicit_other_ai=True,
            classifier_type="local",
        )
        == "local"
    )


def test_explicit_ai_is_job_or_product_flag():
    class P:
        product_info = {"image_localization": {"allow_ai_models": True}}

    assert explicit_ai_image_requested(P(), None) is True
    assert explicit_ai_image_requested(P(), False) is False
    assert explicit_ai_image_requested(type("Q", (), {"product_info": {}})(), True) is True
    assert explicit_ai_image_requested(type("Q", (), {"product_info": {}})(), None) is False


def test_collapse_keeps_one_library_poster():
    poster = "https://cdn.example/poster.jpg"
    urls = collapse_repeated_poster_urls(
        ["https://cdn.example/look.jpg", poster, poster, "https://cdn.example/detail.jpg"],
        {poster},
    )
    assert urls == [
        "https://cdn.example/look.jpg",
        poster,
        "https://cdn.example/detail.jpg",
    ]


def test_gpt_image_failure_stops_localization():
    exc = ImageLocalizationFatalDependencyError(
        "IMAGE_LOCALIZATION_FATAL_DEPENDENCY:gpt_image_failed: OpenAI images/edits lỗi HTTP 401"
    )
    assert is_image_localization_fatal_dependency_error(exc)


def test_gemini_review_only_flags_ink_smear():
    assert parse_gemini_ink_smear('{"smear": false}') is False
    assert parse_gemini_ink_smear('{"smear": true}') is True
    prompt = size_laundry_nano_prompt("vi")
    assert "Vietnamese" in prompt
    assert "remove the entire person" in prompt
    assert "Do not invent" in prompt
