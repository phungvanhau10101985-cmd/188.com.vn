# ocr_processor.py
import io
import re
import time
from typing import List, Tuple, Dict, Optional
import numpy as np
import cv2

from google.cloud import vision
from config import GCP_KEY_FILE, PAID_OCR_PROVIDER, OCR_CONFIDENCE_THRESHOLD, OCR_WORD_CJK_SUPPLEMENT
from error_handler import ErrorHandler


def _gcp_json_path_for_vision() -> str:
    """Tránh from_service_account_file('') → [Errno 2] No such file or directory: ''"""
    raw = (GCP_KEY_FILE or "").strip()
    if not raw:
        raise RuntimeError(
            "Thiếu file JSON Google Cloud Vision (GCP_KEY_FILE rỗng). "
            "Đặt IMAGE_LOCALIZATION_GCP_KEY_FILE hoặc GOOGLE_APPLICATION_CREDENTIALS trỏ tới service account, "
            "hoặc đặt file gcp-vision-service-account.json trong thư mục runtime image localization (xem backend/.env.example)."
        )
    return raw


def _iou_xyxy(a: Tuple[int, ...], b: Tuple[int, ...]) -> float:
    """Intersection over union của hai bbox (x1,y1,x2,y2)."""
    if len(a) < 4 or len(b) < 4:
        return 0.0
    ax1, ay1, ax2, ay2 = float(a[0]), float(a[1]), float(a[2]), float(a[3])
    bx1, by1, bx2, by2 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(1.0, (ax2 - ax1) * (ay2 - ay1))
    area_b = max(1.0, (bx2 - bx1) * (by2 - by1))
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class OCRProcessor:
    def __init__(self):
        self.paid_extraction_count = 0
        self.error_handler = ErrorHandler()
        self.chinese_char_regex = re.compile(
            r'[\u4E00-\u9FFF\u3400-\u4DBF\uF900-\uFAFF\u20000-\u2A6DF\u2A700-\u2B73F\u2B740-\u2B81F\u2B820-\u2CEAF\u2CEB0-\u2EBEF]'
        )
    
    def contains_chinese(self, text: str) -> bool:
        if not text or not isinstance(text, str): return False
        return bool(self.chinese_char_regex.search(text))

    def _filter_bad_blocks(self, results: List[Tuple[str, tuple]], image_bytes: bytes) -> List[Tuple[str, tuple]]:
        """
        Lọc bỏ các kết quả OCR bị nhiễu.
        SỬA ĐỔI: Chỉ lọc bỏ các khung RẤT TO (rác > 60% ảnh), giữ lại mọi text khác.
        """
        if not results: return []
        
        # Giải mã ảnh từ bytes để lấy kích thước
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None: return results
            img_h, img_w = img.shape[:2]
            img_area = img_h * img_w
        except Exception as e:
            # Nếu lỗi đọc ảnh thì bỏ qua bước lọc, trả về kết quả gốc
            print(f"⚠️ Không thể đọc kích thước ảnh để lọc nhiễu: {e}")
            return results

        valid_results = []
        for text, bbox in results:
            x1, y1, x2, y2 = bbox
            w = x2 - x1
            h = y2 - y1
            box_area = w * h
            
            # --- CÁC LUẬT LỌC (HEURISTICS) ---
            
            # Luật 1: Quá to so với ảnh (Lớn hơn 60% ảnh -> Khả năng cao là rác hoặc background)
            # Chỉ giữ lại luật này để loại bỏ các khung ảo bao trùm cả ảnh
            if box_area > (img_area * 0.6):
                print(f"  🗑️ Đã lọc bỏ khối text quá khổ (>60% ảnh): '{text[:20]}...'")
                continue

            # --- ĐÃ XÓA BỎ LUẬT KIỂM TRA ĐỘ DÀI VÀ MẬT ĐỘ ---
            # Để đảm bảo không xóa nhầm các từ ngắn như màu sắc, size, v.v.
            
            valid_results.append((text, bbox))
            
        return valid_results
    
    def extract_text_google_vision(self, image_bytes: bytes) -> List[Tuple[str, tuple]]:
        """OCR thường - Có retry vô tận"""
        def _do_ocr():
            client = vision.ImageAnnotatorClient.from_service_account_file(_gcp_json_path_for_vision())
            image = vision.Image(content=image_bytes)
            image_context = vision.ImageContext(language_hints=['zh', 'vi', 'en'])
            
            response = client.text_detection(image=image, image_context=image_context)
            if response.error.message: raise Exception(f"Google Vision error: {response.error.message}")
                
            texts = response.text_annotations
            results = []
            if texts:
                # texts[0] là toàn bộ văn bản, từ [1] trở đi là từng từ/câu
                for text in texts[1:]:
                    desc = text.description.strip()
                    if not desc: continue
                    vertices = text.bounding_poly.vertices
                    x_coords = [vertex.x for vertex in vertices]
                    y_coords = [vertex.y for vertex in vertices]
                    results.append((desc, (min(x_coords), min(y_coords), max(x_coords), max(y_coords))))
            
            self.paid_extraction_count += 1
            return results
        
        # Smart retry vô tận
        return self.error_handler.smart_retry(_do_ocr, max_immediate_retries=3, long_wait_minutes=3)

    def _append_cjk_from_word_detection(
        self,
        paragraph_results: List[Tuple[str, tuple]],
        image_bytes: bytes,
    ) -> List[Tuple[str, tuple]]:
        """
        Document layout đôi khi drop cả block (confidence thấp / chữ nghệ thuật / màu nền tương phản khác).
        Toàn văn `document.text` vẫn có CJK -> bổ sung các bbox cấp từ/word từ `text_detection`.
        """
        stitched = "".join((t or "") for t, _ in paragraph_results)
        if self.contains_chinese(stitched):
            return paragraph_results
        extras: List[Tuple[str, tuple]] = []
        try:
            raw_word = self._extract_words_google_vision_raw(image_bytes)
        except Exception as e:
            print(f"  ⚠️ Không merge CJK word-level: {e}")
            return paragraph_results
        for text, bbox in raw_word:
            if not text or not self.contains_chinese(text.strip()):
                continue
            dup = False
            for _, eb in paragraph_results:
                if _iou_xyxy(bbox, eb) >= 0.88:
                    dup = True
                    break
            for _, eb in extras:
                if _iou_xyxy(bbox, eb) >= 0.88:
                    dup = True
                    break
            if not dup:
                extras.append((text, bbox))
        if extras:
            print(
                f"    🔗 Đã bổ sung {len(extras)} cụm CJK từ nhận dạng word-level "
                "(Document OCR thiếu block)"
            )
        out = list(paragraph_results)
        out.extend(extras)
        return out

    def _extract_words_google_vision_raw(self, image_bytes: bytes) -> List[Tuple[str, tuple]]:
        """Chỉ lấy (text,bbox) từ text_detection annotations[1:] — không tăng counter (gọi từ merge)."""
        client = vision.ImageAnnotatorClient.from_service_account_file(_gcp_json_path_for_vision())
        image = vision.Image(content=image_bytes)
        image_context = vision.ImageContext(language_hints=['zh', 'vi', 'en'])
        response = client.text_detection(image=image, image_context=image_context)
        if response.error.message:
            raise Exception(f"Google Vision error: {response.error.message}")
        texts = response.text_annotations
        results = []
        if texts:
            for ann in texts[1:]:
                desc = ann.description.strip()
                if not desc:
                    continue
                vertices = ann.bounding_poly.vertices
                xs = [vertex.x for vertex in vertices]
                ys = [vertex.y for vertex in vertices]
                results.append((desc, (min(xs), min(ys), max(xs), max(ys))))
        return results
    
    def enhanced_ocr_extract(self, image_bytes: bytes) -> List[Tuple[str, tuple]]:
        """OCR nâng cao (Document Text Detection) - Có retry vô tận"""
        def _do_enhanced_ocr():
            client = vision.ImageAnnotatorClient.from_service_account_file(_gcp_json_path_for_vision())
            image = vision.Image(content=image_bytes)
            image_context = vision.ImageContext(language_hints=['zh', 'vi', 'en'])
            
            response = client.document_text_detection(image=image, image_context=image_context)
            if response.error.message: raise Exception(f"Google Vision enhanced error: {response.error.message}")
                
            document = response.full_text_annotation
            results: List[Tuple[str, tuple]] = []
            full_doc = ""
            if document:
                full_doc = (document.text or "").strip()
                for page in document.pages:
                    for block in page.blocks:
                        block_conf = float(getattr(block, "confidence", 1.0) or 1.0)
                        for paragraph in block.paragraphs:
                            paragraph_text = "".join(
                                ["".join([s.text for s in w.symbols]) for w in paragraph.words]
                            )
                            if not paragraph_text.strip():
                                continue
                            para_conf = getattr(paragraph, "confidence", None)
                            has_cjk = self.contains_chinese(paragraph_text)
                            # Trước đây: bỏ cả block nếu block_conf thấp → dễ mất hẳn khối tiếng Trung nửa dưới.
                            if not has_cjk:
                                if para_conf is not None and float(para_conf) < OCR_CONFIDENCE_THRESHOLD:
                                    continue
                                if para_conf is None and block_conf < OCR_CONFIDENCE_THRESHOLD:
                                    continue

                            words_vertices = []
                            for w in paragraph.words:
                                words_vertices.extend(w.bounding_box.vertices)
                            if not words_vertices:
                                continue
                            xs = [v.x for v in words_vertices]
                            ys = [v.y for v in words_vertices]
                            results.append((paragraph_text, (min(xs), min(ys), max(xs), max(ys))))

                stitched_para = "".join((t or "") for t, _ in results)
                # document.text không có CJK nhưng vẫn có thể thiếu paragraph (Vision chỉ trả «230», v.v.)
                if not self.contains_chinese(stitched_para) and (
                    OCR_WORD_CJK_SUPPLEMENT or (full_doc and self.contains_chinese(full_doc))
                ):
                    results = self._append_cjk_from_word_detection(results, image_bytes)

            # Nếu enhanced không ra kết quả nhưng không lỗi -> Fallback về thường
            if not results:
                return self.extract_text_google_vision(image_bytes)

            self.paid_extraction_count += 1
            return results
        
        # Smart retry vô tận
        return self.error_handler.smart_retry(_do_enhanced_ocr, max_immediate_retries=3, long_wait_minutes=3)
    
    def process_image(self, image_bytes: bytes) -> List[Tuple[str, tuple]]:
        """
        Xử lý ảnh: OCR -> Filter -> Log kết quả
        """
        print("🔍 Đang nhận diện text bằng Google Vision (Chế độ kiên trì)...")
        
        # 1. Gọi API để lấy kết quả thô
        raw_results = self.enhanced_ocr_extract(image_bytes)
        
        # 2. Lọc bỏ các kết quả sai/nhiễu/quá khổ trước khi trả về
        clean_results = self._filter_bad_blocks(raw_results, image_bytes)
        
        # --- LOGGING CHI TIẾT ---
        if clean_results:
            print(f"    📄 [OCR KẾT QUẢ] Tìm thấy {len(clean_results)} cụm text:")
            for i, (text, bbox) in enumerate(clean_results):
                # In ra nội dung text tìm thấy để debug
                print(f"      👉 Block {i+1}: '{text}'")
        else:
            print("    ⚪ [OCR KẾT QUẢ] Không tìm thấy text nào (Ảnh sạch).")
        # ------------------------
        
        return clean_results
    
    def get_stats(self):
        return {
            'total_images_processed': self.paid_extraction_count,
            'error_stats': self.error_handler.get_stats()
        }