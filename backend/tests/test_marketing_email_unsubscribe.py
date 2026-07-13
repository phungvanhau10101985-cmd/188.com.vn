"""Unit tests — ngừng nhận tin email marketing."""

from unittest.mock import MagicMock, patch

from app.services.marketing_email_unsubscribe import (
    build_unsubscribe_token,
    parse_unsubscribe_token,
    unsubscribe_marketing_email,
)


def test_unsubscribe_token_roundtrip():
    email = "Lan.Example@Mail.COM"
    token = build_unsubscribe_token(email)
    parsed = parse_unsubscribe_token(token)
    assert parsed == "lan.example@mail.com"


def test_unsubscribe_token_rejects_tampered():
    token = build_unsubscribe_token("a@b.com")
    bad = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert parse_unsubscribe_token(bad) is None


@patch("app.services.marketing_email_unsubscribe.crud_newsletter.unsubscribe_email")
@patch("app.services.marketing_email_unsubscribe.crud_marketing_email.is_suppressed", return_value=False)
@patch("app.services.marketing_email_unsubscribe.crud_marketing_email.suppress_email")
@patch("app.services.marketing_email_unsubscribe.crud_marketing_email.mask_email", return_value="l***n@b.com")
def test_unsubscribe_marketing_email_creates_suppression(
    _mask,
    mock_suppress,
    _is_suppressed,
    mock_newsletter_unsub,
):
    db = MagicMock()
    row = MagicMock()
    mock_suppress.return_value = row
    created, masked = unsubscribe_marketing_email(db, "lan@b.com")
    assert created is True
    assert masked == "l***n@b.com"
    mock_suppress.assert_called_once()
    mock_newsletter_unsub.assert_called_once_with(db, "lan@b.com")
