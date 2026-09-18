from datetime import date
from io import BytesIO

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.marketing_icon import MarketingIconAsset
from app.services import marketing_icon as svc


def _png_bytes(size: int = 536, color: str = "#ea580c") -> bytes:
    stream = BytesIO()
    Image.new("RGB", (size, size), color).save(stream, format="PNG")
    return stream.getvalue()


def _session():
    engine = create_engine("sqlite:///:memory:")
    MarketingIconAsset.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_icon_prompt_locks_square_sale_and_source_logo():
    prompt = svc.build_icon_prompt(day=9, month=9, discount_percent=6, version=2)
    assert "1:1" in prompt
    assert "SALE 9.9" in prompt
    assert "GIẢM 6%" in prompt
    assert "32x32" in prompt
    assert "180x180" in prompt
    assert "favicon" in prompt.lower()
    assert "web app" in prompt.lower()
    assert "Phiên bản sáng tạo 2" in prompt


def test_image_square_png_crops_and_resizes():
    raw = _png_bytes(size=800)
    out, width, height = svc._image_square_png(raw, size=512)
    assert width == 512
    assert height == 512
    with Image.open(BytesIO(out)) as image:
        assert image.size == (512, 512)
        assert image.format == "PNG"


def test_generate_sale_icon_rejects_non_matching_day():
    db = _session()
    try:
        svc.generate_sale_icon(db, day=10, month=9, discount_percent=6)
    except ValueError as exc:
        assert "ngày trùng tháng" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_generate_deduplicates_and_force_replaces(monkeypatch):
    db = _session()
    deleted_urls: list[str] = []
    monkeypatch.setattr(svc, "default_app_web_icon_url", lambda: "https://cdn.test/logo.png")
    monkeypatch.setattr(svc, "download_source_icon", lambda url: (_png_bytes(), "image/png"))
    monkeypatch.setattr(svc, "gemini_edit_square_icon", lambda *a, **k: _png_bytes(640))
    monkeypatch.setattr(
        svc,
        "_upload_icon",
        lambda data, *, key, version: f"https://cdn.test/{key}/v{version}.png",
    )
    monkeypatch.setattr(svc, "_admin_preview_email", lambda db, row: None)

    def _capture_deleted(urls):
        deleted_urls.extend(list(urls))
        return len(urls)

    monkeypatch.setattr(svc, "delete_bunny_storage_objects_for_urls", _capture_deleted)

    first = svc.generate_sale_icon(db, day=9, month=9, discount_percent=6, notify_admin=False)
    reused = svc.generate_sale_icon(db, day=9, month=9, discount_percent=6, notify_admin=False)
    assert reused.id == first.id
    assert first.aspect_ratio == "1:1"
    assert first.image_width == 512
    assert first.image_height == 512
    assert first.source_image_url == "https://cdn.test/logo.png"
    assert first.campaign_key == "sale-09-09-p6"

    replacement = svc.generate_sale_icon(
        db, day=9, month=9, discount_percent=6, force=True, notify_admin=False
    )
    assert replacement.id != first.id
    assert replacement.is_active is True
    assert replacement.version == 2
    leftover = db.query(MarketingIconAsset).all()
    assert len(leftover) == 1
    assert leftover[0].id == replacement.id
    assert first.image_url in deleted_urls


def test_current_sale_icon_uses_asset_only_when_same_day_month(monkeypatch):
    db = _session()
    row = MarketingIconAsset(
        kind="sale",
        campaign_key="sale-09-09-p6",
        date_key="09-09",
        discount_percent=6,
        image_url="https://cdn.test/sale-icon.png",
        aspect_ratio="1:1",
        prompt="test",
        provider="gemini",
        model="gemini-test",
        status="ready",
        version=1,
        is_active=True,
    )
    db.add(row)
    db.commit()
    monkeypatch.setattr(svc, "default_app_web_icon_url", lambda: "https://cdn.test/logo.png")

    class _State:
        phase = "active"
        event_date = date(2026, 9, 9)
        event_label = "Sale 9/9"
        discount_percent = 6.0

    class _Off:
        phase = None
        event_date = None
        event_label = None
        discount_percent = 0

    import app.services.sale_calendar as sale_svc

    monkeypatch.setattr(sale_svc, "resolve_sale_calendar_state", lambda db, user=None: _State())
    on = svc.current_sale_icon_state(db)
    assert on["is_sale"] is True
    assert on["icon_url"] == "https://cdn.test/sale-icon.png"
    assert on["phase"] == "active"

    monkeypatch.setattr(sale_svc, "resolve_sale_calendar_state", lambda db, user=None: _Off())
    off = svc.current_sale_icon_state(db)
    assert off["is_sale"] is False
    assert off["icon_url"] == "https://cdn.test/logo.png"


def test_ensure_daily_sale_icons_reuses_and_respects_budget(monkeypatch):
    db = _session()
    monkeypatch.setattr(
        svc,
        "matching_same_day_month_event",
        lambda db: (9, 9, 6.0),
    )
    created = {"n": 0}

    def _fake_generate(db, *, day, month, discount_percent, notify_admin=True, force=False):
        created["n"] += 1
        row = MarketingIconAsset(
            kind="sale",
            campaign_key="sale-09-09-p6",
            date_key="09-09",
            discount_percent=discount_percent,
            image_url="https://cdn.test/sale-icon.png",
            aspect_ratio="1:1",
            prompt="test",
            provider="gemini",
            model="gemini-test",
            status="ready",
            version=1,
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    monkeypatch.setattr(svc, "generate_sale_icon", _fake_generate)

    pending = svc.ensure_daily_sale_icons(db, max_create=0, notify_admin=False)
    assert pending["pending"] == 1
    assert created["n"] == 0

    first = svc.ensure_daily_sale_icons(db, max_create=1, notify_admin=False)
    assert first["created"] == 1
    reused = svc.ensure_daily_sale_icons(db, max_create=1, notify_admin=False)
    assert reused["reused"] == 1
    assert created["n"] == 1
