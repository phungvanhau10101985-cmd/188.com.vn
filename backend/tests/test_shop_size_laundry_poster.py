"""Kho ảnh size/giặt và nhánh GPT Image."""

from app.services.image_localization_service import (
    ImageLocalizationFatalDependencyError,
    ImageLocalizationGptStopError,
    LegacyImageLocalizationPipeline,
    PartProcessOutcome,
    SIZE_LAUNDRY_GPT_QUALITY,
    _normalize_openai_image_quality,
    gpt_edit_quality,
    is_image_localization_fatal_dependency_error,
    is_image_localization_gpt_stop_error,
)
from app.services.shop_size_laundry_poster import (
    category_level2_slug_from_full_slug,
    collapse_repeated_poster_urls,
    explicit_ai_image_requested,
    is_apparel_category,
    language_prompt,
    normalize_shop_name_chinese,
    select_localization_engine,
)


def test_shop_and_cat2_key():
    assert normalize_shop_name_chinese("  Shop   Alpha  ") == "shop alpha"
    assert category_level2_slug_from_full_slug("thoi-trang-nu/ao-nu/ao-thun-nu") == "ao-nu"
    assert category_level2_slug_from_full_slug("thoi-trang-nu") == ""


def test_ai_off_draws_local_and_ai_on_sends_every_image_to_gpt():
    assert select_localization_engine(classification="gemini", allows_ai=False, has_size_or_laundry=True) == "local"
    assert select_localization_engine(classification="local", allows_ai=False) == "local"
    assert select_localization_engine(classification="gemini", allows_ai=True, has_size_or_laundry=True) == "ai"
    assert select_localization_engine(classification="local", allows_ai=True, has_size_or_laundry=False) == "ai"
    assert select_localization_engine(classification="delete", allows_ai=True) == "delete"
    assert select_localization_engine(classification="keep", allows_ai=False) == "keep"


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
    exc = ImageLocalizationGptStopError("OpenAI images/edits lỗi HTTP 401")
    assert is_image_localization_gpt_stop_error(exc)
    assert is_image_localization_fatal_dependency_error(exc)
    plain = ImageLocalizationFatalDependencyError(
        "IMAGE_LOCALIZATION_FATAL_DEPENDENCY:gpt_image_failed: OpenAI images/edits lỗi HTTP 401"
    )
    assert is_image_localization_fatal_dependency_error(plain)


def test_size_prompt_removes_fashion_model():
    prompt = language_prompt("vi", remove_model=True)
    assert "Vietnamese" in prompt
    assert "Erase only the fashion model photograph" in prompt
    assert "1 斤 = 0.5 kg" in prompt
    assert "Keep the product photo and any fashion model" not in prompt


def test_apparel_sheet_prompt_removes_model_and_product_photo():
    prompt = language_prompt("vi", strip_photos=True)
    assert "Also erase product photographs" in prompt
    assert "Keep the size table" in prompt
    assert "Do not invent measurements" in prompt
    assert "Erase only the fashion model photograph" not in prompt


def test_size_laundry_gpt_quality_is_medium_and_other_images_stay_high():
    assert SIZE_LAUNDRY_GPT_QUALITY == "medium"
    assert gpt_edit_quality("medium", "high") == "medium"
    assert gpt_edit_quality(None, "high") == "high"
    assert _normalize_openai_image_quality("medium") == "high"


def test_size_sheet_edit_requests_medium(monkeypatch):
    pipe = LegacyImageLocalizationPipeline.__new__(LegacyImageLocalizationPipeline)
    pipe.language = "vi"
    seen = {}

    def edit(*_a, **kwargs):
        seen["quality"] = kwargs.get("quality")
        return b"gpt", "GPT xong"

    pipe._gpt_edit = edit
    pipe._decode_image_bytes = lambda _b: "gpt-image"
    monkeypatch.setattr(
        "app.services.image_localization_service.detect_ink_bleed",
        lambda _b: {"bleed": False, "where": ""},
    )
    monkeypatch.setattr(
        "app.services.image_localization_service._encode_image_bytes",
        lambda _image, _filename: b"jpg",
    )

    class _Ocr:
        def process_image(self, _b):
            return [{"text": "Ngực 80 cm", "bbox": [0, 0, 10, 10]}]

    pipe.OCRProcessor = _Ocr
    pipe._run_gpt_image(
        {"original_url": "u"},
        None,
        None,
        "orig",
        "a.jpg",
        _SIZE_BLOCKS,
        strip_photos=True,
    )
    assert seen["quality"] == "medium"


def test_apparel_category_is_clothing_not_shoes_or_bags():
    assert is_apparel_category("thoi-trang-nu/ao-nu/ao-thun-nu") is True
    assert is_apparel_category("thoi-trang-nu/vay-chan-vay-nu") is True
    assert is_apparel_category("thoi-trang-nam/quan-dai-nam") is True
    assert is_apparel_category("do-lot-nu/bra-ao-nguc-nu") is True
    assert is_apparel_category("trang-phuc-bau-hau-san/do-mac-bau-hang-ngay") is True
    assert is_apparel_category("thoi-trang-nu/set-do-nu") is True
    assert is_apparel_category("giay-dep-nu/boot-nu") is False
    assert is_apparel_category("tui-xach-nu/tui-deo-vai") is False
    assert is_apparel_category("phu-kien-nu/khan-choang") is False
    assert is_apparel_category("thoi-trang-tre-em/giay-dep-tre-em") is False
    assert is_apparel_category("the-thao-da-ngoai/ao-mua") is False
    assert is_apparel_category(None, cat2_name="Áo thun nữ") is True
    assert is_apparel_category(None, cat2_name="Giày cao gót") is False


_SIZE_BLOCKS = [
    {"text": "尺码表", "bbox": [0, 0, 40, 12]},
    {"text": "胸围", "bbox": [0, 20, 40, 32]},
    {"text": "S", "bbox": [50, 20, 70, 32]},
    {"text": "M", "bbox": [80, 20, 100, 32]},
    {"text": "L", "bbox": [110, 20, 130, 32]},
    {"text": "88cm", "bbox": [0, 40, 40, 52]},
]


def _apparel_pipe():
    pipe = LegacyImageLocalizationPipeline.__new__(LegacyImageLocalizationPipeline)
    pipe.apparel_sheets = True
    pipe.allows_ai_image_models = False
    pipe.dry_run = True
    pipe.language = "vi"
    pipe.poster_shop_norm = "shop a"
    pipe.poster_cat2_slug = "ao-nu"
    pipe.image_classifier = type("C", (), {})()
    pipe.image_classifier.classify_image = lambda *_a, **_k: {"type": "local", "details": {}}
    pipe._library_poster_outcome = lambda *_a, **_k: None
    return pipe


def test_apparel_size_sheet_goes_to_gpt_when_job_is_local():
    pipe = _apparel_pipe()
    seen = {}

    def gpt(*_a, **kwargs):
        seen["strip"] = kwargs.get("strip_photos")
        return PartProcessOutcome("processed", "out", "ok", detail={"gpt_image": True})

    pipe._run_gpt_image = gpt
    out = pipe._process_image_part(
        {"image_data": "orig", "ocr_results": _SIZE_BLOCKS, "original_url": "u", "filename": "a.jpg"},
        None,
        None,
    )
    assert seen["strip"] is True
    assert out.detail["apparel_sheet"] is True
    assert out.detail["sheet_kinds"] == ["size"]


def test_apparel_size_gpt_failure_keeps_the_original():
    pipe = _apparel_pipe()

    def gpt(*_a, **_k):
        raise ImageLocalizationGptStopError("Thiếu OPENAI_API_KEY")

    pipe._run_gpt_image = gpt
    out = pipe._process_image_part(
        {"image_data": "orig", "ocr_results": _SIZE_BLOCKS, "original_url": "u", "filename": "a.jpg"},
        None,
        None,
    )
    assert out.action == "kept"
    assert out.image == "orig"


def test_ink_bleed_after_two_regens_stops_the_apparel_job():
    pipe = _apparel_pipe()

    def gpt(*_a, **_k):
        raise ImageLocalizationGptStopError("Mực loang vẫn còn sau 2 lần tạo lại — mực loang")

    pipe._run_gpt_image = gpt
    try:
        pipe._process_image_part(
            {"image_data": "orig", "ocr_results": _SIZE_BLOCKS, "original_url": "u", "filename": "a.jpg"},
            None,
            None,
        )
    except ImageLocalizationGptStopError as exc:
        assert "Mực loang vẫn còn sau 2 lần" in str(exc)
    else:
        raise AssertionError("mực loang phải dừng job")


def test_leftover_chinese_is_redrawn_locally(monkeypatch):
    pipe = LegacyImageLocalizationPipeline.__new__(LegacyImageLocalizationPipeline)
    pipe.language = "vi"
    pipe._gpt_edit = lambda *_a, **_k: (b"gpt", "GPT xong")
    pipe._decode_image_bytes = lambda _b: "gpt-image"
    monkeypatch.setattr(
        "app.services.image_localization_service.detect_ink_bleed",
        lambda _b: {"bleed": False, "where": ""},
    )
    monkeypatch.setattr(
        "app.services.image_localization_service._encode_image_bytes",
        lambda _image, _filename: b"jpg",
    )

    class _Ocr:
        def process_image(self, _b):
            return [{"text": "80元", "bbox": [1, 2, 10, 12]}]

    pipe.OCRProcessor = _Ocr
    seen = {}

    def local(data, *_a, **_k):
        seen["text"] = data["ocr_results"][0]["text"]
        return ("processed", "drawn", "local")

    pipe._process_local = local
    out = pipe._run_gpt_image(
        {"original_url": "u"},
        None,
        None,
        "orig",
        "a.jpg",
        [{"text": "尺码表", "bbox": [0, 0, 8, 8]}],
        strip_photos=True,
    )
    assert seen["text"] == "80元"
    assert out.action == "processed"
    assert out.image == "drawn"
    assert out.detail["local_chinese_redraw"] is True


def test_ink_bleed_regenerates_twice_then_stops(monkeypatch):
    pipe = LegacyImageLocalizationPipeline.__new__(LegacyImageLocalizationPipeline)
    pipe.language = "vi"
    calls = {"n": 0}

    def edit(*_a, **_k):
        calls["n"] += 1
        return b"gpt", "GPT"

    pipe._gpt_edit = edit
    pipe._decode_image_bytes = lambda _b: "img"
    monkeypatch.setattr(
        "app.services.image_localization_service.detect_ink_bleed",
        lambda _b: {"bleed": True, "where": "bảng size"},
    )
    monkeypatch.setattr(
        "app.services.image_localization_service._encode_image_bytes",
        lambda _image, _filename: b"jpg",
    )
    try:
        pipe._run_gpt_image(
            {"original_url": "u"},
            None,
            None,
            "orig",
            "a.jpg",
            [],
        )
    except ImageLocalizationGptStopError as exc:
        assert "Mực loang vẫn còn sau 2 lần tạo lại" in str(exc)
    else:
        raise AssertionError("phải dừng sau 2 lần tạo lại")
    assert calls["n"] == 3


def test_apparel_look_photo_stays_local_when_job_is_local():
    pipe = _apparel_pipe()
    pipe._run_gpt_image = lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("không gửi GPT"))
    pipe._process_local = lambda *_a, **_k: ("kept", "orig", "local")
    out = pipe._process_image_part(
        {
            "image_data": "orig",
            "ocr_results": [{"text": "新款女装", "bbox": [0, 0, 40, 12]}],
            "original_url": "u",
            "filename": "a.jpg",
        },
        None,
        None,
    )
    assert out.action == "kept"
    assert out.message == "local"


def test_apparel_reuses_versioned_library_when_job_is_local(monkeypatch):
    pipe = _apparel_pipe()
    pipe.dry_run = False

    def lookup(_shop, _slug, render_version=None):
        if render_version != "table-only-1":
            return {}
        return {"size": "https://cdn.example/sheet.jpg"}

    monkeypatch.setattr("app.services.image_localization_service.lookup_stored_sheets", lookup)
    pipe._library_poster_outcome = LegacyImageLocalizationPipeline._library_poster_outcome.__get__(pipe)
    out = pipe._process_image_part(
        {"image_data": "orig", "ocr_results": _SIZE_BLOCKS, "original_url": "u", "filename": "a.jpg"},
        None,
        None,
    )
    assert out.final_url == "https://cdn.example/sheet.jpg"
    assert out.detail["library_hit"] is True
