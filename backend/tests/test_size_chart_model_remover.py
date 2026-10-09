"""Ảnh kích thước: xóa người mẫu, giữ chữ bên cạnh."""

import cv2
import numpy as np

from app.services.size_chart_model_remover import has_ink_smear, person_mask_from_seed, remove_fashion_model


def test_blank_chart_is_unchanged():
    img = np.full((120, 200, 3), 255, np.uint8)
    out, removed = remove_fashion_model(img)
    assert removed is False
    assert np.array_equal(out, img)


def test_seeded_portrait_does_not_erase_separated_text():
    img = np.full((240, 480, 3), 255, np.uint8)
    cv2.circle(img, (90, 90), 48, (30, 40, 160), thickness=-1)
    cv2.putText(img, "SIZE", (260, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
    mask = person_mask_from_seed(img, (60, 60, 40, 40))
    assert mask is not None
    assert int(mask[90, 90]) > 0
    assert int(mask[100, 270]) == 0
    filled = img.copy()
    filled[mask > 0] = 255
    assert int(filled[90, 90, 0]) > 200
    assert int(filled[95, 280, 0]) < 80


def test_ink_smear_is_flagged_and_chart_bars_are_not():
    clean = np.full((360, 280, 3), 248, np.uint8)
    cv2.putText(clean, "Can nang 47kg", (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (20, 20, 20), 1, cv2.LINE_AA)
    clean[120:136, 20:180] = (176, 176, 176)
    assert has_ink_smear(clean) is False

    smeared = clean.copy()
    streak = np.zeros((90, 160), np.uint8)
    cv2.line(streak, (8, 30), (150, 18), 150, 7)
    cv2.line(streak, (12, 48), (140, 70), 120, 5)
    cv2.line(streak, (20, 62), (130, 40), 170, 4)
    streak = cv2.GaussianBlur(streak, (21, 21), 0)
    patch = smeared[180:270, 40:200]
    gray = streak[:, :, None]
    patch[:] = np.clip(patch.astype(np.int16) - gray, 0, 255).astype(np.uint8)
    assert has_ink_smear(smeared) is True
