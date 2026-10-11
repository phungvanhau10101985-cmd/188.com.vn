"""Cổng thử ảnh: hạn 7 ngày và nhãn engine."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from types import SimpleNamespace

from app.services.image_localization_trial import (
    describe_trial_engine,
    list_trials,
    normalize_trial_product_kind,
    purge_expired_trials,
    run_trial,
    trial_file_path,
)


def test_expired_trial_folder_is_removed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_LOCALIZATION_RUNTIME_DIR", str(tmp_path))
    old_id = "a" * 32
    fresh_id = "b" * 32
    old = tmp_path / "trials" / old_id
    fresh = tmp_path / "trials" / fresh_id
    old.mkdir(parents=True)
    fresh.mkdir(parents=True)
    created = datetime.now(timezone.utc) - timedelta(days=8)
    (old / "meta.json").write_text(
        '{"id":"%s","created_at":"%s","has_source":true}' % (old_id, created.isoformat()),
        encoding="utf-8",
    )
    (old / "source.jpg").write_bytes(b"old")
    (fresh / "meta.json").write_text(
        '{"id":"%s","created_at":"%s","filename":"now.jpg","status":"processed","engine":"local","has_source":true}'
        % (fresh_id, datetime.now(timezone.utc).isoformat()),
        encoding="utf-8",
    )
    (fresh / "source.jpg").write_bytes(b"new")

    assert purge_expired_trials() == 1
    assert not old.exists()
    assert fresh.exists()
    rows = list_trials()
    assert [row["id"] for row in rows] == [fresh_id]
    assert trial_file_path(fresh_id, "source") == fresh / "source.jpg"
    assert trial_file_path("../" + fresh_id, "source") is None
    assert trial_file_path(fresh_id, "result") is None


def test_trial_product_kind_selects_the_same_branch_as_the_job(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "IMAGE_LOCALIZATION_RUNTIME_DIR", str(tmp_path))
    captured = {}

    class FakePipe:
        def __init__(self, _language, _gemini, **kwargs):
            captured["apparel_sheets"] = kwargs.get("apparel_sheets")
            captured["allows_ai"] = kwargs.get("allows_ai_image_models")
            captured["gemini_mode"] = kwargs.get("gemini_mode")

        def process_single_image(self, _product, _url, _image_bytes, _filename):
            return SimpleNamespace(status="kept", message="giữ", detail={}, consult_ocr_texts=[])

    class FakeGemini:
        def __init__(self, *_args, **_kwargs):
            return None

        def close(self):
            return None

    monkeypatch.setattr("app.services.image_localization_trial.LegacyImageLocalizationPipeline", FakePipe)
    monkeypatch.setattr("app.services.image_localization_trial.GeminiApiImageAdapter", FakeGemini)

    apparel = run_trial(b"sheet", "sheet.png", mode="local_only", product_kind="apparel")
    assert captured == {"apparel_sheets": True, "allows_ai": False, "gemini_mode": "api"}
    assert apparel["product_kind"] == "apparel"
    assert "nhánh thời trang" in apparel["logs"][0]

    other = run_trial(b"poster", "poster.png", mode="local_only", product_kind="other")
    assert captured["apparel_sheets"] is False
    assert other["product_kind"] == "other"
    assert "không phải thời trang" in other["logs"][0]

    try:
        normalize_trial_product_kind("giay")
    except ValueError as exc:
        assert "apparel" in str(exc)
    else:
        raise AssertionError("loại lạ phải bị từ chối")


def test_engine_label_follows_the_image_route():
    assert describe_trial_engine("local_only", "processed", {}, "vẽ local")["engine"] == "local"
    assert describe_trial_engine("api", "processed", {"image_engine": "gemini"}, "")["engine"] == "gemini"
    assert describe_trial_engine("openai", "processed", {"gpt_image": True}, "")["engine"] == "gpt"
    assert describe_trial_engine("api", "processed", {}, "poster thường")["engine"] == "local"
    assert describe_trial_engine("api", "deleted", {}, "từ khóa")["engine"] == "deleted"
