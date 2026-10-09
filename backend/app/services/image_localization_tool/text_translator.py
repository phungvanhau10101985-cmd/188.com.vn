# text_translator.py
import os
import re
import unicodedata
import requests
import time
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Any
import hashlib
import json

from config import DEEPSEEK_API_KEY, DEEPSEEK_URL, SKIP_REGEX, DOMAIN_REGEX
from error_handler import ErrorHandler

try:
    from app.services.deepseek_http import deepseek_chat_completions, deepseek_message_text
except Exception:  # standalone tool path / tests without app package
    deepseek_chat_completions = None
    deepseek_message_text = None

@dataclass
class SizeLaundryFlags:
    is_size: bool = False
    is_laundry: bool = False
    comprehensive: bool = False

    @property
    def is_size_or_laundry(self) -> bool:
        return self.is_size or self.is_laundry


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

    def _is_explicit_size_chart_title(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).lower()
        compact = re.sub(r"[\s\u3000:_：\-|/]+", "", t)
        title_keywords = [
            "\u5c3a\u7801\u8868",  # size table
            "\u5c3a\u5bf8\u8868",  # dimension table
            "\u5c3a\u7801\u5bf9\u7167\u8868",
            "\u5c3a\u5bf8\u5bf9\u7167\u8868",
            "\u9009\u62e9\u5c3a\u7801",
            "\u9009\u5c3a\u7801",
            "sizechart",
            "sizetable",
            "sizeguide",
            "bangsize",
            "b\u1ea3ngsize",
            "chonsize",
            "ch\u1ecdnsize",
            "huongdanchonsize",
            "h\u01b0\u1edbngd\u1eabnch\u1ecdnsize",
        ]
        return any(keyword in compact for keyword in title_keywords)

    def _has_product_info_guard(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).lower()
        product_info_keywords = [
            "product info", "material show", "material",
            "\u4ea7\u54c1\u4fe1\u606f", "\u5546\u54c1\u4fe1\u606f",
            "\u4ea7\u54c1\u53c2\u6570", "\u57fa\u672c\u53c2\u6570", "\u53c2\u6570",
            "\u6750\u8d28", "\u6750\u6599", "\u9762\u6599", "\u76ae\u9762",
            "\u989c\u8272", "\u8272\u53f7", "\u6b3e\u53f7", "\u578b\u53f7",
            "\u5e2e\u9ad8", "\u5185\u589e\u9ad8", "\u5e95\u9ad8", "\u8ddf\u9ad8",
            "kpu", "\u805a\u6c28\u916f",
        ]
        return any(keyword in t for keyword in product_info_keywords)

    def _is_size_dimension_label(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).lower()
        labels = [
            "\u80f8\u56f4", "\u8170\u56f4", "\u81c0\u56f4", "\u80a9\u5bbd",
            "\u8863\u957f", "\u8896\u957f", "\u88e4\u957f", "\u88d9\u957f",
            "\u8eab\u9ad8", "\u4f53\u91cd", "\u811a\u957f", "\u5185\u957f",
            "\u978b\u7801", "\u6b27\u7801", "\u7801\u6570",
            "chest", "waist", "hip", "shoulder", "length", "sleeve",
            "height", "weight", "foot length",
        ]
        return any(label in t for label in labels)

    def _has_size_table_context(self, items: List[Tuple[str, tuple]]) -> bool:
        texts = [str(text or "") for text, _ in items if str(text or "").strip()]
        if not texts:
            return False

        combined = "\n".join(unicodedata.normalize("NFKC", text).lower() for text in texts)
        has_explicit_title = any(self._is_explicit_size_chart_title(text) for text in texts)
        size_token_count = sum(1 for text in texts if self._is_size_token_text(text))
        size_label_count = sum(1 for text in texts if self._is_size_dimension_label(text))
        has_unit = bool(re.search(r"(?:cm|\u5398\u7c73|mm|kg|\u65a4)", combined, re.IGNORECASE))
        has_table_word = bool(re.search(r"(?:\u8868|\u5bf9\u7167\u8868|table|chart)", combined, re.IGNORECASE))
        has_size_keyword = any(self._is_size_table_keyword_text(text) for text in texts)
        size_block_count = sum(
            1
            for text in texts
            if (
                self._is_size_token_text(text)
                or self._is_size_dimension_label(text)
                or self._is_explicit_size_chart_title(text)
            )
        )
        size_block_ratio = size_block_count / max(1, len(texts))

        if has_explicit_title:
            return True

        # Aggressive policy: any clear size chart/table section deletes the whole image,
        # even when the image also contains model/product/spec text.
        if has_size_keyword and size_label_count >= 1 and size_token_count >= 3:
            return True
        if size_label_count >= 2 and size_token_count >= 5:
            return True
        if has_table_word and size_label_count >= 1 and size_token_count >= 3:
            return True

        return (
            has_table_word
            and size_token_count >= 5
            and size_label_count >= 2
            and has_unit
            and size_block_ratio >= 0.35
        )

    def _is_size_table_block(self, text: str) -> bool:
        return (
            self._is_explicit_size_chart_title(text)
            or self._is_size_dimension_label(text)
            or self._is_size_token_text(text)
        )

    def _is_laundry_care_text(self, text: str) -> bool:
        if not text:
            return False
        t = unicodedata.normalize("NFKC", str(text)).lower()
        compact = re.sub(r"[\s\u3000:_：\-|/]+", "", t)
        keywords = [
            "\u6d17\u6da4", "\u6e05\u6d17", "\u4fdd\u517b", "\u62a4\u7406", "\u6e05\u6d01",
            "\u6c34\u6d17", "\u5e72\u6d17", "\u624b\u6d17", "\u673a\u6d17",
            "\u667e\u5e72", "\u98ce\u5e72", "\u9634\u5e72", "\u70d8\u5e72",
            "\u71a8\u70eb", "\u70eb\u6597", "\u6f02\u767d", "\u4e0d\u53ef\u6f02\u767d",
            "\u6d17\u6c34\u551b", "\u6d17\u6da4\u6807\u8bc6", "\u6d17\u6807",
            "\u6d17\u6da4\u8bf4\u660e", "\u6d17\u6da4\u65b9\u5f0f", "\u6d17\u6da4\u5efa\u8bae", "\u6d17\u6da4\u5c0f\u8d34\u58eb",
            "washing", "washinginstruction", "carelabel", "washinglabel",
            "handwash", "machinewash", "dryclean", "donotbleach", "donotiron", "tumbledry",
        ]
        return any(k in compact or k in t for k in keywords)

    def _has_laundry_care_context(self, items: List[Tuple[str, tuple]]) -> bool:
        texts = [str(text or "") for text, _ in items if str(text or "").strip()]
        if not texts:
            return False
        combined = "\n".join(unicodedata.normalize("NFKC", text).lower() for text in texts)
        laundry_count = sum(1 for text in texts if self._is_laundry_care_text(text))
        strong_title = bool(
            re.search(
                r"(\u6d17\u6da4\u8bf4\u660e|\u6d17\u6da4\u65b9\u5f0f|\u6d17\u6da4\u5efa\u8bae|\u6d17\u6c34\u551b|\u62a4\u7406\u8bf4\u660e|washing\s*instruction|care\s*label|washing\s*label)",
                combined,
                re.IGNORECASE,
            )
        )
        has_care_action = bool(
            re.search(
                r"(\u624b\u6d17|\u673a\u6d17|\u5e72\u6d17|\u6c34\u6d17|\u6f02\u767d|\u71a8\u70eb|hand\s*wash|machine\s*wash|dry\s*clean|bleach|iron)",
                combined,
                re.IGNORECASE,
            )
        )
        return strong_title or (laundry_count >= 2 and has_care_action)


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
        if not (DEEPSEEK_API_KEY or "").strip():
            raise RuntimeError(
                "IMAGE_LOCALIZATION_FATAL_DEPENDENCY:deepseek_missing_key: "
                "Thiếu DEEPSEEK_API_KEY nên không thể dịch ảnh bằng DeepSeek."
            )

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
2. Giữ nguyên số đo cm và số đã ghi kg. Nếu có 斤 thì đổi sang kg (1斤 = 0,5kg).
3. Dịch cả tiếng Anh lẫn tiếng Trung nếu có.
4. Không giải thích thêm."""

        model = (os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash").strip() or "deepseek-v4-flash"
        payload = {
            "model": model,
            "messages": [{"role":"user","content":prompt}],
            "temperature": 0.1,
            # V4 thinking mặc định chiếm hết budget → content rỗng, bbox bị xóa trắng.
            "max_tokens": 400,
            "thinking": {"type": "disabled"},
        }
        
        def _clean_translated(raw: str) -> str:
            translated = (raw or "").strip()
            translated = re.sub(r'^(Dịch:|Bản dịch:|Translation:|Vietnamese:)\s*', '', translated, flags=re.IGNORECASE)
            translated = translated.strip('"').strip("'")
            return re.sub(r'\s+', ' ', translated).strip()

        def _do_request():
            if deepseek_chat_completions is not None:
                r = deepseek_chat_completions(
                    payload, timeout=30, api_url=DEEPSEEK_URL, api_key=DEEPSEEK_API_KEY
                )
            else:
                r = self.session.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30)
            if r.status_code >= 400:
                raise RuntimeError(f"DeepSeek API lỗi HTTP {r.status_code}: {(r.text or '')[:800]}")
            if not r.content: raise Exception("API trả về response rỗng")
            try: j = r.json()
            except json.JSONDecodeError: raise Exception(f"API trả về JSON không hợp lệ")
            if "choices" not in j or not j["choices"]: raise Exception(f"API response thiếu choices")
            if deepseek_message_text is not None:
                translated = deepseek_message_text(j)
            else:
                msg = j["choices"][0].get("message") or {}
                translated = str(msg.get("content") or "").strip() or str(msg.get("reasoning_content") or "").strip()
            return _clean_translated(translated)
        
        translated = self.error_handler.smart_retry(_do_request, max_immediate_retries=3, long_wait_minutes=3)
        print(f"    🟡 [DỊCH] '{text}' ➡️ '{translated}'")
        self.translation_cache[text_hash] = translated
        return translated 
    
    def _jin_to_kg_label(self, raw_number: str) -> str:
        value = float(str(raw_number).replace(",", "."))
        kg = value / 2.0
        if abs(kg - round(kg)) < 1e-9:
            return f"{int(round(kg))}kg"
        return f"{kg:.1f}kg"

    def _is_bare_chinese_weight_header(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", str(text or ""))
        if re.search(r"kg|公斤|千克", compact, re.IGNORECASE):
            return False
        return bool(re.fullmatch(r"(体重|重量|净重|淨重|毛重)", compact))

    def chinese_weight_replacements(self, items: List[Tuple[str, tuple]]) -> Dict[int, str]:
        """斤 và số trần dưới cột 体重/重量 (không ghi kg) đổi sang kg. 1斤 = 0,5kg."""
        headers = []
        for idx, (text, bbox) in enumerate(items):
            if not self._is_bare_chinese_weight_header(text) or not bbox or len(bbox) < 4:
                continue
            x1, y1, x2, y2 = [float(v) for v in list(bbox)[:4]]
            headers.append((x1, y1, x2, y2))
        out: Dict[int, str] = {}
        for idx, (text, bbox) in enumerate(items):
            raw = str(text or "").strip()
            if "斤" in raw:
                converted = self.process_jin_weight_text(raw)
                if converted != raw:
                    stripped = self.remove_chinese_characters(converted).strip()
                    out[idx] = stripped or converted
                continue
            if not headers or not bbox or len(bbox) < 4:
                continue
            if not re.fullmatch(r"\d+(?:[\.,]\d+)?", raw):
                continue
            x1, y1, x2, _y2 = [float(v) for v in list(bbox)[:4]]
            cx = (x1 + x2) / 2
            best_gap = None
            for hx1, hy1, hx2, hy2 in headers:
                pad = max(8.0, (hx2 - hx1) * 0.35)
                if cx < hx1 - pad or cx > hx2 + pad or y1 + 2 < hy1:
                    continue
                gap = y1 - hy2
                if gap < -4:
                    continue
                if best_gap is None or gap < best_gap:
                    best_gap = gap
            if best_gap is None:
                continue
            out[idx] = self._jin_to_kg_label(raw)
        return out

    def review_localized_size_laundry(self, source_ocr: List[Any], output_ocr: List[Any]) -> List[str]:
        """Lỗi còn lại sau GPT: chữ Trung, 斤, thiếu cm/kg, hoặc cân nặng chưa đổi sang kg."""
        source_items = self._normalize_ocr_items(source_ocr)
        output_items = self._normalize_ocr_items(output_ocr)
        source_text = "\n".join(text for text, _bbox in source_items)
        output_text = "\n".join(text for text, _bbox in output_items)
        if source_text.strip() and not output_text.strip():
            return ["không đọc được chữ trên ảnh GPT"]
        problems: List[str] = []
        hanzi = self.chinese_regex.findall(output_text)
        if hanzi:
            problems.append(f"còn {len(hanzi)} chữ Trung")
        if "斤" in output_text:
            problems.append("còn đơn vị 斤")
        compact = output_text.replace(" ", "").replace(",", ".")

        def missing_number(raw: str) -> bool:
            norm = str(raw).replace(",", ".")
            if norm.endswith(".0"):
                norm = norm[:-2]
            if not norm:
                return False
            return re.search(rf"(?<!\d){re.escape(norm)}(?!\d)", compact) is None

        missing_cm = []
        for match in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*(?:cm|厘米)", source_text, flags=re.IGNORECASE):
            token = match.group(1)
            if missing_number(token):
                missing_cm.append(token.replace(",", "."))
        if missing_cm:
            problems.append("thiếu số đo cm: " + ", ".join(dict.fromkeys(missing_cm)))
        missing_kg = []
        for match in re.finditer(r"(\d+(?:[\.,]\d+)?)\s*(?:kg|公斤|千克)", source_text, flags=re.IGNORECASE):
            token = match.group(1)
            if missing_number(token):
                missing_kg.append(token.replace(",", "."))
        if missing_kg:
            problems.append("thiếu số kg: " + ", ".join(dict.fromkeys(missing_kg)))
        missing_converted = []
        for label in self.chinese_weight_replacements(source_items).values():
            for token in re.findall(r"\d+(?:[\.,]\d+)?", label):
                if missing_number(token):
                    missing_converted.append(token.replace(",", "."))
        if missing_converted:
            problems.append("chưa đổi cân nặng sang kg: " + ", ".join(dict.fromkeys(missing_converted)))
        return problems

    def process_jin_weight_text(self, text: str) -> str:
        if not text or '斤' not in text: return text
        original_text = text
        result = text
        patterns = [
            r'(\d+(?:[\.,]\d+)?)\s*[-~–—至到]\s*(\d+(?:[\.,]\d+)?)\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*[~≈∼∽]\s*(\d+(?:[\.,]\d+)?)\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*[至到]\s*(\d+(?:[\.,]\d+)?)\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*斤\s*[-~–—至到]\s*(\d+(?:[\.,]\d+)?)\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*[左右大约約约]\s*斤',
            r'(\d+(?:[\.,]\d+)?)\s*斤\s*[左右大约約约]',
        ]
        for pattern in patterns:
            matches = list(re.finditer(pattern, result))
            for match in matches:
                full_match = match.group(0)
                if full_match not in result:
                    continue
                numbers = re.findall(r'\d+(?:[\.,]\d+)?', full_match)
                if not numbers:
                    continue
                converted_numbers = [self._jin_to_kg_label(num).removesuffix("kg") for num in numbers]
                if len(numbers) == 2:
                    replacement = f"{converted_numbers[0]}-{converted_numbers[1]}kg"
                else:
                    replacement = f"{converted_numbers[0]}kg"
                result = result.replace(full_match, replacement)
        
        if '斤' in result and not any(char.isdigit() for char in result):
            result = result.replace('斤', "0,5kg")
        
        final_result = re.sub(r'\s+', ' ', result).strip()
        if original_text != final_result:
            print(f"    ⚖️ [QUY ĐỔI] '{original_text}' ➡️ '{final_result}'")
        return final_result

    def summarize_product_info(self, raw_text_list: List[str]) -> str:
        return "" 

    def _normalize_ocr_items(self, ocr_results: List[Any]) -> List[Tuple[str, tuple]]:
        normalized_items: List[Tuple[str, tuple]] = []
        for item in ocr_results or []:
            if isinstance(item, dict):
                text = item.get("text", "")
                bbox = item.get("bbox", [])
            else:
                text = item[0] if len(item) > 0 else ""
                bbox = item[1] if len(item) > 1 else []
            if text:
                normalized_items.append((text, bbox))
        return normalized_items

    def has_size_or_laundry_context(self, ocr_results: List[Any]) -> bool:
        return self.size_laundry_flags(ocr_results).is_size_or_laundry

    def size_laundry_flags(self, ocr_results: List[Any]) -> SizeLaundryFlags:
        """Size, giặt tẩy, và poster đủ cả bảng size (>=3 cỡ + nhãn số đo) lẫn hướng dẫn giặt."""
        items = self._normalize_ocr_items(ocr_results)
        if not items:
            return SizeLaundryFlags()
        is_size = self._has_size_table_context(items)
        is_laundry = self._has_laundry_care_context(items)
        comprehensive = False
        if is_size and is_laundry:
            texts = [str(text or "") for text, _ in items if str(text or "").strip()]
            size_token_count = sum(1 for text in texts if self._is_size_token_text(text))
            size_label_count = sum(1 for text in texts if self._is_size_dimension_label(text))
            comprehensive = size_token_count >= 3 and size_label_count >= 1
        return SizeLaundryFlags(is_size, is_laundry, comprehensive)
    
    def classify_and_process_blocks(
        self,
        ocr_results: List[Any],
        image_url: str = "",
        *,
        delete_size_and_laundry: bool = True,
    ) -> Tuple[List[Tuple[str, tuple]], List[Tuple[str, tuple]]]:
        """
        Phân loại và xử lý text blocks. 
        Hỗ trợ input cả Dict và Tuple để tránh lỗi format.
        """
        processed_blocks = []
        ignore_blocks = []
        
        if not ocr_results: return [], []
        
        print(f"  📝 Phân tích {len(ocr_results)} khối text để dịch...")

        normalized_items = self._normalize_ocr_items(ocr_results)
        if not normalized_items:
            return [], []

        if self._has_factory_intro_context(normalized_items):
            print("    [FACTORY INTRO] delete image")
            return None

        weight_replacements = self.chinese_weight_replacements(normalized_items)
        size_table_context = self._has_size_table_context(normalized_items)
        if size_table_context:
            print("    [SIZE TABLE] vẽ local — không xóa ảnh")
        elif self._has_laundry_care_context(normalized_items):
            print("    [LAUNDRY CARE] vẽ local — không xóa ảnh")
        # Tham số cũ: bảng size / giặt không còn xóa ảnh dù caller truyền True.
        _ = delete_size_and_laundry

        for idx, (text, bbox) in enumerate(normalized_items):
            if idx in weight_replacements:
                converted = weight_replacements[idx]
                print(f"    ⚖️ [QUY ĐỔI] '{text}' ➡️ '{converted}'")
                processed_blocks.append((converted, bbox))
                continue
            if self._is_standalone_cm_measurement(text.strip()):
                print(f"    [CM] group with processed text: '{text.strip()}'")
                processed_blocks.append((text.strip(), tuple(bbox)))
                continue
            
            if self.contains_forbidden_content(text):
                # SKIP_REGEX cũng khớp domain. URL trên tem SP chỉ xóa dòng chữ,
                # không xóa cả ảnh — nếu không storefront gắn nhầm ảnh gallery vào SKU.
                without_domain = self.domain_regex.sub(" ", text)
                if self.skip_regex.search(without_domain):
                    print(f"    🔴 [CẤM] Phát hiện từ khóa: '{text}' -> XÓA ẢNH")
                    return None
                print(f"    🗑️ [XÓA] Domain (giữ ảnh): '{text}'")
                processed_blocks.append(("", bbox))
                continue
            
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
                    if not str(translated_text or "").strip():
                        # DeepSeek rỗng: giữ pixel gốc. Không được inpaint rồi bỏ qua bước vẽ.
                        print(f"    ⚠️ [DỊCH RỖNG] giữ nguyên, không xóa: '{text}'")
                        ignore_blocks.append((text, bbox))
                    else:
                        processed_blocks.append((translated_text, bbox))
            else:
                ignore_blocks.append((text, bbox))
        
        return processed_blocks, ignore_blocks
