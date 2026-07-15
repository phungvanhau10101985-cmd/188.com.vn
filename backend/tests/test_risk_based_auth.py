from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Response
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api.endpoints import auth_email
from app.core.config import settings
from app.core.security import (
    ADMIN_DESTRUCTIVE_STEP_UP_PURPOSE,
    create_admin_step_up_token,
    create_admin_token,
    create_step_up_token,
    verify_recent_admin_auth,
    verify_recent_user_auth,
)
from app.models.auth_challenge import AuthActionChallenge
from app.models.email_login_challenge import EmailLoginChallenge
from app.schemas.auth_email import EmailAuthVerifyOtpBody
from app.services.auth_challenge import consume_challenge, issue_challenge


@pytest.fixture(autouse=True)
def ensure_test_secret(monkeypatch):
    monkeypatch.setattr(settings, "SECRET_KEY", "test-only-secret-key-with-sufficient-entropy")


def _request_with_cookie(name: str, value: str) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [(b"cookie", f"{name}={value}".encode())],
    }
    return Request(scope)


def test_email_request_no_longer_has_prior_challenge_auto_login():
    assert not hasattr(auth_email, "_auto_login_if_prior_email_challenge_consumed")
    assert not hasattr(auth_email, "_had_consumed_email_challenge")


def test_step_up_token_is_user_and_purpose_bound():
    user = SimpleNamespace(id=42)
    token = create_step_up_token(42, "sensitive_action")
    request = _request_with_cookie(settings.STEP_UP_COOKIE_NAME, token)

    verify_recent_user_auth(request, user, "sensitive_action")

    with pytest.raises(HTTPException) as exc:
        verify_recent_user_auth(request, user, "admin_elevation")
    assert exc.value.status_code == 428


def test_admin_step_up_token_is_admin_bound():
    admin = SimpleNamespace(id=7)
    token = create_admin_step_up_token(7, ADMIN_DESTRUCTIVE_STEP_UP_PURPOSE)
    request = _request_with_cookie(settings.ADMIN_STEP_UP_COOKIE_NAME, token)
    verify_recent_admin_auth(request, admin, ADMIN_DESTRUCTIVE_STEP_UP_PURPOSE)

    with pytest.raises(HTTPException) as exc:
        verify_recent_admin_auth(request, SimpleNamespace(id=8), ADMIN_DESTRUCTIVE_STEP_UP_PURPOSE)
    assert exc.value.status_code == 428


def test_admin_token_uses_admin_specific_ttl():
    before = datetime.now(timezone.utc).timestamp()
    token = create_admin_token(7, amr=["password", "otp"])
    payload = jwt.get_unverified_claims(token)
    ttl = float(payload["exp"]) - before
    assert payload["amr"] == ["password", "otp"]
    assert int(settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES) * 60 - 5 <= ttl
    assert ttl <= int(settings.ADMIN_ACCESS_TOKEN_EXPIRE_MINUTES) * 60 + 5


def test_action_challenge_is_single_use_and_attempt_limited():
    engine = create_engine("sqlite:///:memory:")
    AuthActionChallenge.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        with patch("app.services.auth_challenge.send_security_otp_email"):
            row = issue_challenge(
                db,
                subject_type="user",
                subject_id=9,
                purpose="sensitive_action",
                email="owner@example.com",
            )
        assert len(row.public_id) >= 32
        assert not row.public_id.isdigit()
        with pytest.raises(ValueError, match="không đúng"):
            consume_challenge(
                db,
                challenge_id=row.public_id,
                subject_type="user",
                subject_id=9,
                purpose="sensitive_action",
                otp="000000",
            )

        # Set the known hash directly so the test never needs access to an emailed OTP.
        from app.services.auth_challenge import hash_secret

        row.otp_hash = hash_secret("123456")
        db.commit()
        consume_challenge(
            db,
            challenge_id=row.public_id,
            subject_type="user",
            subject_id=9,
            purpose="sensitive_action",
            otp="123456",
        )
        with pytest.raises(ValueError, match="hết hạn"):
            consume_challenge(
                db,
                challenge_id=row.public_id,
                subject_type="user",
                subject_id=9,
                purpose="sensitive_action",
                otp="123456",
            )
    finally:
        db.close()


def test_email_login_otp_locks_after_failed_attempts():
    engine = create_engine("sqlite:///:memory:")
    EmailLoginChallenge.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = EmailLoginChallenge(
            email_normalized="owner@example.com",
            otp_hash=auth_email._hash_otp("123456"),
            magic_token_hash=auth_email._hash_magic("unused"),
            expires_at=datetime.now(timezone.utc).replace(microsecond=0),
            attempts=0,
        )
        # Keep the challenge valid beyond now.
        from datetime import timedelta

        row.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.add(row)
        db.commit()
        body = EmailAuthVerifyOtpBody(
            email="owner@example.com",
            otp="000000",
            remember_device=False,
        )
        for _ in range(int(settings.OTP_MAX_RETRIES)):
            with pytest.raises(HTTPException) as exc:
                auth_email.email_auth_verify_otp(body, Response(), BackgroundTasks(), db)
            assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            auth_email.email_auth_verify_otp(body, Response(), BackgroundTasks(), db)
        assert exc.value.status_code == 429
    finally:
        db.close()
