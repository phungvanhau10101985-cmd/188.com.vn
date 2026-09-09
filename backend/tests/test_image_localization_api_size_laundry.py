"""Bảng size / giặt tẩy: xóa khi local-only, giữ khi Gemini API mode."""
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


def test_size_table_deleted_by_default_local_policy():
    tr = _translator()
    assert tr.classify_and_process_blocks(SIZE_OCR, delete_size_and_laundry=True) is None


def test_size_table_preserved_when_api_mode_local_fallback():
    tr = _translator()
    assert tr.has_size_or_laundry_context(SIZE_OCR) is True
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Ngực"):
        result = tr.classify_and_process_blocks(SIZE_OCR, delete_size_and_laundry=False)
    assert result is not None


def test_laundry_deleted_locally_but_detected_for_api():
    tr = _translator()
    assert tr.has_size_or_laundry_context(LAUNDRY_OCR) is True
    assert tr.classify_and_process_blocks(LAUNDRY_OCR, delete_size_and_laundry=True) is None
    with patch.object(tr, "call_deepseek_for_translation_single", return_value="Giặt tay"):
        assert tr.classify_and_process_blocks(LAUNDRY_OCR, delete_size_and_laundry=False) is not None


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
