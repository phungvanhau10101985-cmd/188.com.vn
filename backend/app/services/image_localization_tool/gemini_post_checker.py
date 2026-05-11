# gemini_post_checker.py
import os
import cv2
import numpy as np
import json
import time
import re
from typing import List, Dict, Tuple, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import traceback
import hashlib
import logging

# Import các config và module xử lý
from config import *
from ocr_processor import OCRProcessor
from text_translator import TextTranslator  # Module dịch (DeepSeek)
from image_processor import ImageProcessor  # Module vẽ ảnh/inpainting (Xử lý ảnh đợt 1)

# Setup logger
logger = logging.getLogger('gemini_checker')
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL))

class GeminiPostChecker:
    """
    Kiểm tra và sửa lỗi ảnh sau khi Gemini xử lý.
    Sử dụng lại toàn bộ công nghệ của đợt 1 (Translator + ImageProcessor) để đảm bảo chất lượng.
    """
    
    def __init__(self):
        # 1. OCR Processor: Dùng Google Vision để soi lỗi (giống đợt 1)
        self.ocr_processor = OCRProcessor()
        
        # 2. Translator: Dùng để dịch các chữ Hán còn sót (giống đợt 1)
        self.translator = TextTranslator()
        
        # 3. Image Processor: Dùng để xóa nền cũ và vẽ chữ Việt đẹp (giống đợt 1)
        self.img_processor = ImageProcessor()
        
        # Thư mục tạm
        self.temp_batch_dir = os.path.join(TEMP_IMAGES_DIR, "gemini_batches")
        os.makedirs(self.temp_batch_dir, exist_ok=True)
        
        logger.info("🚀 Gemini Post Checker: Sẵn sàng (OCR + Translate + Redraw)")
    
    def check_chinese_in_gemini_image(self, gemini_image_info: Dict) -> Dict:
        """
        Kiểm tra xem ảnh Gemini có còn tiếng Trung không bằng OCR đợt 2.
        """
        try:
            image_data = None
            
            # Ưu tiên lấy ảnh đã fix (nếu có), hoặc ảnh từ Gemini, hoặc đọc từ file
            if gemini_image_info.get('fixed', False) and 'fixed_image_data' in gemini_image_info:
                image_data = gemini_image_info['fixed_image_data']
            elif 'image_data' in gemini_image_info:
                image_data = gemini_image_info['image_data']
            elif 'image_bytes' in gemini_image_info:
                nparr = np.frombuffer(gemini_image_info['image_bytes'], np.uint8)
                image_data = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image_data is None:
                img_path = gemini_image_info.get('path') or gemini_image_info.get('file_path')
                if img_path and os.path.exists(img_path):
                    image_data = cv2.imread(img_path)
            
            if image_data is None:
                return {'has_chinese': False, 'chinese_chars': 0, 'ocr_results': []}
            
            # Encode ảnh sang bytes để gửi OCR
            _, img_encoded = cv2.imencode('.jpg', image_data, [cv2.IMWRITE_JPEG_QUALITY, 90])
            img_bytes = img_encoded.tobytes()
            
            # Gọi OCRProcessor (Google Vision)
            ocr_results = self.ocr_processor.process_image(img_bytes)
            
            # Phân tích kết quả OCR
            total_chinese_chars = 0
            chinese_details = []
            
            for i, (text, bbox) in enumerate(ocr_results):
                if not text or not text.strip():
                    continue
                
                # Hàm kiểm tra chữ Hán
                has_chinese, count, hanzi_list = self._check_chinese_in_text(text)
                
                if has_chinese:
                    total_chinese_chars += count
                    chinese_details.append({
                        'text': text,
                        'bbox': bbox,
                        'count': count,
                        'hanzi_list': hanzi_list
                    })
            
            if total_chinese_chars > 0:
                logger.warning(f"   ⚠️ Phát hiện {total_chinese_chars} chữ Hán sót lại trong ảnh.")

            return {
                'has_chinese': total_chinese_chars > 0,
                'chinese_chars': total_chinese_chars,
                'text_blocks': len(ocr_results),
                'ocr_results': ocr_results,
                'chinese_details': chinese_details
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra tiếng Trung: {e}")
            return {'has_chinese': False, 'chinese_chars': 0, 'ocr_results': []}
    
    def _check_chinese_in_text(self, text: str) -> Tuple[bool, int, List[str]]:
        """Kiểm tra chữ Hán trong text"""
        if not text or not isinstance(text, str):
            return False, 0, []
        
        hanzi_chars = []
        for char in text:
            try:
                code_point = ord(char)
                if (0x4E00 <= code_point <= 0x9FFF) or \
                   (0x3400 <= code_point <= 0x4DBF) or \
                   (0xF900 <= code_point <= 0xFAFF):
                    hanzi_chars.append(char)
            except:
                continue
        
        return len(hanzi_chars) > 0, len(hanzi_chars), hanzi_chars
    
    def _create_batch_from_gemini_images(self, gemini_tracked_images: List[Dict]) -> Tuple[Optional[str], Dict]:
        """Ghép các ảnh Gemini thành một batch để tiết kiệm request OCR"""
        if not gemini_tracked_images:
            return None, {}
        
        logger.info(f"📦 Post-Check: Tạo batch OCR từ {len(gemini_tracked_images)} ảnh")
        timestamp = int(time.time())
        
        images_data = []
        mapping_info = {
            'batch_id': f"gemini_batch_{timestamp}",
            'images': {},
            'positions': {},
            'gemini_info': []
        }
        
        current_y = 0
        valid_count = 0
        
        for idx, img_info in enumerate(gemini_tracked_images):
            try:
                # Lấy dữ liệu ảnh
                image_data = img_info.get('image_data')
                if image_data is None:
                    img_path = img_info.get('path')
                    if img_path and os.path.exists(img_path):
                        image_data = cv2.imread(img_path)
                
                if image_data is None: continue
                
                h, w = image_data.shape[:2]
                
                # Lưu thông tin mapping
                img_mapping = {
                    'original_index': idx,
                    'original_path': img_info.get('path', ''),
                    'original_url': img_info.get('original_url', ''),
                    'filename': img_info.get('filename', f'image_{idx}')
                }
                
                mapping_info['images'][valid_count] = img_mapping
                mapping_info['positions'][valid_count] = {'start_y': current_y, 'end_y': current_y + h, 'width': w, 'height': h}
                
                images_data.append({'image': image_data, 'height': h, 'width': w})
                
                current_y += h
                valid_count += 1
                
            except Exception:
                continue
        
        if valid_count == 0: return None, {}
        
        # Ghép ảnh dọc
        max_width = max(img['width'] for img in images_data)
        canvas = np.ones((current_y, max_width, 3), dtype=np.uint8) * 255
        
        curr_y = 0
        for img in images_data:
            h, w = img['height'], img['width']
            x_offset = (max_width - w) // 2
            canvas[curr_y:curr_y+h, x_offset:x_offset+w] = img['image']
            curr_y += h
            
        batch_filename = f"gemini_batch_{timestamp}.jpg"
        batch_path = os.path.join(self.temp_batch_dir, batch_filename)
        cv2.imwrite(batch_path, canvas, [cv2.IMWRITE_JPEG_QUALITY, 95])
        
        return batch_path, mapping_info

    def _distribute_ocr_results(self, batch_ocr_results, mapping_info):
        """Chia kết quả OCR batch về từng ảnh con"""
        image_ocr_map = {idx: [] for idx in mapping_info.get('images', {}).keys()}
        if not batch_ocr_results: return image_ocr_map
        
        max_width = 0
        for idx, pos in mapping_info['positions'].items():
            if pos['width'] > max_width: max_width = pos['width']
            
        for text, bbox in batch_ocr_results:
            x1, y1, x2, y2 = bbox
            text_cy = (y1 + y2) / 2
            
            # Tìm xem text thuộc ảnh nào
            found_img_idx = None
            for idx, pos in mapping_info['positions'].items():
                if pos['start_y'] <= text_cy < pos['end_y']:
                    found_img_idx = idx
                    break
            
            if found_img_idx is not None:
                pos = mapping_info['positions'][found_img_idx]
                img_width = pos['width']
                x_offset = (max_width - img_width) // 2
                start_y = pos['start_y']
                
                local_bbox = (
                    max(0, x1 - x_offset),
                    max(0, y1 - start_y),
                    min(img_width, x2 - x_offset),
                    min(pos['height'], y2 - start_y)
                )
                
                # Chỉ lấy nếu box hợp lệ
                if local_bbox[2] > local_bbox[0] and local_bbox[3] > local_bbox[1]:
                    image_ocr_map[found_img_idx].append((text, local_bbox))
                    
        return image_ocr_map

    def _fix_single_gemini_image(self, gemini_info: Dict, ocr_results: List[Tuple[str, Tuple]]) -> Tuple[bool, Optional[str], Optional[np.ndarray], int]:
        """
        Sửa ảnh: Dịch text tiếng Trung và vẽ lại bằng ImageProcessor.
        Trả về: (Success, Path, Image, ProcessedCount)
        """
        try:
            # 1. Lấy dữ liệu ảnh gốc
            image_data = gemini_info.get('image_data')
            if image_data is None:
                img_path = gemini_info.get('original_path') or gemini_info.get('path')
                if img_path and os.path.exists(img_path):
                    image_data = cv2.imread(img_path)
            
            if image_data is None: return False, None, None, 0
            
            # 2. Lọc ra các khối text cần dịch (chứa tiếng Trung)
            blocks_to_process = []
            for text, bbox in ocr_results:
                if not text or not text.strip(): continue
                has_chinese, _, _ = self._check_chinese_in_text(text)
                if has_chinese:
                    blocks_to_process.append((text, bbox))
            
            if not blocks_to_process: return False, None, None, 0
            
            processed_count = len(blocks_to_process)
            logger.info(f"   🛠️ Đang sửa {processed_count} cụm từ tiếng Trung sót lại...")

            # 3. Dùng TextTranslator để dịch và phân loại
            processed_blocks, _ = self.translator.classify_and_process_blocks(
                blocks_to_process, 
                gemini_info.get('original_url', '')
            )
            
            if not processed_blocks:
                logger.warning("   ⚠️ Không dịch được block nào.")
                return False, None, None, 0

            # 4. Dùng ImageProcessor để vẽ lại (Inpainting + Draw Text)
            fixed_image = self.img_processor.process_image_with_text(
                image_data, 
                processed_blocks, 
                ignore_blocks=[] 
            )
            
            if fixed_image is None:
                logger.error("   ❌ ImageProcessor vẽ lại thất bại.")
                return False, None, None, 0
            
            # 5. Lưu ảnh đã sửa
            timestamp = int(time.time())
            url_hash = hashlib.md5(gemini_info.get('original_url', '').encode()).hexdigest()[:8]
            filename = gemini_info.get('filename', f'gemini_fixed_{timestamp}')
            clean_filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
            
            fixed_filename = f"repaired_{timestamp}_{url_hash}_{clean_filename[-30:]}.jpg"
            fixed_path = os.path.join(self.temp_batch_dir, fixed_filename)
            
            cv2.imwrite(fixed_path, fixed_image, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            logger.info(f"   ✅ Đã sửa và lưu: {fixed_filename}")
            return True, fixed_path, fixed_image, processed_count
            
        except Exception as e:
            logger.error(f"❌ Lỗi quy trình sửa ảnh (Fix): {e}")
            traceback.print_exc()
            return False, None, None, 0
    
    def _process_single_gemini_image_task(self, gemini_info: Dict, ocr_results: List[Tuple[str, Tuple]]) -> Dict:
        """Task chạy song song cho từng ảnh"""
        result = {
            'fixed': False, 
            'fixed_path': None, 
            'fixed_image_data': None,
            'has_chinese_after_gemini': False,
            'chinese_chars_left': 0,
            'fixed_count': 0  # Trường mới: Số lượng cụm từ đã sửa
        }
        
        try:
            if not ocr_results: return result
            
            # Đếm số chữ Hán sót lại
            total_chinese = 0
            for text, _ in ocr_results:
                has_chinese, count, _ = self._check_chinese_in_text(text)
                if has_chinese: total_chinese += count
            
            if total_chinese == 0: return result
            
            result['has_chinese_after_gemini'] = True
            result['chinese_chars_left'] = total_chinese
            
            # Tiến hành sửa
            fixed, path, img, fixed_count = self._fix_single_gemini_image(gemini_info, ocr_results)
            
            if fixed:
                result['fixed'] = True
                result['fixed_path'] = path
                result['fixed_image_data'] = img
                result['fixed_count'] = fixed_count
                # Sau khi sửa xong, coi như sạch
                result['has_chinese_after_gemini'] = False 
                result['chinese_chars_left'] = 0
                
        except Exception as e:
            logger.error(f"❌ Task lỗi: {e}")
            
        return result
    
    def check_and_fix_gemini_batch(self, gemini_tracked_images: List[Dict]) -> List[Dict]:
        """
        Hàm chính: Nhận danh sách ảnh từ Gemini -> Check OCR -> Fix lỗi (Dịch & Vẽ lại).
        """
        if not gemini_tracked_images or not GEMINI_POST_CHECK_ENABLED:
            return gemini_tracked_images
        
        logger.info(f"🔍 BẮT ĐẦU HẬU KIỂM {len(gemini_tracked_images)} ẢNH TỪ GEMINI...")
        
        try:
            # 1. Tạo batch và OCR (Tiết kiệm chi phí API)
            batch_path, mapping_info = self._create_batch_from_gemini_images(gemini_tracked_images)
            
            if not batch_path:
                logger.warning("⚠️ Không tạo được batch, chuyển sang check từng ảnh.")
                return self._check_images_individually(gemini_tracked_images)
            
            # 2. OCR toàn bộ batch
            batch_ocr_results = self.ocr_processor.process_image(open(batch_path, 'rb').read())
            logger.info(f"   📄 OCR Batch hoàn tất: {len(batch_ocr_results)} text blocks.")
            
            # 3. Phân phối kết quả về từng ảnh
            image_ocr_map = self._distribute_ocr_results(batch_ocr_results, mapping_info)
            
            # 4. Xử lý song song: Check và Fix từng ảnh
            with ThreadPoolExecutor(max_workers=min(GEMINI_MAX_WORKERS, len(gemini_tracked_images))) as executor:
                futures = []
                
                # Mapping lại index
                idx_map = {} # mapping_idx -> original_list_idx
                for map_idx, info in mapping_info['images'].items():
                    idx_map[map_idx] = info['original_index']
                
                for map_idx, ocr_res in image_ocr_map.items():
                    orig_idx = idx_map.get(map_idx)
                    if orig_idx is not None and orig_idx < len(gemini_tracked_images):
                        gemini_img = gemini_tracked_images[orig_idx]
                        future = executor.submit(self._process_single_gemini_image_task, gemini_img, ocr_res)
                        futures.append((orig_idx, future))
                
                # Thu thập kết quả
                for orig_idx, future in futures:
                    try:
                        update_info = future.result(timeout=GEMINI_CHECK_TIMEOUT)
                        gemini_tracked_images[orig_idx].update(update_info)
                    except Exception as e:
                        logger.error(f"❌ Lỗi xử lý ảnh index {orig_idx}: {e}")
            
            # Xóa file tạm
            try:
                if os.path.exists(batch_path): os.remove(batch_path)
            except: pass
            
            return gemini_tracked_images
            
        except Exception as e:
            logger.error(f"❌ Lỗi luồng check batch: {e}")
            traceback.print_exc()
            return self._check_images_individually(gemini_tracked_images)
    
    def _check_images_individually(self, gemini_tracked_images: List[Dict]) -> List[Dict]:
        """Fallback: Check từng ảnh nếu batch lỗi"""
        for img_info in gemini_tracked_images:
            try:
                check_res = self.check_chinese_in_gemini_image(img_info)
                
                if check_res['has_chinese']:
                    img_info['has_chinese_after_gemini'] = True
                    img_info['chinese_chars_left'] = check_res['chinese_chars']
                    
                    # Cố gắng sửa
                    fixed, path, img, fixed_count = self._fix_single_gemini_image(img_info, check_res['ocr_results'])
                    if fixed:
                        img_info['fixed'] = True
                        img_info['fixed_path'] = path
                        img_info['fixed_image_data'] = img
                        img_info['fixed_count'] = fixed_count
                        img_info['has_chinese_after_gemini'] = False
                else:
                    img_info['has_chinese_after_gemini'] = False
                    
            except Exception as e:
                logger.error(f"❌ Lỗi check lẻ: {e}")
        return gemini_tracked_images
    
    def cleanup_temp_files(self):
        try:
            import shutil
            if os.path.exists(self.temp_batch_dir):
                shutil.rmtree(self.temp_batch_dir)
                os.makedirs(self.temp_batch_dir, exist_ok=True)
        except: pass

# Singleton instance
gemini_post_checker = GeminiPostChecker()