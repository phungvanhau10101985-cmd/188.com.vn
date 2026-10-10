# image_processor.py
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple
import re
import os
import platform
from config import FONT_PATH, LOGO_PATH
import random

class ImageProcessor:
    def __init__(self):
        self.font_path = self._find_best_font(FONT_PATH)
        print(f"  🔤 ImageProcessor sử dụng font: {self.font_path}")
        
        # Cỡ tối thiểu khi vẽ chữ bản địa hóa (binary search trong [_calc_box / _binary_search_font]).
        self.MIN_FONT_SIZE = 14
        self.MAX_FONT_SIZE = 140
        self.STROKE_WIDTH_RATIO = 0.05
        # Legacy ratio; không dùng làm stride dòng nữa (xem _wrapped_block_height / _draw_text_centered).
        self.LINE_HEIGHT_RATIO = 1.2
        # Padding nội bộ lỏng hơn một chút để chữ không sát mép
        self.INTERNAL_PADDING = 8
        self.font_cache = {}
        
        self.logo_img = None
        if os.path.exists(LOGO_PATH):
            self.logo_img = cv2.imread(str(LOGO_PATH), cv2.IMREAD_UNCHANGED)

    def _find_best_font(self, config_font_path: str) -> str:
        if config_font_path and os.path.exists(config_font_path):
            return config_font_path
        system = platform.system()
        search_paths = []
        font_names = ["arial.ttf", "tahoma.ttf", "times.ttf", "seguiemj.ttf", "calibri.ttf"]
        if system == "Windows":
            search_paths = ["C:/Windows/Fonts"]
        elif system == "Linux":
            search_paths = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/noto"]
            font_names = ["DejaVuSans.ttf", "NotoSans-Regular.ttf"] + font_names
        elif system == "Darwin":
            search_paths = ["/System/Library/Fonts", "/Library/Fonts"]
            font_names = ["Helvetica.ttc", "Arial.ttf"] + font_names

        for path in search_paths:
            if not os.path.exists(path): continue
            for font in font_names:
                full_path = os.path.join(path, font)
                if os.path.exists(full_path): return full_path
        return config_font_path or "arial.ttf"

    def _get_font(self, size: int):
        if size in self.font_cache: return self.font_cache[size]
        try:
            font = ImageFont.truetype(self.font_path, size)
            self.font_cache[size] = font
            return font
        except:
            return ImageFont.load_default()

    def _get_avg_color(self, img_roi: np.ndarray) -> Tuple[int, int, int]:
        """Lấy màu trung bình của vùng ảnh (tốt hơn median cho gradient)"""
        if img_roi.size == 0: return (255, 255, 255)
        # Tính mean theo từng kênh
        avg_color = np.mean(img_roi, axis=(0, 1))
        return tuple(map(int, avg_color))

    def _add_noise(self, img: np.ndarray, intensity=5):
        """Thêm nhiễu hạt nhẹ để nền trông tự nhiên hơn"""
        h, w, c = img.shape
        noise = np.random.randn(h, w, c) * intensity
        noisy_img = img + noise
        return np.clip(noisy_img, 0, 255).astype(np.uint8)

    def _clip_bbox(self, bbox: Tuple[int, int, int, int], h_img: int, w_img: int) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = map(int, bbox)
        return max(0, x1), max(0, y1), min(w_img, x2), min(h_img, y2)

    def _expand_bbox_for_inpaint(self, bbox: Tuple[int, int, int, int], h_img: int, w_img: int) -> Tuple[int, int, int, int]:
        """Expand OCR bbox lightly so only text strokes are removed."""
        x1, y1, x2, y2 = map(int, bbox)
        w_box = max(1, x2 - x1)
        h_box = max(2, y2 - y1)
        pad = max(4, min(14, int(0.12 * max(w_box, h_box))))
        return self._clip_bbox((x1 - pad, y1 - pad, x2 + pad, y2 + pad), h_img, w_img)

    def _build_text_mask(self, roi: np.ndarray) -> np.ndarray:
        """Build a stroke-level text mask while preserving the panel/background."""
        if roi.size == 0:
            return np.zeros((0, 0), dtype=np.uint8)

        h, w = roi.shape[:2]
        if h < 3 or w < 3:
            return np.zeros((h, w), dtype=np.uint8)

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blur_k = max(5, min(31, (min(h, w) // 2) * 2 + 1))
        bg_gray = cv2.medianBlur(gray, blur_k)
        bg_color = cv2.medianBlur(roi, blur_k)

        diff_gray = cv2.absdiff(gray, bg_gray)
        diff_color = np.max(
            np.abs(roi.astype(np.int16) - bg_color.astype(np.int16)), axis=2
        ).astype(np.uint8)

        th_gray = max(10, int(np.percentile(diff_gray, 82)))
        th_color = max(14, int(np.percentile(diff_color, 82)))
        mask = ((diff_gray >= th_gray) | (diff_color >= th_color)).astype(np.uint8) * 255

        edges = cv2.Canny(gray, 40, 130)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.bitwise_or(mask, cv2.bitwise_and(cv2.dilate(edges, kernel, iterations=1), cv2.dilate(mask, kernel, iterations=1)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        clean = np.zeros_like(mask)
        roi_area = max(1, h * w)
        for idx in range(1, num):
            area = int(stats[idx, cv2.CC_STAT_AREA])
            bw = int(stats[idx, cv2.CC_STAT_WIDTH])
            bh = int(stats[idx, cv2.CC_STAT_HEIGHT])
            if area < 3:
                continue
            if area > roi_area * 0.42:
                continue
            if bw > w * 0.96 and bh > h * 0.55:
                continue
            clean[labels == idx] = 255

        if np.count_nonzero(clean) == 0:
            return clean
        return cv2.dilate(clean, kernel, iterations=2)

    def _fill_bbox_with_surrounding_background(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return img

        ref_pad = max(5, min(14, int(0.18 * max(x2 - x1, y2 - y1))))
        rx1, ry1 = max(0, x1 - ref_pad), max(0, y1 - ref_pad)
        rx2, ry2 = min(w_img, x2 + ref_pad), min(h_img, y2 + ref_pad)
        roi = img[ry1:ry2, rx1:rx2]
        if roi.size == 0:
            return img

        mask_center = np.zeros(roi.shape[:2], dtype=np.uint8)
        cv2.rectangle(mask_center, (x1 - rx1, y1 - ry1), (x2 - rx1, y2 - ry1), 255, -1)
        bg_pixels = roi[mask_center == 0]
        if bg_pixels.size == 0:
            bg_pixels = roi.reshape(-1, 3)
        fill_color = np.median(bg_pixels, axis=0).astype(np.uint8)

        out = img.copy()
        out[y1:y2, x1:x2] = fill_color

        edge_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        cv2.rectangle(edge_mask, (x1, y1), (x2, y2), 255, max(2, min(5, ref_pad // 2)))
        return cv2.inpaint(out, edge_mask, 2, cv2.INPAINT_TELEA)

    def _inpaint_text_strokes(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa nét chữ trên ảnh sản phẩm, giữ nguyên da/kim loại bên trong bbox OCR."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return img
        mask = self._build_text_mask(img[y1:y2, x1:x2])
        if mask.size == 0 or int(np.count_nonzero(mask)) < 8:
            return img
        full_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        full_mask[y1:y2, x1:x2] = mask
        return cv2.inpaint(img, full_mask, 3, cv2.INPAINT_TELEA)

    def _advanced_inpainting(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa chữ trên nền phẳng. Bbox đè lên ảnh sản phẩm thì chỉ xóa nét chữ."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._expand_bbox_for_inpaint(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return img
        if self._region_is_product_photo(img, (x1, y1, x2, y2)):
            return self._inpaint_text_strokes(img, (x1, y1, x2, y2))
        return self._fill_bbox_with_surrounding_background(img, (x1, y1, x2, y2))

    def _estimate_text_color(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int] | None:
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._expand_bbox_for_inpaint(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return None
        roi = img[y1:y2, x1:x2]
        mask = self._build_text_mask(roi)
        pixels = roi[mask > 0]
        if pixels.size < 9:
            return None
        b, g, r = np.median(pixels, axis=0)
        return (int(r), int(g), int(b))

    def _phone_min_font_size(self, img_w: int) -> int:
        """Cỡ chữ tối thiểu khi ảnh hiện full ngang điện thoại (~390px, ~14px CSS)."""
        scaled = int(round(max(1, int(img_w)) * 14 / 390))
        return max(self.MIN_FONT_SIZE, min(64, scaled))

    def _luminance(self, rgb: Tuple[int, int, int]) -> float:
        return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]

    def _snap_ink_rgb(self, rgb: Tuple[int, int, int], bg_rgb: Tuple[int, int, int] | None = None) -> Tuple[int, int, int]:
        """Giữ màu nét gốc: chữ sáng trên nền tối thành trắng, chữ tối trên nền sáng thành đen."""
        r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        lum = self._luminance((r, g, b))
        if bg_rgb is not None:
            bg_lum = self._luminance(bg_rgb)
            if lum - bg_lum >= 35 and lum >= 150:
                return (255, 255, 255)
            if bg_lum - lum >= 35 and lum <= 120:
                return (0, 0, 0)
        if lum >= 186:
            return (255, 255, 255)
        if lum <= 70:
            return (0, 0, 0)
        return (r, g, b)

    def _background_bgr(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return (255, 255, 255)
        roi = img[y1:y2, x1:x2]
        mask = self._build_text_mask(roi)
        pixels = roi[mask == 0] if mask.size and int(np.count_nonzero(mask)) else roi.reshape(-1, roi.shape[-1])
        if getattr(pixels, "size", 0) < 3:
            pixels = roi.reshape(-1, roi.shape[-1])
        med = np.median(pixels, axis=0)
        return (int(med[0]), int(med[1]), int(med[2]))

    def _median_bgr(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return (255, 255, 255)
        roi = img[y1:y2, x1:x2]
        if roi.size == 0:
            return (255, 255, 255)
        med = np.median(roi.reshape(-1, roi.shape[-1]), axis=0)
        return (int(med[0]), int(med[1]), int(med[2]))

    def _resolve_ink_rgb(self, img_bgr: np.ndarray, bbox: Tuple[int, int, int, int]) -> Tuple[int, int, int]:
        sampled = self._estimate_text_color(img_bgr, bbox)
        bg_bgr = self._background_bgr(img_bgr, bbox)
        bg_rgb = (bg_bgr[2], bg_bgr[1], bg_bgr[0])
        h_img, w_img = img_bgr.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        roi = img_bgr[y1:y2, x1:x2] if x2 > x1 and y2 > y1 else None
        if roi is not None and roi.size:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            if self._is_text_on_flat_paper(gray):
                if sampled is not None and (max(sampled) - min(sampled)) >= 45:
                    return self._snap_ink_rgb(sampled, bg_rgb)
                return (0, 0, 0)
        if sampled is not None:
            snapped = self._snap_ink_rgb(sampled, bg_rgb)
            if abs(self._luminance(snapped) - self._luminance(bg_rgb)) >= 50:
                return snapped
        return self._get_text_style(bg_rgb)["text_color"]

    def _row_slot_bounds(
        self,
        src: Tuple[int, int, int, int],
        others: List[Tuple[int, int, int, int]],
        img_w: int,
    ) -> Tuple[int, int]:
        """Khoảng ngang còn trống trên cùng hàng, không đè chữ bên cạnh."""
        x1, y1, x2, y2 = src
        cy = (y1 + y2) / 2
        reach = max(12, y2 - y1)
        prev_right = None
        next_left = None
        for ox1, oy1, ox2, oy2 in others:
            same_band = abs(((oy1 + oy2) / 2) - cy) <= max(reach, oy2 - oy1) * 1.6
            overlaps_y = min(y2, oy2) - max(y1, oy1) > 0
            if not same_band and not overlaps_y:
                continue
            if ox2 <= x1 + 2 and (prev_right is None or ox2 > prev_right):
                prev_right = ox2
            elif ox1 >= x2 - 2 and (next_left is None or ox1 < next_left):
                next_left = ox1
        if prev_right is None and next_left is None:
            return 2, img_w - 2
        right = ((x2 + next_left) // 2) if next_left is not None else img_w - 2
        left = ((prev_right + x1) // 2) if prev_right is not None else 2
        if prev_right is None:
            left = max(2, x1 - max(8, right - x2))
        if next_left is None:
            right = min(img_w - 2, x2 + max(8, x1 - left))
        if right - left < 8:
            return x1, max(x1 + 8, x2)
        return left, right

    def _inset_white_card(self, img: np.ndarray, src: Tuple[int, int, int, int]):
        """Thẻ trắng nằm giữa ảnh (không phải nền trắng full)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h_img, w_img = gray.shape[:2]
        sx1, sy1, sx2, sy2 = (int(src[0]), int(src[1]), int(src[2]), int(src[3]))
        cx = max(0, min(w_img - 1, (sx1 + sx2) // 2))
        probes = list(range(max(0, sy1 - 8), min(h_img - 1, sy2 + 40)))
        best = None
        for y in probes:
            mask = (gray[y] > 210).astype(np.uint8).reshape(1, -1)
            gap = cv2.getStructuringElement(cv2.MORPH_RECT, (41, 1))
            closed = cv2.morphologyEx(mask * 255, cv2.MORPH_CLOSE, gap).ravel()
            if int(closed[cx]) == 0:
                continue
            left = cx
            while left > 0 and int(closed[left - 1]) > 0:
                left -= 1
            right = cx
            while right < w_img - 1 and int(closed[right + 1]) > 0:
                right += 1
            span = right - left
            if span < w_img * 0.28 or span > w_img * 0.92:
                continue
            if best is None or span > best[0]:
                best = (span, left, right, y)
        if best is None:
            return None
        _span, left, right, y = best

        def row_ok(yy: int) -> bool:
            seg = gray[yy, left:right + 1]
            return float(np.mean(seg > 200)) > 0.45

        y1, y2 = y, y
        while y1 > 0 and row_ok(y1 - 1):
            y1 -= 1
        while y2 < h_img - 1 and row_ok(y2 + 1):
            y2 += 1
        if y2 - y1 < 20:
            return None
        return left, y1, right + 1, y2 + 1

    def _apply_inset_caption_cards(self, img: np.ndarray, blocks: List[Dict], phone_min: int) -> None:
        """Các nhãn cùng hàng trên một thẻ trắng dùng chung một dải, không cắt chữ."""
        h_img, w_img = img.shape[:2]
        pending = [item for item in blocks if item.get("_paper") and item.get("_draw") and item.get("src_bbox")]
        used = set()
        for item in pending:
            if id(item) in used:
                continue
            src = tuple(map(int, item["src_bbox"]))
            cy = (src[1] + src[3]) / 2
            reach = max(12, src[3] - src[1])
            row = [item]
            for other in pending:
                if other is item or id(other) in used:
                    continue
                ob = tuple(map(int, other["src_bbox"]))
                ocy = (ob[1] + ob[3]) / 2
                if abs(ocy - cy) <= max(reach, ob[3] - ob[1]) * 1.8:
                    row.append(other)
            if len(row) < 2:
                continue
            card = self._inset_white_card(img, src)
            if card is None:
                continue
            for part in row:
                used.add(id(part))
            card_x1, card_y1, card_x2, card_y2 = card
            row.sort(key=lambda it: int(it["src_bbox"][0]))
            n = len(row)
            col_w = max(8, (card_x2 - card_x1) // n)
            fitted = []
            tallest = 0
            for part in row:
                text = str(part.get("text") or "").strip()
                font, lines, pad = self._fit_cell_lines(
                    text,
                    col_w - 8,
                    phone_min * 6,
                    min_size=phone_min,
                    max_size=phone_min,
                )
                if not font:
                    fitted.append(None)
                    continue
                _need_w, need_h = self._line_block_size(font, lines, pad)
                tallest = max(tallest, need_h)
                fitted.append((font, lines, pad))
            if tallest < 8:
                continue
            y1 = max(card_y1, min(int(it["src_bbox"][1]) for it in row) - 2)
            y2 = min(h_img - 2, y1 + tallest + 8)
            img[y1:y2, card_x1:card_x2] = (255, 255, 255)
            for index, part in enumerate(row):
                pack = fitted[index]
                if not pack:
                    continue
                font, lines, pad = pack
                x1 = card_x1 + index * col_w
                x2 = card_x2 if index == n - 1 else card_x1 + (index + 1) * col_w
                part["ink_rgb"] = (0, 0, 0)
                part["_align"] = "top-center"
                part["_draw"] = (font, lines, pad, (x1, y1 + 4, x2, y2))

    def _repaint_bbox_to_background(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa nét chữ trong hộp OCR bằng màu nền ngay ngoài hộp."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return img
        pad = 4
        ox1, oy1 = max(0, x1 - pad), max(0, y1 - pad)
        ox2, oy2 = min(w_img, x2 + pad), min(h_img, y2 + pad)
        outer = img[oy1:oy2, ox1:ox2]
        ring = np.ones(outer.shape[:2], dtype=bool)
        ring[(y1 - oy1):(y2 - oy1), (x1 - ox1):(x2 - ox1)] = False
        samples = outer[ring]
        if samples.size < 9:
            return img
        bg = np.median(samples, axis=0)
        inner = img[y1:y2, x1:x2].copy()
        diff = np.max(np.abs(inner.astype(np.int16) - bg.astype(np.int16)), axis=2)
        mask = (diff > 28).astype(np.uint8) * 255
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)
        inner[mask > 0] = bg
        out = img.copy()
        out[y1:y2, x1:x2] = inner
        return out

    def _erase_strokes_with_local_color(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa nét chữ bằng màu nền quanh nét, tránh vệt loang của inpaint trên da."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return img
        roi = img[y1:y2, x1:x2]
        mask = self._build_text_mask(roi)
        if mask.size == 0 or int(np.count_nonzero(mask)) < 8:
            return img
        bg_pixels = roi[mask == 0]
        if bg_pixels.size < 9:
            return self._inpaint_text_strokes(img, (x1, y1, x2, y2))
        fill = np.median(bg_pixels, axis=0).astype(np.uint8)
        out = img.copy()
        painted = out[y1:y2, x1:x2]
        painted[mask > 0] = fill
        out[y1:y2, x1:x2] = painted
        return out

    def _rects_intersect(self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
        return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

    def _expand_draw_box(
        self,
        img: np.ndarray,
        box: Tuple[int, int, int, int],
        need_w: int,
        need_h: int,
        blockers: List[Tuple[int, int, int, int]],
    ) -> Tuple[int, int, int, int]:
        """Nới ô chữ trên cùng nền (thẻ trắng, lớp phủ) để vừa cỡ tối thiểu, không đè ô khác."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, box)), h_img, w_img)
        ref = self._background_bgr(img, (x1, y1, x2, y2))

        def strip_ok(rect: Tuple[int, int, int, int]) -> bool:
            sx1, sy1, sx2, sy2 = rect
            if sx2 - sx1 < 1 or sy2 - sy1 < 1:
                return False
            if sx1 < 0 or sy1 < 0 or sx2 > w_img or sy2 > h_img:
                return False
            for blocker in blockers:
                if self._rects_intersect(rect, blocker):
                    return False
            med = self._median_bgr(img, rect)
            return max(abs(med[i] - ref[i]) for i in range(3)) <= 36

        def grow(axis: str, sign: int) -> None:
            nonlocal x1, y1, x2, y2
            for _ in range(80):
                if axis == "x" and (x2 - x1) >= need_w:
                    return
                if axis == "y" and (y2 - y1) >= need_h:
                    return
                if axis == "x" and sign > 0:
                    trial = (x2, y1, min(w_img, x2 + 4), y2)
                    if not strip_ok(trial):
                        return
                    x2 = trial[2]
                elif axis == "x" and sign < 0:
                    trial = (max(0, x1 - 4), y1, x1, y2)
                    if not strip_ok(trial):
                        return
                    x1 = trial[0]
                elif axis == "y" and sign > 0:
                    trial = (x1, y2, x2, min(h_img, y2 + 4))
                    if not strip_ok(trial):
                        return
                    y2 = trial[3]
                else:
                    trial = (x1, max(0, y1 - 4), x2, y1)
                    if not strip_ok(trial):
                        return
                    y1 = trial[1]

        grow("y", 1)
        grow("y", -1)
        grow("x", 1)
        grow("x", -1)
        return x1, y1, x2, y2

    def _get_text_style(self, bg_color: Tuple[int, int, int]) -> Dict:
        bg_lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        if bg_lum > 140:
            return {'text_color': (0, 0, 0), 'stroke_color': (255, 255, 255), 'use_shadow': False}
        else:
            return {'text_color': (255, 255, 255), 'stroke_color': (0, 0, 0), 'use_shadow': True}

    def _line_gap(self, font_size: int) -> int:
        return max(1, int(font_size * 0.08))

    def _stroke_width_for_size(self, font_size: int) -> int:
        if font_size < 24:
            return 1
        return min(3, max(1, int(round(font_size * self.STROKE_WIDTH_RATIO))))

    def _wrapped_block_height(self, draw, lines: List[str], font, stroke_width: int) -> int:
        """Tổng chiều cao khối chữ đa dòng — đo bằng textbbox có stroke (tránh đè glyph)."""
        if not lines or not font:
            return 0
        fs = getattr(font, "size", self.MIN_FONT_SIZE) or self.MIN_FONT_SIZE
        gap = self._line_gap(fs)
        h = 0
        for i, line in enumerate(lines):
            bb = draw.textbbox(
                (0, 0), line, font=font, stroke_width=stroke_width, anchor="lt"
            )
            h += bb[3] - bb[1]
            if i < len(lines) - 1:
                h += gap
        return h

    def _wrap_text(self, text, font, max_width, draw, stroke_width: int = 0):
        """Đo độ rộng có stroke để chia dòng không bị tràn ngang và đẩy dòng chồng lên nhau."""
        if not font:
            return [text]
        lines, words = [], text.split()
        current_line = []
        sw = stroke_width if stroke_width is not None else 0
        for word in words:
            test_line = current_line + [word]
            s = " ".join(test_line)
            bb = draw.textbbox((0, 0), s, font=font, stroke_width=sw, anchor="lt")
            if bb[2] - bb[0] <= max_width:
                current_line = test_line
            else:
                lines.append(" ".join(current_line) if current_line else word)
                current_line = [word] if current_line else []
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    def _vertical_padding_budget(self, font_size: int) -> int:
        """Dự trữ dọc khi ước lượng hộp (_calc_box_centered)."""
        return max(3, min(18, self.INTERNAL_PADDING + int(font_size * 0.12)))

    def _calc_box_centered(self, text, bbox, img_w, img_h, draw):
        """Keep translated text inside the OCR box so it cannot cover product photos."""
        del text, draw
        if not bbox or len(bbox) < 4:
            return bbox
        return self._clip_bbox(tuple(map(int, bbox[:4])), img_h, img_w)

    def _binary_search_font(self, text, w, h, draw):
        # 8px only when the original caption is too short for the usual 14px floor.
        low, high = 8, self.MAX_FONT_SIZE
        best_size, best_lines = 8, [text]
        eff_w = max(10, w - self.INTERNAL_PADDING * 2)
        eff_h = max(8, h - self.INTERNAL_PADDING)

        while low <= high:
            mid = (low + high) // 2
            font = self._get_font(mid)
            if not font:
                break
            stroke_w = self._stroke_width_for_size(mid)
            lines = self._wrap_text(text, font, eff_w, draw, stroke_width=stroke_w)
            total_h = self._wrapped_block_height(draw, lines, font, stroke_w)
            if total_h <= eff_h:
                best_size, best_lines, low = mid, lines, mid + 1
            else:
                high = mid - 1

        font = self._get_font(best_size)
        stroke_w = self._stroke_width_for_size(best_size)
        lines = self._wrap_text(text, font, eff_w, draw, stroke_width=stroke_w)
        total_h = self._wrapped_block_height(draw, lines, font, stroke_w)
        if total_h > eff_h:
            compact = " ".join(str(text).split())
            lines = self._wrap_text(compact, font, eff_w, draw, stroke_width=stroke_w)
        return best_size, lines

    def _draw_text_centered(self, draw, lines, bbox, font, style):
        if not font:
            return
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        cx = x1 + w // 2
        fs = getattr(font, "size", self.MIN_FONT_SIZE) or self.MIN_FONT_SIZE
        stroke_width = self._stroke_width_for_size(fs)
        gap = self._line_gap(fs)

        total_h = self._wrapped_block_height(draw, lines, font, stroke_width)
        cy = y1 + h // 2
        y_cursor = cy - total_h // 2

        for line in lines:
            bb0 = draw.textbbox(
                (0, 0), line, font=font, stroke_width=stroke_width, anchor="lt"
            )
            iy = int(y_cursor - bb0[1])
            ix = int(round(cx - (bb0[0] + bb0[2]) / 2))
            line_top = iy + bb0[1]
            line_bottom = iy + bb0[3]
            if line_bottom > y2 + 2:
                break
            if line_top < y1 - 1:
                y_cursor = line_bottom + gap
                continue

            if style["use_shadow"]:
                shadow_offset = max(1, min(3, int(round(fs * 0.035))))
                draw.text(
                    (ix + shadow_offset, iy + shadow_offset),
                    line,
                    font=font,
                    fill=(30, 30, 30),
                    stroke_width=0,
                    anchor="lt",
                )

            draw.text(
                (ix, iy),
                line,
                font=font,
                fill=style["text_color"],
                stroke_width=stroke_width,
                stroke_fill=style["stroke_color"],
                anchor="lt",
            )

            ba = draw.textbbox(
                (ix, iy), line, font=font, stroke_width=stroke_width, anchor="lt"
            )
            y_cursor = ba[3] + gap

    def _is_cm_measurement_text(self, text: str) -> bool:
        compact = re.sub(r"[\s\u3000\r\n]+", "", str(text or ""))
        return bool(re.fullmatch(r"(?:\d+(?:[\.,]\d+)?|[\.,]\d+)[cC][mM]", compact))

    def _should_attach_cm_to_group(self, group: List[Dict], item: Dict) -> bool:
        item_is_cm = self._is_cm_measurement_text(item.get("text", ""))
        group_has_cm = any(self._is_cm_measurement_text(g.get("text", "")) for g in group)
        if not item_is_cm and not group_has_cm:
            return False

        group_box = self._union_bbox([g["bbox"] for g in group])
        ax1, ay1, ax2, ay2 = group_box
        bx1, by1, bx2, by2 = item["bbox"]
        ah, bh = max(1, ay2 - ay1), max(1, by2 - by1)
        y_overlap = min(ay2, by2) - max(ay1, by1)
        center_close = abs(((ay1 + ay2) / 2) - ((by1 + by2) / 2)) <= max(ah, bh) * 1.2
        same_row = y_overlap > -max(8, min(ah, bh) * 0.6) or center_close
        if not same_row:
            return False

        horizontal_gap = max(0, max(bx1 - ax2, ax1 - bx2))
        return horizontal_gap <= max(80, int(max(ax2 - ax1, bx2 - bx1) * 0.9))

    def _bbox_intersects_or_close(self, a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> bool:
        ax1, ay1, ax2, ay2 = map(int, a)
        bx1, by1, bx2, by2 = map(int, b)
        aw, ah = max(1, ax2 - ax1), max(1, ay2 - ay1)
        bw, bh = max(1, bx2 - bx1), max(1, by2 - by1)
        pad_x = max(12, int(min(aw, bw) * 0.18))
        pad_y = max(8, int(min(ah, bh) * 0.85))
        return not (
            ax2 + pad_x < bx1
            or bx2 + pad_x < ax1
            or ay2 + pad_y < by1
            or by2 + pad_y < ay1
        )

    def _union_bbox(self, boxes: List[Tuple[int, int, int, int]]) -> Tuple[int, int, int, int]:
        return (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )

    def _merge_dense_processed_blocks(self, processed_blocks: List, img_w: int, img_h: int) -> List[Tuple[str, tuple]]:
        """Merge local OCR fragments that would otherwise be drawn on top of each other."""
        normalized = []
        for text, bbox in processed_blocks:
            if not bbox or len(bbox) < 4:
                continue
            bb = self._clip_bbox(tuple(map(int, bbox[:4])), img_h, img_w)
            if bb[2] <= bb[0] or bb[3] <= bb[1]:
                continue
            normalized.append({"text": str(text or "").strip(), "bbox": bb})

        if len(normalized) < 2:
            return [(b["text"], b["bbox"]) for b in normalized]

        groups = []
        for item in sorted(normalized, key=lambda x: (x["bbox"][1], x["bbox"][0])):
            target = None
            for group in groups:
                group_box = self._union_bbox([g["bbox"] for g in group])
                if self._bbox_intersects_or_close(group_box, item["bbox"]) or self._should_attach_cm_to_group(group, item):
                    target = group
                    break
            if target is None:
                groups.append([item])
            else:
                target.append(item)

        changed = True
        while changed:
            changed = False
            merged = []
            while groups:
                group = groups.pop(0)
                group_box = self._union_bbox([g["bbox"] for g in group])
                match_idx = None
                for idx, other in enumerate(groups):
                    other_box = self._union_bbox([g["bbox"] for g in other])
                    if self._bbox_intersects_or_close(group_box, other_box) or any(
                        self._should_attach_cm_to_group(group, candidate) for candidate in other
                    ):
                        match_idx = idx
                        break
                if match_idx is None:
                    merged.append(group)
                else:
                    group.extend(groups.pop(match_idx))
                    groups.append(group)
                    changed = True
            groups = merged

        merged_blocks = []
        for group in groups:
            group = sorted(group, key=lambda x: (x["bbox"][1], x["bbox"][0]))
            if len(group) == 1:
                merged_blocks.append((group[0]["text"], group[0]["bbox"]))
                continue
            boxes = [g["bbox"] for g in group]
            union = self._union_bbox(boxes)
            uw, uh = union[2] - union[0], union[3] - union[1]
            total_area = sum(max(1, (b[2] - b[0]) * (b[3] - b[1])) for b in boxes)
            density = total_area / max(1, uw * uh)
            should_merge = density > 0.10 or len(group) >= 3
            if not should_merge:
                merged_blocks.extend((g["text"], g["bbox"]) for g in group)
                continue
            text = " ".join(g["text"] for g in group if g["text"])
            x1, y1, x2, y2 = union
            # Chỉ nới vài pixel để xóa nét chữ, không kéo khung vào ảnh sản phẩm bên dưới.
            expanded = self._clip_bbox((x1 - 4, y1 - 3, x2 + 4, y2 + 3), img_h, img_w)
            merged_blocks.append((text, expanded))

        return merged_blocks

    def _xyxy(self, bbox) -> Tuple[int, int, int, int]:
        x1, y1, x2, y2 = map(int, bbox[:4])
        return x1, y1, x2, y2

    def _cluster_edges(self, values: List[float], gap: float) -> List[List[float]]:
        groups: List[List[float]] = []
        current: List[float] = []
        for value in sorted(values):
            if not current or value - current[-1] <= gap:
                current.append(value)
            else:
                groups.append(current)
                current = [value]
        if current:
            groups.append(current)
        return groups

    def _text_rows_have_photo_gap(self, items: List[Dict]) -> bool:
        """Poster điểm nổi bật có khoảng trống lớn (ảnh sản phẩm) giữa các dải chữ.

        Bảng size thì các hàng sát nhau. Khoảng cách hàng >= 150px là ảnh nằm giữa,
        không phải một ô của bảng.
        """
        if len(items) < 4:
            return False
        row_groups = self._cluster_edges([float(it["y1"]) for it in items], 18)
        if len(row_groups) < 2:
            return False
        centers = sorted(sum(group) / len(group) for group in row_groups)
        gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        return bool(gaps) and max(gaps) >= 150

    def _looks_like_table(self, items: List[Dict]) -> bool:
        if len(items) < 6:
            return False
        if self._text_rows_have_photo_gap(items):
            return False
        columns = [g for g in self._cluster_edges([it["x1"] for it in items], 28) if len(g) >= 3]
        rows = self._cluster_edges([it["y1"] for it in items], 14)
        return len(columns) >= 2 and len(rows) >= 4

    def _is_compact_label(self, item: Dict) -> bool:
        text = str(item.get("text") or "").strip()
        if not text or item.get("erase_only"):
            return False
        if item["x2"] - item["x1"] > 110:
            return False
        if re.search(r"\d{2,}", text):
            return False
        return len(text) <= 18

    def _is_trailing_measurement(self, text: str) -> bool:
        value = str(text or "").strip()
        if not value or len(value) > 28 or re.search(r"[\u4e00-\u9fff]", value):
            return False
        if not re.search(r"\d", value):
            return False
        return bool(re.search(r"cm|mm|kg|ml|%", value, re.I) or re.fullmatch(r"[~±]?\d[\d./~\s-]*", value))

    def _attach_trailing_measurements(self, items: List[Dict], obstacles: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        measures = [it for it in items if self._is_trailing_measurement(it["text"])]
        measures += [it for it in obstacles if self._is_trailing_measurement(it["text"])]
        consumed = set()
        labels = []
        for item in items:
            if self._is_trailing_measurement(item["text"]):
                continue
            center_y = (item["y1"] + item["y2"]) / 2
            match = None
            for other in sorted(measures, key=lambda it: it["x1"]):
                if id(other) in consumed:
                    continue
                gap = other["x1"] - item["x2"]
                if gap < -4 or gap > 16:
                    continue
                other_center = (other["y1"] + other["y2"]) / 2
                if abs(other_center - center_y) <= max(item["y2"] - item["y1"], other["y2"] - other["y1"], 14):
                    match = other
                    break
            if not match:
                labels.append(item)
                continue
            consumed.add(id(match))
            measure_text = str(match["text"]).strip()
            label = str(item["text"]).strip()
            text = label if measure_text in label else f"{label} {measure_text}".strip()
            labels.append({
                **item,
                "text": text,
                "y1": min(item["y1"], match["y1"]),
                "y2": max(item["y2"], match["y2"]),
                "x2": match["x2"],
            })
        leftover = [it for it in measures if id(it) not in consumed and it in items]
        obstacles_left = [it for it in obstacles if id(it) not in consumed]
        return labels + leftover, obstacles_left

    def _merge_stacked_paragraphs(self, items: List[Dict], image_width: int) -> List[Dict]:
        if len(items) < 2 or image_width < 1:
            return items
        sorted_items = sorted(items, key=lambda it: (it["y1"], it["x1"]))
        used = set()
        out = []
        for item in sorted_items:
            if id(item) in used:
                continue
            group = [item]
            used.add(id(item))
            last = item
            for other in sorted_items:
                if id(other) in used:
                    continue
                prev_w = last["x2"] - last["x1"]
                next_w = other["x2"] - other["x1"]
                gap = other["y1"] - last["y2"]
                both_wide = prev_w >= image_width * 0.42 and next_w >= image_width * 0.42
                shorter_wrap = (
                    prev_w >= image_width * 0.42
                    and next_w >= image_width * 0.28
                    and next_w < prev_w - 8
                )
                if (
                    (both_wide or shorter_wrap)
                    and abs(last["x1"] - other["x1"]) <= 16
                    and -2 <= gap <= 16
                ):
                    group.append(other)
                    used.add(id(other))
                    last = other
            if len(group) == 1:
                out.append(item)
                continue
            out.append({
                **item,
                "text": " ".join(str(entry["text"]).strip() for entry in group if str(entry["text"]).strip()),
                "x1": min(entry["x1"] for entry in group),
                "y1": min(entry["y1"] for entry in group),
                "x2": max(entry["x2"] for entry in group),
                "y2": max(entry["y2"] for entry in group),
            })
        return out

    def _expand_table_cells(self, items: List[Dict], obstacles: List[Dict], image_width: int) -> List[Dict]:
        del image_width
        pool = items + obstacles
        expanded = []
        for item in items:
            src_bbox = (item["x1"], item["y1"], item["x2"], item["y2"])
            contained = []
            area_item = max(1, (item["x2"] - item["x1"]) * (item["y2"] - item["y1"]))
            for other in pool:
                if other is item:
                    continue
                cx = (other["x1"] + other["x2"]) / 2
                cy = (other["y1"] + other["y2"]) / 2
                inside = (
                    item["x1"] + 2 < cx < item["x2"] - 2
                    and item["y1"] + 2 < cy < item["y2"] - 2
                )
                area_other = (other["x2"] - other["x1"]) * (other["y2"] - other["y1"])
                if inside and area_other < area_item * 0.5:
                    contained.append(other)
            if len(contained) >= 2:
                expanded.append({**item, "text": "", "erase_only": True, "src_bbox": src_bbox})
                continue
            line_h = max(12, item["y2"] - item["y1"])
            center_y = (item["y1"] + item["y2"]) / 2
            max_h_gap = max(72, int((item["x2"] - item["x1"]) * 1.4))
            max_v_gap = max(36, int(line_h * 1.6))
            to_the_right = sorted(
                (
                    other for other in pool
                    if other is not item
                    and other["x1"] >= item["x2"] - 4
                    and other["x1"] - item["x2"] <= max_h_gap
                    and abs(((other["y1"] + other["y2"]) / 2) - center_y) <= max(line_h, other["y2"] - other["y1"], 18)
                ),
                key=lambda it: it["x1"],
            )
            right = to_the_right[0] if to_the_right else None
            below_all = sorted(
                (
                    other for other in pool
                    if other is not item
                    and other["y1"] >= item["y2"] - 2
                    and other["y1"] - item["y2"] <= max_v_gap
                    and min(item["x2"], other["x2"]) - max(item["x1"], other["x1"]) > 4
                ),
                key=lambda it: (it["y1"], it["x1"]),
            )
            below = below_all[0] if below_all else None
            x2 = right["x1"] - 8 if right else item["x2"]
            if right and self._is_compact_label(item) and self._is_compact_label(right):
                gap = right["x1"] - item["x2"]
                if gap > 36:
                    x2 = min(x2, item["x2"] + gap // 2)
            y2 = below["y1"] - 4 if below else item["y2"]
            if not below and to_the_right:
                beside = [
                    other for other in to_the_right
                    if abs(((other["y1"] + other["y2"]) / 2) - center_y) <= max(line_h, other["y2"] - other["y1"], 14)
                ]
                if beside:
                    y2 = max(y2, max(other["y2"] for other in beside))
            for other in pool:
                if other is item:
                    continue
                cx = (other["x1"] + other["x2"]) / 2
                cy = (other["y1"] + other["y2"]) / 2
                if cx <= item["x1"] + 6 or cx >= x2 or cy <= item["y1"] + 6 or cy >= y2:
                    continue
                if other["y1"] >= item["y1"] + 4:
                    y2 = min(y2, other["y1"] - 2)
                elif other["x1"] >= item["x1"] + 4:
                    x2 = min(x2, other["x1"] - 2)
            x2 = max(item["x2"], x2)
            y2 = max(item["y2"], y2)
            if below:
                y2 = min(y2, below["y1"] - 2)
            expanded.append({
                **item,
                "src_bbox": src_bbox,
                "x1": item["x1"],
                "y1": item["y1"],
                "x2": max(item["x1"] + 1, int(x2)),
                "y2": max(item["y1"] + 1, int(y2)),
            })
        with_erase = []
        for item in expanded:
            if not self._is_compact_label(item):
                with_erase.append(item)
                continue
            center_y = (item["y1"] + item["y2"]) / 2
            left_sibling = any(
                other is not item
                and self._is_compact_label(other)
                and other["x2"] <= item["x1"] + 6
                and abs(((other["y1"] + other["y2"]) / 2) - center_y) <= 14
                for other in expanded
            )
            if left_sibling:
                with_erase.append(item)
                continue
            titles = [
                other for other in expanded
                if other is not item
                and self._is_compact_label(other)
                and other["x1"] <= item["x1"] + 4
                and other["y2"] <= item["y1"] + 2
                and item["y1"] - other["y2"] <= 24
            ]
            title = max(titles, key=lambda it: it["y1"]) if titles else None
            if not title or title["x1"] >= item["x1"] - 8:
                with_erase.append(item)
                continue
            y = max(0, item["y1"] - 1)
            with_erase.append({
                **item,
                "erase": (title["x1"], y, item["x2"], item["y2"] + 2),
            })
        return with_erase

    def _layout_table_blocks(self, processed_blocks: List, ignore_blocks: List, img_w: int, img_h: int) -> List[Dict] | None:
        items = []
        for text, bbox in processed_blocks:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 <= x1 or y2 <= y1:
                continue
            items.append({"text": str(text or "").strip(), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        obstacles = []
        for text, bbox in ignore_blocks:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 <= x1 or y2 <= y1:
                continue
            obstacles.append({"text": str(text or "").strip(), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        items, obstacles = self._attach_trailing_measurements(items, obstacles)
        items = self._merge_stacked_paragraphs(items, img_w)
        if not self._looks_like_table(items):
            return None
        return self._expand_table_cells(items, obstacles, img_w)

    def _line_block_size(self, font, lines: List[str], pad: int) -> Tuple[int, int]:
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        gap = self._line_gap(getattr(font, "size", self.MIN_FONT_SIZE) or self.MIN_FONT_SIZE)
        width = 1
        height = 0
        for i, line in enumerate(lines or [""]):
            bb = probe.textbbox((0, 0), line or " ", font=font)
            width = max(width, bb[2] - bb[0])
            height += bb[3] - bb[1]
            if i:
                height += gap
        return width + pad * 2, max(height, 1) + 2

    def _fit_cell_lines(
        self,
        text: str,
        width: int,
        height: int,
        min_size: int | None = None,
        max_size: int | None = None,
    ):
        text = re.sub(r"[˙•]+\s*$", "", str(text or "").strip())
        text = re.sub(r"(IP65)(?=[A-Za-z])", r"\1\n", text)
        text = re.sub(r"\s*:\s*", ": ", text)
        text = re.sub(r"\s*,\s*", ", ", text)
        floor = max(6, int(min_size if min_size is not None else self.MIN_FONT_SIZE))
        pad = 2 if width >= 80 else 1
        inner_w = max(8, width - pad * 2)
        inner_h = max(8, height - 2)
        probe = ImageDraw.Draw(Image.new("RGB", (max(width, 8), max(height, 8))))

        def width_of(font, line: str) -> int:
            box = probe.textbbox((0, 0), line, font=font)
            return box[2] - box[0]

        def wrap_pixels(font, value: str) -> List[str]:
            lines: List[str] = []
            for part in str(value or "").split("\n"):
                part = part.strip()
                if not part:
                    continue
                lines.extend(self._wrap_text(part, font, inner_w, probe, stroke_width=0))
            return lines or [str(value or "")]

        def block_fits(font, lines: List[str]) -> bool:
            if not font or not lines:
                return False
            gap = self._line_gap(getattr(font, "size", floor) or floor)
            total_h = 0
            for i, line in enumerate(lines):
                if width_of(font, line) > inner_w + 1:
                    return False
                bb = probe.textbbox((0, 0), line, font=font)
                total_h += bb[3] - bb[1]
                if i:
                    total_h += gap
            return total_h <= inner_h + 1

        body = text
        hi_cap = int(max_size or self.MAX_FONT_SIZE)
        hi = min(self.MAX_FONT_SIZE, hi_cap, max(floor, inner_h))
        for size in range(hi, floor - 1, -1):
            font = self._get_font(size)
            if not font:
                continue
            if "\n" not in body and block_fits(font, [body]):
                return font, [body], pad
            lines = wrap_pixels(font, body)
            if block_fits(font, lines):
                return font, lines, pad
        font = self._get_font(floor) or self._get_font(self.MIN_FONT_SIZE)
        lines = wrap_pixels(font, body) if font else [body]
        return font, lines, pad

    def _region_is_color_photo(self, img: np.ndarray, bbox) -> bool:
        """Ảnh màu (da, áo, sản phẩm). Thanh xám và nền trắng không tính."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return False
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if self._is_text_on_flat_paper(gray):
            return False
        b, g, r = cv2.split(roi)
        color_spread = float(np.mean(np.abs(r.astype(np.int16) - g.astype(np.int16))))
        color_spread += float(np.mean(np.abs(g.astype(np.int16) - b.astype(np.int16))))
        return color_spread > 12 and float(np.std(gray)) > 16

    def _is_text_on_flat_paper(self, gray: np.ndarray) -> bool:
        """Chữ đen trên nền kem/trắng phẳng. Nét chữ làm lệch màu nhưng không phải ảnh sản phẩm."""
        paper = gray >= 200
        if float(np.mean(paper)) < 0.45 or int(np.count_nonzero(paper)) < 20:
            return False
        if float(np.std(gray[paper])) >= 18:
            return False
        ink = (gray < 175).astype(np.uint8)
        count, _labels, stats, _cent = cv2.connectedComponentsWithStats(ink, connectivity=8)
        if count <= 1:
            return True
        largest = float(stats[1:, cv2.CC_STAT_AREA].max()) / float(max(1, ink.size))
        return largest < 0.12

    def _region_is_product_photo(self, img: np.ndarray, bbox) -> bool:
        """Vùng da/kim loại có màu và dải xám giữa — khác nền trắng đen của bảng size."""
        if self._region_is_color_photo(img, bbox):
            return True
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return False
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        std = float(np.std(gray))
        midtones = float(np.mean((gray > 40) & (gray < 215)))
        return std > 26 and midtones > 0.4

    def _box_remainder(self, outer, inner) -> List[Tuple[int, int, int, int]]:
        ox1, oy1, ox2, oy2 = map(int, outer)
        ix1, iy1, ix2, iy2 = map(int, inner)
        ix1, iy1 = max(ox1, ix1), max(oy1, iy1)
        ix2, iy2 = min(ox2, ix2), min(oy2, iy2)
        if ix2 <= ix1 or iy2 <= iy1:
            return [(ox1, oy1, ox2, oy2)]
        parts = []
        if oy1 < iy1:
            parts.append((ox1, oy1, ox2, iy1))
        if iy2 < oy2:
            parts.append((ox1, iy2, ox2, oy2))
        if ox1 < ix1:
            parts.append((ox1, iy1, ix1, iy2))
        if ix2 < ox2:
            parts.append((ix2, iy1, ox2, iy2))
        return parts

    def _table_expansion_covers_photo(self, img: np.ndarray, blocks: List[Dict]) -> bool:
        for item in blocks:
            src = item.get("src_bbox")
            box = item.get("erase") or (item["x1"], item["y1"], item["x2"], item["y2"])
            regions = self._box_remainder(box, src) if src else [tuple(map(int, box))]
            if any(self._region_is_product_photo(img, part) for part in regions):
                return True
        return False

    def _layout_in_situ_blocks(
        self,
        processed_blocks: List,
        ignore_blocks: List,
        img_w: int,
        img_h: int,
    ) -> List[Dict] | None:
        """Giữ mỗi dòng trong hộp OCR, chỉ nới tới chữ bên cạnh. Không gộp cả trang."""
        items = []
        obstacles = []
        for text, bbox in processed_blocks or []:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 <= x1 or y2 <= y1:
                continue
            items.append({"text": str(text or "").strip(), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        for text, bbox in ignore_blocks or []:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 <= x1 or y2 <= y1:
                continue
            obstacles.append({"text": str(text or "").strip(), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        if not items:
            return None
        items, obstacles = self._attach_trailing_measurements(items, obstacles)
        items = self._merge_stacked_paragraphs(items, img_w)
        pool = items + obstacles
        placed = []
        for item in items:
            if not str(item.get("text") or "").strip():
                continue
            src = (item["x1"], item["y1"], item["x2"], item["y2"])
            line_h = max(8, item["y2"] - item["y1"])
            center_y = (item["y1"] + item["y2"]) / 2
            same_row_limit = max(line_h, 12) * 0.85
            rights = sorted(
                (
                    other
                    for other in pool
                    if other is not item
                    and other["x1"] >= item["x2"] - 2
                    and abs(((other["y1"] + other["y2"]) / 2) - center_y) <= same_row_limit
                ),
                key=lambda it: it["x1"],
            )
            right = rights[0] if rights else None
            belows = sorted(
                (
                    other
                    for other in pool
                    if other is not item
                    and other["y1"] >= item["y2"] - 2
                    and min(item["x2"], other["x2"]) - max(item["x1"], other["x1"]) > 2
                ),
                key=lambda it: it["y1"],
            )
            below = belows[0] if belows else None
            width = max(1, item["x2"] - item["x1"])
            if right:
                gap = right["x1"] - item["x2"]
                x2 = item["x2"] + min(40, max(0, gap - 3)) if gap > 72 else max(item["x2"], right["x1"] - 3)
            else:
                extra = max(56, int(width * 2.6))
                x2 = min(img_w - 6, item["x2"] + extra)
            if below:
                room = below["y1"] - 2 - item["y2"]
                y2 = item["y2"] + min(max(0, room), max(line_h, 18))
            else:
                y2 = min(img_h - 2, item["y2"] + max(4, int(line_h * 0.6)))
            placed.append({
                **item,
                "src_bbox": src,
                "x1": item["x1"],
                "y1": item["y1"],
                "x2": max(item["x2"], int(x2)),
                "y2": max(item["y2"], int(y2)),
            })
        return placed or None

    def _draw_lines_in_cell(
        self,
        cell: Image.Image,
        lines: List[str],
        font,
        fill: Tuple[int, int, int],
        pad: int,
        *,
        align: str = "center",
        anchor: Tuple[int, int, int, int] | None = None,
    ) -> None:
        draw = ImageDraw.Draw(cell)
        w, h = cell.size
        ax, ay, aw, ah = anchor or (0, 0, w, h)
        gap = self._line_gap(getattr(font, "size", self.MIN_FONT_SIZE) or self.MIN_FONT_SIZE)
        sizes = []
        total_h = 0
        max_w = 1
        for i, line in enumerate(lines):
            bb = draw.textbbox((0, 0), line, font=font)
            sizes.append(bb)
            max_w = max(max_w, bb[2] - bb[0])
            total_h += bb[3] - bb[1]
            if i:
                total_h += gap
        if align == "top":
            y = ay + 1
        elif align == "top-center":
            y = ay
        else:
            y = ay + max(0, (ah - total_h) // 2)
        for line, bb in zip(lines, sizes):
            lw = bb[2] - bb[0]
            if align == "top":
                x = ax + pad
            else:
                x = ax + max(0, (aw - lw) // 2)
            draw.text((x - bb[0], y - bb[1]), line, font=font, fill=fill)
            y += (bb[3] - bb[1]) + gap
            if align == "top" and y >= ay + ah:
                break

    def _draw_table_blocks(
        self,
        image_data: np.ndarray,
        blocks: List[Dict],
        *,
        protect_color_only: bool = False,
    ) -> np.ndarray:
        img = image_data.copy()
        h_img, w_img = img.shape[:2]
        phone_min = self._phone_min_font_size(w_img)
        is_protected = self._region_is_color_photo if protect_color_only else self._region_is_product_photo
        ordered = sorted(blocks, key=lambda it: ((it["x2"] - it["x1"]) * (it["y2"] - it["y1"])), reverse=True)
        safe_boxes = {}
        for item in ordered:
            src = item.get("src_bbox") or (item["x1"], item["y1"], item["x2"], item["y2"])
            item["ink_rgb"] = self._resolve_ink_rgb(image_data, tuple(map(int, src)))
            if protect_color_only:
                erase = tuple(map(int, src))
            else:
                erase = item.get("erase") or (item["x1"], item["y1"], item["x2"], item["y2"])
                if src and any(is_protected(img, part) for part in self._box_remainder(erase, src)):
                    erase = src
            x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, erase)), h_img, w_img)
            if x2 <= x1 or y2 <= y1 or is_protected(img, (x1, y1, x2, y2)):
                safe_boxes[id(item)] = None
                continue
            keep_bg = False
            if protect_color_only:
                img = self._repaint_bbox_to_background(img, (x1, y1, x2, y2))
                bg_bgr = self._background_bgr(image_data, (x1, y1, x2, y2))
                outside = self._median_bgr(image_data, (
                    max(0, x1 - 6), max(0, y1 - 6), min(w_img, x2 + 6), min(h_img, y2 + 6),
                ))
                paper_bgr = bg_bgr if self._luminance((bg_bgr[2], bg_bgr[1], bg_bgr[0])) > self._luminance((outside[2], outside[1], outside[0])) else outside
                item["_paper"] = self._luminance((paper_bgr[2], paper_bgr[1], paper_bgr[0])) >= 185
                item["_paper_bgr"] = paper_bgr if item["_paper"] else None
            else:
                keep_bg = False
                img[y1:y2, x1:x2] = (255, 255, 255)
            safe_boxes[id(item)] = (x1, y1, x2, y2, keep_bg)
        if protect_color_only:
            sources = [
                tuple(map(int, item.get("src_bbox") or (item["x1"], item["y1"], item["x2"], item["y2"])))
                for item in blocks
                if safe_boxes.get(id(item))
            ]
            for item in blocks:
                saved = safe_boxes.get(id(item))
                if not saved:
                    continue
                text = str(item.get("text") or "").strip()
                src = tuple(map(int, item.get("src_bbox") or (item["x1"], item["y1"], item["x2"], item["y2"])))
                sx1, sy1, sx2, sy2 = src
                src_h = max(2, sy2 - sy1)
                left, right = self._row_slot_bounds(src, [box for box in sources if box != src], w_img)
                slot_w = max(8, right - left)
                glyph_h = max(phone_min, src_h - 2)
                font, lines, pad = self._fit_cell_lines(
                    text,
                    slot_w,
                    max(src_h + 4, phone_min * 4),
                    min_size=phone_min,
                    max_size=glyph_h,
                )
                if not font:
                    continue
                need_w, need_h = self._line_block_size(font, lines, pad)
                need_w = min(need_w, slot_w)
                cx = (sx1 + sx2) // 2
                cy = (sy1 + sy2) // 2
                x1 = int(cx - need_w / 2)
                x1 = min(max(left, x1), max(left, right - need_w))
                if item.get("_paper") and need_h > src_h + 2:
                    y1 = sy1
                else:
                    y1 = int(cy - need_h / 2)
                x1 = max(0, min(x1, w_img - need_w))
                y1 = max(0, min(y1, h_img - 2))
                x2 = min(w_img, x1 + need_w)
                y2 = min(h_img, y1 + need_h)
                item["_draw"] = (font, lines, pad, (x1, y1, x2, y2))
                item["_align"] = "top-center" if item.get("_paper") else "center"
            self._apply_inset_caption_cards(img, blocks, phone_min)
            for item in blocks:
                if item.get("_paper") and item.get("_draw") and item.get("_paper_bgr") is not None:
                    _font, _lines, _pad, (px1, py1, px2, py2) = item["_draw"]
                    if img[py1:py2, px1:px2].size and float(np.mean(img[py1:py2, px1:px2] > 230)) < 0.8:
                        img[py1:py2, px1:px2] = (255, 255, 255)
        pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        for item in blocks:
            text = str(item.get("text") or "").strip()
            if not text or item.get("erase_only"):
                continue
            saved = safe_boxes.get(id(item))
            if not saved:
                continue
            ox1, oy1, ox2, oy2, keep_bg = saved
            x1, y1, x2, y2 = ox1, oy1, ox2, oy2
            prepared = item.get("_draw") if protect_color_only else None
            anchor = None
            if prepared:
                font, lines, pad, (x1, y1, x2, y2) = prepared
                anchor = (0, 0, max(1, x2 - x1), max(1, y2 - y1))
            else:
                w, h = x2 - x1, y2 - y1
                if w < 2 or h < 2:
                    continue
                font, lines, pad = self._fit_cell_lines(text, w, h, min_size=6, max_size=14)
            if not font:
                continue
            x1, y1, x2, y2 = self._clip_bbox((x1, y1, x2, y2), h_img, w_img)
            w, h = x2 - x1, y2 - y1
            if w < 2 or h < 2:
                continue
            fill = item.get("ink_rgb") or (0, 0, 0)
            if keep_bg or prepared:
                cell = pil.crop((x1, y1, x2, y2))
            else:
                cell = Image.new("RGB", (w, h), (255, 255, 255))
            self._draw_lines_in_cell(
                cell,
                lines,
                font,
                fill,
                pad,
                align=item.get("_align") or ("center" if protect_color_only else "top"),
                anchor=anchor,
            )
            pil.paste(cell, (x1, y1))
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

    def check_processed_overlap(self, processed_blocks: List, img_w: int, img_h: int, threshold: float = 0.01) -> Tuple[bool, float]:
        """
        Kiểm tra xem các khối text sau khi dịch (processed_blocks) có bị đè lên nhau không.
        Trả về: (True/False, tỷ lệ đè lớn nhất)
        """
        if not processed_blocks or len(processed_blocks) < 2:
            return False, 0.0

        measure_img = Image.new("RGB", (img_w, img_h))
        draw = ImageDraw.Draw(measure_img)

        new_boxes = []
        for text, old_bbox in processed_blocks:
            if not text or not text.strip():
                continue
            bb = tuple(map(int, old_bbox))
            final_bbox = self._calc_box_centered(text, bb, img_w, img_h, draw)
            new_boxes.append(final_bbox)

        # 2. Kiểm tra va chạm giữa các hộp mới
        max_overlap_ratio = 0.0
        has_overlap = False

        for i in range(len(new_boxes)):
            for j in range(i + 1, len(new_boxes)):
                box1 = new_boxes[i]
                box2 = new_boxes[j]

                # Tính diện tích giao nhau
                x_left = max(box1[0], box2[0])
                y_top = max(box1[1], box2[1])
                x_right = min(box1[2], box2[2])
                y_bottom = min(box1[3], box2[3])

                if x_right > x_left and y_bottom > y_top:
                    intersection_area = (x_right - x_left) * (y_bottom - y_top)
                    
                    # Tính diện tích từng hộp
                    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
                    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
                    
                    # Tính tỷ lệ đè so với hộp nhỏ hơn (để nhạy hơn)
                    min_area = min(area1, area2)
                    if min_area > 0:
                        ratio = intersection_area / min_area
                        if ratio > max_overlap_ratio:
                            max_overlap_ratio = ratio
                        
                        if ratio > threshold:
                            has_overlap = True

        return has_overlap, max_overlap_ratio

    def process_image_with_text(self, image_data: np.ndarray, processed_blocks: List, ignore_blocks: List) -> np.ndarray:
        img_h, img_w = image_data.shape[:2]
        table_blocks = self._layout_table_blocks(processed_blocks, ignore_blocks, img_w, img_h)
        if table_blocks is not None and self._table_expansion_covers_photo(image_data, table_blocks):
            print("  [TABLE] bỏ — ô chữ đè lên ảnh sản phẩm")
            table_blocks = None
        if table_blocks is not None:
            print(f"  [TABLE] vẽ {len(table_blocks)} ô trong khung, không gộp đè")
            return self.add_smart_watermark(self._draw_table_blocks(image_data, table_blocks), [])
        in_situ = self._layout_in_situ_blocks(processed_blocks, ignore_blocks, img_w, img_h)
        if in_situ:
            for item in in_situ:
                src = item.get("src_bbox")
                box = (item["x1"], item["y1"], item["x2"], item["y2"])
                if src and self._region_is_color_photo(image_data, box):
                    item["x1"], item["y1"], item["x2"], item["y2"] = src
                    item.pop("erase", None)
            print(f"  [IN SITU] vẽ {len(in_situ)} khối đúng hộp OCR")
            return self.add_smart_watermark(
                self._draw_table_blocks(image_data, in_situ, protect_color_only=True),
                [],
            )
        processed_blocks = self._merge_dense_processed_blocks(processed_blocks, img_w, img_h)

        all_blocks = []
        for t, b in processed_blocks:
            all_blocks.append({'text': t, 'bbox': b, 'area': (b[2]-b[0])*(b[3]-b[1]), 'is_ignore': False})
        for t, b in ignore_blocks:
            all_blocks.append({'text': t, 'bbox': b, 'area': (b[2]-b[0])*(b[3]-b[1]), 'is_ignore': True})

        if not processed_blocks:
            return self.add_smart_watermark(image_data, all_blocks)

        # Clean img dùng để xóa nền
        clean_img = image_data.copy()
        
        # Sắp xếp xử lý
        sorted_blocks = sorted(all_blocks, key=lambda x: x["area"], reverse=True)

        # 1. Xóa nền: bbox OCR (+ đệm trong _expand_bbox_for_inpaint / _advanced_inpainting)
        for item in sorted_blocks:
            if item["is_ignore"]:
                continue
            erase_bbox = tuple(map(int, item["bbox"]))
            if self._region_is_product_photo(clean_img, erase_bbox):
                item["skip_photo"] = True
                continue
            clean_img = self._advanced_inpainting(clean_img, erase_bbox)

        pil_img = Image.fromarray(cv2.cvtColor(clean_img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        for item in sorted_blocks:
            if item["is_ignore"] or item.get("skip_photo") or not str(item.get("text", "")).strip():
                continue

            final_bbox = self._calc_box_centered(
                item["text"], tuple(map(int, item["bbox"])), img_w, img_h, draw
            )
            w = final_bbox[2] - final_bbox[0]
            h = final_bbox[3] - final_bbox[1]
            fs, lines = self._binary_search_font(item["text"], w, h, draw)

            # Lấy màu nền tại vị trí box cũ để chọn màu chữ
            bx1, by1, bx2, by2 = map(int, item['bbox'])
            # Crop vùng nhỏ ở tâm box cũ
            cx, cy = (bx1+bx2)//2, (by1+by2)//2
            roi_sample = clean_img[cy-2:cy+2, cx-2:cx+2]
            avg_color = self._get_avg_color(roi_sample)

            font = self._get_font(fs)
            style = self._get_text_style(avg_color)
            # Force high-contrast pure tones; avoid gray text inherited from OCR colors.
            if style["text_color"] != (255, 255, 255):
                style["text_color"] = (0, 0, 0)
                style["stroke_color"] = (255, 255, 255)
                style["use_shadow"] = False
            else:
                style["text_color"] = (255, 255, 255)
                style["stroke_color"] = (0, 0, 0)
                style["use_shadow"] = True

            if w < 2 or h < 2:
                continue
            # Vẽ trên crop để chữ dài không tràn sang cột bên cạnh hoặc lên ảnh.
            crop = pil_img.crop(final_bbox)
            self._draw_text_centered(ImageDraw.Draw(crop), lines, (0, 0, w, h), font, style)
            pil_img.paste(crop, (final_bbox[0], final_bbox[1]))

        # Chuyển lại OpenCV
        final_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return self.add_smart_watermark(final_img, all_blocks)

    def add_smart_watermark(self, img_cv, text_blocks):
        """Thêm watermark logo thông minh vào ảnh với xử lý lỗi type safe"""
        if self.logo_img is None: 
            return img_cv
        
        try:
            # Kiểm tra và chuyển đổi type an toàn
            if not isinstance(img_cv, np.ndarray):
                print(f"⚠️ Warning: img_cv không phải numpy array, type: {type(img_cv)}")
                return img_cv
                
            # Lấy kích thước ảnh và đảm bảo là integer
            h_img, w_img = img_cv.shape[:2]
            h_img = int(h_img)
            w_img = int(w_img)
            
            print(f"DEBUG watermark - h_img: {h_img} ({type(h_img)}), w_img: {w_img} ({type(w_img)})")
            
            if w_img > h_img * 2.5: 
                return img_cv 

            if self.logo_img is None:
                return img_cv
                
            # Lấy kích thước logo
            h_logo, w_logo = self.logo_img.shape[:2]
            h_logo = int(h_logo)
            w_logo = int(w_logo)
            
            # Tính toán kích thước target
            target_w = max(40, int(w_img * 0.15))
            target_h = int(h_logo * (target_w / w_logo))
            
            target_w = int(target_w)
            target_h = int(target_h)
            
            print(f"DEBUG watermark - target_w: {target_w}, target_h: {target_h}")
            
            # Resize logo
            logo_resized = cv2.resize(self.logo_img, (target_w, target_h), interpolation=cv2.INTER_AREA)
            
            margin = 20
            occupied = []
            
            # Xử lý text_blocks an toàn
            for b in text_blocks:
                if 'bbox' in b:
                    try:
                        # Đảm bảo tất cả giá trị là integer
                        if isinstance(b['bbox'], (list, tuple)) and len(b['bbox']) == 4:
                            x1, y1, x2, y2 = b['bbox']
                            x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                            occupied.append((x1-5, y1-5, x2+5, y2+5))
                        else:
                            print(f"⚠️ Warning: bbox không hợp lệ: {b.get('bbox')}")
                    except Exception as e:
                        print(f"⚠️ Lỗi xử lý bbox: {b.get('bbox')}, error: {e}")
            
            pos = None
            
            # Tìm vị trí đặt logo
            for x_start in [w_img - target_w - margin, margin]:
                x_start = int(x_start)
                y_curr = margin
                
                while y_curr + target_h < h_img:
                    # Tạo rect với tất cả giá trị integer
                    rect = (x_start, y_curr, x_start + target_w, y_curr + target_h)
                    
                    # Kiểm tra va chạm an toàn
                    collision = False
                    for o in occupied:
                        try:
                            o_x1, o_y1, o_x2, o_y2 = o
                            # Ép kiểu về integer cho chắc
                            o_x1, o_y1, o_x2, o_y2 = int(o_x1), int(o_y1), int(o_x2), int(o_y2)
                            
                            if not (rect[2] < o_x1 or rect[0] > o_x2 or rect[3] < o_y1 or rect[1] > o_y2):
                                collision = True
                                break
                        except Exception as e:
                            print(f"⚠️ Lỗi kiểm tra va chạm: {o}, error: {e}")
                    
                    if not collision: 
                        pos = (x_start, y_curr)
                        break
                    y_curr += 20
                    
                if pos: 
                    break
            
            if not pos: 
                pos = (int(w_img - target_w - margin), int(margin))
            
            x, y = pos
            x = int(x)
            y = int(y)
            
            print(f"DEBUG watermark - final position: x={x}, y={y}, target_w={target_w}, target_h={target_h}")
            
            # Kiểm tra biên cuối cùng
            if (y + target_h > h_img) or (x + target_w > w_img) or (y < 0) or (x < 0):
                print(f"⚠️ Logo vượt quá biên ảnh, bỏ qua watermark")
                return img_cv

            # Thêm logo vào ảnh
            if len(logo_resized.shape) == 3 and logo_resized.shape[2] == 4:
                # Logo có alpha channel
                b, g, r, a = cv2.split(logo_resized)
                roi = img_cv[y:y+target_h, x:x+target_w]
                alpha = a / 255.0
                for c in range(3): 
                    roi[:,:,c] = (alpha * logo_resized[:,:,c] + (1.0-alpha) * roi[:,:,c])
                img_cv[y:y+target_h, x:x+target_w] = roi
            else:
                # Logo không có alpha channel
                img_cv[y:y+target_h, x:x+target_w] = logo_resized
            
            print(f"✅ Đã thêm watermark tại vị trí ({x}, {y})")
            return img_cv
            
        except Exception as e:
            print(f"⚠️ Lỗi không mong muốn trong add_smart_watermark: {e}")
            import traceback
            traceback.print_exc()
            return img_cv

    def resize_to_target_size(self, image_data: np.ndarray, target_width: int, target_height: int) -> np.ndarray:
        try:
            current_height, current_width = image_data.shape[:2]
            if current_width == target_width and current_height == target_height:
                return image_data
            return cv2.resize(image_data, (target_width, target_height), interpolation=cv2.INTER_CUBIC)
        except Exception:
            return image_data