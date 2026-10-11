"""Cổng thử ảnh: hạn 7 ngày và nhãn engine."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.services.image_localization_trial import (
    describe_trial_engine,
    list_trials,
    purge_expired_trials,
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


def test_engine_label_follows_the_image_route():
    assert describe_trial_engine("local_only", "processed", {}, "vẽ local")["engine"] == "local"
    assert describe_trial_engine("api", "processed", {"image_engine": "gemini"}, "")["engine"] == "gemini"
    assert describe_trial_engine("openai", "processed", {"gpt_image": True}, "")["engine"] == "gpt"
    assert describe_trial_engine("api", "processed", {}, "poster thường")["engine"] == "local"
    assert describe_trial_engine("api", "deleted", {}, "từ khóa")["engine"] == "deleted"
