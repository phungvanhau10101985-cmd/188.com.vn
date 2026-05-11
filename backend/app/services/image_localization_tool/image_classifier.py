# image_classifier.py - FULL CODE HOÀN CHỈNH
from typing import List, Tuple, Dict
import re
from config import IMAGE_CLASSIFICATION, SKIP_REGEX, DOMAIN_REGEX, URGENT_DELETE_REGEX

def normalize_ocr_results(ocr_results):
    """
    Chuẩn hóa OCR results về định dạng dictionary thống nhất
    OCR có thể trả về: tuple(text, bbox) HOẶC dict{'text':..., 'bbox':...}
    """
    normalized = []
    if not ocr_results:
        return normalized
    
    for item in ocr_results:
        if isinstance(item, dict) and 'text' in item and 'bbox' in item:
            # Đảm bảo bbox là list số, không phải string
            bbox = item['bbox']
            if isinstance(bbox, str):
                try:
                    # Xử lý nhiều định dạng: "[1,2,3,4]", "(1,2,3,4)", "1,2,3,4"
                    cleaned = bbox.strip('[](){}')
                    parts = [p.strip() for p in cleaned.split(',') if p.strip()]
                    bbox = [int(float(p)) for p in parts[:4]]
                except:
                    bbox = []
            elif isinstance(bbox, (list, tuple)):
                # Đảm bảo tất cả phần tử là số
                validated = []
                for val in bbox[:4]:
                    if isinstance(val, (int, float)):
                        validated.append(int(val))
                    elif isinstance(val, str) and val.strip().replace('.', '', 1).isdigit():
                        validated.append(int(float(val.strip())))
                    else:
                        validated.append(0)
                bbox = validated
            item['bbox'] = bbox
            normalized.append(item)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            text = str(item[0]) if len(item) > 0 else ''
            bbox = item[1] if len(item) > 1 else []
            
            # Đảm bảo bbox là list số
            if isinstance(bbox, str):
                try:
                    cleaned = bbox.strip('[](){}')
                    parts = [p.strip() for p in cleaned.split(',') if p.strip()]
                    bbox = [int(float(p)) for p in parts[:4]]
                except:
                    bbox = []
            elif isinstance(bbox, (list, tuple)):
                validated = []
                for val in bbox[:4]:
                    if isinstance(val, (int, float)):
                        validated.append(int(val))
                    elif isinstance(val, str) and val.strip().replace('.', '', 1).isdigit():
                        validated.append(int(float(val.strip())))
                    else:
                        validated.append(0)
                bbox = validated
            
            normalized.append({'text': text, 'bbox': bbox})
    
    return normalized

class ImageClassifier:
    """Phân loại ảnh để chọn phương pháp xử lý tối ưu - ĐÃ THÊM XỬ LÝ TỪ KHÓA GIẶT TẨY"""
    
    def __init__(self):
        self.max_simple_blocks = IMAGE_CLASSIFICATION['MAX_SIMPLE_TEXT_BLOCKS']
        self.complex_keywords = IMAGE_CLASSIFICATION['COMPLEX_KEYWORDS']
        self.size_table_keywords = IMAGE_CLASSIFICATION['SIZE_TABLE_KEYWORDS']
        self.product_info_keywords = IMAGE_CLASSIFICATION['PRODUCT_INFO_KEYWORDS']
        self.delete_keywords = IMAGE_CLASSIFICATION['DELETE_KEYWORDS']
        self.urgent_delete_keywords = IMAGE_CLASSIFICATION['URGENT_DELETE_KEYWORDS']
        self.laundry_care_keywords = IMAGE_CLASSIFICATION['LAUNDRY_CARE_KEYWORDS']
        
        # Tối ưu: tạo set để tìm kiếm nhanh hơn
        self.size_table_set = set(self.size_table_keywords)
        self.product_info_set = set(self.product_info_keywords)
        self.delete_set = set(self.delete_keywords)
        self.complex_set = set(self.complex_keywords)
        self.urgent_delete_set = set(self.urgent_delete_keywords)
        self.laundry_care_set = set(self.laundry_care_keywords)
    
    def _validate_bbox(self, bbox):
        """Đảm bảo bbox là list số hợp lệ"""
        if not bbox or not isinstance(bbox, (list, tuple, str)):
            return [0, 0, 100, 100]  # Giá trị mặc định
        
        # Nếu là string, chuyển thành list số
        if isinstance(bbox, str):
            try:
                # Xử lý nhiều định dạng: "[1,2,3,4]", "(1,2,3,4)", "1,2,3,4"
                cleaned = bbox.strip('[](){}')
                parts = [p.strip() for p in cleaned.split(',') if p.strip()]
                if len(parts) >= 4:
                    return [int(float(p)) for p in parts[:4]]
                else:
                    return [0, 0, 100, 100]
            except Exception as e:
                print(f"      ⚠️ Lỗi validate bbox string '{bbox}': {e}")
                return [0, 0, 100, 100]
        
        # Nếu là list/tuple, đảm bảo tất cả là số
        validated = []
        for item in bbox[:4]:  # Chỉ lấy 4 phần tử đầu
            if isinstance(item, (int, float)):
                validated.append(int(item))
            elif isinstance(item, str):
                try:
                    validated.append(int(float(item.strip())))
                except:
                    validated.append(0)
            else:
                validated.append(0)
        
        # Đảm bảo có đủ 4 phần tử
        while len(validated) < 4:
            validated.append(0)
        
        # Đảm bảo x2 > x1 và y2 > y1
        if validated[2] <= validated[0]:
            validated[2] = validated[0] + 10
        if validated[3] <= validated[1]:
            validated[3] = validated[1] + 10
        
        return validated
    
    def _is_real_chinese_hanzi(self, char: str) -> bool:
        """
        Kiểm tra CHÍNH XÁC xem ký tự có phải là chữ Hán (Hanzi) không
        Chỉ nhận diện ký tự Hán thật sự, không nhận diện Latin, số, ký tự đặc biệt
        """
        if not char or len(char) != 1:
            return False
        
        code_point = ord(char)
        
        # PHẠM VI UNICODE CHÍNH XÁC CHO CHỮ HÁN (HANZI):
        
        # 1. CJK Unified Ideographs (Hán tự phổ thông) - 4E00-9FFF
        # Bao gồm hầu hết chữ Hán dùng trong tiếng Trung, Nhật, Hàn hiện đại
        if 0x4E00 <= code_point <= 0x9FFF:
            return True
        
        # 2. CJK Unified Ideographs Extension A - 3400-4DBF
        # Hán tự mở rộng A, chủ yếu là các biến thể cổ và địa phương
        if 0x3400 <= code_point <= 0x4DBF:
            return True
        
        # 3. CJK Compatibility Ideographs - F900-FAFF
        # Hán tự tương thích, chủ yếu dùng trong mã hóa cũ
        if 0xF900 <= code_point <= 0xFAFF:
            return True
        
        # 4. CJK Unified Ideographs Extension B - 20000-2A6DF
        # Hán tự mở rộng B, các ký tự hiếm và cổ
        if 0x20000 <= code_point <= 0x2A6DF:
            return True
        
        # 5. CJK Unified Ideographs Extension C - 2A700-2B73F
        if 0x2A700 <= code_point <= 0x2B73F:
            return True
        
        # 6. CJK Unified Ideographs Extension D - 2B740-2B81F
        if 0x2B740 <= code_point <= 0x2B81F:
            return True
        
        # 7. CJK Unified Ideographs Extension E - 2B820-2CEAF
        if 0x2B820 <= code_point <= 0x2CEAF:
            return True
        
        # 8. CJK Unified Ideographs Extension F - 2CEB0-2EBEF
        if 0x2CEB0 <= code_point <= 0x2EBEF:
            return True
        
        return False
    
    def _has_real_chinese_hanzi(self, text: str, min_chars: int = 2) -> Tuple[bool, int, List[str]]:
        """
        Kiểm tra CHÍNH XÁC xem text có chứa chữ Hán thật sự không
        Trả về: (có_đủ_ký_tự, số_lượng, danh_sách_ký_tự_hán)
        """
        if not text or not text.strip():
            return False, 0, []
        
        hanzi_chars = []
        
        # Phân tích từng ký tự
        for char in text:
            if self._is_real_chinese_hanzi(char):
                hanzi_chars.append(char)
        
        hanzi_count = len(hanzi_chars)
        has_sufficient_hanzi = hanzi_count >= min_chars
        
        # DEBUG: Kiểm tra kỹ
        if text and hanzi_count > 0:
            print(f"      🔍 Phân tích ký tự trong: '{text[:30]}...'")
            print(f"      Tổng ký tự: {len(text)}, Hán tự tìm thấy: {hanzi_count}")
            print(f"      Các Hán tự: {hanzi_chars}")
        
        return has_sufficient_hanzi, hanzi_count, hanzi_chars
    
    def _has_chinese_text(self, text_blocks: List[Dict], min_chars: int = 2) -> Tuple[bool, int, List[str]]:
        """
        Kiểm tra xem có chữ Hán thật sự không
        Trả về: (có_đủ_ký_tự, tổng_số_ký_tự, danh_sách_tất_cả_ký_tự_hán)
        """
        if not text_blocks:
            return False, 0, []
        
        total_hanzi_chars = 0
        all_hanzi_chars = []
        
        for item in text_blocks:
            text = item.get('text', '')
            if not text or not text.strip():
                continue
            
            has_text_hanzi, count, hanzi_list = self._has_real_chinese_hanzi(text, 1)
            if has_text_hanzi:
                total_hanzi_chars += count
                all_hanzi_chars.extend(hanzi_list)
        
        # Phải có ít nhất min_chars ký tự Hán TỔNG CỘNG
        has_sufficient_hanzi = total_hanzi_chars >= min_chars
        
        return has_sufficient_hanzi, total_hanzi_chars, all_hanzi_chars
    
    def _is_only_latin_or_common_symbols(self, text: str) -> bool:
        """
        Kiểm tra xem text có chỉ chứa chữ Latin, số, hoặc ký tự thông thường không
        Nếu chỉ có những ký tự này -> coi như không có nội dung Hán
        """
        if not text:
            return True
        
        # Regex kiểm tra chỉ chứa:
        # 1. Chữ Latin (A-Z, a-z)
        # 2. Số (0-9)
        # 3. Khoảng trắng, dấu câu thông thường
        # 4. Các ký tự đặc biệt thông dụng
        latin_symbols_pattern = r'^[\sA-Za-z0-9\-_.,;:!?@#$%^&*()+=/\'"\[\]{}|~`<>]*$'
        
        return bool(re.match(latin_symbols_pattern, text))
    
    def _check_urgent_delete(self, text: str) -> Tuple[bool, str]:
        """
        Kiểm tra URGENT DELETE - XÓA NGAY LẬP TỨC nếu phát hiện từ khóa cấm
        Ưu tiên cao nhất, không cần kiểm tra gì thêm
        """
        if not text:
            return False, ""
        
        # 1. Kiểm tra từ khóa URGENT (nhanh nhất)
        for keyword in self.urgent_delete_keywords:
            if keyword in text:
                return True, f"Từ khóa URGENT: {keyword}"
        
        # 2. Kiểm tra URGENT DELETE REGEX
        urgent_match = URGENT_DELETE_REGEX.search(text)
        if urgent_match:
            matched_text = urgent_match.group()
            return True, f"Pattern URGENT: {matched_text}"
        
        # 3. Kiểm tra SKIP REGEX với từ khóa đặc biệt
        skip_match = SKIP_REGEX.search(text)
        if skip_match:
            matched_text = skip_match.group()
            
            # DANH SÁCH TỪ KHÓA PHẢI XÓA NGAY (từ nội dung ảnh của bạn)
            must_delete_keywords = [
                '一手货源', '一件代发', '未经授权', '盗用图片',
                '投诉', '本店所有', '货源充足', '大量现货',
                '价格优惠', '量大从优', '大量招', '关于退换',
                '概不负责', '特此声明'
            ]
            
            for keyword in must_delete_keywords:
                if keyword in text:
                    return True, f"Từ khóa bắt buộc xóa: {keyword}"
        
        return False, ""
    
    def _check_laundry_care_keywords(self, text: str) -> Tuple[bool, str, List[str]]:
        """
        Kiểm tra xem text có chứa từ khóa hướng dẫn giặt tẩy không
        Trả về: (có_từ_khóa, từ_khóa_phát_hiện, danh_sách_từ_khóa)
        """
        if not text:
            return False, "", []
        
        detected_keywords = []
        
        # Kiểm tra từng từ khóa giặt tẩy
        for keyword in self.laundry_care_keywords:
            if keyword in text:
                detected_keywords.append(keyword)
        
        if detected_keywords:
            # Chọn từ khóa đầu tiên làm đại diện
            main_keyword = detected_keywords[0]
            return True, main_keyword, detected_keywords
        
        return False, "", []
    
    def _quick_classify_from_ocr_blocks(self, text_blocks: List[Dict]) -> Dict[str, any]:
        """
        Phân loại NHANH từ OCR blocks - chạy TRƯỚC khi dịch
        ĐÃ THÊM KIỂM TRA TỪ KHÓA GIẶT TẨY
        """
        if not text_blocks:
            return {'type': 'keep', 'reason': 'Không có text blocks', 'details': {'text_blocks': 0}}
        
        text_blocks_to_draw = [b for b in text_blocks if b.get('text') and b.get('text').strip()]
        num_text_blocks = len(text_blocks_to_draw)
        
        print(f"      📝 Phân tích {num_text_blocks} text blocks...")
        
        # BƯỚC 0: KIỂM TRA URGENT DELETE - ƯU TIÊN CAO NHẤT
        for item in text_blocks_to_draw:
            text = item.get('text', '')
            if not text:
                continue
            
            need_urgent_delete, reason = self._check_urgent_delete(text)
            if need_urgent_delete:
                return {
                    'type': 'delete',
                    'reason': f'URGENT DELETE: {reason}',
                    'details': {
                        'text_blocks': num_text_blocks,
                        'detected_keyword': reason,
                        'text_snippet': text[:100],
                        'urgent_delete': True,
                        'action': 'DELETE_IMMEDIATELY'
                    }
                }
        
        # BƯỚC 1: Kiểm tra nhanh nếu chỉ có Latin/symbols -> KEEP ngay
        all_latin_only = True
        for item in text_blocks_to_draw:
            text = item.get('text', '')
            if not self._is_only_latin_or_common_symbols(text):
                all_latin_only = False
                break
        
        if all_latin_only:
            return {
                'type': 'keep',
                'reason': 'Chỉ chứa chữ Latin/số/ký tự thông thường, không có Hán tự',
                'details': {
                    'text_blocks': num_text_blocks,
                    'has_chinese': False,
                    'all_latin_only': True,
                    'quick_detection': True
                }
            }
        
        # BƯỚC 2: Kiểm tra nhanh tín hiệu XÓA thông thường
        for item in text_blocks_to_draw:
            text = item.get('text', '')
            if not text:
                continue
                
            # Kiểm tra pattern xóa (CHÍNH XÁC)
            skip_match = SKIP_REGEX.search(text)
            if skip_match:
                matched_text = skip_match.group()
                
                # PHÂN BIỆT: "尺码" (kích thước) vs "价格" (giá)
                if '尺码' in text and not any(price_char in text for price_char in ['¥', '￥', '$', '价格', '价目', '报价']):
                    continue  # Bỏ qua, không xóa
                
                # PHÂN BIỆT: "规格" (thông số) vs "规格表" (bảng giá)
                if '规格' in text and '价格表' not in text:
                    continue
                
                return {
                    'type': 'delete',
                    'reason': f'Ảnh chứa thông tin cần xóa: {matched_text}',
                    'details': {
                        'text_blocks': num_text_blocks,
                        'detected_pattern': matched_text,
                        'quick_detection': True
                    }
                }
            
            # Kiểm tra domain (CHÍNH XÁC)
            domain_match = DOMAIN_REGEX.search(text)
            if domain_match:
                domain = domain_match.group()
                
                # PHÂN BIỆT: Domain 188.com.vn (của chúng ta) vs domain khác
                if '188.com.vn' in text:
                    continue
                
                return {
                    'type': 'delete',
                    'reason': f'Ảnh chứa domain: {domain}',
                    'details': {
                        'text_blocks': num_text_blocks,
                        'detected_domain': domain,
                        'quick_detection': True
                    }
                }
        
        # BƯỚC 3: Kiểm tra nhanh từ khóa GIẶT TẨY - ƯU TIÊN CHO GEMINI
        for item in text_blocks_to_draw:
            text = item.get('text', '')
            if not text:
                continue
            
            # Kiểm tra từ khóa giặt tẩy
            has_laundry_care, keyword, all_keywords = self._check_laundry_care_keywords(text)
            if has_laundry_care:
                # Kiểm tra xem có đủ Hán tự không
                has_sufficient_hanzi, hanzi_count, hanzi_list = self._has_real_chinese_hanzi(text, 2)
                
                if has_sufficient_hanzi:
                    print(f"      🧺 PHÁT HIỆN TỪ KHÓA GIẶT TẨY: {keyword}")
                    return {
                        'type': 'gemini',
                        'reason': f'Chứa từ khóa giặt tẩy: {keyword} ({hanzi_count} Hán tự)',
                        'details': {
                            'text_blocks': num_text_blocks,
                            'detected_keyword': keyword,
                            'all_keywords': all_keywords,
                            'hanzi_count': hanzi_count,
                            'laundry_care': True,
                            'quick_detection': True
                        }
                    }
        
        # BƯỚC 4: Kiểm tra nhanh tín hiệu GEMINI - CHỈ KHI CÓ ĐỦ HÁN TỰ
        for item in text_blocks_to_draw:
            text = item.get('text', '')
            if not text:
                continue
            
            # Kiểm tra xem có đủ ký tự Hán không (ít nhất 2)
            has_sufficient_hanzi, hanzi_count, hanzi_list = self._has_real_chinese_hanzi(text, 2)
            
            # Nếu không có đủ Hán tự, bỏ qua kiểm tra từ khóa
            if not has_sufficient_hanzi:
                continue
            
            # CHỈ KHI CÓ ĐỦ HÁN TỰ mới kiểm tra từ khóa
            text_lower = text.lower()
            
            # 1. Kiểm tra từ khóa kích thước QUAN TRỌNG
            critical_size_keywords = ['尺码', '尺寸', '码数', '码', 'size table', 'size chart']
            for keyword in critical_size_keywords:
                if keyword in text or keyword in text_lower:
                    return {
                        'type': 'gemini',
                        'reason': f'Chứa từ khóa kích thước: {keyword} ({hanzi_count} Hán tự)',
                        'details': {
                            'text_blocks': num_text_blocks,
                            'detected_keyword': keyword,
                            'hanzi_count': hanzi_count,
                            'quick_detection': True
                        }
                    }
            
            # 2. Kiểm tra từ khóa bảng
            table_keywords = ['表', '表格', '对照表', '参数表', '规格表', 'chart', 'table']
            for keyword in table_keywords:
                if keyword in text:
                    return {
                        'type': 'gemini',
                        'reason': f'Chứa từ khóa bảng: {keyword} ({hanzi_count} Hán tự)',
                        'details': {
                            'text_blocks': num_text_blocks,
                            'detected_keyword': keyword,
                            'hanzi_count': hanzi_count,
                            'quick_detection': True
                        }
                    }
            
            # 3. Kiểm tra từ khóa sản phẩm quan trọng
            product_critical_keywords = ['款号:', '颜色:', '型号:', '规格:', '参数:', '产品参数', '产品/参数', '产品参数PARAMETERS']
            for keyword in product_critical_keywords:
                if keyword in text:
                    return {
                        'type': 'gemini',
                        'reason': f'Chứa thông tin sản phẩm: {keyword} ({hanzi_count} Hán tự)',
                        'details': {
                            'text_blocks': num_text_blocks,
                            'detected_keyword': keyword,
                            'hanzi_count': hanzi_count,
                            'quick_detection': True
                        }
                    }
        
        # Nếu không phát hiện nhanh, trả về None để xử lý tiếp
        return None
    
    def _calculate_overlap_ratio(self, rect1: Tuple, rect2: Tuple) -> float:
        """Tính tỷ lệ chồng lấn giữa 2 hình chữ nhật"""
        try:
            # Đảm bảo tất cả là số
            x1_1, y1_1, x2_1, y2_1 = [int(float(x)) for x in rect1[:4]]
            x1_2, y1_2, x2_2, y2_2 = [int(float(x)) for x in rect2[:4]]
        except (ValueError, TypeError, IndexError) as e:
            print(f"      ⚠️ Lỗi convert bbox trong calculate_overlap_ratio: {e}")
            return 0.0
        
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
    
    def _detect_serious_overlap(self, text_blocks: List[Dict]) -> Tuple[bool, float]:
        """Phát hiện chữ bị đè nghiêm trọng"""
        if not text_blocks or len(text_blocks) < 2:
            return False, 0.0
        
        # Chỉ lấy các khối có text và bbox hợp lệ
        valid_blocks = []
        for item in text_blocks:
            text = item.get('text', '')
            bbox = self._validate_bbox(item.get('bbox', []))
            if text and text.strip() and len(bbox) == 4:
                valid_blocks.append({'text': text, 'bbox': bbox})
        
        if len(valid_blocks) < 2:
            return False, 0.0
        
        total_overlap_ratio = 0.0
        overlap_count = 0
        
        # Kiểm tra từng cặp
        for i in range(len(valid_blocks)):
            for j in range(i + 1, len(valid_blocks)):
                bbox1 = valid_blocks[i].get('bbox', [])
                bbox2 = valid_blocks[j].get('bbox', [])
                
                if len(bbox1) == 4 and len(bbox2) == 4:
                    overlap_ratio = self._calculate_overlap_ratio(bbox1, bbox2)
                    
                    if overlap_ratio > 0:
                        total_overlap_ratio += overlap_ratio
                        overlap_count += 1
        
        if overlap_count == 0:
            return False, 0.0
        
        avg_overlap = total_overlap_ratio / overlap_count
        threshold = IMAGE_CLASSIFICATION['OVERLAP_THRESHOLD']
        has_serious_overlap = avg_overlap > threshold
        
        return has_serious_overlap, avg_overlap
    
    def _contains_complex_keywords(self, text_blocks: List[Dict]) -> Tuple[bool, str]:
        """
        Kiểm tra xem text blocks có chứa từ khóa phức tạp không
        ĐÃ THÊM KIỂM TRA TỪ KHÓA GIẶT TẨY
        """
        if not text_blocks:
            return False, ""
            
        for item in text_blocks:
            text = item.get('text', '')
            if not text:
                continue
                
            text_lower = text.lower()
            
            # 1. Kiểm tra từ khóa GIẶT TẨY PHỨC TẢP
            laundry_complex_patterns = [
                '洗涤说明', '洗涤方式', '洗涤标识', '洗水唛',
                '衣物护理', '面料保养', '清洗保养',
                'WASHING INSTRUCTION', 'CARE LABEL'
            ]
            for pattern in laundry_complex_patterns:
                if pattern in text:
                    return True, pattern
            
            # 2. Bảng kích thước phức tạp (có table/chart)
            table_patterns = ['size table', 'size chart', '尺寸表', '尺码表', '对照表']
            for pattern in table_patterns:
                if pattern in text or pattern in text_lower:
                    return True, pattern
            
            # 3. Thông số kỹ thuật phức tạp (bảng nhiều cột)
            complex_patterns = ['参数表', '规格表', 'technical specification', 'spec sheet']
            for pattern in complex_patterns:
                if pattern in text:
                    return True, pattern
            
            # 4. Biểu đồ, sơ đồ
            diagram_patterns = ['diagram', 'chart', '示意图', '结构图']
            for pattern in diagram_patterns:
                if pattern in text_lower:
                    return True, pattern
        
        return False, ""
    
    def _contains_laundry_care_keywords(self, text_blocks: List[Dict]) -> Tuple[bool, str, List[str]]:
        """
        Kiểm tra xem text blocks có chứa từ khóa hướng dẫn giặt tẩy không
        Trả về: (có_từ_khóa, từ_khóa_chính, danh_sách_tất_cả)
        """
        if not text_blocks:
            return False, "", []
        
        all_detected_keywords = []
        main_keyword = ""
        
        for item in text_blocks:
            text = item.get('text', '')
            if not text:
                continue
                
            has_laundry_care, keyword, detected_keywords = self._check_laundry_care_keywords(text)
            if has_laundry_care:
                all_detected_keywords.extend(detected_keywords)
                if not main_keyword:
                    main_keyword = keyword
        
        if all_detected_keywords:
            return True, main_keyword, all_detected_keywords
        
        return False, "", []
    
    def classify_image(self, 
                      processed_blocks: List,
                      ignore_blocks: List,
                      original_url: str) -> Dict[str, any]:
        """
        Phân loại ảnh - ĐÃ THÊM XỬ LÝ TỪ KHÓA GIẶT TẨY
        
        QUY TẮC MỚI:
        1. KIỂM TRA URGENT DELETE TRƯỚC - XÓA NGAY NẾU PHÁT HIỆN
        2. Ảnh có từ khóa GIẶT TẨY + đủ Hán tự → GEMINI (ưu tiên)
        3. Ảnh có ≥2 Hán tự + không chồng chéo → LOCAL 
        4. Chỉ dùng Gemini khi:
           - Có từ khóa phức tạp (bảng, biểu đồ, giặt tẩy)
           - Bị chồng chéo > threshold
        """
        print(f"\n    🔍 CLASSIFY IMAGE: {original_url[:80]}...")
        
        # CHUẨN HÓA OCR BLOCKS
        processed_blocks = normalize_ocr_results(processed_blocks)
        ignore_blocks = normalize_ocr_results(ignore_blocks)
        
        # VALIDATE BBOX - QUAN TRỌNG!
        for item in processed_blocks:
            if 'bbox' in item:
                item['bbox'] = self._validate_bbox(item['bbox'])
        
        # DEBUG: Hiển thị tất cả OCR blocks
        print(f"    📋 Tổng số OCR blocks: {len(processed_blocks)}")
        
        # BƯỚC 0: KIỂM TRA URGENT DELETE - XÓA NGAY LẬP TỨC
        print(f"    ⚠️  Kiểm tra URGENT DELETE...")
        for item in processed_blocks:
            text = item.get('text', '')
            if not text or not text.strip():
                continue
            
            need_urgent_delete, reason = self._check_urgent_delete(text)
            if need_urgent_delete:
                print(f"    🚨 PHÁT HIỆN NỘI DUNG CẤM KHẨN: {reason}")
                print(f"    🗑️  XÓA NGAY LẬP TỨC!")
                
                return {
                    'type': 'delete',
                    'reason': f'URGENT DELETE: {reason}',
                    'details': {
                        'text_blocks': len([b for b in processed_blocks if b.get('text') and b.get('text').strip()]),
                        'detected_keyword': reason,
                        'text_snippet': text[:100],
                        'urgent_delete': True,
                        'action': 'DELETE_IMMEDIATELY'
                    }
                }
        
        # BƯỚC 1: Phân loại NHANH từ OCR blocks
        quick_result = self._quick_classify_from_ocr_blocks(processed_blocks)
        if quick_result:
            print(f"    ⚡ QUICK CLASSIFICATION: {quick_result['type']} - {quick_result['reason']}")
            return quick_result
        
        # BƯỚC 2: Kiểm tra chi tiết Hán tự
        has_sufficient_hanzi, total_hanzi_chars, all_hanzi_chars = self._has_chinese_text(processed_blocks, 2)
        
        # DEBUG: Hiển thị chi tiết từng block
        for i, item in enumerate(processed_blocks[:5]):  # Chỉ hiển thị 5 blocks đầu
            text = item.get('text', '')
            if text and text.strip():
                has_hanzi, count, hanzi_list = self._has_real_chinese_hanzi(text, 1)
                text_preview = text[:30] + "..." if len(text) > 30 else text
                print(f"    📄 Block {i}: '{text_preview}'")
                print(f"       Hán tự: {count}, Cụ thể: {hanzi_list if hanzi_list else 'Không có'}")
        
        print(f"    📊 Tổng Hán tự tìm thấy: {total_hanzi_chars} ký tự")
        if all_hanzi_chars:
            print(f"    🀄 Các Hán tự: {all_hanzi_chars}")
        
        # Nếu KHÔNG có đủ 2 ký tự Hán THẬT -> KEEP ngay
        if not has_sufficient_hanzi:
            reason = ""
            if total_hanzi_chars == 0:
                reason = f'Không có chữ Hán (chỉ có Latin/số/ký tự thông thường)'
            elif total_hanzi_chars == 1:
                reason = f'Chỉ có 1 ký tự Hán ({all_hanzi_chars[0]}), cần ít nhất 2 ký tự'
            else:
                reason = f'Không đủ ký tự Hán cần dịch ({total_hanzi_chars} ký tự, cần ít nhất 2)'
            
            return {
                'type': 'keep',
                'reason': reason,
                'details': {
                    'text_blocks': len([b for b in processed_blocks if b.get('text') and b.get('text').strip()]),
                    'hanzi_count': total_hanzi_chars,
                    'hanzi_list': all_hanzi_chars,
                    'has_sufficient_hanzi': False,
                    'is_clean': True
                }
            }
        
        print(f"    ✅ Có đủ {total_hanzi_chars} ký tự Hán, tiếp tục phân loại...")
        
        # Nếu có đủ Hán tự, tiếp tục phân loại chi tiết
        text_blocks_to_draw = [b for b in processed_blocks if b.get('text') and b.get('text').strip()]
        num_text_blocks = len(text_blocks_to_draw)
        
        # BƯỚC 3: Kiểm tra TỪ KHÓA GIẶT TẨY chi tiết
        has_laundry_care, laundry_keyword, all_laundry_keywords = self._contains_laundry_care_keywords(text_blocks_to_draw)
        
        if has_laundry_care:
            print(f"    🧺 PHÁT HIỆN TỪ KHÓA GIẶT TẨY: {laundry_keyword}")
            print(f"    📋 Tất cả từ khóa: {all_laundry_keywords}")
            
            # Ảnh có từ khóa giặt tẩy -> ƯU TIÊN GỬI GEMINI
            return {
                'type': 'gemini',
                'reason': f'Chứa từ khóa hướng dẫn giặt tẩy: {laundry_keyword} - {total_hanzi_chars} Hán tự',
                'details': {
                    'text_blocks': num_text_blocks,
                    'laundry_keyword': laundry_keyword,
                    'all_laundry_keywords': all_laundry_keywords,
                    'hanzi_count': total_hanzi_chars,
                    'hanzi_list': all_hanzi_chars,
                    'has_laundry_care': True,
                    'priority': 'HIGH'  # Ưu tiên cao
                }
            }
        
        # BƯỚC 4: Kiểm tra chữ bị đè
        has_overlap, overlap_ratio = self._detect_serious_overlap(text_blocks_to_draw)
        
        # LOGIC MỚI: Chỉ gửi Gemini nếu bị đè nghiêm trọng
        if has_overlap:
            threshold = IMAGE_CLASSIFICATION['OVERLAP_THRESHOLD']
            return {
                'type': 'gemini',
                'reason': f'Chữ Hán bị đè nghiêm trọng ({overlap_ratio:.1%} > {threshold:.1%}) - {total_hanzi_chars} Hán tự',
                'details': {
                    'text_blocks': num_text_blocks,
                    'overlap_ratio': overlap_ratio,
                    'hanzi_count': total_hanzi_chars,
                    'hanzi_list': all_hanzi_chars,
                    'has_overlap': True
                }
            }
        
        # BƯỚC 5: Kiểm tra từ khóa phức tạp (bao gồm cả từ khóa giặt tẩy phức tạp)
        has_complex_keywords, keyword = self._contains_complex_keywords(text_blocks_to_draw)
        if has_complex_keywords:
            return {
                'type': 'gemini',
                'reason': f'Chứa nội dung phức tạp: {keyword} - {total_hanzi_chars} Hán tự',
                'details': {
                    'text_blocks': num_text_blocks,
                    'complex_keyword': keyword,
                    'hanzi_count': total_hanzi_chars,
                    'hanzi_list': all_hanzi_chars,
                    'has_overlap': False
                }
            }
        
        # BƯỚC 6: LOGIC MỚI - Xử lý LOCAL cho tất cả ảnh có chữ Hán thông thường
        # KHÔNG GIỚI HẠN số blocks, miễn là không chồng chéo và không phức tạp
        print(f"    📈 LOGIC MỚI: Ảnh có {num_text_blocks} blocks chữ Hán thông thường -> Xử lý LOCAL")
        
        return {
            'type': 'local',
            'reason': f'Ảnh nhiều chữ Hán thông thường ({num_text_blocks} blocks, {total_hanzi_chars} Hán tự, không bị đè, không phức tạp)',
            'details': {
                'text_blocks': num_text_blocks,
                'overlap_ratio': overlap_ratio,
                'hanzi_count': total_hanzi_chars,
                'hanzi_list': all_hanzi_chars,
                'has_overlap': False,
                'is_normal_chinese': True,
                'has_laundry_care': has_laundry_care  # Thêm flag này
            }
        }

# Singleton instance
image_classifier = ImageClassifier()