"""Xóa ảnh người mẫu trên bảng size. Chỉ đụng vùng có khuôn mặt, giữ chữ và bảng số đo."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

Box = Tuple[int, int, int, int]


def remove_fashion_model(image: np.ndarray) -> Tuple[np.ndarray, bool]:
    """Trả (ảnh, đã_xóa). Không thấy khuôn mặt thì giữ nguyên pixel."""
    if image is None or not hasattr(image, "ndim") or image.ndim != 3 or image.shape[0] < 40 or image.shape[1] < 40:
        return image, False
    bgr = image
    if bgr.shape[2] == 4:
        bgr = cv2.cvtColor(bgr, cv2.COLOR_BGRA2BGR)
    faces = _detect_faces(bgr)
    if not faces:
        return image, False
    mask = np.zeros(bgr.shape[:2], np.uint8)
    for face in faces:
        part = person_mask_from_seed(bgr, face)
        if part is not None:
            mask = cv2.bitwise_or(mask, part)
    if int(np.count_nonzero(mask)) < 80:
        return image, False
    out = _fill_mask(bgr, mask)
    if image.shape[2] == 4:
        merged = image.copy()
        merged[:, :, :3] = out
        return merged, True
    return out, True


def person_mask_from_seed(bgr: np.ndarray, seed: Box) -> Optional[np.ndarray]:
    """Vùng người nối với ô seed, dừng ở nền trắng. Ảnh chân dung được phủ kín bằng hình tròn."""
    h, w = bgr.shape[:2]
    x, y, fw, fh = _clip_box(seed, w, h)
    if fw < 8 or fh < 8:
        return None
    bg = _background_color(bgr)
    dist = np.linalg.norm(bgr.astype(np.int16) - bg.reshape(1, 1, 3), axis=2)
    fg = (dist > 24).astype(np.uint8)
    fg[y : y + fh, x : x + fw] = 1
    _num, labels = cv2.connectedComponents(fg, connectivity=8)
    window = labels[y : y + fh, x : x + fw]
    vals, counts = np.unique(window[window > 0], return_counts=True)
    if len(vals) == 0:
        return None
    label = int(vals[int(np.argmax(counts))])
    mask = np.where(labels == label, np.uint8(255), np.uint8(0))
    close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close)
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return None
    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    area_frac = float(len(xs)) / float(h * w)
    if area_frac > 0.45 or bw > int(w * 0.55):
        return _portrait_circle(h, w, (x, y, fw, fh))
    aspect = bw / float(max(1, bh))
    if 0.62 <= aspect <= 1.55 and bh < int(h * 0.42):
        pad = max(6, int(max(bw, bh) * 0.04))
        cx = int((xs.min() + xs.max()) / 2)
        cy = int((ys.min() + ys.max()) / 2)
        radius = int(max(bw, bh) / 2 + pad)
        circle = np.zeros((h, w), np.uint8)
        cv2.circle(circle, (cx, cy), radius, 255, thickness=-1)
        return circle
    grow = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    return cv2.dilate(mask, grow, iterations=1)


def _portrait_circle(height: int, width: int, face: Box) -> np.ndarray:
    x, y, fw, fh = face
    mask = np.zeros((height, width), np.uint8)
    cx = int(x + fw / 2)
    cy = int(y + fh * 0.55)
    radius = int(max(fw, fh) * 1.35)
    cv2.circle(mask, (cx, cy), radius, 255, thickness=-1)
    return mask


def _detect_faces(bgr: np.ndarray) -> List[Box]:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    cascade_dir = cv2.data.haarcascades
    found: List[Box] = []
    clf = cv2.CascadeClassifier(cascade_dir + "haarcascade_frontalface_default.xml")
    if clf.empty():
        return []
    for frame, flip in ((gray, False), (cv2.flip(gray, 1), True)):
        rects = clf.detectMultiScale(frame, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
        width = gray.shape[1]
        for rx, ry, fw, fh in rects:
            if flip:
                rx = width - int(rx) - int(fw)
            found.append((int(rx), int(ry), int(fw), int(fh)))
    profile = cv2.CascadeClassifier(cascade_dir + "haarcascade_profileface.xml")
    if not profile.empty():
        for frame, flip in ((gray, False), (cv2.flip(gray, 1), True)):
            rects = profile.detectMultiScale(frame, scaleFactor=1.08, minNeighbors=4, minSize=(28, 28))
            width = gray.shape[1]
            for rx, ry, fw, fh in rects:
                if flip:
                    rx = width - int(rx) - int(fw)
                found.append((int(rx), int(ry), int(fw), int(fh)))
    return _dedupe_boxes(found)


def _background_color(bgr: np.ndarray) -> np.ndarray:
    h, w = bgr.shape[:2]
    t = max(4, min(12, h // 40, w // 40))
    border = np.concatenate(
        [
            bgr[:t, :, :].reshape(-1, 3),
            bgr[-t:, :, :].reshape(-1, 3),
            bgr[:, :t, :].reshape(-1, 3),
            bgr[:, -t:, :].reshape(-1, 3),
        ]
    )
    return np.median(border, axis=0)


def _clip_box(box: Box, width: int, height: int) -> Box:
    x, y, fw, fh = box
    x = max(0, min(int(x), width - 1))
    y = max(0, min(int(y), height - 1))
    fw = max(1, min(int(fw), width - x))
    fh = max(1, min(int(fh), height - y))
    return x, y, fw, fh


def _dedupe_boxes(boxes: Sequence[Box]) -> List[Box]:
    kept: List[Box] = []
    for box in boxes:
        if any(_iou(box, other) > 0.35 for other in kept):
            continue
        kept.append(box)
    return kept


def _iou(a: Box, b: Box) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x1, y1 = max(ax, bx), max(ay, by)
    x2, y2 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter <= 0:
        return 0.0
    union = aw * ah + bw * bh - inter
    return float(inter) / float(max(1, union))


def _fill_mask(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    ring_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    ring = cv2.subtract(cv2.dilate(mask, ring_kernel, iterations=2), mask)
    pixels = bgr[ring > 0]
    out = bgr.copy()
    if pixels.size >= 30:
        med = np.median(pixels.reshape(-1, 3), axis=0)
        spread = np.std(pixels.reshape(-1, 3), axis=0)
        if float(np.max(spread)) < 28:
            out[mask > 0] = med.astype(np.uint8)
            return out
    return cv2.inpaint(out, mask, 5, cv2.INPAINT_TELEA)


def has_ink_smear(bgr: np.ndarray) -> bool:
    """Vệt mực loang trên nền giấy: vùng xám mờ, không phải chữ nét và không phải thanh chỉ số đều."""
    if bgr is None or bgr.ndim != 3 or bgr.shape[0] < 40 or bgr.shape[1] < 40:
        return False
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    channels = bgr.astype(np.int16)
    sat = channels.max(axis=2) - channels.min(axis=2)
    lap = np.abs(cv2.Laplacian(gray, cv2.CV_16S))
    soft = ((gray > 70) & (gray < 220) & (sat < 28) & (lap < 12)).astype(np.uint8)
    soft = cv2.morphologyEx(soft, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    count, _labels, stats, _cent = cv2.connectedComponentsWithStats(soft, connectivity=8)
    page = float(gray.size)
    for idx in range(1, count):
        area = int(stats[idx, cv2.CC_STAT_AREA])
        if area < 350 or area > page * 0.12:
            continue
        bw = int(stats[idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
        fill = area / float(max(1, bw * bh))
        x = int(stats[idx, cv2.CC_STAT_LEFT])
        y = int(stats[idx, cv2.CC_STAT_TOP])
        roi = gray[y : y + bh, x : x + bw]
        comp = soft[y : y + bh, x : x + bw] > 0
        if int(np.count_nonzero(comp)) < 350:
            continue
        spread = float(np.std(roi[comp]))
        if fill > 0.72 and spread < 18:
            continue
        if spread >= 12 and fill < 0.85:
            return True
    return False
