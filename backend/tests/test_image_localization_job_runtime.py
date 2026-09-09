"""Helpers for image localization job resume / stall / worker identity."""

from datetime import datetime, timedelta, timezone

from app.services.image_localization_job_runtime import (
    cmdline_looks_like_imgloc_worker,
    job_updated_at_is_stalled,
    should_abort_auto_resume,
    worker_process_title,
)


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
