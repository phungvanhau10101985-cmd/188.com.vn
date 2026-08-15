from unittest.mock import patch

from starlette.requests import Request

from app.services.auth_failure_alert import is_crawler_user_agent, maybe_notify_auth_login_failure


def test_is_crawler_user_agent_facebook_indexer():
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36 "
        "(compatible; meta-webindexer/1.1 "
        "(+https://developers.facebook.com/docs/sharing/webmasters/crawler))"
    )
    assert is_crawler_user_agent(ua) is True


def test_is_crawler_user_agent_keeps_real_in_app_customers():
    facebook_in_app = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 26_6 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/23G71 Safari/604.1 "
        "[FBAN/FBIOS;FBAV/573.0.0.47.73;FBBV/1032158285]"
    )
    zalo_in_app = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Zalo iOS/260701804"
    )
    chrome = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    )
    assert is_crawler_user_agent(facebook_in_app) is False
    assert is_crawler_user_agent(zalo_in_app) is False
    assert is_crawler_user_agent(chrome) is False
    assert is_crawler_user_agent("") is False
    assert is_crawler_user_agent(None) is False


def _request(path: str, user_agent: str, ip: str = "2a03:2880:f800:27::") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "query_string": b"",
            "headers": [
                (b"user-agent", user_agent.encode()),
                (b"x-forwarded-for", ip.encode()),
            ],
            "client": ("127.0.0.1", 12345),
        }
    )


def test_maybe_notify_skips_facebook_crawler():
    request = _request(
        "/api/v1/auth/report-login-failure",
        "Mozilla/5.0 (compatible; meta-webindexer/1.1)",
    )
    with patch("app.services.auth_failure_alert.threading.Thread") as thread_mock:
        maybe_notify_auth_login_failure(
            request,
            status_code=400,
            detail="[google_client] Không tải được đăng nhập Google.",
        )
        thread_mock.assert_not_called()


def test_maybe_notify_still_alerts_real_browser():
    request = _request(
        "/api/v1/auth/report-login-failure",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/151.0.0.0 Safari/537.36",
    )
    with patch("app.services.auth_failure_alert.threading.Thread") as thread_mock:
        maybe_notify_auth_login_failure(
            request,
            status_code=400,
            detail="[google_client] Không tải được đăng nhập Google.",
        )
        thread_mock.assert_called_once()
