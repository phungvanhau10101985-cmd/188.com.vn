# image_processor.py
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List, Tuple
import math
import re
import os
import platform
from config import FONT_PATH, LOGO_PATH
import random

class ImageProcessor:
    def __init__(self):
        self.font_path = self._find_best_font(FONT_PATH)
        print(f"  🔤 ImageProcessor sử dụng font: {self.font_path}")
        
        self.MIN_FONT_SIZE = 12
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

    def _advanced_inpainting(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Erase the whole OCR bbox and synthesize a clean background from nearby pixels."""
        h_img, w_img = img.shape[:2]
        x1, y1, x2, y2 = self._expand_bbox_for_inpaint(bbox, h_img, w_img)
        if x2 <= x1 or y2 <= y1:
            return img
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
        """Keep translated text near the original bbox; wrap/shrink instead of enlarging."""
        if not text:
            return bbox
        x1, y1, x2, y2 = map(int, bbox)

        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2

        orig_w = max(1, x2 - x1)
        orig_h = max(1, y2 - y1)

        font_min = self._get_font(self.MIN_FONT_SIZE)
        if not font_min:
            return bbox

        text_bbox = draw.textbbox((0, 0), text, font=font_min)
        text_w = text_bbox[2] - text_bbox[0]

        text_len = len(str(text))
        width_scale = 1.75 if text_len > 80 else 1.35
        max_w = min(img_w - 8, max(orig_w + 80, int(orig_w * width_scale), self.MIN_FONT_SIZE * 10))
        req_w = max(orig_w, min(text_w + self.INTERNAL_PADDING * 2, max_w))

        usable_w = max(10, req_w - self.INTERNAL_PADDING * 2)
        lines_count = max(1, math.ceil(text_w / usable_w))
        lh_est = int(self.MIN_FONT_SIZE * max(self.LINE_HEIGHT_RATIO, 1.42))
        gap_est = self._line_gap(self.MIN_FONT_SIZE)
        v_budget = self._vertical_padding_budget(self.MIN_FONT_SIZE)
        needed_h = lines_count * lh_est + max(0, lines_count - 1) * gap_est + v_budget * 2
        height_scale = 4.5 if text_len > 80 else 2.6
        max_h = min(img_h - 8, max(orig_h + 90, int(orig_h * height_scale), self.MIN_FONT_SIZE * 6))
        req_h = max(orig_h, min(needed_h, max_h))

        new_w_half = int(req_w) // 2
        new_h_half = int(req_h) // 2

        nx1 = cx - new_w_half
        nx2 = cx + new_w_half
        ny1 = cy - new_h_half
        ny2 = cy + new_h_half

        if nx1 < 0:
            nx2 += 0 - nx1
            nx1 = 0
        if nx2 > img_w:
            nx1 -= nx2 - img_w
            nx2 = img_w

        if ny1 < 0:
            ny2 += 0 - ny1
            ny1 = 0
        if ny2 > img_h:
            ny1 -= ny2 - img_h
            ny2 = img_h

        nx1, ny1 = max(0, nx1), max(0, ny1)
        return (int(nx1), int(ny1), int(nx2), int(ny2))

    def _binary_search_font(self, text, w, h, draw):
        low, high = self.MIN_FONT_SIZE, self.MAX_FONT_SIZE
        best_size, best_lines = self.MIN_FONT_SIZE, [text]
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
            pad_x = max(18, int((x2 - x1) * 0.08))
            pad_y = max(12, int((y2 - y1) * 0.25))
            expanded = self._clip_bbox((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), img_h, img_w)
            merged_blocks.append((text, expanded))

        return merged_blocks

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
            clean_img = self._advanced_inpainting(clean_img, erase_bbox)

        pil_img = Image.fromarray(cv2.cvtColor(clean_img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        for item in sorted_blocks:
            if item["is_ignore"] or not str(item.get("text", "")).strip():
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

            self._draw_text_centered(draw, lines, final_bbox, font, style)

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