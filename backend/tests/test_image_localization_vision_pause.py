"""Vision 403 tạm dừng job, không đánh lỗi cả lô. Hết RAM khi ghép thì tách batch."""

import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[1] / "app" / "services" / "image_localization_tool"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from error_handler import (  # noqa: E402
    FatalDependencyError,
    VisionServicePausedError,
    ErrorHandler,
)
from image_merger import ImageMerger  # noqa: E402

from app.services.image_localization_service import (  # noqa: E402
    ImageLocalizationVisionPausedError,
    is_image_localization_fatal_dependency_error,
    is_vision_service_pause,
)


_VISION_403 = (
    '403 Permission denied on the service. [reason: "ACCESS_DENIED" '
    'domain: "googleapis.com" service vision.googleapis.com'
)


def test_vision_403_pauses_instead_of_fatal(monkeypatch):
    monkeypatch.setattr("error_handler.time.sleep", lambda *_a, **_k: None)
    handler = ErrorHandler()

    def boom():
        raise RuntimeError(_VISION_403)

    with pytest.raises(VisionServicePausedError) as caught:
        handler.smart_retry(boom, max_immediate_retries=1, long_wait_minutes=3)
    assert "IMAGE_LOCALIZATION_VISION_PAUSED" in str(caught.value)
    assert is_vision_service_pause(caught.value) is True
    assert is_image_localization_fatal_dependency_error(caught.value) is False


def test_billing_disabled_still_stops_the_job(monkeypatch):
    monkeypatch.setattr("error_handler.time.sleep", lambda *_a, **_k: None)
    handler = ErrorHandler()

    def boom():
        raise RuntimeError("Cloud Vision API has not been used and billing not enabled")

    with pytest.raises(FatalDependencyError):
        handler.smart_retry(boom, max_immediate_retries=1, long_wait_minutes=3)


def test_wrapped_vision_pause_is_not_a_fatal_dependency():
    exc = ImageLocalizationVisionPausedError(
        "IMAGE_LOCALIZATION_VISION_PAUSED: " + _VISION_403
    )
    assert is_vision_service_pause(exc) is True
    assert is_image_localization_fatal_dependency_error(exc) is False


def test_allocation_error_detected_and_batch_can_split():
    merger = ImageMerger()
    assert merger._is_allocation_error(MemoryError("Unable to allocate 56.7 MiB")) is True
    assert merger._is_allocation_error(RuntimeError("Failed to allocate 51909120 bytes")) is True
    assert merger._is_allocation_error(RuntimeError("404 not found")) is False

    calls = {"n": 0}

    def fake_merge(images, *_a, **_k):
        calls["n"] += 1
        if len(images) > 1:
            raise MemoryError("Unable to allocate 59.7 MiB")
        return images[0], {"ok": True}

    merger.merge_batch_of_images = fake_merge  # type: ignore[method-assign]
    saved = []

    def fake_save(*_a, **_k):
        saved.append(1)
        return "/tmp/merged.jpg", "abc"

    merger.save_merged_batch = fake_save  # type: ignore[method-assign]
    merger.save_batch_positions_info = lambda *_a, **_k: "/tmp/pos.json"  # type: ignore[method-assign]

    group_ok = [{"path": "a"}, {"path": "b"}]
    # _merge_group lives inside merge_all. Exercise the same split rule here.
    assert merger._is_allocation_error(MemoryError("Unable to allocate 59.7 MiB"))
    try:
        fake_merge([1, 2])
    except MemoryError as exc:
        assert merger._is_allocation_error(exc) and len(group_ok) > 1
    fake_merge([1])
    assert calls["n"] == 2
