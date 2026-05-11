# image_processor.py
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from typing import List, Tuple, Dict
import math
import os
import platform
from config import FONT_PATH, LOGO_PATH
import random

class ImageProcessor:
    def __init__(self):
        self.font_path = self._find_best_font(FONT_PATH)
        print(f"  🔤 ImageProcessor sử dụng font: {self.font_path}")
        
        self.MIN_FONT_SIZE = 14
        self.MAX_FONT_SIZE = 140
        self.STROKE_WIDTH_RATIO = 0.15
        # Legacy ratio; không dùng làm stride dòng nữa (xem _wrapped_block_height / _draw_text_centered).
        self.LINE_HEIGHT_RATIO = 1.2
        # Padding nội bộ lỏng hơn một chút để chữ không sát mép
        self.INTERNAL_PADDING = 12 
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

    def _advanced_inpainting(self, img: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
        """Xóa nền thông minh: Fill màu trung bình viền + Inpaint biên + Noise"""
        x1, y1, x2, y2 = map(int, bbox)
        h_img, w_img = img.shape[:2]
        
        # Mở rộng vùng tham chiếu để lấy màu nền
        pad_ref = 5
        rx1, ry1 = max(0, x1 - pad_ref), max(0, y1 - pad_ref)
        rx2, ry2 = min(w_img, x2 + pad_ref), min(h_img, y2 + pad_ref)
        
        # Lấy các pixel viền xung quanh bbox
        roi_full = img[ry1:ry2, rx1:rx2]
        mask_center = np.zeros(roi_full.shape[:2], dtype=np.uint8)
        # Mask phần lõi (phần chữ cần xóa) trong hệ tọa độ ROI
        cv2.rectangle(mask_center, (x1-rx1, y1-ry1), (x2-rx1, y2-ry1), 255, -1)
        
        # Lấy màu trung bình của phần KHÔNG phải mask (tức là phần nền xung quanh)
        bg_pixels = roi_full[mask_center == 0]
        if bg_pixels.size > 0:
            avg_color = np.mean(bg_pixels, axis=0)
        else:
            avg_color = (255, 255, 255)

        # 1. Fill vùng cần xóa bằng màu trung bình (tránh bị vết nhòe Telea ở giữa)
        img[y1:y2, x1:x2] = avg_color

        # 2. Tạo mask viền mỏng để inpaint vùng tiếp giáp giữa màu fill và ảnh gốc
        mask_border = np.zeros((h_img, w_img), dtype=np.uint8)
        # Vẽ hình chữ nhật rỗng bao quanh biên
        thickness = 4 
        cv2.rectangle(mask_border, (x1-2, y1-2), (x2+2, y2+2), 255, thickness)
        
        # Inpaint vùng biên để hòa trộn
        img = cv2.inpaint(img, mask_border, 3, cv2.INPAINT_TELEA)

        # 3. Blur nhẹ vùng vừa xử lý để làm mượt
        # Chỉ blur vùng bbox + một chút viền
        bx1, by1 = max(0, x1-2), max(0, y1-2)
        bx2, by2 = min(w_img, x2+2), min(h_img, y2+2)
        roi_blur = img[by1:by2, bx1:bx2]
        if roi_blur.size > 0:
            roi_blur = cv2.GaussianBlur(roi_blur, (7, 7), 0)
            # Thêm chút noise giả lập
            roi_blur = self._add_noise(roi_blur, intensity=3)
            img[by1:by2, bx1:bx2] = roi_blur
            
        return img

    def _get_text_style(self, bg_color: Tuple[int, int, int]) -> Dict:
        bg_lum = 0.299 * bg_color[0] + 0.587 * bg_color[1] + 0.114 * bg_color[2]
        if bg_lum > 140:
            return {'text_color': (0, 0, 0), 'stroke_color': (255, 255, 255), 'use_shadow': False}
        else:
            return {'text_color': (255, 255, 255), 'stroke_color': (0, 0, 0), 'use_shadow': True}

    def _line_gap(self, font_size: int) -> int:
        """Khoảng cách nhỏ giữa các dòng (song song với _draw_text_centered)."""
        return max(2, int(font_size * 0.08))

    def _stroke_width_for_size(self, font_size: int) -> int:
        return max(2, int(font_size * self.STROKE_WIDTH_RATIO))

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

    def _wrap_text(self, text, font, max_width, draw):
        if not font: return [text]
        lines, words = [], text.split()
        current_line = []
        for word in words:
            test_line = current_line + [word]
            if draw.textbbox((0, 0), ' '.join(test_line), font=font)[2] <= max_width: 
                current_line = test_line
            else:
                lines.append(' '.join(current_line) if current_line else word)
                current_line = [word] if current_line else []
        if current_line: lines.append(' '.join(current_line))
        return lines

    def _calc_box_centered(self, text, bbox, img_w, img_h, draw):
        """Tính toán hộp mới sao cho ĐỒNG TÂM với hộp cũ"""
        if not text: return bbox
        x1, y1, x2, y2 = bbox
        
        # 1. Tìm tâm của hộp cũ
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        
        orig_w = x2 - x1
        orig_h = y2 - y1
        
        # Font tối thiểu để ước lượng
        font_min = self._get_font(self.MIN_FONT_SIZE)
        if not font_min: return bbox
        
        # Đo kích thước text
        text_bbox = draw.textbbox((0, 0), text, font=font_min)
        text_w = text_bbox[2] - text_bbox[0]
        
        # Tính toán chiều rộng cần thiết (bao gồm padding)
        # Giữ nguyên độ rộng nếu text nhỏ hơn hộp cũ (để che hết vết xóa)
        # Mở rộng nếu text lớn hơn
        req_w = max(orig_w, text_w + self.INTERNAL_PADDING * 2)
        
        # Tính số dòng ước lượng
        lines_count = math.ceil(text_w / max(10, req_w - self.INTERNAL_PADDING * 2))
        # Ước lượng cao dòng thực tế (VN + dấu + stroke ~ tương đương vẽ có stroke nhỏ)
        lh_est = int(self.MIN_FONT_SIZE * max(self.LINE_HEIGHT_RATIO, 1.42))
        gap_est = self._line_gap(self.MIN_FONT_SIZE)
        req_h = max(
            orig_h,
            lines_count * lh_est + max(0, lines_count - 1) * gap_est + self.INTERNAL_PADDING * 2,
        )

        # 2. Tính tọa độ mới dựa trên tâm (cx, cy)
        new_w_half = req_w // 2
        new_h_half = req_h // 2
        
        nx1 = cx - new_w_half
        nx2 = cx + new_w_half
        ny1 = cy - new_h_half
        ny2 = cy + new_h_half
        
        # 3. Kẹp giá trị vào trong ảnh (Clamping)
        # Nếu bị đẩy ra ngoài biên, ta dịch chuyển ngược lại nhưng cố giữ kích thước
        if nx1 < 0: 
            nx2 += (0 - nx1) # Đẩy sang phải
            nx1 = 0
        if nx2 > img_w:
            nx1 -= (nx2 - img_w) # Đẩy sang trái
            nx2 = img_w
            
        if ny1 < 0:
            ny2 += (0 - ny1)
            ny1 = 0
        if ny2 > img_h:
            ny1 -= (ny2 - img_h)
            ny2 = img_h
            
        # Đảm bảo không âm sau khi dịch chuyển
        nx1, ny1 = max(0, nx1), max(0, ny1)
        
        return (nx1, ny1, nx2, ny2)

    def _binary_search_font(self, text, w, h, draw):
        low, high = self.MIN_FONT_SIZE, self.MAX_FONT_SIZE
        best_size, best_lines = self.MIN_FONT_SIZE, [text]
        # Padding ngang an toàn
        eff_w = max(10, w - self.INTERNAL_PADDING) 
        
        while low <= high:
            mid = (low + high) // 2
            font = self._get_font(mid)
            if not font: break
            
            lines = self._wrap_text(text, font, eff_w, draw)
            stroke_w = self._stroke_width_for_size(mid)
            total_h = self._wrapped_block_height(draw, lines, font, stroke_w)
            
            # Cho phép lố chiều cao một chút (1.1) vì padding dọc đã lo
            if total_h <= h * 1.1: 
                best_size, best_lines, low = mid, lines, mid + 1
            else: 
                high = mid - 1
        return best_size, best_lines

    def _draw_text_centered(self, draw, lines, bbox, font, style):
        if not font: return
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
                draw.text(
                    (ix + 2, iy + 2),
                    line,
                    font=font,
                    fill=(0, 0, 0),
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

    def check_processed_overlap(self, processed_blocks: List, img_w: int, img_h: int, threshold: float = 0.01) -> Tuple[bool, float]:
        """
        Kiểm tra xem các khối text sau khi dịch (processed_blocks) có bị đè lên nhau không.
        Trả về: (True/False, tỷ lệ đè lớn nhất)
        """
        if not processed_blocks or len(processed_blocks) < 2:
            return False, 0.0

        # Tạo dummy image/draw để tính toán kích thước text (cần thiết cho _calc_box_centered)
        dummy_img = Image.new('RGB', (10, 10))
        draw = ImageDraw.Draw(dummy_img)

        # 1. Tính toán tất cả các hộp mới (New Bounding Boxes)
        new_boxes = []
        for text, old_bbox in processed_blocks:
            if not text or not text.strip():
                continue
            # Tái sử dụng logic tính toán hộp của quá trình vẽ thật
            new_bbox = self._calc_box_centered(text, old_bbox, img_w, img_h, draw)
            new_boxes.append(new_bbox)

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
        all_blocks = []
        for t, b in processed_blocks: 
            all_blocks.append({'text': t, 'bbox': b, 'area': (b[2]-b[0])*(b[3]-b[1]), 'is_ignore': False})
        for t, b in ignore_blocks: 
            all_blocks.append({'text': t, 'bbox': b, 'area': (b[2]-b[0])*(b[3]-b[1]), 'is_ignore': True})

        if not processed_blocks: return self.add_smart_watermark(image_data, all_blocks)

        img_h, img_w = image_data.shape[:2]
        # Clean img dùng để xóa nền
        clean_img = image_data.copy()
        
        # Sắp xếp xử lý
        sorted_blocks = sorted(all_blocks, key=lambda x: x['area'], reverse=True)

        # 1. Xóa nền (Advanced Inpainting)
        for item in sorted_blocks:
            if item['is_ignore']: continue
            # Xóa nền cũ bằng thuật toán mới
            clean_img = self._advanced_inpainting(clean_img, item['bbox'])

        # 2. Tính toán Box mới (Centered) & Vẽ chữ
        # Convert sang PIL để vẽ chữ đẹp hơn
        pil_img = Image.fromarray(cv2.cvtColor(clean_img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        
        for item in sorted_blocks:
            if item['is_ignore'] or not item['text'].strip(): continue
            
            # Tính box mới đồng tâm với box cũ
            final_bbox = self._calc_box_centered(item['text'], item['bbox'], img_w, img_h, draw)
            
            # Lấy màu nền tại vị trí box cũ để chọn màu chữ
            bx1, by1, bx2, by2 = map(int, item['bbox'])
            # Crop vùng nhỏ ở tâm box cũ
            cx, cy = (bx1+bx2)//2, (by1+by2)//2
            roi_sample = clean_img[cy-2:cy+2, cx-2:cx+2]
            avg_color = self._get_avg_color(roi_sample)
            
            # Tìm size và vẽ
            fs, lines = self._binary_search_font(item['text'], final_bbox[2]-final_bbox[0], final_bbox[3]-final_bbox[1], draw)
            font = self._get_font(fs)
            style = self._get_text_style(avg_color)
            
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