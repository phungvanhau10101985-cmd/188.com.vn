# text_translator.py
import re
import requests
import time
from typing import List, Tuple, Dict, Optional, Any
import hashlib
import json

from config import DEEPSEEK_API_KEY, DEEPSEEK_URL, SKIP_REGEX, DOMAIN_REGEX
from error_handler import ErrorHandler

class TextTranslator:
    def __init__(self):
        self.session = requests.Session()
        self.skip_regex = SKIP_REGEX
        self.domain_regex = DOMAIN_REGEX
        self.error_handler = ErrorHandler()
        self.chinese_regex = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df\U0002a700-\U0002b73f\U0002b740-\U0002b81f\U0002b820-\U0002ceaf]')
        self.translation_cache = {}
        
    def contains_forbidden_content(self, text: str) -> bool:
        if not text or not isinstance(text, str): return False
        return bool(self.skip_regex.search(text))
    
    def contains_chinese(self, text: str) -> bool:
        if not text or not isinstance(text, str): return False
        return bool(self.chinese_regex.search(text))
    
    def remove_chinese_characters(self, text: str) -> str:
        if not text: return text
        cleaned_text = self.chinese_regex.sub('', text)
        return re.sub(r'\s+', ' ', cleaned_text).strip()
    
    def call_deepseek_for_translation_single(self, text: str) -> str:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        if text_hash in self.translation_cache:
            cached_result = self.translation_cache[text_hash]
            print(f"    ⚡ [CACHE] '{text}' ➡️ '{cached_result}'")
            return cached_result
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}", 
            "Content-Type": "application/json"
        }
        
        prompt = f"""Dịch đoạn văn bản ngắn sau sang tiếng Việt (chuẩn thương mại điện tử):
"{text}"
YÊU CẦU:
1. CHỈ trả về kết quả tiếng Việt. KHÔNG lặp lại prompt.
2. Giữ nguyên số liệu (45kg, 5cm...).
3. Dịch cả tiếng Anh lẫn tiếng Trung nếu có.
4. Không giải thích thêm."""

        payload = {
            "model": "deepseek-chat",
            "messages": [{"role":"user","content":prompt}],
            "temperature": 0.1,
            "max_tokens": 100
        }
        
        def _do_request():
            r = self.session.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            if not r.content: raise Exception("API trả về response rỗng")
            try: j = r.json()
            except json.JSONDecodeError: raise Exception(f"API trả về JSON không hợp lệ")
            if "choices" not in j or not j["choices"]: raise Exception(f"API response thiếu choices")
            
            translated = j["choices"][0]["message"]["content"].strip()
            translated = re.sub(r'^(Dịch:|Bản dịch:|Translation:|Vietnamese:)\s*', '', translated, flags=re.IGNORECASE)
            translated = translated.strip('"').strip("'")
            translated = re.sub(r'\s+', ' ', translated).strip()
            return translated
        
        translated = self.error_handler.smart_retry(_do_request, max_immediate_retries=3, long_wait_minutes=3)
        print(f"    🟡 [DỊCH] '{text}' ➡️ '{translated}'")
        self.translation_cache[text_hash] = translated
        return translated 
    
    def process_jin_weight_text(self, text: str) -> str:
        if not text or '斤' not in text: return text
        original_text = text
        result = text
        patterns = [
            r'(\d+)\s*[-~–—至到]\s*(\d+)\s*斤', r'(\d+)\s*斤',
            r'(\d+)\s*[~≈∼∽]\s*(\d+)\s*斤', r'(\d+)\s*[至到]\s*(\d+)\s*斤',
            r'(\d+)\s*斤\s*[-~–—至到]\s*(\d+)\s*斤', r'(\d+)\s*[左右大约約约]\s*斤',
            r'(\d+)\s*斤\s*[左右大约約约]',
        ]
        for pattern in patterns:
            matches = re.finditer(pattern, result)
            for match in matches:
                full_match = match.group(0)
                numbers = [int(num) for num in re.findall(r'\d+', full_match)]
                if not numbers: continue
                converted_numbers = [str(round(num / 2)) for num in numbers]
                if len(numbers) == 2: replacement = f"{converted_numbers[0]}-{converted_numbers[1]}kg"
                else: replacement = f"{converted_numbers[0]}kg"
                result = result.replace(full_match, replacement)
        
        if '斤' in result and not any(char.isdigit() for char in result):
            result = result.replace('斤', "0,5kg")
        
        final_result = re.sub(r'\s+', ' ', result).strip()
        if original_text != final_result:
            print(f"    ⚖️ [QUY ĐỔI] '{original_text}' ➡️ '{final_result}'")
        return final_result

    def summarize_product_info(self, raw_text_list: List[str]) -> str:
        return "" 
    
    def classify_and_process_blocks(self, ocr_results: List[Any], image_url: str = "") -> Tuple[List[Tuple[str, tuple]], List[Tuple[str, tuple]]]:
        """
        Phân loại và xử lý text blocks. 
        Hỗ trợ input cả Dict và Tuple để tránh lỗi format.
        """
        processed_blocks = []
        ignore_blocks = []
        
        if not ocr_results: return [], []
        
        print(f"  📝 Phân tích {len(ocr_results)} khối text để dịch...")

        for item in ocr_results:
            # FIX: Handle mixed format
            if isinstance(item, dict):
                text = item.get('text', '')
                bbox = item.get('bbox', [])
            else:
                text = item[0] if len(item) > 0 else ''
                bbox = item[1] if len(item) > 1 else []

            if not text: continue
            
            if self.contains_forbidden_content(text):
                print(f"    🔴 [CẤM] Phát hiện từ khóa: '{text}' -> XÓA ẢNH")
                return None
            
            has_chinese = self.contains_chinese(text)
            has_jin = '斤' in text
            is_domain = bool(self.domain_regex.search(text))
            is_old_year = any(y in text for y in ['2019', '2020', '2021', '2022', '2023', '2024'])
            
            if is_domain:
                print(f"    🗑️ [XÓA] Domain: '{text}'")
                processed_blocks.append(("", bbox))
            elif is_old_year:
                 print(f"    🗑️ [XÓA] Năm cũ: '{text}'")
                 processed_blocks.append(("", bbox))
            elif has_jin:
                if any(c.isdigit() for c in text):
                    processed = self.process_jin_weight_text(text)
                    processed = self.remove_chinese_characters(processed)
                    processed_blocks.append((processed, bbox))
                else:
                    processed_blocks.append(("Trọng Lượng TQ/ 1 cân = 0,5kg", bbox))
            elif has_chinese:
                if len(text.strip()) == 1:
                    ignore_blocks.append((text, bbox))
                else:
                    translated_text = self.call_deepseek_for_translation_single(text)
                    processed_blocks.append((translated_text, bbox))
            else:
                ignore_blocks.append((text, bbox))
        
        return processed_blocks, ignore_blocks