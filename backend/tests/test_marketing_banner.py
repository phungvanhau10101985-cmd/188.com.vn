from datetime import date
from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.marketing_banner import MarketingBannerAsset
from app.models.user import User
from app.services import marketing_banner as svc


def _png_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (2100, 900), "#ea580c").save(stream, format="PNG")
    return stream.getvalue()


def _session(*, with_users: bool = False):
    engine = create_engine("sqlite:///:memory:")
    if with_users:
        User.__table__.create(engine)
    MarketingBannerAsset.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_campaign_key_reuses_month_day_and_changes_with_real_discount():
    assert svc.campaign_key("sale", 9, 9, 6) == "sale-09-09-p6"
    assert svc.campaign_key("sale", 9, 9, 8) == "sale-09-09-p8"
    assert svc.campaign_key("birthday", 1, 2, 10) == "birthday-02-01-p10"


def test_prompts_lock_date_percent_and_single_21_9_image():
    sale = svc.build_banner_prompt(kind="sale", day=9, month=9, discount_percent=6)
    birthday = svc.build_banner_prompt(
        kind="birthday", day=5, month=9, discount_percent=10
    )
    assert "21:9" in sale
    assert "SALE 9.9 - GIẢM 6%" in sale
    assert "MỪNG SINH NHẬT 05/09 - TẶNG 10%" in birthday
    assert "Không ghi tên khách" in birthday


def test_generate_deduplicates_and_force_keeps_version_history(monkeypatch):
    db = _session()
    raw = _png_bytes()
    monkeypatch.setattr(svc, "gemini_generate_image_from_text", lambda *a, **k: raw)
    monkeypatch.setattr(
        svc,
        "_upload_banner",
        lambda data, *, kind, key, version: f"https://cdn.test/{key}/v{version}.png",
    )
    monkeypatch.setattr(svc, "_admin_preview_email", lambda db, row: None)

    first = svc.generate_banner(
        db,
        kind="sale",
        day=9,
        month=9,
        discount_percent=6,
    )
    reused = svc.generate_banner(
        db,
        kind="sale",
        day=9,
        month=9,
        discount_percent=6,
    )
    replacement = svc.generate_banner(
        db,
        kind="sale",
        day=9,
        month=9,
        discount_percent=6,
        force=True,
    )

    assert reused.id == first.id
    assert replacement.version == 2
    assert replacement.is_active is True
    db.refresh(first)
    assert first.is_active is False
    assert replacement.image_width == 2100
    assert replacement.image_height == 900


def test_birthday_targets_only_dates_with_active_customers():
    db = _session(with_users=True)
    db.add_all(
        [
            User(email="active@example.com", date_of_birth=date(1990, 9, 12), is_active=True),
            User(email="inactive@example.com", date_of_birth=date(1991, 9, 13), is_active=False),
            User(email="later@example.com", date_of_birth=date(1992, 9, 20), is_active=True),
        ]
    )
    db.commit()

    targets = svc._birthday_dates_with_customers(db, date(2026, 9, 5))
    assert targets == [date(2026, 9, 12)]


def test_february_29_customer_uses_february_28_in_non_leap_year():
    db = _session(with_users=True)
    db.add(
        User(
            email="leap@example.com",
            date_of_birth=date(1992, 2, 29),
            is_active=True,
        )
    )
    db.commit()

    targets = svc._birthday_dates_with_customers(db, date(2026, 2, 21))
    assert targets == [date(2026, 2, 28)]
