"""Tests for image localization temp file cleanup."""
from pathlib import Path

from app.services.image_localization_temp_cleanup import (
    cleanup_merge_batch_files,
    paths_from_merge_batches,
)


def test_paths_from_merge_batches_collects_all_referenced_files(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    temp_images = runtime / "temp_images"
    temp_images.mkdir(parents=True)
    orig = temp_images / "orig_1_test.jpg"
    merged = temp_images / "merged_batch1_abc.jpg"
    positions = temp_images / "positions_batch1_abc.json"
    for p in (orig, merged, positions):
        p.write_bytes(b"x")

    monkeypatch.setattr(
        "app.services.image_localization_temp_cleanup.settings.IMAGE_LOCALIZATION_RUNTIME_DIR",
        str(runtime),
    )

    batches = {
        "batches": [
            {
                "merged_path": str(merged),
                "positions_file": str(positions),
            }
        ],
        "column_mapping": {
            "https://example.com/a.jpg": {"original_path": str(orig), "status": "PROCESSED"},
        },
    }
    assert paths_from_merge_batches(batches) == {str(orig), str(merged), str(positions)}
    assert cleanup_merge_batch_files(batches) == 3
    assert not orig.exists()
    assert not merged.exists()
    assert not positions.exists()


def test_cleanup_skips_paths_outside_runtime(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    (runtime / "temp_images").mkdir(parents=True)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x")

    monkeypatch.setattr(
        "app.services.image_localization_temp_cleanup.settings.IMAGE_LOCALIZATION_RUNTIME_DIR",
        str(runtime),
    )

    batches = {
        "batches": [],
        "column_mapping": {"https://x/y.jpg": {"original_path": str(outside)}},
    }
    assert cleanup_merge_batch_files(batches) == 0
    assert outside.exists()
