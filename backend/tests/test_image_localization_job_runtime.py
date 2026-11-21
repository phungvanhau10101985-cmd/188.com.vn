"""Helpers for image localization job resume / stall / worker identity."""

from datetime import datetime, timedelta, timezone

from types import SimpleNamespace

from app.services.image_localization_job_runtime import (
    cmdline_looks_like_imgloc_worker,
    job_awaits_product_selection,
    job_updated_at_is_stalled,
    should_abort_auto_resume,
    vision_pause_ready,
    wait_for_imgloc_memory,
    worker_process_title,
)


def test_new_job_with_empty_queue_must_select_products():
    fresh = SimpleNamespace(queue_product_ids=[], processed_product_ids=[], started_at=None)
    assert job_awaits_product_selection(fresh) is True
    started = SimpleNamespace(
        queue_product_ids=["p1"],
        processed_product_ids=[],
        started_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )
    assert job_awaits_product_selection(started) is False
    resumed_empty = SimpleNamespace(
        queue_product_ids=[],
        processed_product_ids=["p1"],
        started_at=datetime(2026, 11, 20, tzinfo=timezone.utc),
    )
    assert job_awaits_product_selection(resumed_empty) is False


def test_wait_for_memory_continues_when_ram_is_enough(monkeypatch):
    monkeypatch.setattr(
        "app.services.image_localization_job_runtime.memory_pressure_blocks_imgloc",
        lambda: (False, "MemAvailable=2200MB"),
    )
    monkeypatch.setattr(
        "app.services.image_localization_job_runtime.release_imgloc_heap",
        lambda: None,
    )
    assert wait_for_imgloc_memory() is True


def test_wait_for_memory_stops_when_cancelled(monkeypatch):
    monkeypatch.setattr(
        "app.services.image_localization_job_runtime.memory_pressure_blocks_imgloc",
        lambda: (True, "MemAvailable=1500MB < min=2000MB"),
    )
    monkeypatch.setattr(
        "app.services.image_localization_job_runtime.release_imgloc_heap",
        lambda: None,
    )
    monkeypatch.setattr(
        "app.services.image_localization_job_runtime.time.sleep",
        lambda _seconds: None,
    )
    assert wait_for_imgloc_memory(lambda: True) is False


def test_worker_process_title_fits_prctl():
    assert worker_process_title("e32ad16cd0334fdc86669c518baa59c6") == "imgloc-e32ad16c"
    assert len(worker_process_title("e32ad16cd0334fdc86669c518baa59c6")) == 15


def test_cmdline_matches_spawn_but_not_resource_tracker():
    spawn = "python -c from multiprocessing.spawn import spawn_main; spawn_main(tracker_fd=38, pipe_handle=40)"
    tracker = "python -c from multiprocessing.resource_tracker import main;main(12)"
    assert cmdline_looks_like_imgloc_worker("python", spawn) is True
    assert cmdline_looks_like_imgloc_worker("python", tracker) is False
    assert cmdline_looks_like_imgloc_worker("imgloc-e32ad16c", spawn) is True
    assert cmdline_looks_like_imgloc_worker("imgloc-e32ad16c", "") is True


def test_vision_pause_waits_before_the_next_attempt():
    stamped = datetime(2026, 11, 21, 2, 34, tzinfo=timezone.utc)
    too_soon = stamped + timedelta(minutes=5)
    ready = stamped + timedelta(minutes=10)
    assert vision_pause_ready(stamped, now=too_soon) is False
    assert vision_pause_ready(stamped, now=ready) is True
    assert vision_pause_ready(None) is True


def test_abort_auto_resume_only_after_consecutive_empty_resumes():
    assert should_abort_auto_resume(resume_count=5, max_resume=6) is False
    assert should_abort_auto_resume(resume_count=6, max_resume=6) is True
    assert should_abort_auto_resume(resume_count=20, max_resume=0) is False


def test_stall_detection_uses_updated_at():
    now = datetime(2026, 9, 9, 8, 40, tzinfo=timezone.utc)
    fresh = now - timedelta(seconds=30)
    stale = now - timedelta(seconds=1200)
    assert job_updated_at_is_stalled(fresh, stall_seconds=1200, now=now) is False
    assert job_updated_at_is_stalled(stale, stall_seconds=1200, now=now) is True
    assert job_updated_at_is_stalled(None, stall_seconds=1200, now=now) is False
    naive = datetime(2026, 9, 9, 8, 0, 0)
    assert job_updated_at_is_stalled(naive, stall_seconds=1200, now=now) is True
