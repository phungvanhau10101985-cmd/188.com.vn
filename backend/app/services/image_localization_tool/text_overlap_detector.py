# text_overlap_detector.py
import math
from typing import List, Tuple
from config import IMAGE_CLASSIFICATION

class TextOverlapDetector:
    """Phát hiện chữ bị đè lên nhau sau khi dịch"""
    
    def __init__(self, overlap_threshold: float = None):
        self.overlap_threshold = overlap_threshold or IMAGE_CLASSIFICATION['OVERLAP_THRESHOLD']
    
    def calculate_overlap_ratio(self, rect1: Tuple, rect2: Tuple) -> float:
        """Tính tỷ lệ diện tích chồng lấn giữa 2 hình chữ nhật"""
        x1_1, y1_1, x2_1, y2_1 = rect1
        x1_2, y1_2, x2_2, y2_2 = rect2
        
        # Tính tọa độ giao nhau
        x_left = max(x1_1, x1_2)
        y_top = max(y1_1, y1_2)
        x_right = min(x2_1, x2_2)
        y_bottom = min(y2_1, y2_2)
        
        if x_right <= x_left or y_bottom <= y_top:
            return 0.0
        
        # Tính diện tích giao nhau
        overlap_area = (x_right - x_left) * (y_bottom - y_top)
        
        # Tính diện tích từng khối
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        # Trả về tỷ lệ so với khối nhỏ hơn
        smaller_area = min(area1, area2)
        return overlap_area / smaller_area if smaller_area > 0 else 0
    
    def detect_serious_overlap(self, text_blocks: List[Tuple[str, tuple]]) -> Tuple[bool, float]:
        """
        Phát hiện chữ bị đè nghiêm trọng
        Trả về: (có_bị_đè, tỷ_lệ_đè_trung_bình)
        """
        if not text_blocks or len(text_blocks) < 2:
            return False, 0.0
        
        # Chỉ lấy các khối có text
        valid_blocks = [(text, bbox) for text, bbox in text_blocks if text and text.strip()]
        
        if len(valid_blocks) < 2:
            return False, 0.0
        
        total_overlap_ratio = 0.0
        overlap_count = 0
        
        # Kiểm tra từng cặp
        for i in range(len(valid_blocks)):
            for j in range(i + 1, len(valid_blocks)):
                _, bbox1 = valid_blocks[i]
                _, bbox2 = valid_blocks[j]
                
                overlap_ratio = self.calculate_overlap_ratio(bbox1, bbox2)
                
                if overlap_ratio > 0:
                    total_overlap_ratio += overlap_ratio
                    overlap_count += 1
        
        if overlap_count == 0:
            return False, 0.0
        
        avg_overlap = total_overlap_ratio / overlap_count
        has_serious_overlap = avg_overlap > self.overlap_threshold
        
        return has_serious_overlap, avg_overlap
    
    def contains_complex_keywords(self, text_blocks: List[Tuple[str, tuple]]) -> bool:
        """Kiểm tra xem có chứa từ khóa phức tạp không"""
        complex_keywords = IMAGE_CLASSIFICATION['COMPLEX_KEYWORDS']
        
        for text, _ in text_blocks:
            if not text:
                continue
            for keyword in complex_keywords:
                if keyword in text:
                    return True
        return False

# Singleton instance
overlap_detector = TextOverlapDetector()