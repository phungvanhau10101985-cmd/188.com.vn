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


def test_profit_uses_cny_rate_shipping_and_ads():
    from decimal import Decimal

    from app.services.ad_spend_profit import (
        goods_cny_from_lines,
        goods_cny_matching_listing,
        order_cost_vnd,
        period_profit,
        stored_cny_price,
    )
    from app.services.listing_cny_grid import (
        cny_exchange_multiplier_from_grid,
        estimate_listing_vnd_rounded,
        listing_vnd_to_cny,
    )

    goods = goods_cny_from_lines([(2, "50"), (1, "20¥")])
    assert goods == Decimal("120")
    assert goods_cny_from_lines([(1, "")]) is None
    assert goods_cny_from_lines([]) is None

    rate = Decimal("3580")
    for crawled in (50, 80, 95, 110, 150, 290, 300, 310, 400):
        selling = estimate_listing_vnd_rounded(crawled, cny_exchange_multiplier_from_grid(crawled), float(rate))
        assert selling is not None
        restored = listing_vnd_to_cny(selling, float(rate))
        assert restored is not None
        assert abs(restored - crawled) < 1.5
        back = estimate_listing_vnd_rounded(restored, cny_exchange_multiplier_from_grid(restored), float(rate))
        assert back == selling

    # Bậc >280 dùng hệ số 2.5. Gộp nhầm với 2.6 sẽ đảo 2.880.000 thành ~285 ¥ rồi quy xuôi ra 2.770.000.
    selling_288 = listing_vnd_to_cny(2_880_000, 3880)
    assert selling_288 is not None and selling_288 > 290
    assert (
        estimate_listing_vnd_rounded(selling_288, cny_exchange_multiplier_from_grid(selling_288), 3880)
        == 2_880_000
    )
    assert stored_cny_price("giày tây nam g05") is None
    assert stored_cny_price("146,00") == 146
    inverted_label = goods_cny_matching_listing([(1, 3_410_000, "giày tây nam g05")], Decimal("3880"))
    assert inverted_label is not None and float(inverted_label) > 100

    assert goods_cny_matching_listing([(1, 860000, "80")], rate) == Decimal("80")
    # Đơn có giá bán nhưng dòng không có giá tệ số và không có đơn giá — đảo từ tiền hàng của đơn.
    from_order = goods_cny_matching_listing([(1, 0, "giày tây nam g05", 0)], Decimal("3880"), 1_200_000)
    assert from_order is not None and float(from_order) > 0
    mixed = goods_cny_matching_listing(
        [(1, 860000, "80"), (1, 0, None, 0)],
        rate,
        2_000_000,
    )
    assert mixed is not None and float(mixed) != 80
    inverted_only = goods_cny_matching_listing([(1, selling, None)], rate)
    assert inverted_only is not None
    assert abs(float(inverted_only) - 400) < 1.5

    rate = Decimal("3700")
    cost = order_cost_vnd(
        goods_cny=Decimal("100"),
        ship_china_cny=Decimal("10"),
        ship_border_cny=Decimal("20"),
        ship_hanoi_vnd=Decimal("30000"),
        vnd_per_cny=rate,
    )
    assert cost == Decimal("511000")
    revenue = Decimal("1000000")
    assert period_profit(revenue_vnd=revenue, cost_vnd=cost, ad_spend_vnd=Decimal("200000")) == Decimal("289000")
    assert period_profit(revenue_vnd=revenue, cost_vnd=None, ad_spend_vnd=Decimal("1")) is None
    assert order_cost_vnd(
        goods_cny=None,
        ship_china_cny=Decimal("0"),
        ship_border_cny=Decimal("0"),
        ship_hanoi_vnd=Decimal("0"),
        vnd_per_cny=rate,
    ) is None
