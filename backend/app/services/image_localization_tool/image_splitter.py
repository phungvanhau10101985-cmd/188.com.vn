# image_splitter.py
import cv2
import numpy as np
import json
import re
import os
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any

# Cấu hình Logging
logger = logging.getLogger(__name__)

# Regex phát hiện chữ Hán
CHINESE_CHAR_REGEX = re.compile(r'[\u4e00-\u9fff]')

# Import Config (Có fallback nếu file config chưa có biến)
try:
    from config import (
        MAX_IMAGE_HEIGHT,
        MIN_IMAGE_HEIGHT,
        SPLIT_SAFE_MARGIN,
        SPLIT_MIN_GAP_SIZE,
        SPLIT_MIN_CHINESE_BLOCKS,
        SPLIT_3_PARTS_THRESHOLD,
        SPLIT_MIN_BLOCKS_FOR_3
    )
except ImportError:
    # Giá trị mặc định nếu không tìm thấy config
    MAX_IMAGE_HEIGHT = 1100
    MIN_IMAGE_HEIGHT = 700
    SPLIT_SAFE_MARGIN = 25
    SPLIT_MIN_GAP_SIZE = 50
    SPLIT_MIN_CHINESE_BLOCKS = 5
    SPLIT_3_PARTS_THRESHOLD = 2400
    SPLIT_MIN_BLOCKS_FOR_3 = 4

class EnhancedImageSplitter:
    """Class xử lý logic cắt ảnh thông minh dựa trên mật độ chữ và khoảng trắng"""
    
    def __init__(self, 
                 max_image_height: int = MAX_IMAGE_HEIGHT, 
                 min_image_height: int = MIN_IMAGE_HEIGHT,
                 safe_margin: int = SPLIT_SAFE_MARGIN,
                 min_gap_size: int = SPLIT_MIN_GAP_SIZE,
                 min_chinese_blocks: int = SPLIT_MIN_CHINESE_BLOCKS):
        
        self.max_image_height = max_image_height
        self.min_image_height = min_image_height
        self.safe_margin = safe_margin
        self.min_gap_size = min_gap_size
        self.min_chinese_blocks = min_chinese_blocks

    def should_split_image(self, image_height: int, ocr_blocks: List[Any]) -> bool:
        """Quyết định xem có nên cắt ảnh hay không"""
        # 1. Kiểm tra chiều cao
        if image_height <= self.max_image_height:
            return False
        
        # 2. Kiểm tra mật độ chữ Hán
        chinese_block_count = 0
        for item in ocr_blocks:
            # Hỗ trợ cả format dict và tuple
            text = item.get('text', '') if isinstance(item, dict) else (item[0] if len(item) > 0 else '')
            
            if text and CHINESE_CHAR_REGEX.search(str(text)):
                chinese_block_count += 1
        
        if chinese_block_count < self.min_chinese_blocks:
            logger.info(f"  🚫 Không chia: Ảnh dài {image_height}px nhưng ít chữ Hán ({chinese_block_count} cụm)")
            return False
            
        logger.info(f"  ✂️ Đủ điều kiện chia: Cao {image_height}px & {chinese_block_count} cụm chữ Hán")
        return True
    
    def find_safe_split_points(self, image_height: int, ocr_blocks: List[Any]) -> List[int]:
        """Tìm các điểm cắt an toàn (vùng không có chữ)"""
        # Tạo bản đồ vùng bị chiếm dụng bởi chữ (Mask)
        y_occupied = np.zeros(image_height, dtype=bool)
        
        for item in ocr_blocks:
            # Lấy bbox chuẩn hóa
            if isinstance(item, dict):
                bbox = item.get('bbox', [])
            else:
                bbox = item[1] if len(item) > 1 else []
            
            if bbox and len(bbox) >= 4:
                try:
                    y1, y2 = int(bbox[1]), int(bbox[3])
                    # Thêm lề an toàn để không cắt sát chữ
                    y1 = max(0, y1 - self.safe_margin)
                    y2 = min(image_height, y2 + self.safe_margin)
                    y_occupied[y1:y2] = True
                except: continue

        # Quyết định số phần (2 hoặc 3)
        num_parts = 2
        try:
            from config import SPLIT_3_PARTS_THRESHOLD
            threshold_3 = SPLIT_3_PARTS_THRESHOLD
        except: threshold_3 = 2400

        if image_height > threshold_3:
            num_parts = 3

        ideal_part_height = image_height // num_parts
        split_points = [0]
        
        # Tìm điểm cắt cho từng phần
        for i in range(1, num_parts):
            target_y = i * ideal_part_height
            best_split = -1
            min_dist = float('inf')
            
            # Quét xung quanh target_y để tìm khoảng trắng
            search_range = 400 # Phạm vi tìm kiếm +/- pixel
            start_scan = max(0, target_y - search_range)
            end_scan = min(image_height, target_y + search_range)
            
            # Thuật toán tìm khoảng trống (gap)
            current_gap_start = -1
            
            for y in range(start_scan, end_scan):
                if not y_occupied[y]: # Vùng trống
                    if current_gap_start == -1: current_gap_start = y
                else: # Vùng có chữ
                    if current_gap_start != -1:
                        # Kết thúc 1 gap -> Kiểm tra độ lớn
                        gap_size = y - current_gap_start
                        if gap_size >= self.min_gap_size:
                            mid_gap = current_gap_start + gap_size // 2
                            dist = abs(mid_gap - target_y)
                            if dist < min_dist:
                                min_dist = dist
                                best_split = mid_gap
                        current_gap_start = -1
            
            # Nếu tìm thấy điểm cắt tốt
            if best_split != -1:
                split_points.append(best_split)
            else:
                # Fallback: Cắt cứng nếu không tìm thấy chỗ trống (hiếm gặp)
                logger.warning(f"  ⚠️ Không tìm thấy điểm cắt an toàn quanh {target_y}, cắt cứng.")
                split_points.append(target_y)
        
        # Thêm điểm cuối
        split_points.append(image_height)
        
        # Lọc lại: Loại bỏ điểm 0 đầu tiên và điểm cuối cùng để trả về danh sách điểm cắt
        return [p for p in split_points if 0 < p < image_height]

    def _adjust_ocr_for_split_part(self, ocr_blocks: List[Any], y_start: int, y_end: int) -> List[Dict]:
        """Điều chỉnh tọa độ OCR cho phần ảnh con sau khi cắt"""
        adjusted_blocks = []
        for item in ocr_blocks:
            if isinstance(item, dict):
                text, bbox = item.get('text', ''), item.get('bbox', [])
            else:
                text = item[0]
                bbox = item[1] if len(item) > 1 else []
            
            if not bbox or len(bbox) < 4: continue
            
            x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
            
            # Kiểm tra xem text có nằm trong phần cắt này không (chấp nhận nằm 1 phần)
            center_y = (y1 + y2) / 2
            if y_start <= center_y < y_end:
                new_y1 = max(0, y1 - y_start)
                new_y2 = min(y2 - y_start, y_end - y_start)
                
                # Chỉ thêm nếu chiều cao hợp lý
                if new_y2 > new_y1:
                    adjusted_blocks.append({'text': text, 'bbox': [x1, new_y1, x2, new_y2]})
                    
        return adjusted_blocks

    def split_image_if_needed(self, image: np.ndarray, ocr_blocks: List[Any], original_url: str, filename: str) -> List[Dict[str, Any]]:
        """Hàm chính để thực hiện cắt ảnh"""
        height, width = image.shape[:2]
        
        # 1. Check điều kiện
        if not self.should_split_image(height, ocr_blocks):
            # Return dạng list chứa 1 phần tử (chính nó)
            return [{
                'image': image, 'ocr_blocks': ocr_blocks, 
                'y_offset': 0, 'height': height,
                'filename': filename, 'original_url': original_url,
                'is_split': False, 'part_index': 0, 'total_parts': 1
            }]
        
        # 2. Tìm điểm cắt
        split_points = self.find_safe_split_points(height, ocr_blocks)
        if not split_points:
             return [{
                'image': image, 'ocr_blocks': ocr_blocks, 'y_offset': 0, 'height': height,
                'filename': filename, 'original_url': original_url,
                'is_split': False, 'part_index': 0, 'total_parts': 1
            }]

        logger.info(f"  ✂️ Thực hiện cắt tại Y={split_points}")
        
        # 3. Thực hiện cắt
        image_parts = []
        base_name, ext = os.path.splitext(filename)
        if not ext: ext = '.jpg'
        
        # Tạo danh sách biên: [0, p1, p2, height]
        boundaries = [0] + split_points + [height]
        
        for i in range(len(boundaries) - 1):
            y_start = boundaries[i]
            y_end = boundaries[i+1]
            
            # Crop ảnh
            part_img = image[y_start:y_end, :]
            
            # Adjust OCR
            part_ocr = self._adjust_ocr_for_split_part(ocr_blocks, y_start, y_end)
            
            part_filename = f"{base_name}_part{i+1}_of_{len(boundaries)-1}{ext}"
            
            # URL ảo để định danh
            part_url = f"{original_url}_part_{i}"
            
            image_parts.append({
                'image': part_img,
                'ocr_blocks': part_ocr,
                'y_offset': y_start,
                'height': y_end - y_start,
                'filename': part_filename,
                'original_url': original_url,
                'part_url': part_url,
                'is_split': True,
                'part_index': i,
                'total_parts': len(boundaries) - 1
            })
            
        return image_parts

class ImageSplitter:
    """Wrapper class để tích hợp vào main pipeline"""
    def __init__(self):
        # Khởi tạo core logic với config tự động import
        self.enhanced_splitter = EnhancedImageSplitter()
    
    def load_merged_info(self, positions_file: str) -> Dict[str, Any]:
        try:
            if not os.path.exists(positions_file): return {}
            with open(positions_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Lỗi đọc file vị trí: {e}")
            return {}
    
    def map_ocr_to_original_coordinates(self, batch_ocr_results: List[Any], img_info: Dict[str, Any]) -> List[Dict]:
        """Chuyển đổi tọa độ OCR từ ảnh Batch to lớn về tọa độ của ảnh gốc"""
        if not batch_ocr_results or not img_info: return []
        
        bx, by = img_info.get('x', 0), img_info.get('y', 0)
        bw, bh = img_info.get('width', 0), img_info.get('height', 0)
        scale = img_info.get('scale_factor', 1.0)
        if scale <= 0: scale = 1.0
            
        mapped_results = []
        for item in batch_ocr_results:
            # Chuẩn hóa input item
            if isinstance(item, dict):
                text = item.get('text', '')
                bbox = item.get('bbox', [])
            else:
                text = item[0] if len(item) > 0 else ''
                bbox = item[1] if len(item) > 1 else []
            
            if not bbox or len(bbox) < 4: continue
            
            # Convert sang int để so sánh an toàn
            try:
                x1, y1, x2, y2 = [int(float(val)) for val in bbox[:4]]
            except: continue

            # Kiểm tra xem box này có nằm trong vùng ảnh con không
            if (x2 < bx or x1 > bx + bw or y2 < by or y1 > by + bh): 
                continue
            
            # Tính toán tọa độ gốc (đảo ngược scale và offset)
            # Công thức: (Batch_Coord - Offset) / Scale
            orig_x1 = int(max(0, x1 - bx) / scale)
            orig_y1 = int(max(0, y1 - by) / scale)
            orig_x2 = int(min(bw, x2 - bx) / scale)
            orig_y2 = int(min(bh, y2 - by) / scale)
            
            if orig_x2 > orig_x1 and orig_y2 > orig_y1:
                mapped_results.append({'text': text, 'bbox': [orig_x1, orig_y1, orig_x2, orig_y2]})
                
        return mapped_results

    def process_all_batches(self, batches_result: Dict, all_ocr_results: Dict) -> Dict:
        """Hàm chính: Nhận kết quả Batch -> Trả về danh sách ảnh con (đã cắt hoặc giữ nguyên)"""
        if not batches_result.get('success'): return {}
        all_split_results = {}
        
        # Duyệt qua từng batch
        for batch_info in batches_result.get('batches', []):
            b_idx = batch_info['batch_index']
            positions_file = batch_info['positions_file']
            batch_ocr = all_ocr_results.get(b_idx, [])
            
            # Load thông tin vị trí
            merged_info = self.load_merged_info(positions_file)
            positions = merged_info.get('positions', {})
            
            # Duyệt từng ảnh trong batch này
            for filename, img_info in positions.items():
                try:
                    original_url = img_info.get('original_url')
                    original_path = img_info.get('original_path')
                    
                    if not original_path or not os.path.exists(original_path): continue
                    
                    # Đọc ảnh gốc từ ổ cứng
                    original_img = cv2.imread(original_path)
                    if original_img is None: continue
                    
                    # 1. Map OCR từ Batch về Gốc
                    mapped_ocr = self.map_ocr_to_original_coordinates(batch_ocr, img_info)
                    
                    # 2. Gọi logic cắt ảnh nâng cao
                    image_parts = self.enhanced_splitter.split_image_if_needed(original_img, mapped_ocr, original_url, filename)
                    
                    # 3. Lưu kết quả vào dict tổng
                    mapping_info = batches_result.get('column_mapping', {}).get(original_url, {})
                    source_cols = mapping_info.get('source_columns', [])
                    
                    for part in image_parts:
                        # Key của dict kết quả: Nếu cắt thì dùng part_url, không thì dùng url gốc
                        key = part['part_url'] if part['is_split'] else original_url
                        
                        all_split_results[key] = {
                            'image_data': part['image'],
                            'ocr_results': part['ocr_blocks'],
                            'filename': part['filename'],
                            'original_url': original_url,
                            'is_split_part': part['is_split'],
                            'part_index': part['part_index'],
                            'total_parts': part['total_parts'],
                            'source_columns': source_cols,
                            'y_offset': part['y_offset']
                        }
                        
                except Exception as e:
                    logger.error(f"  ❌ Lỗi xử lý cắt ảnh {filename}: {e}")
                    import traceback
                    traceback.print_exc()
            
        return all_split_results