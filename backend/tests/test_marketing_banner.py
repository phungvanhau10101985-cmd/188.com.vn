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
    assert svc.campaign_key("warehouse", 0, 0, 30) == "warehouse-p30"
    assert svc.campaign_key("warehouse", 0, 0, 30.0) == "warehouse-p30"
    assert svc.campaign_key("warehouse", 0, 0, 60) == "warehouse-p60"


def test_prompts_lock_date_percent_and_single_21_9_image():
    sale = svc.build_banner_prompt(
        kind="sale",
        day=9,
        month=9,
        discount_percent=6,
        copy={
            "verse": "Deal vui đúng hẹn - chọn liền hôm nay",
            "cta": "SĂN DEAL NGAY",
            "art_direction": "editorial tối giản",
        },
    )
    birthday = svc.build_banner_prompt(
        kind="birthday", day=5, month=9, discount_percent=10
    )
    assert "21:9" in sale
    assert "SALE 9.9 - GIẢM 6%" in sale
    assert "Deal vui đúng hẹn - chọn liền hôm nay" in sale
    assert "MỪNG SINH NHẬT 05/09 - TẶNG 10%" in birthday
    assert "Không ghi tên khách" in birthday
    warehouse = svc.build_banner_prompt(
        kind="warehouse",
        day=0,
        month=0,
        discount_percent=30,
        copy={
            "verse": "Hàng kho giá sốc - chốt liền hôm nay",
            "cta": "SĂN HÀNG KHO",
            "art_direction": "lửa nóng cháy hàng",
        },
    )
    assert "SALE KHO - GIẢM 30%" in warehouse
    assert "Hàng kho giá sốc - chốt liền hôm nay" in warehouse
    assert "SĂN HÀNG KHO" in warehouse


def test_generate_deduplicates_and_force_keeps_version_history(monkeypatch):
    db = _session()
    raw = _png_bytes()
    monkeypatch.setattr(svc, "gemini_generate_image_from_text", lambda *a, **k: raw)
    monkeypatch.setattr(
        svc,
        "generate_dynamic_copy",
        lambda **kwargs: {
            "verse": f"Câu sáng tạo phiên bản {kwargs['version']}",
            "cta": "MUA NGAY",
            "art_direction": f"phong cách {kwargs['version']}",
        },
    )
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
    assert first.prompt != replacement.prompt
    assert "Câu sáng tạo phiên bản 2" in replacement.prompt
    assert replacement.is_active is True
    db.refresh(first)
    assert first.is_active is False
    assert replacement.image_width == 2100
    assert replacement.image_height == 900


def test_ensure_daily_banners_creates_at_most_one_and_reports_pending(monkeypatch):
    db = _session(with_users=True)
    db.add_all(
        [
            User(email="a@example.com", date_of_birth=date(1990, 9, 7), is_active=True),
            User(email="b@example.com", date_of_birth=date(1991, 9, 8), is_active=True),
            User(email="c@example.com", date_of_birth=date(1992, 9, 9), is_active=True),
        ]
    )
    db.commit()
    raw = _png_bytes()
    monkeypatch.setattr(svc, "gemini_generate_image_from_text", lambda *a, **k: raw)
    monkeypatch.setattr(
        svc,
        "generate_dynamic_copy",
        lambda **kwargs: {
            "verse": "Tuổi mới an vui - quà riêng trao tay",
            "cta": "NHẬN QUÀ CỦA TÔI",
            "art_direction": "ấm áp sang trọng",
        },
    )
    monkeypatch.setattr(
        svc,
        "_upload_banner",
        lambda data, *, kind, key, version: f"https://cdn.test/{key}/v{version}.png",
    )
    monkeypatch.setattr(svc, "_admin_preview_email", lambda db, row: None)
    monkeypatch.setattr(svc, "list_upcoming_events", lambda db, limit=12: [])

    import app.services.warehouse_clearance as warehouse_svc

    monkeypatch.setattr(
        warehouse_svc,
        "get_warehouse_clearance_settings",
        lambda db: (False, 0),
    )

    first = svc.ensure_daily_banners(
        db, today=date(2026, 9, 7), max_create=1, notify_admin=False
    )
    assert first["birthday"]["created"] == 1
    assert first["birthday"]["reused"] == 0
    assert first["birthday"]["pending"] == 2
    assert first["birthday"]["failed"] == 0

    second = svc.ensure_daily_banners(
        db, today=date(2026, 9, 7), max_create=1, notify_admin=False
    )
    assert second["birthday"]["created"] == 1
    assert second["birthday"]["reused"] == 1
    assert second["birthday"]["pending"] == 1

    rest = svc.ensure_daily_banners(
        db, today=date(2026, 9, 7), max_create=8, notify_admin=False
    )
    assert rest["birthday"]["created"] == 1
    assert rest["birthday"]["reused"] == 2
    assert rest["birthday"]["pending"] == 0
    ready = (
        db.query(MarketingBannerAsset)
        .filter(
            MarketingBannerAsset.kind == "birthday",
            MarketingBannerAsset.status == "ready",
        )
        .count()
    )
    assert ready == 3


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


def test_birthday_test_prefers_existing_asset_inside_next_seven_days():
    db = _session()
    row = MarketingBannerAsset(
        kind="birthday",
        campaign_key=svc.campaign_key("birthday", 9, 9, 10),
        date_key="09-09",
        discount_percent=10,
        image_url="https://cdn.test/birthday-09-09.png",
        aspect_ratio="21:9",
        prompt="test",
        provider="gemini",
        model="gemini-test",
        status="ready",
        version=1,
        is_active=True,
    )
    db.add(row)
    db.commit()

    found, event_date = svc.find_test_birthday_asset(db, today=date(2026, 9, 5))
    assert found is not None
    assert found.id == row.id
    assert event_date == date(2026, 9, 9)


def test_warehouse_banner_reuses_percent_and_creates_new_percent(monkeypatch):
    db = _session()
    raw = _png_bytes()
    monkeypatch.setattr(svc, "gemini_generate_image_from_text", lambda *a, **k: raw)
    monkeypatch.setattr(
        svc,
        "generate_dynamic_copy",
        lambda **kwargs: {
            "verse": "Hàng kho giá sốc - chốt liền hôm nay",
            "cta": "SĂN HÀNG KHO",
            "art_direction": "lửa nóng cháy hàng",
        },
    )
    monkeypatch.setattr(
        svc,
        "_upload_banner",
        lambda data, *, kind, key, version: f"https://cdn.test/{key}/v{version}.png",
    )
    monkeypatch.setattr(svc, "_admin_preview_email", lambda db, row: None)

    first = svc.ensure_warehouse_banner(db, discount_percent=30)
    reused = svc.ensure_warehouse_banner(db, discount_percent=30)
    sixty = svc.ensure_warehouse_banner(db, discount_percent=60)
    hidden = svc.ensure_warehouse_banner(db, discount_percent=0)

    assert first is not None
    assert reused is not None
    assert sixty is not None
    assert reused.id == first.id
    assert sixty.id != first.id
    assert first.campaign_key == "warehouse-p30"
    assert sixty.campaign_key == "warehouse-p60"
    assert first.date_key == "kho"
    assert "SALE KHO - GIẢM 30%" in first.prompt
    assert "SALE KHO - GIẢM 60%" in sixty.prompt
    assert hidden is None
    assert svc.find_active_warehouse_asset(db, 30).id == first.id
