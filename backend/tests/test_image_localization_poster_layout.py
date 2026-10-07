"""Poster điểm nổi bật không được tô trắng lên ảnh sản phẩm."""
import sys
from pathlib import Path

import numpy as np

TOOL_DIR = Path(__file__).resolve().parents[1] / "app" / "services" / "image_localization_tool"
if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

from image_processor import ImageProcessor  # noqa: E402


def _processor() -> ImageProcessor:
    return ImageProcessor()


def _leather(h: int, w: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = np.zeros((h, w, 3), np.uint8)
    yy = np.linspace(70, 190, h, dtype=np.float32)[:, None]
    xx = np.linspace(40, 120, w, dtype=np.float32)[None, :]
    base[:, :, 0] = np.clip(xx * 0.55, 0, 255)
    base[:, :, 1] = np.clip(yy * 0.55, 0, 255)
    base[:, :, 2] = np.clip(yy, 0, 255)
    noise = rng.integers(-18, 18, (h, w, 3), dtype=np.int16)
    return np.clip(base.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_feature_poster_keeps_product_photos():
    img = np.full((1200, 800, 3), 255, np.uint8)
    img[200:480, 40:760] = _leather(280, 720, 1)
    img[680:860, 30:250] = _leather(180, 220, 2)
    img[680:860, 290:510] = _leather(180, 220, 3)
    img[680:860, 550:770] = _leather(180, 220, 4)
    img[900:1080, 20:780] = _leather(180, 760, 5)
    photos = [
        (200, 480, 40, 760),
        (680, 860, 30, 250),
        (680, 860, 290, 510),
        (680, 860, 550, 770),
        (900, 1080, 20, 780),
    ]
    before = [img[y1:y2, x1:x2].copy() for y1, y2, x1, x2 in photos]

    blocks = []
    for col, x in enumerate((30, 290, 550)):
        blocks.append((f"Tieu de {col}", (x, 520, x + 200, 558)))
        blocks.append((f"Mo ta ngan {col} da that", (x, 568, x + 200, 608)))
        blocks.append((f"Dong chu thu hai cot {col}", (x, 616, x + 200, 656)))
    blocks.extend(
        [
            ("Chat lieu ben", (24, 24, 150, 78)),
            ("Tho may", (190, 24, 330, 78)),
            ("Kim khi", (370, 24, 520, 78)),
            ("Lot trong", (560, 24, 740, 78)),
            ("Kim loai cao cap", (30, 1100, 280, 1140)),
            ("Ba lo phong cach co dien", (30, 1150, 640, 1188)),
        ]
    )

    out = _processor().process_image_with_text(img, blocks, [])

    for (y1, y2, x1, x2), original in zip(photos, before):
        delta = np.abs(out[y1:y2, x1:x2].astype(np.int16) - original.astype(np.int16)).mean()
        assert delta < 8, f"anh san pham bi to trang tai {(x1, y1)} delta={delta:.1f}"

    caption = out[520:656, 30:230]
    assert int(caption.min()) < 40


def test_size_chart_still_uses_table_cells():
    img = np.full((260, 520, 3), 180, np.uint8)
    blocks = []
    for row in range(5):
        y1 = 20 + row * 40
        for col, label in enumerate(("Nguc", "Eo", "Vai", "Dai ao")):
            x1 = 16 + col * 126
            blocks.append((f"{label} {row + 1}", (x1, y1, x1 + 86, y1 + 28)))

    proc = _processor()
    assert proc._layout_table_blocks(blocks, [], 520, 260) is not None
    out = proc.process_image_with_text(img, blocks, [])
    # Khoảng giữa hai cột cùng hàng phải được tô nền bảng, không giữ xám 180.
    assert int(out[32, 112, 0]) >= 245
    assert int(out[28:44, 20:90].min()) < 40


def test_photo_bbox_is_not_filled_white():
    photo = _leather(160, 220, 7)
    img = np.full((200, 260, 3), 255, np.uint8)
    img[20:180, 20:240] = photo
    out = _processor().process_image_with_text(img, [("chu de len anh", (20, 20, 240, 180))], [])
    assert np.array_equal(out[20:180, 20:240], photo)


def test_brand_logo_skips_corner_that_already_has_an_icon(monkeypatch):
    from app.services import image_localization_service as svc

    logo = np.zeros((36, 72, 4), np.uint8)
    logo[:, :, 2] = 255
    logo[:, :, 3] = 255
    monkeypatch.setattr(svc, "_get_brand_logo_bgra_template", lambda: logo)

    flat = np.zeros((220, 420, 3), np.uint8)
    stamped = svc.apply_brand_logo_top_right_bgr(flat.copy())
    assert int(stamped[12, 360, 2]) > 200

    busy = np.zeros((220, 420, 3), np.uint8)
    busy[6:70, 300:410] = 255
    busy[16:48, 320:390:6] = 0
    original = busy.copy()
    kept = svc.apply_brand_logo_top_right_bgr(busy)
    assert np.array_equal(kept, original)
