"""Test chia batch merge theo MERGE_MAX_PIXELS."""

import sys
from pathlib import Path

import numpy as np

_TOOL = Path(__file__).resolve().parents[1] / "app" / "services" / "image_localization_tool"
if str(_TOOL) not in sys.path:
    sys.path.insert(0, str(_TOOL))

from image_merger import ImageMerger  # noqa: E402


def _fake_img(w: int, h: int) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_plan_respects_70mp_for_tall_product_gallery():
    merger = ImageMerger()
    merger.batch_size = 10
    merger.merge_max_pixels = 70_000_000

    # Kích thước thật của SP A718502906789a188P6981 (13 ảnh alicdn)
    heights = [960, 960, 8536, 960, 960, 8492, 960, 960, 8324, 960, 960, 960, 8688]
    images = [_fake_img(2480, h) for h in heights]

    plans = merger.plan_merge_batch_indices(images)
    assert len(plans) > 1, "13 ảnh cao phải tách >1 batch khi giới hạn 70MP"

    for batch_indices in plans:
        batch_imgs = [images[i] for i in batch_indices]
        px = merger.estimate_merged_pixel_count(batch_imgs)
        assert px <= 70_000_000, f"batch {batch_indices} = {px/1e6:.1f} MP"
        assert len(batch_indices) <= 10

    covered = sorted(i for b in plans for i in b)
    assert covered == list(range(len(images)))


def test_old_fixed_10_batch_would_exceed_70mp():
    merger = ImageMerger()
    heights = [960, 960, 8536, 960, 960, 8492, 960, 960, 8324, 960]
    images = [_fake_img(2480, h) for h in heights]
    px = merger.estimate_merged_pixel_count(images)
    assert px > 70_000_000
