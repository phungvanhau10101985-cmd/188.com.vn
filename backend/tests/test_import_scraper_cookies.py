"""Tests for shared Playwright scraper cookies."""
from app.services.import_scraper_cookies import (
    bucket_cookies_by_seed_url,
    cookie_domains,
    parse_cookie_text,
    seed_playwright_context_cookies,
)


def test_parse_cookie_json_multi_domain():
    raw = """[
        {"domain": "hibox.mn", "name": "sess", "value": "abc", "path": "/"},
        {"domain": ".vipomall.vn", "name": "token", "value": "xyz", "path": "/"}
    ]"""
    cookies = parse_cookie_text(raw)
    assert len(cookies) == 2
    domains = cookie_domains(cookies)
    assert "hibox.mn" in domains
    assert "vipomall.vn" in domains


def test_bucket_cookies_by_seed_url():
    cookies = parse_cookie_text(
        '[{"domain":"hibox.mn","name":"a","value":"1","path":"/"},'
        '{"domain":"vipomall.vn","name":"b","value":"2","path":"/"}]'
    )
    buckets = bucket_cookies_by_seed_url(cookies)
    assert "https://hibox.mn/" in buckets
    assert "https://vipomall.vn/" in buckets


def test_seed_playwright_no_cookies_returns_zero():
    class _Ctx:
        def add_cookies(self, _bucket):
            raise AssertionError("should not add")

    class _Page:
        def goto(self, *_a, **_k):
            raise AssertionError("should not navigate")

    assert seed_playwright_context_cookies(_Ctx(), _Page()) == 0
