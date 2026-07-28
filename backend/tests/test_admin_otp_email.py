from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.admin_otp_email import mask_email_for_display, resolve_admin_otp_recipient_email


def test_resolve_admin_otp_prefers_linked_user_email():
    admin = SimpleNamespace(
        id=2,
        email="linked-admin-2@188.com.vn",
        linked_user_id=26628,
    )
    user = SimpleNamespace(email="phungvanhau10101985@gmail.com")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = user

    assert resolve_admin_otp_recipient_email(db, admin) == "phungvanhau10101985@gmail.com"


def test_resolve_admin_otp_uses_admin_email_when_not_linked():
    admin = SimpleNamespace(
        id=1,
        email="phungvanhau10101985@gmail.com",
        linked_user_id=None,
    )
    db = MagicMock()

    assert resolve_admin_otp_recipient_email(db, admin) == "phungvanhau10101985@gmail.com"


def test_mask_email_for_display():
    assert mask_email_for_display("phungvanhau10101985@gmail.com") == "p***5@gmail.com"
