from app.services.import_scraper_cookies import (
    bucket_cookies_by_seed_url,
    cookie_domain_warnings,
    parse_cookie_text,
)


def test_parse_cookie_json_vipomall_domain():
    cookies = parse_cookie_text(
        '[{"domain":"vipomall.vn","name":"sess","value":"abc","path":"/"}]',
        default_domain="",
    )
    domains = {c.get("domain", "").lstrip(".").lower() for c in cookies}
    assert "vipomall.vn" in domains


def test_seed_urls_include_vipomall():
    buckets = bucket_cookies_by_seed_url(
        [{"domain": "vipomall.vn", "name": "a", "value": "1", "path": "/"}]
    )
    assert any("vipomall.vn" in u for u in buckets)


def test_cookie_domain_warnings_reject_188():
    warns = cookie_domain_warnings(["188.com.vn"])
    assert warns
    assert "188.com.vn" in warns[0]
