# backend/tests/test_ladipage_deepseek_text.py
from unittest.mock import MagicMock, patch

from app.services import ladipage_ai_service as svc


def test_call_deepseek_text_returns_content():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": '{"headline":"Test"}'}, "finish_reason": "stop"}],
    }

    with patch.object(svc.settings, "DEEPSEEK_API_KEY", "sk-test-key"):
        with patch.object(svc.requests, "post", return_value=mock_resp) as post:
            out = svc._call_deepseek_text("prompt", max_tokens=100)

    assert out == '{"headline":"Test"}'
    payload = post.call_args.kwargs["json"]
    assert payload["response_format"] == {"type": "json_object"}
    assert payload.get("thinking") == {"type": "disabled"}
    assert payload["model"]


def test_call_deepseek_text_missing_api_key():
    with patch.object(svc.settings, "DEEPSEEK_API_KEY", ""):
        assert svc._call_deepseek_text("prompt") is None


def test_generate_hero_text_uses_deepseek():
    context = {"title": "Giày da nam", "sample_products": []}
    with patch.object(svc, "_call_deepseek_text", return_value='{"headline":"H","subheadline":"S"}'):
        out = svc.generate_hero_text(context)
    assert out == {"headline": "H", "subheadline": "S"}
