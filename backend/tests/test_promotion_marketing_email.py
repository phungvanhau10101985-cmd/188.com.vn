"""Unit tests — email marketing tự động (giỏ bỏ dở / nhớ bạn)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import promotion_grants as grant_svc


def _user(**kwargs):
    base = dict(id=1, email="", full_name="Lan")
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_valid_email():
    assert grant_svc._valid_email("a@b.com") == "a@b.com"
    assert grant_svc._valid_email("  a@b.com  ") == "a@b.com"
    assert grant_svc._valid_email("not-an-email") is None
    assert grant_svc._valid_email("") is None


def test_resolve_user_email_from_account():
    user = _user(email="lan@example.com")
    db = MagicMock()
    assert grant_svc._resolve_user_email(db, user) == "lan@example.com"
    db.query.assert_not_called()


def test_resolve_user_email_from_order_when_account_empty():
    user = _user(email="")
    order = SimpleNamespace(customer_email="order@example.com")
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = [order]
    db = MagicMock()
    db.query.return_value = q
    assert grant_svc._resolve_user_email(db, user) == "order@example.com"


@patch.object(grant_svc.settings, "COMEBACK_EMAIL_ENABLED", True)
@patch.object(grant_svc.settings, "PROMO_EMAIL_COOLDOWN_HOURS", 24)
@patch.object(grant_svc, "_has_recent_promo_grant", return_value=True)
@patch.object(grant_svc, "_resolve_user_email", return_value="lan@example.com")
def test_maybe_send_comeback_email_skips_when_cart_abandon_recent(
    _mock_email,
    _mock_recent,
):
    db = MagicMock()
    user = _user()
    promo = SimpleNamespace(
        code="COMEBACK10",
        discount_percent=10,
        max_discount_amount=100000,
    )
    assert grant_svc._maybe_send_comeback_email(
        db,
        user=user,
        promotion=promo,
        valid_days=5,
    ) is False


@patch.object(grant_svc.settings, "COMEBACK_EMAIL_ENABLED", True)
@patch.object(grant_svc.settings, "PROMO_EMAIL_COOLDOWN_HOURS", 24)
@patch.object(grant_svc, "_has_recent_promo_grant", return_value=False)
@patch.object(grant_svc, "_resolve_user_email", return_value="lan@example.com")
@patch("app.services.email_service.send_comeback_email")
def test_maybe_send_comeback_email_sends(
    mock_send,
    _mock_email,
    _mock_recent,
):
    db = MagicMock()
    user = _user(full_name="Lan")
    promo = SimpleNamespace(
        code="COMEBACK10",
        discount_percent=10,
        max_discount_amount=100000,
    )
    assert grant_svc._maybe_send_comeback_email(
        db,
        user=user,
        promotion=promo,
        valid_days=5,
    ) is True
    mock_send.assert_called_once()
    assert mock_send.call_args.args[0] == "lan@example.com"


def test_grant_voucher_skips_when_user_already_used_code():
    promo = SimpleNamespace(id=9, is_active=True, code="CARTSAVE188", per_user_limit=1)
    db = MagicMock()
    with (
        patch("app.crud.promotion.get_promotion_by_code", return_value=promo),
        patch("app.crud.promotion.promotion_per_user_exhausted", return_value=True),
    ):
        result = grant_svc.grant_voucher(
            db,
            user_id=1,
            promo_code="CARTSAVE188",
            source="cart_abandon",
            notify=False,
        )
    assert result is None
    db.add.assert_not_called()


def test_retire_exhausted_grants_hides_used_cart_code():
    promo = SimpleNamespace(id=9, code="CARTSAVE188", per_user_limit=1)
    grant = SimpleNamespace(promotion=promo, status="active", used_at=None)
    query = MagicMock()
    query.options.return_value = query
    query.filter.return_value = query
    query.all.return_value = [grant]
    db = MagicMock()
    db.query.return_value = query
    with patch("app.crud.promotion.promotion_per_user_exhausted", return_value=True):
        count = grant_svc.retire_exhausted_grants(db, user_id=1)
    assert count == 1
    assert grant.status == "used"
    assert grant.used_at is not None
    db.commit.assert_called_once()
