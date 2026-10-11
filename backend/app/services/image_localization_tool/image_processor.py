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
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.size else None
        radius = 3
        if gray is not None and gray.size:
            light = float(np.mean(gray >= 150))
            dark = float(np.mean(gray <= 80))
            if light >= 0.35 and 0.04 <= dark <= 0.45:
                x1, y1 = max(0, x1 - 3), max(0, y1 - 3)
                x2, y2 = min(w_img, x2 + 3), min(h_img, y2 + 3)
                roi = img[y1:y2, x1:x2]
                gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                mask = (gray <= 140).astype(np.uint8) * 255
                mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
                radius = 6
            else:
                mask = self._build_text_mask(roi)
        else:
            mask = self._build_text_mask(roi)
        if mask.size == 0 or int(np.count_nonzero(mask)) < 8:
            return img
        full_mask = np.zeros((h_img, w_img), dtype=np.uint8)
        full_mask[y1:y2, x1:x2] = mask
        return cv2.inpaint(img, full_mask, radius, cv2.INPAINT_TELEA)

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
        pending = [
            item for item in blocks
            if item.get("_paper") and item.get("_draw") and item.get("src_bbox") and not item.get("_locked")
        ]
        used = set()
        for item in pending:
            if id(item) in used:
                continue
            src = tuple(map(int, item["src_bbox"]))
            row = [item]
            for other in pending:
                if other is item or id(other) in used:
                    continue
                ob = tuple(map(int, other["src_bbox"]))
                overlap_y = min(src[3], ob[3]) - max(src[1], ob[1])
                shorter = max(1, min(src[3] - src[1], ob[3] - ob[1]))
                if overlap_y >= shorter * 0.35:
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
            spans = []
            for index, part in enumerate(row):
                src_box = tuple(map(int, part["src_bbox"]))
                x1 = src_box[0]
                if index + 1 < n:
                    x2 = int(row[index + 1]["src_bbox"][0]) - 3
                else:
                    box_w = max(8, src_box[2] - src_box[0])
                    x2 = min(card_x2, src_box[2] + max(24, box_w))
                spans.append((x1, max(x1 + 8, x2)))
            row_heights = sorted(
                max(8, int(part["src_bbox"][3]) - int(part["src_bbox"][1])) for part in row
            )
            typical = row_heights[len(row_heights) // 2]
            fitted = []
            tallest = 0
            for part, (x1, x2) in zip(row, spans):
                text = str(part.get("text") or "").strip()
                src_h = max(12, int(part["src_bbox"][3]) - int(part["src_bbox"][1]))
                font, lines, pad = self._fit_cell_lines(
                    text,
                    max(8, x2 - x1 - 4),
                    max(src_h + 4, src_h),
                    min_size=9,
                    max_size=max(12, min(src_h, int(typical * 1.25))),
                )
                if not font:
                    fitted.append(None)
                    continue
                _need_w, need_h = self._line_block_size(font, lines, pad)
                tallest = max(tallest, min(need_h, src_h + 4))
                fitted.append((font, lines, pad))
            if tallest < 8:
                continue
            y1 = max(card_y1, min(int(it["src_bbox"][1]) for it in row) - 2)
            y2 = min(h_img - 2, y1 + tallest + 4)
            below = []
            for other in blocks:
                if other in row or not other.get("src_bbox"):
                    continue
                ob = tuple(map(int, other["src_bbox"]))
                if ob[1] >= y1 + 4:
                    below.append(ob[1])
            if below:
                y2 = min(y2, min(below) - 2)
            if y2 - y1 < 8:
                continue
            before = img.copy()
            color = row[0].get("_paper_bgr") or (255, 255, 255)
            for (x1, x2), pack in zip(spans, fitted):
                if not pack or x2 <= x1:
                    continue
                self._paint_panel_keep_art(img, before, (x1, y1, min(x2, w_img - 2), y2), color)
            for part, (x1, x2), pack in zip(row, spans, fitted):
                if not pack:
                    continue
                font, lines, pad = pack
                part["ink_rgb"] = (0, 0, 0)
                part["_align"] = "top"
                part["_draw"] = (font, lines, pad, (x1, y1 + 1, min(x2, w_img - 2), y2))

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
        local = self._uniform_surround_bgr(img, (x1, y1, x2, y2), pad=pad)
        if local is None:
            return self._inpaint_text_strokes(img, (x1, y1, x2, y2))
        bg = np.array(local, dtype=np.uint8)
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
        local = self._uniform_surround_bgr(img, (x1, y1, x2, y2))
        if local is None:
            return self._inpaint_text_strokes(img, (x1, y1, x2, y2))
        fill = np.array(local, dtype=np.uint8)
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
            merged = {
                **item,
                "text": text,
                "y1": min(item["y1"], match["y1"]),
                "y2": max(item["y2"], match["y2"]),
                "x2": match["x2"],
            }
            if item.get("src_boxes") or match.get("src_boxes"):
                boxes = list(item.get("src_boxes") or [(item["x1"], item["y1"], item["x2"], item["y2"])])
                boxes.extend(match.get("src_boxes") or [(match["x1"], match["y1"], match["x2"], match["y2"])])
                merged["src_boxes"] = boxes
            labels.append(merged)
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
        if self._flat_panel_bgr(img, (x1, y1, x2, y2)) is not None:
            return False
        b, g, r = cv2.split(roi)
        color_spread = float(np.mean(np.abs(r.astype(np.int16) - g.astype(np.int16))))
        color_spread += float(np.mean(np.abs(g.astype(np.int16) - b.astype(np.int16))))
        return color_spread > 12 and float(np.std(gray)) > 16

    def _smooth_field_light_caption(self, img: np.ndarray, bbox) -> bool:
        """Chữ sáng trên nền trời/gradient mịn. Khác ảnh sản phẩm và khác thẻ màu đặc."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return False
        gray = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY).astype(np.float32)
        blur = cv2.GaussianBlur(gray, (0, 0), 2.5)
        glyphs = (gray - blur > 8) & (gray > 170)
        glyph_u8 = glyphs.astype(np.uint8) * 255
        count, _labels, stats, _cent = cv2.connectedComponentsWithStats(glyph_u8, connectivity=8)
        if count <= 1:
            return False
        areas = stats[1:, cv2.CC_STAT_AREA]
        strokes = areas[areas >= 12]
        if strokes.size == 0 or float(strokes.sum()) / float(max(1, areas.sum())) < 0.85:
            return False
        frac = float(np.mean(glyphs))
        if frac < 0.08 or frac > 0.5:
            return False
        field = ~glyphs
        if float(np.mean(field)) < 0.4 or float(np.mean(gray[field])) < 130:
            return False
        resid = np.abs(gray - blur)
        if float(np.std(resid[field])) > 16:
            return False
        field_bgr = np.median(img[y1:y2, x1:x2][field], axis=0)
        blue, green, red = (int(field_bgr[0]), int(field_bgr[1]), int(field_bgr[2]))
        if blue < 140 or green < 140:
            return False
        if red - blue > 25:
            return False
        return True

    def _erase_light_glyphs(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa nét chữ sáng trên nền mịn, giữ gradient phía sau."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(bbox, h_img, w_img)
        x1, y1 = max(0, x1 - 2), max(0, y1 - 2)
        x2, y2 = min(w_img, x2 + 2), min(h_img, y2 + 2)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return img
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if gray.shape[0] >= 28:
            level = float(np.percentile(gray, 40))
            mask = (gray.astype(np.float32) > level + 26).astype(np.uint8) * 255
            mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1)
            painted = roi.copy()
            selected = mask > 0
            for yy in range(painted.shape[0]):
                field = painted[yy][~selected[yy]]
                if field.shape[0] < 6:
                    continue
                painted[yy][selected[yy]] = np.median(field, axis=0)
            edge = cv2.subtract(cv2.dilate(mask, np.ones((3, 3), np.uint8)), cv2.erode(mask, np.ones((3, 3), np.uint8)))
            blur = cv2.GaussianBlur(painted, (0, 0), 0.8)
            painted[edge > 0] = blur[edge > 0]
            out = img.copy()
            out[y1:y2, x1:x2] = painted
            return out
        gray_f = gray.astype(np.float32)
        blur = cv2.GaussianBlur(gray_f, (0, 0), 2.2)
        mask = ((gray_f - blur > 8) & (gray_f > 165)).astype(np.uint8) * 255
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        if int(np.count_nonzero(mask)) < 8:
            return img
        full = np.zeros((h_img, w_img), dtype=np.uint8)
        full[y1:y2, x1:x2] = mask
        return cv2.inpaint(img, full, 5, cv2.INPAINT_TELEA)

    def _sky_limit_y(self, img: np.ndarray, bbox) -> int | None:
        """Đường viền sáng ngay dưới nhãn, để chữ không tràn khỏi ô icon."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        xa, xb = max(0, x1 - 24), min(w_img, x2 + 24)
        for yy in range(y2 + 2, min(h_img, y2 + 42)):
            seg = gray[yy, xa:xb]
            if seg.size >= 8 and float(np.mean(seg > 215)) > 0.55:
                return yy
        return None

    def _is_text_on_flat_paper(self, gray: np.ndarray) -> bool:
        """Chữ đen trên nền kem/trắng phẳng. Nét chữ làm lệch màu nhưng không phải ảnh sản phẩm."""
        paper = gray >= 185
        if float(np.mean(paper)) < 0.42 or int(np.count_nonzero(paper)) < 20:
            return False
        if float(np.std(gray[paper])) >= 18:
            return False
        ink = (gray < 175).astype(np.uint8)
        count, _labels, stats, _cent = cv2.connectedComponentsWithStats(ink, connectivity=8)
        if count <= 1:
            return True
        largest = float(stats[1:, cv2.CC_STAT_AREA].max()) / float(max(1, ink.size))
        return largest < 0.16

    def _flat_panel_bgr(self, img: np.ndarray, bbox) -> Tuple[int, int, int] | None:
        """Nền một màu (thẻ nâu, ô xanh, giấy sáng). None nếu là ảnh sản phẩm có vân."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 6 or y2 - y1 < 6:
            return None
        pixels = img[y1:y2, x1:x2].reshape(-1, 3).astype(np.int16)
        if pixels.shape[0] < 12:
            return None
        med = np.median(pixels, axis=0)
        close = np.max(np.abs(pixels - med), axis=1) < 34
        if float(np.mean(close)) < 0.52:
            return None
        if float(np.std(pixels[close], axis=0).mean()) > 12:
            return None
        return (int(med[0]), int(med[1]), int(med[2]))

    def _panel_clip(self, img: np.ndarray, bbox, color: Tuple[int, int, int]) -> Tuple[int, int, int, int]:
        """Vùng cùng màu quanh hộp chữ, không tràn sang áo/sản phẩm."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        target = np.array(color, dtype=np.int16)

        def row_match(y: int, xa: int, xb: int) -> bool:
            if xb - xa < 4 or y < 0 or y >= h_img:
                return False
            row = img[y, xa:xb].astype(np.int16)
            return float(np.mean(np.max(np.abs(row - target), axis=1) < 36)) > 0.62

        top, bot = y1, y2
        while top > 0 and row_match(top - 1, x1, x2):
            top -= 1
        while bot < h_img and row_match(bot, x1, x2):
            bot += 1
        left, right = x1, x2
        mid_y1, mid_y2 = max(top, y1), min(bot, y2)
        if mid_y2 <= mid_y1:
            mid_y1, mid_y2 = top, bot

        def col_match(x: int) -> bool:
            if x < 0 or x >= w_img or mid_y2 - mid_y1 < 4:
                return False
            col = img[mid_y1:mid_y2, x].astype(np.int16)
            return float(np.mean(np.max(np.abs(col - target), axis=1) < 36)) > 0.62

        while left > 0 and col_match(left - 1):
            left -= 1
        while right < w_img and col_match(right):
            right += 1
        return left, top, right, bot

    def _flat_run_right(self, img: np.ndarray, x: int, y1: int, y2: int, color: Tuple[int, int, int]) -> int:
        """Đi sang phải trên nền phẳng. Nét chữ cùng hàng không tính là hết nền."""
        h_img, w_img = img.shape[:2]
        y1 = max(0, min(h_img - 1, int(y1)))
        y2 = max(y1 + 1, min(h_img, int(y2)))
        target = np.array(color, dtype=np.int16)
        panel_rgb = (int(color[2]), int(color[1]), int(color[0]))
        light_panel = self._luminance(panel_rgb) >= 170
        cursor = max(0, int(x))
        while cursor < w_img - 1:
            col = img[y1:y2, cursor]
            if col.size == 0:
                break
            near = np.max(np.abs(col.astype(np.int16) - target), axis=1) < 42
            spread = col.max(axis=1).astype(np.int16) - col.min(axis=1).astype(np.int16)
            if int(np.count_nonzero(spread >= 36)) >= 4:
                break
            gray = cv2.cvtColor(col.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY).ravel()
            ink = (gray < 165) if light_panel else (gray > 150)
            plain = near & (spread < 36)
            if float(np.mean(plain | (ink & (spread < 28)))) < 0.72:
                break
            cursor += 1
        return cursor

    def _illustration_left(self, img: np.ndarray, x: int, y1: int, y2: int) -> int:
        """Cột trái nhất của hình có màu (sơ đồ, mũi tên), bên phải mốc x."""
        h_img, w_img = img.shape[:2]
        y1 = max(0, min(h_img - 1, int(y1)))
        y2 = max(y1 + 1, min(h_img, int(y2)))
        x = max(0, min(w_img - 1, int(x)))
        band = img[y1:y2, x:w_img]
        if band.size == 0:
            return w_img
        spread = band.max(axis=2).astype(np.int16) - band.min(axis=2).astype(np.int16)
        hits = np.where((spread >= 36).sum(axis=0) >= 4)[0]
        if hits.size == 0:
            return w_img
        return x + int(hits[0])

    def _uniform_surround_bgr(self, img: np.ndarray, rect, pad: int = 6) -> Tuple[int, int, int] | None:
        """Màu nền ngay ngoài hộp. None nếu vành không cùng một màu."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, rect)), h_img, w_img)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return None
        ox1, oy1 = max(0, x1 - pad), max(0, y1 - pad)
        ox2, oy2 = min(w_img, x2 + pad), min(h_img, y2 + pad)
        outer = img[oy1:oy2, ox1:ox2]
        if outer.size == 0:
            return None
        ring = np.ones(outer.shape[:2], dtype=bool)
        ring[(y1 - oy1):(y2 - oy1), (x1 - ox1):(x2 - ox1)] = False
        samples = outer[ring]
        if samples.shape[0] < 12:
            return None
        spread = samples.max(axis=1).astype(np.int16) - samples.min(axis=1).astype(np.int16)
        plain = samples[spread < 30]
        if plain.shape[0] < 12:
            return None
        med = np.median(plain, axis=0)
        close = np.max(np.abs(plain.astype(np.int16) - med.astype(np.int16)), axis=1) < 24
        if float(np.mean(close)) < 0.7:
            return None
        if float(np.std(plain[close].astype(np.float32), axis=0).mean()) > 12:
            return None
        return (int(med[0]), int(med[1]), int(med[2]))

    def _plate_bgr(self, img: np.ndarray, rect) -> Tuple[int, int, int]:
        """Màu nền đặc để che chữ cũ. Ưu tiên vành cùng màu, không thì lấy phần sáng quanh hộp."""
        local = self._uniform_surround_bgr(img, rect, pad=5)
        if local is not None:
            return local
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, rect)), h_img, w_img)
        pad = 5
        ox1, oy1 = max(0, x1 - pad), max(0, y1 - pad)
        ox2, oy2 = min(w_img, x2 + pad), min(h_img, y2 + pad)
        outer = img[oy1:oy2, ox1:ox2]
        if outer.size == 0:
            return self._background_bgr(img, (x1, y1, x2, y2))
        ring = np.ones(outer.shape[:2], dtype=bool)
        ring[(y1 - oy1):(y2 - oy1), (x1 - ox1):(x2 - ox1)] = False
        samples = outer[ring]
        if samples.shape[0] < 8:
            samples = outer.reshape(-1, 3)
        tone = samples.mean(axis=1)
        keep = samples[tone >= np.percentile(tone, 55)]
        if keep.shape[0] < 4:
            keep = samples
        med = np.median(keep, axis=0)
        return (int(med[0]), int(med[1]), int(med[2]))

    def _solid_cover_text(self, img: np.ndarray, bbox) -> np.ndarray:
        """Tô kín hộp chữ bằng nền đặc để che hết nét cũ. Không đè ảnh sản phẩm."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return img
        if self._region_is_color_photo(img, (x1, y1, x2, y2)) and not self._is_light_chart_surface(img, (x1, y1, x2, y2)):
            return img
        px1, py1, px2, py2 = self._expand_light_ink(img, x1, y1, x2, y2)
        if self._region_is_color_photo(img, (px1, py1, px2, py2)):
            px1, py1, px2, py2 = x1, y1, x2, y2
        color = np.array(self._plate_bgr(img, (px1, py1, px2, py2)), dtype=np.uint8)
        out = img.copy()
        out[py1:py2, px1:px2] = color
        return out

    def _expand_light_ink(self, img: np.ndarray, x1: int, y1: int, x2: int, y2: int, margin: int = 6):
        """Nới hộp tới nét chữ sát bên trên nền sáng, không nuốt cả ảnh tối."""
        h_img, w_img = img.shape[:2]
        xa, ya = max(0, x1 - margin), max(0, y1 - margin)
        xb, yb = min(w_img, x2 + margin), min(h_img, y2 + margin)
        gray = cv2.cvtColor(img[ya:yb, xa:xb], cv2.COLOR_BGR2GRAY)
        if float(np.mean(gray >= 140)) < 0.5:
            return x1, y1, x2, y2
        ink = gray < 150
        if float(np.mean(ink)) > 0.32 or int(np.count_nonzero(ink)) < 8:
            return max(0, x1 - 2), max(0, y1 - 2), min(w_img, x2 + 2), min(h_img, y2 + 2)
        ys, xs = np.where(ink)
        return xa + int(xs.min()), ya + int(ys.min()), xa + int(xs.max()) + 1, ya + int(ys.max()) + 1

    def _is_light_chart_surface(self, img: np.ndarray, bbox) -> bool:
        """Nền bảng sáng, ít màu. Khác da và ảnh sản phẩm."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, bbox)), h_img, w_img)
        if x2 - x1 < 4 or y2 - y1 < 4:
            return False
        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        if float(np.mean(gray >= 140)) < 0.45:
            return False
        b, g, r = cv2.split(roi)
        spread = float(np.mean(np.abs(r.astype(np.int16) - g.astype(np.int16))))
        spread += float(np.mean(np.abs(g.astype(np.int16) - b.astype(np.int16))))
        return spread < 14

    def _paint_panel_keep_art(self, img: np.ndarray, original: np.ndarray, rect, color: Tuple[int, int, int]) -> None:
        """Tô nền đặc bằng màu ngay quanh vị trí đó. Không tô nếu quanh đó không cùng màu."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._clip_bbox(tuple(map(int, rect)), h_img, w_img)
        if x2 - x1 < 2 or y2 - y1 < 2:
            return
        local = self._uniform_surround_bgr(original, (x1, y1, x2, y2)) or self._uniform_surround_bgr(img, (x1, y1, x2, y2))
        if local is None:
            return
        color = local
        orig = original[y1:y2, x1:x2]
        diff = np.max(np.abs(orig.astype(np.int16) - np.array(color, dtype=np.int16)), axis=2)
        far = (diff > 36).astype(np.uint8) * 255
        art = cv2.morphologyEx(far, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
        roi = img[y1:y2, x1:x2]
        roi[art == 0] = color
        img[y1:y2, x1:x2] = roi

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

    def _spec_items(self, processed_blocks: List, ignore_blocks: List, img_w: int, img_h: int) -> List[Dict]:
        items = []
        for text, bbox in processed_blocks or []:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 <= x1 or y2 <= y1 or not str(text or "").strip():
                continue
            items.append({
                "text": str(text).strip(),
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "src_boxes": [(x1, y1, x2, y2)],
            })
        obstacles = []
        for text, bbox in ignore_blocks or []:
            if not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = self._clip_bbox(self._xyxy(bbox), img_h, img_w)
            if x2 > x1 and y2 > y1:
                obstacles.append({"text": str(text or "").strip(), "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        items, _obstacles = self._attach_trailing_measurements(items, obstacles)
        return items

    def _dominant_spec_column(self, items: List[Dict]) -> List[Dict] | None:
        """Một cột thông số xếp dọc, không phải bảng nhiều cột."""
        if len(items) < 5:
            return None
        groups: List[List[Dict]] = []
        for item in sorted(items, key=lambda it: it["x1"]):
            if not groups or item["x1"] - groups[-1][-1]["x1"] > 48:
                groups.append([item])
            else:
                groups[-1].append(item)
        best = max(groups, key=len)
        if len(best) < 5 or len(best) < 0.62 * len(items):
            return None
        ys = sorted(int(it["y1"]) for it in best)
        gaps = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        gaps = [gap for gap in gaps if gap > 4]
        if not gaps or sorted(gaps)[len(gaps) // 2] > 48:
            return None
        if max(it["y2"] for it in best) - min(it["y1"] for it in best) < 80:
            return None
        return best

    def _coalesce_spec_continuations(self, items: List[Dict]) -> List[Dict]:
        """Nối dòng OCR bị cắt giữa câu. Câu đã chấm hết thì giữ thành đoạn riêng."""
        merged: List[Dict] = []
        for item in sorted(items, key=lambda it: (it["y1"], it["x1"])):
            if not merged:
                merged.append(dict(item))
                continue
            prev = merged[-1]
            gap = item["y1"] - prev["y2"]
            prev_wide = prev["x2"] - prev["x1"] >= 180
            same_left = abs(item["x1"] - prev["x1"]) <= 20
            unfinished = not str(prev["text"]).rstrip().endswith((".", "!", "?", "。", "！"))
            if prev_wide and same_left and unfinished and -2 <= gap <= 10:
                boxes = list(prev.get("src_boxes") or [])
                boxes.extend(item.get("src_boxes") or [(item["x1"], item["y1"], item["x2"], item["y2"])])
                nxt = str(item["text"]).strip()
                if nxt[:1].isupper() and not nxt.isupper():
                    nxt = nxt[:1].lower() + nxt[1:]
                prev["text"] = f"{prev['text']} {nxt}".strip()
                prev["x1"] = min(prev["x1"], item["x1"])
                prev["y1"] = min(prev["y1"], item["y1"])
                prev["x2"] = max(prev["x2"], item["x2"])
                prev["y2"] = max(prev["y2"], item["y2"])
                prev["src_boxes"] = boxes
                continue
            merged.append(dict(item))
        return merged

    def _text_pixel_size(self, font, text: str) -> Tuple[int, int]:
        probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
        bb = probe.textbbox((0, 0), text or " ", font=font)
        return bb[2] - bb[0], bb[3] - bb[1]

    def _paper_right_limit(self, image: np.ndarray | None, img_w: int, y1: int, y2: int, x_start: int) -> int:
        if image is None:
            return img_w - 8
        x = max(0, x_start)
        y1 = max(0, y1)
        y2 = min(image.shape[0], max(y1 + 8, y2))
        while x + 16 < img_w:
            if self._region_is_color_photo(image, (x, y1, min(img_w, x + 16), y2)):
                break
            x += 8
        return max(x_start + 48, min(img_w - 8, x))

    def _shared_spec_font(self, labels: List[Tuple[str, int]], max_h: int, max_size: int, min_size: int):
        for size in range(int(max_size), int(min_size) - 1, -1):
            font = self._get_font(size)
            if not font:
                continue
            fits = True
            for text, width in labels:
                tw, th = self._text_pixel_size(font, text)
                if tw > width or th > max_h:
                    fits = False
                    break
            if fits:
                return font
        return self._get_font(min_size)

    def _layout_spec_column(
        self,
        processed_blocks: List,
        ignore_blocks: List,
        img_w: int,
        img_h: int,
        image: np.ndarray | None = None,
    ) -> List[Dict] | None:
        """Cột thông số cạnh ảnh sản phẩm: mỗi nhãn một dòng đúng vị trí, ghi chú xuống dòng bên dưới."""
        items = self._spec_items(processed_blocks, ignore_blocks, img_w, img_h)
        column = self._dominant_spec_column(items)
        if not column:
            return None
        column_ids = {id(item) for item in column}
        rest = [item for item in items if id(item) not in column_ids]
        column_top = min(item["y1"] for item in column)
        headers = [item for item in rest if item["y2"] <= column_top + 12 and item["y1"] < img_h * 0.22]
        if len(headers) != len(rest):
            return None

        body = self._coalesce_spec_continuations(column)
        short_widths = sorted(item["x2"] - item["x1"] for item in body if len(item["text"]) < 36)
        typical = short_widths[len(short_widths) // 2] if short_widths else 100
        paragraphs = [
            item for item in body
            if len(item["text"]) >= 36 and (item["x2"] - item["x1"]) >= max(160, int(typical * 1.7))
        ]
        para_ids = {id(item) for item in paragraphs}
        labels = [item for item in body if id(item) not in para_ids]
        if len(labels) < 4:
            return None
        labels.sort(key=lambda it: it["y1"])
        centers = [(item["y1"] + item["y2"]) / 2 for item in labels]
        gaps = [centers[i + 1] - centers[i] for i in range(len(centers) - 1)]
        gaps = [gap for gap in gaps if gap >= 8]
        pitch = min(gaps) if gaps else max(16, labels[0]["y2"] - labels[0]["y1"])
        max_h = max(12, int(pitch) - 2)

        right = self._paper_right_limit(
            image,
            img_w,
            min(item["y1"] for item in body),
            max(item["y2"] for item in body),
            min(item["x1"] for item in body),
        )
        fitted = [(item["text"], max(48, right - int(item["x1"]) - 2)) for item in labels]
        font = self._shared_spec_font(fitted, max_h, min(22, max_h + 2), 13)
        if not font:
            return None
        for text, width in fitted:
            if self._text_pixel_size(font, text)[0] > width:
                return None

        placed = []
        for item in headers:
            text = str(item["text"]).strip()
            box_h = max(14, item["y2"] - item["y1"] + 4)
            width = max(48, img_w - 10 - int(item["x1"]))
            header_font = self._shared_spec_font([(text, width)], box_h, 22, 13)
            if not header_font or self._text_pixel_size(header_font, text)[0] > width:
                return None
            tw, th = self._text_pixel_size(header_font, text)
            cy = (item["y1"] + item["y2"]) / 2
            y1 = int(round(cy - th / 2))
            placed.append(self._locked_spec_item(item, header_font, [text], int(item["x1"]), y1, tw, th))

        label_bottom = 0
        for item in labels:
            text = str(item["text"]).strip()
            tw, th = self._text_pixel_size(font, text)
            cy = (item["y1"] + item["y2"]) / 2
            y1 = int(round(cy - th / 2))
            if label_bottom and y1 < label_bottom + 1:
                y1 = label_bottom + 1
            x1 = int(item["x1"])
            if x1 + tw > right:
                return None
            node = self._locked_spec_item(item, font, [text], x1, y1, tw, th)
            placed.append(node)
            label_bottom = node["_draw"][3][3]

        cursor = label_bottom + max(6, int(getattr(font, "size", 14) * 0.45))
        for item in sorted(paragraphs, key=lambda it: it["y1"]):
            text = str(item["text"]).strip()
            x1 = int(item["x1"])
            width = max(80, right - x1)
            top = max(int(item["y1"]), cursor)
            avail_h = max(28, img_h - 6 - top)
            para_font, lines, pad = self._fit_cell_lines(
                text,
                width,
                avail_h,
                min_size=13,
                max_size=getattr(font, "size", 16),
            )
            if not para_font:
                return None
            glyph_w = max(self._text_pixel_size(para_font, line)[0] for line in lines)
            _need_w, need_h = self._line_block_size(para_font, lines, pad)
            if top + need_h > img_h - 2:
                return None
            placed.append(self._locked_spec_item(item, para_font, lines, x1, top, glyph_w, need_h, pad=pad))
            cursor = top + need_h + 4
        return placed or None

    def _locked_spec_item(self, item: Dict, font, lines: List[str], x: int, y: int, text_w: int, text_h: int, pad: int = 1) -> Dict:
        x1 = int(x) - pad
        y1 = int(y) - 1
        rect = (x1, y1, int(x) + int(text_w) + pad, int(y) + int(text_h) + 3)
        src_boxes = [
            tuple(map(int, box))
            for box in (item.get("src_boxes") or [(item["x1"], item["y1"], item["x2"], item["y2"])])
        ]
        src = src_boxes[0]
        return {
            "text": "\n".join(lines),
            "x1": src[0],
            "y1": src[1],
            "x2": src[2],
            "y2": src[3],
            "src_bbox": src,
            "src_boxes": src_boxes,
            "_locked": True,
            "_align": "top",
            "_draw": (font, lines, pad, rect),
        }

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
        halo: Tuple[int, int, int] | None = None,
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
            draw.text(
                (x - bb[0], y - bb[1]),
                line,
                font=font,
                fill=fill,
                stroke_width=1 if halo else 0,
                stroke_fill=halo or fill,
            )
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
            if item.get("_locked"):
                sx1, sy1, sx2, sy2 = tuple(map(int, src))
                ox1, oy1 = max(0, sx1 - 8), max(0, sy1 - 8)
                ox2, oy2 = min(w_img, sx2 + 8), min(h_img, sy2 + 8)
                outer = image_data[oy1:oy2, ox1:ox2]
                ring = np.ones(outer.shape[:2], dtype=bool)
                iy1, iy2 = sy1 - oy1, sy2 - oy1
                ix1, ix2 = sx1 - ox1, sx2 - ox1
                if iy2 > iy1 and ix2 > ix1:
                    ring[iy1:iy2, ix1:ix2] = False
                samples = outer[ring] if outer.size else None
                if samples is not None and samples.size >= 3:
                    med = np.median(samples, axis=0)
                    if self._luminance((int(med[2]), int(med[1]), int(med[0]))) >= 160:
                        item["ink_rgb"] = (0, 0, 0)
            if protect_color_only:
                erase = tuple(map(int, src))
            else:
                erase = item.get("erase") or (item["x1"], item["y1"], item["x2"], item["y2"])
                if src and any(is_protected(img, part) for part in self._box_remainder(erase, src)):
                    erase = src
            erase_boxes = [tuple(map(int, box)) for box in (item.get("src_boxes") or [erase])]
            erase_boxes = [self._clip_bbox(box, h_img, w_img) for box in erase_boxes]
            erase_boxes = [box for box in erase_boxes if box[2] > box[0] and box[3] > box[1]]
            sky = bool(erase_boxes) and self._smooth_field_light_caption(image_data, tuple(map(int, src)))
            protected = bool(erase_boxes) and any(is_protected(img, box) for box in erase_boxes)
            if not erase_boxes or (protected and not sky):
                safe_boxes[id(item)] = None
                continue
            item["_sky"] = sky
            x1, y1, x2, y2 = erase_boxes[0]
            keep_bg = False
            if sky:
                for box in erase_boxes:
                    img = self._erase_light_glyphs(img, box)
                item["_flat"] = False
                item["_panel_bgr"] = None
                item["_paper"] = False
                item["_paper_bgr"] = None
                item["ink_rgb"] = (255, 255, 255)
            elif protect_color_only:
                flat = self._flat_panel_bgr(image_data, tuple(map(int, src)))
                item["_flat"] = flat is not None
                if flat is not None:
                    for box in erase_boxes:
                        img = self._solid_cover_text(img, box)
                    item["_panel_bgr"] = flat
                    item["_paper"] = self._luminance((flat[2], flat[1], flat[0])) >= 185
                    item["_paper_bgr"] = flat if item["_paper"] else None
                else:
                    gray = cv2.cvtColor(image_data[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
                    item["_paper_text"] = self._is_text_on_flat_paper(gray)
                    if self._region_is_color_photo(image_data, tuple(map(int, src))) and not self._is_light_chart_surface(image_data, tuple(map(int, src))):
                        for box in erase_boxes:
                            img = self._inpaint_text_strokes(img, box)
                    else:
                        for box in erase_boxes:
                            img = self._solid_cover_text(img, box)
                        if item["_paper_text"]:
                            item["_paper"] = True
                            item["_paper_bgr"] = self._plate_bgr(image_data, tuple(map(int, src)))
                    item["_panel_bgr"] = None
                    if not item.get("_paper"):
                        item["_paper_bgr"] = None
            else:
                keep_bg = False
                local = self._uniform_surround_bgr(image_data, (x1, y1, x2, y2))
                img[y1:y2, x1:x2] = local if local is not None else self._background_bgr(image_data, (x1, y1, x2, y2))
            safe_boxes[id(item)] = (x1, y1, x2, y2, keep_bg)
        if protect_color_only:
            sources = [
                tuple(map(int, item.get("src_bbox") or (item["x1"], item["y1"], item["x2"], item["y2"])))
                for item in blocks
                if safe_boxes.get(id(item))
            ]
            for item in blocks:
                saved = safe_boxes.get(id(item))
                if not saved or (item.get("_locked") and item.get("_draw")):
                    continue
                text = str(item.get("text") or "").strip()
                src = tuple(map(int, item.get("src_bbox") or (item["x1"], item["y1"], item["x2"], item["y2"])))
                sx1, sy1, sx2, sy2 = src
                src_h = max(2, sy2 - sy1)
                others = [box for box in sources if box != src]
                if item.get("_sky"):
                    left, right = self._row_slot_bounds(src, others, w_img)
                    left = max(left, sx1 - 2)
                    extra = 40 if src_h < 26 else max(24, int((sx2 - sx1) * 0.35))
                    cap = sx2 + extra
                    right = min(right, w_img - 4, cap)
                    rule = self._sky_limit_y(image_data, src)
                    if src_h < 26 and rule is not None:
                        limit_y = max(sy2, rule - 2)
                    elif src_h < 26:
                        limit_y = sy2 + src_h
                    else:
                        limit_y = sy2
                    slot_w = max(24, right - left)
                    slot_h = max(src_h, limit_y - sy1)
                    max_font = max(11, min(src_h if src_h >= 28 else max(src_h, 16), slot_h))
                    font, lines, pad = self._fit_cell_lines(
                        text,
                        slot_w,
                        slot_h,
                        min_size=10,
                        max_size=max_font,
                    )
                    if not font:
                        continue
                    need_w, need_h = self._line_block_size(font, lines, pad)
                    need_w = min(need_w, slot_w)
                    x1 = max(0, min(sx1, w_img - need_w))
                    y1 = max(0, min(sy1, h_img - 2))
                    x2 = min(w_img, x1 + need_w)
                    y2 = min(h_img, y1 + need_h)
                    item["ink_rgb"] = (255, 255, 255)
                    item["_draw"] = (font, lines, pad, (x1, y1, x2, y2))
                    item["_align"] = "top"
                    continue
                if item.get("_flat"):
                    left, right = self._row_slot_bounds(src, others, w_img)
                    panel = item.get("_panel_bgr")
                    panel_box = self._panel_clip(image_data, src, panel) if panel is not None else None
                    if panel_box is not None:
                        left = max(left, panel_box[0] + 2)
                        right = min(right, panel_box[2] - 2)
                    probe_bottom = min(h_img, sy2 + src_h)
                    if panel is not None:
                        run = self._flat_run_right(image_data, sx2, sy1, probe_bottom, panel)
                        art = self._illustration_left(image_data, sx2, max(0, sy1 - src_h * 2), probe_bottom)
                        right = min(right, max(sx2, min(run, art) - 16))
                else:
                    left, right = self._row_slot_bounds(src, others, w_img)
                    left = max(sx1, min(left, sx1))
                    cap = sx1 + max(sx2 - sx1, min(w_img // 3, max(120, (sx2 - sx1) * 2)))
                    right = min(right, w_img - 4, cap)
                    panel_box = None
                slot_w = max(24, right - left)
                next_y = None
                for box in sources:
                    if box == src:
                        continue
                    if box[1] < sy2 - 2:
                        continue
                    if min(sx2, box[2]) - max(sx1, box[0]) <= 4:
                        continue
                    next_y = box[1] if next_y is None else min(next_y, box[1])
                limit_y = sy2 + max(8, src_h)
                if next_y is not None:
                    limit_y = min(limit_y, next_y - 2)
                if panel_box is not None:
                    limit_y = min(limit_y, panel_box[3] - 2)
                if not item.get("_flat") and not item.get("_paper_text"):
                    limit_y = sy2 + 2
                slot_h = max(src_h, limit_y - sy1)
                max_font = max(12, min(max(src_h, 14), slot_h))
                if item.get("_paper") or item.get("_paper_text"):
                    heights = sorted(
                        max(1, box[3] - box[1]) for box in sources
                    )
                    typical = heights[len(heights) // 2] if heights else src_h
                    max_font = min(max_font, max(12, int(typical * 1.25)))
                font, lines, pad = self._fit_cell_lines(
                    text,
                    slot_w,
                    slot_h,
                    min_size=11,
                    max_size=max_font,
                )
                if item.get("_flat") and font and len(lines) > 1:
                    one_font, one_lines, one_pad = self._fit_cell_lines(
                        text,
                        slot_w,
                        max(src_h, 12),
                        min_size=16,
                        max_size=max_font,
                    )
                    if one_font and len(one_lines) == 1:
                        font, lines, pad = one_font, one_lines, one_pad
                if not font:
                    continue
                need_w, need_h = self._line_block_size(font, lines, pad)
                need_w = min(need_w, slot_w, max(8, int(right) - sx1))
                if item.get("_flat"):
                    x1 = max(left, sx1)
                    y1 = sy1
                else:
                    x1 = sx1
                    y1 = sy1
                x1 = max(0, min(x1, w_img - 4))
                y1 = max(0, min(y1, h_img - 2))
                x2 = min(w_img, int(right), x1 + need_w)
                y2 = min(h_img, int(limit_y), y1 + need_h)
                if x2 <= x1 or y2 <= y1:
                    continue
                item["_draw"] = (font, lines, pad, (x1, y1, x2, y2))
                item["_align"] = "top"
            self._apply_inset_caption_cards(img, blocks, phone_min)
            for item in blocks:
                if item.get("_locked") or not item.get("_flat") or not item.get("_draw"):
                    continue
                color = item.get("_panel_bgr")
                if color is None:
                    continue
                _font, _lines, _pad, (px1, py1, px2, py2) = item["_draw"]
                if px2 <= px1 or py2 <= py1:
                    continue
                if self._region_is_product_photo(image_data, (px1, py1, px2, py2)):
                    continue
                self._paint_panel_keep_art(img, image_data, (px1, py1, px2, py2), color)
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
            plate = None
            if prepared and not item.get("_sky"):
                on_photo = self._region_is_color_photo(image_data, (x1, y1, x2, y2)) and not self._is_light_chart_surface(image_data, (x1, y1, x2, y2))
                if not on_photo and (item.get("_paper") or item.get("_paper_text") or item.get("_flat") or self._is_light_chart_surface(image_data, (x1, y1, x2, y2))):
                    plate = item.get("_paper_bgr") or item.get("_panel_bgr") or self._plate_bgr(img, (x1, y1, x2, y2))
            if plate is not None:
                cell = Image.new("RGB", (w, h), (int(plate[2]), int(plate[1]), int(plate[0])))
            elif keep_bg or prepared:
                cell = pil.crop((x1, y1, x2, y2))
            else:
                local = self._uniform_surround_bgr(img, (x1, y1, x2, y2))
                if local is None:
                    local = self._background_bgr(img, (x1, y1, x2, y2))
                cell = Image.new("RGB", (w, h), (int(local[2]), int(local[1]), int(local[0])))
            self._draw_lines_in_cell(
                cell,
                lines,
                font,
                fill,
                pad,
                align=item.get("_align") or ("center" if protect_color_only else "top"),
                anchor=anchor,
                halo=item.get("_halo"),
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

    def _erase_cleared_text_blocks(self, image_data: np.ndarray, processed_blocks: List):
        """Dòng để trống (nhà sản xuất, URL) được xóa nét chữ, không vẽ lại."""
        img = image_data
        kept = []
        for text, bbox in processed_blocks or []:
            if str(text or "").strip():
                kept.append((text, bbox))
                continue
            if not bbox or len(bbox) < 4:
                continue
            img = self._erase_strokes_with_local_color(img, tuple(int(v) for v in bbox[:4]))
        return img, kept

    def process_image_with_text(self, image_data: np.ndarray, processed_blocks: List, ignore_blocks: List) -> np.ndarray:
        image_data, processed_blocks = self._erase_cleared_text_blocks(image_data, processed_blocks)
        img_h, img_w = image_data.shape[:2]
        table_blocks = self._layout_table_blocks(processed_blocks, ignore_blocks, img_w, img_h)
        if table_blocks is not None and self._table_expansion_covers_photo(image_data, table_blocks):
            print("  [TABLE] bỏ — ô chữ đè lên ảnh sản phẩm")
            table_blocks = None
        if table_blocks is not None:
            print(f"  [TABLE] vẽ {len(table_blocks)} ô trong khung, không gộp đè")
            return self.add_smart_watermark(self._draw_table_blocks(image_data, table_blocks), [])
        spec_blocks = self._layout_spec_column(processed_blocks, ignore_blocks, img_w, img_h, image_data)
        if spec_blocks:
            print(f"  [SPEC] vẽ {len(spec_blocks)} dòng thông số, giữ ảnh sản phẩm")
            return self.add_smart_watermark(
                self._draw_table_blocks(image_data, spec_blocks, protect_color_only=True),
                [],
            )
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