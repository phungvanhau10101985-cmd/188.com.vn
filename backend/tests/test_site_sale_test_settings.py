"""Site sale test admin — timezone giống CMSN (PostgreSQL VN)."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services.admin_feature_test_site_sale import site_sale_test_settings_payload


def _admin(email: str = "admin@test.com") -> SimpleNamespace:
    return SimpleNamespace(email=email, linked_user_id=None)


def test_payload_enabled_when_expires_future_utc_aware():
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        test_email="shopper@test.com",
        site_sale_test_enabled=True,
        site_sale_test_expires_at=now + timedelta(minutes=10),
        site_sale_test_phase="active",
    )
    out = site_sale_test_settings_payload(_admin(), row)
    assert out["site_sale_test_enabled"] is True
    assert out["site_sale_test_phase"] == "active"


def test_payload_enabled_when_expires_future_naive_vn_wall_clock():
    """psycopg2 trên server VN thường trả naive theo giờ địa phương."""
    vn = timezone(timedelta(hours=7))
    now_vn = datetime.now(vn)
    row = SimpleNamespace(
        test_email="shopper@test.com",
        site_sale_test_enabled=True,
        site_sale_test_expires_at=(now_vn + timedelta(minutes=10)).replace(tzinfo=None),
        site_sale_test_phase="active",
    )
    out = site_sale_test_settings_payload(_admin(), row)
    assert out["site_sale_test_enabled"] is True


def test_payload_disabled_when_expires_past_naive_vn():
    vn = timezone(timedelta(hours=7))
    past_vn = (datetime.now(vn) - timedelta(minutes=5)).replace(tzinfo=None)
    row = SimpleNamespace(
        test_email="shopper@test.com",
        site_sale_test_enabled=True,
        site_sale_test_expires_at=past_vn,
        site_sale_test_phase="active",
    )
    out = site_sale_test_settings_payload(_admin(), row)
    assert out["site_sale_test_enabled"] is False
