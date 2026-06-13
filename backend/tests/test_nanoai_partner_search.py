"""NanoAI partner proxy — phản hồi HTML/Cloudflare."""

from app.services import nanoai_partner_search as nano


def test_looks_like_html_error_page_detects_doctype():
    assert nano._looks_like_html_error_page("<!DOCTYPE html><html>…")


def test_extract_nanoai_error_strips_html():
    raw = "<!DOCTYPE html><!--[if lt IE 7]> <html class=\"no-js ie6 oldie\""
    msg = nano.extract_nanoai_error({"error": raw})
    assert "<!DOCTYPE" not in msg
    assert "NanoAI" in msg


def test_parse_nanoai_http_response_html():
    class _Resp:
        status_code = 403
        text = "<!DOCTYPE html><html><head><title>Attention Required</title>"
        headers = {"content-type": "text/html; charset=UTF-8"}

    status, body = nano._parse_nanoai_http_response(_Resp(), kind="image-search")
    assert status == 502
    assert body.get("ok") is False
    assert body.get("products") == []
    assert "<!DOCTYPE" not in str(body.get("error"))
