"""Chi phí quảng cáo — gộp số liệu và che khóa bí mật."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import ad_spend_service as svc


def test_normalize_ids_strip_punctuation():
    assert svc.normalize_customer_id("123-456-7890") == "1234567890"
    assert svc.normalize_ad_account_id("act_998877") == "998877"


def test_micros_to_amount():
    assert svc.micros_to_amount("2500000") == 2.5
    assert svc.micros_to_amount(None) == 0


def test_parse_date_range_rejects_inverted_and_long_span():
    with pytest.raises(ValueError):
        svc.parse_date_range("2026-09-10", "2026-09-01")
    with pytest.raises(ValueError):
        svc.parse_date_range("2024-01-01", "2026-09-01")


def test_flatten_and_aggregate_google_cost():
    rows = svc.flatten_google_results(
        [
            {
                "campaign": {"id": "11", "name": "Brand"},
                "metrics": {"costMicros": "1500000", "impressions": "10", "clicks": "2"},
                "segments": {"date": "2026-09-02"},
                "customer": {"currencyCode": "VND"},
            },
            {
                "campaign": {"id": "11", "name": "Brand"},
                "metrics": {"costMicros": "500000", "impressions": "4", "clicks": "1"},
                "segments": {"date": "2026-09-01"},
                "customer": {"currencyCode": "VND"},
            },
        ]
    )
    out = svc.aggregate_metric_rows(
        rows,
        date_key="date",
        spend_key="spend_micros",
        impressions_key="impressions",
        clicks_key="clicks",
        campaign_id_key="campaign_id",
        campaign_name_key="campaign_name",
        currency_key="currency",
        spend_is_micros=True,
    )
    assert out["currency"] == "VND"
    assert out["spend"] == 2.0
    assert out["clicks"] == 3
    assert out["daily"][0]["date"] == "2026-09-02"
    assert out["campaigns"][0]["name"] == "Brand"
    assert out["campaigns"][0]["spend"] == 2.0


def test_google_oauth_error_message():
    msg = svc.google_error_message(
        {"error": "invalid_grant", "error_description": "Token has been expired or revoked."}
    )
    assert msg == "Không lấy được token Google: Token has been expired or revoked."


def test_settings_view_hides_secrets():
    row = SimpleNamespace(
        google_developer_token="dev-secret",
        google_client_id="client",
        google_client_secret="secret",
        google_refresh_token="refresh-secret",
        google_customer_id="123-456-7890",
        google_login_customer_id="",
        meta_access_token="meta-secret",
        meta_ad_account_id="act_42",
    )
    with patch.object(svc, "_env_map", return_value={key: "" for key in (
        "google_developer_token",
        "google_client_id",
        "google_client_secret",
        "google_refresh_token",
        "google_customer_id",
        "google_login_customer_id",
        "meta_access_token",
        "meta_ad_account_id",
    )}):
        view = svc.settings_to_view(row)
    blob = str(view)
    assert "dev-secret" not in blob
    assert "refresh-secret" not in blob
    assert "meta-secret" not in blob
    assert view["google_configured"] is True
    assert view["facebook_configured"] is True
    assert view["google_customer_id"] == "1234567890"
    assert view["meta_ad_account_id"] == "42"
    assert view["google_credential_source"] == "database"


def test_total_skips_mixed_currency():
    creds = {
        "google_configured": True,
        "facebook_configured": True,
        "google": {},
        "google_login_customer_id": "",
        "meta_access_token": "t",
        "meta_ad_account_id": "1",
    }
    google_rows = [
        {
            "date": "2026-09-01",
            "spend_micros": 1_000_000,
            "impressions": 1,
            "clicks": 1,
            "campaign_id": "g",
            "campaign_name": "G",
            "currency": "USD",
        }
    ]
    meta_rows = [
        {
            "date": "2026-09-01",
            "spend": "1000",
            "impressions": "3",
            "clicks": "1",
            "campaign_id": "f",
            "campaign_name": "F",
            "currency": "VND",
        }
    ]
    with patch.object(svc, "fetch_google_rows", return_value=(google_rows, False)), patch.object(
        svc, "fetch_meta_rows", return_value=(meta_rows, False)
    ):
        svc.clear_report_cache()
        report = svc.build_report(creds, svc.parse_date_range("2026-09-01", "2026-09-01")[0], svc.parse_date_range("2026-09-01", "2026-09-01")[1])
    assert report["total_status"] == "mixed_currency"
    assert report["total_spend"] is None
    assert report["google"]["spend"] == 1.0
    assert report["facebook"]["spend"] == 1000.0


def test_one_platform_error_keeps_the_other():
    creds = {
        "google_configured": True,
        "facebook_configured": True,
        "google": {},
        "google_login_customer_id": "",
        "meta_access_token": "t",
        "meta_ad_account_id": "1",
    }
    meta_rows = [
        {
            "date": "2026-09-01",
            "spend": "10",
            "impressions": "1",
            "clicks": "1",
            "campaign_id": "f",
            "campaign_name": "F",
            "currency": "VND",
        }
    ]
    with patch.object(svc, "fetch_google_rows", side_effect=svc.AdSpendApiError("developer token bị từ chối")), patch.object(
        svc, "fetch_meta_rows", return_value=(meta_rows, False)
    ):
        svc.clear_report_cache()
        start, end = svc.parse_date_range("2026-09-01", "2026-09-02")
        report = svc.build_report(creds, start, end)
    assert report["google"]["ok"] is False
    assert "developer token" in report["google"]["error"]
    assert report["facebook"]["ok"] is True
    assert report["facebook"]["spend"] == 10.0
    assert report["total_status"] == "incomplete"
