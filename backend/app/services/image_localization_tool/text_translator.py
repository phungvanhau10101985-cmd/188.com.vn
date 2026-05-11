# text_translator.py
import re
import unicodedata
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

    @staticmethod
    def _is_standalone_cm_measurement(text: str) -> bool:
        """Standalone cm measurement: redraw with the same processed group, no DeepSeek."""
        if not text or not isinstance(text, str):
            return False
        t = unicodedata.normalize("NFKC", text)
        t = re.sub(r"[\s\u3000\r\n]+", "", t)
        return bool(re.fullmatch(r"(?:\d+(?:[\.,]\d+)?|[\.,]\d+)[cC][mM]", t))
    

    def _is_size_table_keyword_text(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).lower()
        keywords = [
            "\u5c3a\u7801", "\u5c3a\u5bf8", "\u5c3a\u5bf8\u8868", "\u5c3a\u7801\u8868",
            "\u7801\u6570", "\u89c4\u683c", "\u89c4\u683c\u8868",
            "size", "size chart", "size table", "b\u1ea3ng size", "bang size",
            "ch\u1ecdn size", "chon size", "size guide", "sizing",
            "\u80f8\u56f4", "\u8170\u56f4", "\u81c0\u56f4", "\u80a9\u5bbd",
            "\u8863\u957f", "\u8896\u957f", "\u88e4\u957f", "\u88d9\u957f",
            "\u8eab\u9ad8", "\u4f53\u91cd", "\u811a\u957f", "\u5185\u957f",
            "\u978b\u7801", "\u6b27\u7801", "\u5398\u7c73",
        ]
        return any(k in t for k in keywords)

    def _is_size_token_text(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).strip().lower()
        compact = re.sub(r"[\s\u3000]+", "", t)
        if self._is_standalone_cm_measurement(compact):
            return True
        if re.fullmatch(r"(?:xxxs|xxs|xs|s|m|l|xl|xxl|xxxl|xxxxl|\d{2,3})(?:[-/](?:xxxs|xxs|xs|s|m|l|xl|xxl|xxxl|xxxxl|\d{2,3}))*", compact):
            return True
        if re.fullmatch(r"\d+(?:[\.,]\d+)?(?:cm|mm|kg|g|\u65a4)?", compact):
            return True
        return False

    def _has_size_table_context(self, items: List[Tuple[str, tuple]]) -> bool:
        texts = [str(text or "") for text, _ in items]
        if any(self._is_size_table_keyword_text(text) for text in texts):
            return True
        size_like_count = sum(1 for text in texts if self._is_size_token_text(text))
        has_unit = any(re.search(r"(?:cm|\u5398\u7c73|mm|kg|\u65a4)", unicodedata.normalize("NFKC", text), re.IGNORECASE) for text in texts)
        return size_like_count >= 4 and has_unit

    def _is_size_table_block(self, text: str) -> bool:
        return self._is_size_table_keyword_text(text) or self._is_size_token_text(text)


    def _has_factory_intro_context(self, items: List[Tuple[str, tuple]]) -> bool:
        texts = [unicodedata.normalize("NFKC", str(text or "")).lower() for text, _ in items]
        combined = "\n".join(texts)
        strong_keywords = [
            "\u5b9e\u529b\u5de5\u5382",  # factory strength / factory intro
            "\u751f\u4ea7\u8f66\u95f4",  # production workshop
            "\u5236\u978b\u56e2\u961f",  # shoemaking team
            "\u8bbe\u8ba1\u56e2\u961f",  # design team
            "\u5f00\u53d1\u8bbe\u8ba1\u56e2\u961f",  # development/design team
            "\u51fa\u8d27\u54c1\u8d28\u4e25\u63a7",  # strict outbound quality control
            "\u54c1\u8d28\u4e25\u63a7",  # strict quality control
        ]
        if any(k in combined for k in strong_keywords):
            return True

        signals = [
            "\u5de5\u5382",  # factory
            "\u8f66\u95f4",  # workshop
            "\u516c\u53f8",  # company
            "\u978b\u4e1a",  # footwear company/industry
            "\u56e2\u961f",  # team
            "\u8bbe\u8ba1\u5e08",  # designer
            "\u5f00\u53d1",  # development
            "\u751f\u4ea7\u7ebf",  # production line
            "\u8d28\u68c0",  # quality inspection
            "\u54c1\u63a7",  # quality control
            "\u5458\u5de5",  # staff
            "\u5de5\u4eba",  # worker
        ]
        hit_count = sum(1 for k in signals if k in combined)
        return hit_count >= 2

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

        normalized_items = []
        for item in ocr_results:
            # FIX: Handle mixed format
            if isinstance(item, dict):
                text = item.get('text', '')
                bbox = item.get('bbox', [])
            else:
                text = item[0] if len(item) > 0 else ''
                bbox = item[1] if len(item) > 1 else []
            if text:
                normalized_items.append((text, bbox))

        if self._has_factory_intro_context(normalized_items):
            print("    [FACTORY INTRO] delete image")
            return None

        size_table_context = self._has_size_table_context(normalized_items)
        if size_table_context:
            print("    [SIZE TABLE] delete image")
            return None

        for text, bbox in normalized_items:
            if self._is_standalone_cm_measurement(text.strip()):
                print(f"    [CM] group with processed text: '{text.strip()}'")
                processed_blocks.append((text.strip(), tuple(bbox)))
                continue
            
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
