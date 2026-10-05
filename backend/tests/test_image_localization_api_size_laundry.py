"""Bảng size / giặt tẩy: local vẽ chữ, không xóa ảnh."""
import sys
from pathlib import Path
from unittest.mock import patch

_TOOL = Path(__file__).resolve().parents[1] / "app" / "services" / "image_localization_tool"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from text_translator import TextTranslator  # noqa: E402


def _translator() -> TextTranslator:
    return TextTranslator()


SIZE_OCR = [
    {"text": "尺码表", "bbox": [0, 0, 100, 20]},
    {"text": "胸围", "bbox": [0, 30, 50, 50]},
    {"text": "S", "bbox": [60, 30, 80, 50]},
    {"text": "M", "bbox": [90, 30, 110, 50]},
    {"text": "L", "bbox": [120, 30, 140, 50]},
]

LAUNDRY_OCR = [
    {"text": "洗涤说明", "bbox": [0, 0, 120, 20]},
    {"text": "手洗", "bbox": [0, 30, 60, 50]},
    {"text": "不可漂白", "bbox": [0, 60, 100, 80]},
]


def test_size_table_drawn_on_local_path():
    tr = _translator()
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Ngực"):
        result = tr.classify_and_process_blocks(SIZE_OCR, delete_size_and_laundry=True)
    assert result is not None
    processed, _ignore = result
    assert any(block[0] == "Ngực" for block in processed)


def test_size_table_preserved_when_api_mode_local_fallback():
    tr = _translator()
    assert tr.has_size_or_laundry_context(SIZE_OCR) is True
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Ngực"):
        result = tr.classify_and_process_blocks(SIZE_OCR, delete_size_and_laundry=False)
    assert result is not None


def test_laundry_drawn_locally_and_detected_for_api():
    tr = _translator()
    assert tr.has_size_or_laundry_context(LAUNDRY_OCR) is True
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Giặt tay"):
        local = tr.classify_and_process_blocks(LAUNDRY_OCR, delete_size_and_laundry=True)
        kept = tr.classify_and_process_blocks(LAUNDRY_OCR, delete_size_and_laundry=False)
    assert local is not None and kept is not None
    assert any(block[0] == "Giặt tay" for block in local[0])


def test_forbidden_still_deletes_even_when_preserve_size_laundry():
    tr = _translator()
    ocr = [{"text": "一件代发", "bbox": [0, 0, 100, 20]}]
    assert tr.classify_and_process_blocks(ocr, delete_size_and_laundry=False) is None


def test_empty_deepseek_keeps_original_instead_of_erasing():
    tr = _translator()
    ocr = [{"text": "精美立体压花", "bbox": [10, 20, 100, 40]}]
    with patch.object(tr, "call_deepseek_for_translation_single", return_value=""):
        result = tr.classify_and_process_blocks(ocr, delete_size_and_laundry=True)
    assert result is not None
    processed, ignore = result
    assert processed == []
    assert len(ignore) == 1
    assert ignore[0][0] == "精美立体压花"
    assert list(ignore[0][1]) == [10, 20, 100, 40]


def test_deepseek_payload_disables_v4_thinking():
    tr = _translator()
    captured = {}

    class _Resp:
        status_code = 200
        content = b'{"choices":[{"message":{"content":"ok"}}]}'

        def json(self):
            return {"choices": [{"message": {"content": "Chất lượng cao"}}]}

    def _fake_completions(payload, **kwargs):
        captured.update(payload)
        return _Resp()

    with patch("text_translator.DEEPSEEK_API_KEY", "test-key"), patch(
        "text_translator.deepseek_chat_completions", _fake_completions
    ), patch("text_translator.deepseek_message_text", lambda body: "Chất lượng cao"):
        out = tr.call_deepseek_for_translation_single("高品质")
    assert out == "Chất lượng cao"
    assert captured.get("thinking") == {"type": "disabled"}
    assert int(captured.get("max_tokens") or 0) >= 256


def test_domain_on_label_keeps_image_and_blanks_url():
    """Tem SP có www… không được xóa cả ảnh biến thể."""
    tr = _translator()
    ocr = [
        {"text": "www.yongchuang.com", "bbox": [0, 0, 80, 20]},
        {"text": "好阀选永创", "bbox": [0, 40, 120, 60]},
    ]
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Van tốt"):
        result = tr.classify_and_process_blocks(ocr, delete_size_and_laundry=True)
    assert result is not None
    processed, _ignore = result
    assert ("", (0, 0, 80, 20)) in processed or ("", [0, 0, 80, 20]) in processed
    assert any(block[0] == "Van tốt" for block in processed)


def test_dropship_keyword_still_deletes_image():
    tr = _translator()
    ocr = [{"text": "www.shop.com 一件代发", "bbox": [0, 0, 100, 20]}]
    assert tr.classify_and_process_blocks(ocr, delete_size_and_laundry=True) is None


def test_classifier_does_not_delete_product_photo_for_label_domain():
    from image_classifier import ImageClassifier

    clf = ImageClassifier()
    ocr = [
        {"text": "www.yongchuang.com", "bbox": [10, 10, 90, 30]},
        {"text": "好阀选永创", "bbox": [10, 200, 200, 240]},
    ]
    result = clf.classify_image(ocr, [], "https://example.com/valve.jpg")
    assert result.get("type") != "delete"
