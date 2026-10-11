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
    # Nền ô lấy màu ngay xung quanh, không tô trắng lệch.
    assert abs(int(out[32, 112, 0]) - 180) <= 12
    assert int(out[28:44, 20:90].min()) < 40


def test_photo_gap_chart_draws_labels_in_place():
    img = np.full((900, 400, 3), 255, np.uint8)
    img[30:180, 20:150] = _leather(150, 130, 9)
    photo = img[30:180, 20:150].copy()
    blocks = []
    for i, label in enumerate(("Chieu cao", "Can nang", "Vong nguc", "Vong eo", "Kieu dang", "Mau sac")):
        y = 40 + i * 22
        blocks.append((label, (170, y, 250, y + 16)))
    for row in range(4):
        y = 420 + row * 36
        for col in range(4):
            x = 20 + col * 90
            blocks.append((f"C{col}{row}", (x, y, x + 50, y + 18)))

    out = _processor().process_image_with_text(img, blocks, [])

    delta = np.abs(out[30:180, 20:150].astype(np.int16) - photo.astype(np.int16)).mean()
    assert delta < 8, f"anh mau bi de chu delta={delta:.1f}"
    assert int(out[300, 200].min()) > 240
    assert int(out[46:54, 176:240].min()) < 40
    assert int(out[426:440, 24:64].min()) < 40


def test_text_on_cream_paper_is_redrawn_and_photo_stays():
    import cv2

    img = np.full((420, 320, 3), (236, 244, 248), np.uint8)
    cv2.putText(img, "Tieu de san pham", (18, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2, cv2.LINE_AA)
    cv2.putText(img, "Dong mo ta thu nhat rat dai", (16, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    cv2.putText(img, "Dong mo ta thu hai cung dai", (16, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1, cv2.LINE_AA)
    img[240:400, 20:300] = _leather(160, 280, 11)
    photo = img[240:400, 20:300].copy()
    proc = _processor()
    assert proc._region_is_color_photo(img, (16, 36, 250, 70)) is False
    assert proc._region_is_color_photo(img, (16, 86, 280, 132)) is False
    assert proc._region_is_color_photo(img, (20, 240, 300, 400)) is True

    out = proc.process_image_with_text(
        img,
        [
            ("Tui kep nach det thoi trang", (18, 36, 230, 68)),
            ("Day la dong mo ta dai hon hop OCR", (16, 86, 250, 108)),
            ("Va dong mo ta tiep theo van la chu", (16, 110, 270, 132)),
        ],
        [],
    )
    delta = np.abs(out[240:400, 20:300].astype(np.int16) - photo.astype(np.int16)).mean()
    assert delta < 8, f"anh san pham bi de chu delta={delta:.1f}"
    assert int(out[40:66, 22:220].min()) < 40
    assert not np.array_equal(out[36:132, 16:280], img[36:132, 16:280])


def test_in_situ_keeps_original_ink_and_phone_min_size():
    import cv2

    img = np.full((1024, 768, 3), 255, np.uint8)
    leather = _leather(280, 520, 4)
    img[360:640, 120:640] = leather
    cv2.putText(img, "CAO CAP", (180, 470), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, "MEM", (150, 860), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2, cv2.LINE_AA)
    proc = _processor()
    assert proc._phone_min_font_size(768) >= 27
    out = proc.process_image_with_text(
        img,
        [
            ("Da bo that cao cap", (170, 430, 520, 490)),
            ("Mem mai tinh te", (140, 820, 280, 880)),
        ],
        [],
    )
    title = out[430:520, 170:520]
    assert int(title.max()) > 220, "chu trang goc bi ve thanh chu toi"
    label = out[820:900, 140:300]
    assert int(label.min()) < 40, "chu den goc bi ve thanh chu trang"
    ink_rows = np.where(title.max(axis=2) > 220)[0]
    assert ink_rows.size and int(ink_rows.max() - ink_rows.min()) >= 20


def test_text_on_a_photo_is_not_covered_by_a_flat_plate():
    import cv2

    rng = np.random.default_rng(5)
    img = rng.integers(0, 30, (180, 320, 3), dtype=np.uint8)
    img[20:150, 140:300] = rng.integers(170, 255, (130, 160, 3), dtype=np.uint8)
    before = img[24:40, 150:180].copy()
    cv2.putText(img, "MUI", (150, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    out = _processor().process_image_with_text(
        img,
        [("Tinh khiet khong mui, giu am tot hon", (146, 72, 250, 112))],
        [],
    )
    assert np.array_equal(out[24:40, 150:180], before)
    plate = out[72:112, 146:250]
    assert float(np.std(plate)) > 18


def test_colored_badge_keeps_its_fill_and_gets_new_text():
    import cv2

    img = np.full((180, 220, 3), 248, np.uint8)
    img[40:150, 24:150] = (48, 78, 128)
    cv2.putText(img, "WOOL", (36, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (245, 245, 245), 2, cv2.LINE_AA)
    proc = _processor()
    assert proc._region_is_color_photo(img, (36, 70, 130, 110)) is False
    out = proc.process_image_with_text(img, [("Long cuu", (36, 72, 130, 108))], [])
    badge = out[48:140, 30:140]
    assert int(badge[:, :, 0].mean()) < 90
    assert int(badge.min()) > 180 or int(out[78:100, 40:120].max()) > 200


def test_blank_manufacturer_line_is_erased_without_touching_the_photo():
    import cv2

    img = np.full((120, 240, 3), 255, np.uint8)
    cv2.putText(img, "XUONG", (16, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2, cv2.LINE_AA)
    photo = _leather(70, 80, 6)
    img[20:90, 140:220] = photo
    out = _processor().process_image_with_text(img, [("", (14, 24, 110, 54))], [])
    assert int(out[30:50, 20:100].mean()) > 180
    delta = np.abs(out[20:90, 140:220].astype(np.int16) - photo.astype(np.int16)).mean()
    assert delta < 8


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


def test_spec_column_keeps_the_product_photo_and_separates_lines():
    import cv2

    img = np.full((452, 749, 3), 255, np.uint8)
    img[0:34, :] = (232, 232, 232)
    img[48:430, 40:350] = _leather(382, 310, 3)
    photo = img[48:430, 40:350].copy()
    blocks = [("Thong so san pham", (12, 6, 240, 28)), ("Thong so san pham", (420, 72, 560, 90))]
    y = 110
    for label in (
        "Chat lieu mat giay: PU",
        "Chat lieu lot giay: PU",
        "Chat lieu de: cao su",
        "Mau sac: hoa tiet da bao",
        "Kich co: 34-50",
        "Chieu cao got: 19cm",
        "De be: 9cm",
    ):
        blocks.append((label, (442, y, 560, y + 14)))
        y += 22
    blocks.append((
        "Luu y: do chuan la size 36, moi lan tang mot size thi chieu dai giay tang 5mm va co the lech so voi hang that.",
        (421, y + 16, 700, y + 30),
    ))
    proc = _processor()
    assert proc._layout_spec_column(blocks, [], 749, 452, img) is not None
    out = proc.process_image_with_text(img, blocks, [])
    delta = np.abs(out[48:430, 40:350].astype(np.int16) - photo.astype(np.int16)).mean()
    assert delta < 8, f"anh san pham bi de chu delta={delta:.1f}"
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    column = gray[100:270, 430:700]
    ink_rows = np.where(column.min(axis=1) < 40)[0]
    groups = 0
    previous = -10
    for row in ink_rows:
        if row > previous + 2:
            groups += 1
        previous = int(row)
    assert groups >= 6, f"chu cot thong so bi dinh, chi thay {groups} cum"


def test_long_label_stays_inside_its_row_and_beside_its_neighbor():
    img = np.full((180, 360, 3), 255, np.uint8)
    img[28:42, 320:340] = (0, 0, 255)
    img[100:114, 20:36] = (0, 0, 255)
    blocks = [
        ("Mo ta dai hon rat nhieu so voi o chu goc", (16, 24, 80, 44)),
        ("Ngan", (200, 24, 250, 44)),
        ("Dong duoi", (16, 120, 90, 142)),
    ]
    out = _processor().process_image_with_text(img, blocks, [])
    assert np.all(out[28:42, 320:340, 2] == 255)
    assert np.all(out[100:114, 20:36, 2] == 255)
    assert int(out[26:42, 18:70].min()) < 80
    assert int(out[122:140, 18:80].min()) < 80


def test_old_ink_is_covered_by_a_solid_plate():
    import cv2

    img = np.full((80, 220, 3), 248, np.uint8)
    cv2.putText(img, "OLD", (18, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (30, 30, 30), 2, cv2.LINE_AA)
    before = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    out = _processor().process_image_with_text(img, [("Chu moi", (16, 22, 90, 58))], [])
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    was_ink = before[24:56, 18:88] < 80
    now = gray[24:56, 18:88]
    light = now[now > 40]
    assert float(light.mean()) > 220
    assert int(now.min()) < 40
    assert int(was_ink.sum()) > 20
