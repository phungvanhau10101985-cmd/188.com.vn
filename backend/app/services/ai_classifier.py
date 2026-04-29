# app/services/ai_classifier.py - ĐÃ SỬA LÀM SẠCH TIẾNG TRUNG, DÙNG GEMINI 2.0 FLASH
import requests
import json
from typing import Dict, Any, Optional, List
from app.core.config import settings
import logging
import re

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class AIClassifier:
    def __init__(self):
        self.gemini_api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
        self.gemini_model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
        
    def classify_product(self, product_name: str, chinese_name: str = "") -> Dict[str, Any]:
        """
        Phân loại sản phẩm chi tiết cho export Excel - Dùng Gemini 2.0 Flash, fallback rule-based.
        """
        try:
            # 🎯 QUAN TRỌNG: LƯU TÊN SẢN PHẨM GỐC ĐỂ GHÉP VÀO CUỐI MÔ TẢ VÀ TRÍCH MÃ NHÀ CUNG CẤP
            self.original_product_name = product_name
            
            # 🎯 TRÍCH MÃ NHÀ CUNG CẤP TỪ TÊN SẢN PHẨM (FORMAT DUY NHẤT)
            supplier_code = self._extract_supplier_code(product_name)
            self.supplier_code = supplier_code
            
            # 🎯 TRÍCH CATEGORY TỪ TÊN GỐC SẢN PHẨM
            original_category = self._extract_category_from_name(product_name)
            self.original_category = original_category
            
            # Ưu tiên sử dụng tên tiếng Trung nếu có
            analysis_text = chinese_name if chinese_name and chinese_name.strip() else product_name
            
            if not analysis_text or analysis_text.strip() == "":
                logger.warning("Không có văn bản để phân tích AI")
                return self._get_detailed_fallback_classification(product_name)
            
            print(f"🤖 Bắt đầu phân tích AI chi tiết (Gemini 2.0 Flash): '{analysis_text}'")
            print(f"   🔍 Mã nhà cung cấp trích xuất: '{supplier_code}'")
            print(f"   🔍 Category từ tên gốc: '{original_category}'")
            
            # 🎯 Dùng Gemini 2.0 Flash
            if self.gemini_api_key and len(self.gemini_api_key) >= 10:
                print("🔗 Gọi Gemini 2.0 Flash API...")
                result = self._call_gemini_api(analysis_text)
                if result and self._is_valid_detailed_classification(result):
                    print("✅ Gemini 2.0 Flash thành công!")
                    return result
                print("❌ Gemini không trả về kết quả hợp lệ")
            
            # 🎯 FALLBACK: Rule-based chi tiết
            logger.warning("Gemini không khả dụng hoặc lỗi, sử dụng rule-based fallback")
            return self._get_detailed_rule_based_classification(product_name)
            
        except Exception as e:
            logger.error(f"Lỗi phân tích AI: {e}")
            return self._get_detailed_fallback_classification(product_name)
    
    def _extract_supplier_code(self, product_name: str) -> str:
        """
        Trích xuất mã nhà cung cấp từ tên sản phẩm - FORMAT DUY NHẤT
        Format: ... | Mã nhà sản xuất: {SUPPLIER_CODE}-GXX
        """
        try:
            # Tìm phần mã sau dấu |
            if " | " in product_name:
                # Lấy phần cuối cùng sau dấu | (chứa mã nhà sản xuất)
                code_part = product_name.split(" | ")[-1]
                
                # 🎯 FORMAT DUY NHẤT: Mã nhà sản xuất: {SUPPLIER_CODE}-GXX
                pattern = r'Mã nhà sản xuất:\s*([A-Z]{5})-G\d+'
                match = re.search(pattern, code_part)
                
                if match:
                    supplier_code = match.group(1)
                    print(f"   🎯 Đã trích xuất mã nhà cung cấp: {supplier_code}")
                    return supplier_code
            
            print(f"   ⚠️ Không tìm thấy mã nhà cung cấp trong: {product_name}")
            return ""
            
        except Exception as e:
            print(f"   ❌ Lỗi trích xuất mã nhà cung cấp: {e}")
            return ""
    
    def _extract_category_from_name(self, product_name: str) -> str:
        """
        Trích xuất category từ tên gốc sản phẩm (phần sau dấu -)
        Format: ... - {CATEGORY} | ...
        """
        try:
            # Tìm phần category trước dấu |
            if " | " in product_name:
                name_part = product_name.split(" | ")[0]
                
                # Tìm phần category sau dấu - cuối cùng
                if " - " in name_part:
                    category = name_part.split(" - ")[-1].strip()
                    print(f"   🎯 Đã trích xuất category từ tên gốc: '{category}'")
                    return category
            
            print(f"   ⚠️ Không tìm thấy category trong: {product_name}")
            return ""
            
        except Exception as e:
            print(f"   ❌ Lỗi trích xuất category: {e}")
            return ""
    
    def _call_gemini_api(self, text: str) -> Optional[Dict[str, Any]]:
        """Gọi Gemini 1.5 Pro API cho phân loại chi tiết"""
        try:
            system_instruction = (
                "Bạn là chuyên gia phân loại sản phẩm thương mại điện tử chuyên sâu. "
                "Phân tích kỹ tên sản phẩm và trả về JSON đầy đủ thông tin. "
                "QUAN TRỌNG: KHÔNG được sử dụng bất kỳ ký tự tiếng Trung nào trong câu trả lời, chỉ sử dụng tiếng Việt."
            )
            prompt = self._build_detailed_classification_prompt(text)
            full_prompt = f"{system_instruction}\n\n{prompt}"
            
            url = f"{GEMINI_BASE_URL}/models/{self.gemini_model}:generateContent?key={self.gemini_api_key}"
            payload = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": 1500,
                    "temperature": 0.7,
                    "responseMimeType": "application/json",
                },
            }
            
            response = requests.post(url, json=payload, timeout=45)
            
            if response.status_code == 200:
                result = response.json()
                candidates = result.get("candidates", [])
                if not candidates:
                    return None
                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    return None
                content = (parts[0].get("text") or "").strip()
                print(f"📨 Gemini 1.5 Pro response received ({len(content)} chars)")
                return self._parse_detailed_ai_response(content)
            logger.error("Gemini API error: %s - %s", response.status_code, response.text)
            return None
        except requests.exceptions.Timeout:
            logger.error("Gemini API timeout")
            return None
        except Exception as e:
            logger.error("Lỗi Gemini API: %s", e)
            return None
    
    def _build_detailed_classification_prompt(self, product_text: str) -> str:
        """Xây dựng prompt chi tiết cho phân loại sản phẩm"""
        return f"""
Hãy phân tích CHI TIẾT và phân loại sản phẩm sau:

TÊN SẢN PHẨM: {product_text}

YÊU CẦU PHÂN LOẠI CHI TIẾT (cho cột AG đến AP trong Excel):

1. category (Danh Mục): BỎ QUA trường này (sẽ được lấy từ tên gốc sản phẩm)
2. subcategory (Danh Mục Phụ): Danh mục phụ CHI TIẾT (ví dụ: "giày da nam", "áo sơ mi nam", "váy dạ hội nữ", "áo khoác nữ", KHÔNG được trả về chung chung như "giày", "áo", "váy")
3. gender (Giới Tính): nam, nữ, unisex, trẻ em
4. style (Phong Cách): phong cách chính (casual, sport, formal, vintage, etc.)
5. fashion_style (Kiểu Dáng): kiểu dáng cụ thể (slim fit, oversized, classic, modern, etc.)
6. material (Chất Liệu): chất liệu chính (da bò, vải cotton, vải kaki, da thật, v.v.)
7. occasion (Dịp): dịp sử dụng (công sở, dạo phố, thể thao, tiệc tùng, hàng ngày, v.v.)
8. features (Tính Năng): danh sách 3-5 tính năng nổi bật (array)
9. product_description (Mô tả sản phẩm và content marketing): 
   - Mô tả chi tiết sản phẩm khoảng 300 từ
   - Bao gồm thông tin kỹ thuật, chất liệu, thiết kế
   - Content marketing hấp dẫn, thu hút khách hàng
   - Nhấn mạnh lợi ích và điểm nổi bật
   - Ngôn ngữ tự nhiên, thuyết phục

QUY TẮC QUAN TRỌNG:
- Phân tích KỸ tên sản phẩm, đặc biệt nếu có tiếng Trung
- Subcategory PHẢI CHI TIẾT, không được chung chung
- Content marketing phải chi tiết, hấp dẫn, khoảng 300 từ
- TUYỆT ĐỐI KHÔNG sử dụng bất kỳ ký tự tiếng Trung nào trong câu trả lời
- Chỉ sử dụng tiếng Việt với bảng chữ cái Latinh
- Nếu tên sản phẩm có tiếng Trung, hãy dịch sang tiếng Việt và mô tả bằng tiếng Việt
- Trả về ĐÚNG định dạng JSON dưới đây

ĐỊNH DẠNG JSON BẮT BUỘC:
{{
    "category": "giày dép",
    "subcategory": "giày da nam công sở",
    "gender": "nam",
    "style": "công sở",
    "fashion_style": "classic",
    "material": "da bò thật",
    "occasion": "công sở, tiệc tùng",
    "features": ["chống trượt", "thoáng khí", "dễ vệ sinh"],
    "product_description": "Mô tả chi tiết khoảng 300 từ..."
}}

Chỉ trả về JSON, không thêm bất kỳ text nào khác.
"""
    
    def _parse_detailed_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Phân tích kết quả chi tiết từ AI response - ĐÃ SỬA LÀM SẠCH TIẾNG TRUNG"""
        try:
            # Tìm JSON trong response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = response_text[start_idx:end_idx]
                result = json.loads(json_str)
                
                # Validate các trường bắt buộc
                required_fields = [
                    'category', 'subcategory', 'gender', 'style', 
                    'fashion_style', 'material', 'occasion', 'features', 'product_description'
                ]
                
                for field in required_fields:
                    if field not in result:
                        result[field] = ""
                    elif field == 'features' and not isinstance(result[field], list):
                        result[field] = []
                
                # 🎯 LÀM SẠCH TIẾNG TRUNG TRONG TẤT CẢ CÁC TRƯỜNG
                result = self._clean_chinese_characters(result)
                
                # 🎯 QUAN TRỌNG: GHI ĐÈ CATEGORY BẰNG CATEGORY TỪ TÊN GỐC
                if hasattr(self, 'original_category') and self.original_category:
                    result['category'] = self.original_category
                    print(f"✅ Đã ghi đè category bằng category từ tên gốc: '{self.original_category}'")
                
                # 🎯 CẢI THIỆN SUBCATEGORY NẾU QUÁ CHUNG CHUNG
                current_subcategory = result.get('subcategory', '').strip()
                if current_subcategory in ['giày', 'áo', 'quần', 'váy', 'dép']:
                    # Nếu subcategory quá chung, cải thiện dựa trên category và tên sản phẩm
                    improved_subcategory = self._improve_subcategory(current_subcategory, result.get('category', ''), self.original_product_name)
                    result['subcategory'] = improved_subcategory
                    print(f"🔄 Đã cải thiện subcategory từ '{current_subcategory}' thành '{improved_subcategory}'")
                
                # 🎯 THÊM MÃ NHÀ CUNG CẤP VÀO SUBCATEGORY
                if hasattr(self, 'supplier_code') and self.supplier_code:
                    final_subcategory = result.get('subcategory', '').strip()
                    if final_subcategory and not final_subcategory.endswith(self.supplier_code):
                        result['subcategory'] = f"{final_subcategory} {self.supplier_code}"
                        print(f"✅ Đã thêm mã nhà cung cấp vào subcategory: {result['subcategory']}")
                
                # 🎯 QUAN TRỌNG: GHÉP TÊN SẢN PHẨM GỐC VÀO CUỐI MÔ TẢ VỚI FORMAT MỚI
                if hasattr(self, 'original_product_name') and self.original_product_name:
                    original_name = self.original_product_name.strip()
                    if original_name:
                        current_description = result.get('product_description', '').strip()
                        # 🎯 FORMAT MỚI: Thêm " | Tên sản phẩm: " trước tên sản phẩm
                        if not current_description.endswith(original_name):
                            result['product_description'] = current_description + f" | Tên sản phẩm: {original_name}"
                            print(f"✅ Đã ghép tên sản phẩm gốc vào mô tả với format mới: {original_name}")
                
                print(f"🎯 AI Detailed Classification Result:")
                for key, value in result.items():
                    if key != 'product_description':
                        preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                        print(f"   {key}: {preview}")
                    else:
                        word_count = len(str(value).split())
                        print(f"   {key}: {word_count} từ")
                
                return result
            else:
                raise ValueError("Không tìm thấy JSON trong response")
                
        except Exception as e:
            logger.error(f"Lỗi phân tích AI response: {e}")
            return self._get_detailed_fallback_classification("")
    
    def _clean_chinese_characters(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Làm sạch ký tự tiếng Trung trong tất cả các trường
        """
        cleaned_result = {}
        
        for key, value in result.items():
            if isinstance(value, str):
                # 🎯 LOẠI BỎ KÝ TỰ TIẾNG TRUNG (Unicode range for Chinese characters)
                cleaned_value = re.sub(r'[\u4e00-\u9fff]+', '', value)
                cleaned_value = cleaned_value.strip()
                
                # Nếu sau khi xóa tiếng Trung mà chuỗi trống, giữ nguyên giá trị gốc
                if not cleaned_value:
                    cleaned_value = value
                
                cleaned_result[key] = cleaned_value
                
                # Log nếu có xóa ký tự tiếng Trung
                if value != cleaned_value:
                    print(f"   🧹 Đã làm sạch ký tự tiếng Trung trong trường '{key}'")
                    
            elif isinstance(value, list):
                # Xử lý danh sách features
                cleaned_list = []
                for item in value:
                    if isinstance(item, str):
                        cleaned_item = re.sub(r'[\u4e00-\u9fff]+', '', item)
                        cleaned_item = cleaned_item.strip()
                        if cleaned_item:  # Chỉ thêm nếu không trống
                            cleaned_list.append(cleaned_item)
                    else:
                        cleaned_list.append(str(item))
                
                cleaned_result[key] = cleaned_list
                
            else:
                cleaned_result[key] = value
        
        return cleaned_result
    
    def _improve_subcategory(self, basic_subcategory: str, category: str, product_name: str) -> str:
        """Cải thiện subcategory từ dạng chung chung thành chi tiết"""
        product_lower = product_name.lower()
        
        if basic_subcategory == 'giày':
            if any(word in product_lower for word in ['da', 'leather']):
                return "giày da nam"
            elif any(word in product_lower for word in ['thể thao', 'sport', 'sneaker']):
                return "giày thể thao nam"
            elif any(word in product_lower for word in ['công sở', 'văn phòng', 'office']):
                return "giày công sở nam"
            else:
                return "giày thời trang nam"
                
        elif basic_subcategory == 'áo':
            if any(word in product_lower for word in ['sơ mi', 'shirt']):
                return "áo sơ mi nam"
            elif any(word in product_lower for word in ['thun', 'tee', 't-shirt']):
                return "áo thun nam"
            elif any(word in product_lower for word in ['khoác', 'jacket']):
                return "áo khoác nam"
            else:
                return "áo thời trang nam"
                
        elif basic_subcategory == 'váy':
            if any(word in product_lower for word in ['dạ hội', 'tiệc', 'party', 'đầm']):
                return "váy dạ hội nữ"
            elif any(word in product_lower for word in ['công sở', 'văn phòng']):
                return "váy công sở nữ"
            else:
                return "váy thời trang nữ"
                
        else:
            return basic_subcategory
    
    def _is_valid_detailed_classification(self, result: Dict[str, Any]) -> bool:
        """Kiểm tra kết quả phân loại chi tiết có hợp lệ không"""
        required_fields = [
            'category', 'subcategory', 'gender', 'style', 
            'fashion_style', 'material', 'occasion', 'features', 'product_description'
        ]
        
        for field in required_fields:
            if field not in result or not result[field]:
                return False
        
        # Kiểm tra subcategory không được quá chung chung
        subcategory = result.get('subcategory', '').strip()
        if subcategory in ['giày', 'áo', 'quần', 'váy', 'dép']:
            return False
        
        # Kiểm tra product_description có đủ dài không (ít nhất 100 từ)
        if len(str(result['product_description']).split()) < 100:
            return False
            
        return True
    
    def _get_detailed_rule_based_classification(self, product_name: str) -> Dict[str, Any]:
        """Rule-based classification chi tiết khi AI không hoạt động"""
        # Phân tích chi tiết dựa trên từ khóa
        text_lower = product_name.lower()
        
        # 🎯 LẤY CATEGORY TỪ TÊN GỐC
        if hasattr(self, 'original_category') and self.original_category:
            category = self.original_category
        else:
            # Fallback nếu không trích xuất được category từ tên gốc
            if any(word in text_lower for word in ['giày', 'dép', 'shoe', 'sneaker']):
                category = "giày dép"
            elif any(word in text_lower for word in ['váy', 'đầm', 'dress']):
                category = "quần áo"
            elif any(word in text_lower for word in ['áo', 'quần', 'clothing']):
                category = "quần áo"
            else:
                category = "phụ kiện"
        
        # Xác định subcategory CHI TIẾT
        if any(word in text_lower for word in ['giày', 'dép', 'shoe', 'sneaker']):
            if any(word in text_lower for word in ['da', 'leather']):
                base_subcategory = "giày da nam"
            elif any(word in text_lower for word in ['thể thao', 'sport']):
                base_subcategory = "giày thể thao nam"
            else:
                base_subcategory = "giày thời trang nam"
                
        elif any(word in text_lower for word in ['váy', 'đầm', 'dress']):
            if any(word in text_lower for word in ['dạ hội', 'tiệc', 'party']):
                base_subcategory = "váy dạ hội nữ"
            else:
                base_subcategory = "váy thời trang nữ"
                
        elif any(word in text_lower for word in ['áo khoác', 'jacket']):
            if any(word in text_lower for word in ['nữ']):
                base_subcategory = "áo khoác nữ"
            else:
                base_subcategory = "áo khoác nam"
                
        elif any(word in text_lower for word in ['áo', 'shirt']):
            if any(word in text_lower for word in ['sơ mi']):
                base_subcategory = "áo sơ mi nam"
            else:
                base_subcategory = "áo thun nam"
        else:
            base_subcategory = "thời trang nam"
        
        # 🎯 THÊM MÃ NHÀ CUNG CẤP VÀO SUBCATEGORY
        if hasattr(self, 'supplier_code') and self.supplier_code:
            subcategory = f"{base_subcategory} {self.supplier_code}"
        else:
            subcategory = base_subcategory
        
        # Xác định gender
        if any(word in text_lower for word in ['nam', 'men', 'male']):
            gender = "nam"
        elif any(word in text_lower for word in ['nữ', 'women', 'female']):
            gender = "nữ"
        else:
            gender = "unisex"
        
        # Tạo content marketing chi tiết
        base_description = f"""
Sản phẩm {product_name} là lựa chọn hoàn hảo cho phong cách thời trang hiện đại. Được thiết kế tỉ mỉ từ những chất liệu cao cấp, sản phẩm mang đến sự thoải mái và tự tin cho người sử dụng trong mọi hoạt động hàng ngày.

Với kiểu dáng thời thượng và màu sắc trang nhã, {product_name} dễ dàng kết hợp với nhiều loại trang phục khác nhau, từ casual đến công sở. Chất liệu bền đẹp, đường may tinh tế cùng sự chú trọng đến từng chi tiết nhỏ nhất giúp sản phẩm không chỉ đẹp về mặt thẩm mỹ mà còn đảm bảo độ bền vượt trội theo thời gian.

Sản phẩm phù hợp cho nhiều dịp sử dụng khác nhau: đi làm, dạo phố, du lịch hay các sự kiện quan trọng. Thiết kế ergonomic ôm sát mang lại cảm giác thoải mái tối đa, không gây khó chịu ngay cả khi sử dụng trong thời gian dài.

Đây chắc chắn sẽ là món phụ kiện không thể thiếu trong tủ đồ của những người yêu thích thời trang và quan tâm đến chất lượng. Sở hữu ngay {product_name} để nâng tầm phong cách và khẳng định cá tính riêng của bạn!
"""
        
        # 🎯 GHÉP TÊN SẢN PHẨM GỐC VÀO CUỐI MÔ TẢ VỚI FORMAT MỚI
        final_description = base_description.strip()
        if hasattr(self, 'original_product_name') and self.original_product_name:
            original_name = self.original_product_name.strip()
            if original_name and not final_description.endswith(original_name):
                final_description += f" | Tên sản phẩm: {original_name}"
        
        return {
            "category": category,
            "subcategory": subcategory,
            "gender": gender,
            "style": "thời trang",
            "fashion_style": "hiện đại",
            "material": "chất liệu cao cấp",
            "occasion": "công sở, dạo phố, hàng ngày",
            "features": ["thiết kế thời trang", "chất liệu bền đẹp", "dễ kết hợp"],
            "product_description": final_description
        }
    
    def _get_detailed_fallback_classification(self, product_name: str) -> Dict[str, Any]:
        """Fallback classification chi tiết khi có lỗi"""
        # 🎯 LẤY CATEGORY TỪ TÊN GỐC
        if hasattr(self, 'original_category') and self.original_category:
            category = self.original_category
        else:
            category = "giày dép"
        
        # Xác định subcategory chi tiết
        text_lower = product_name.lower()
        if any(word in text_lower for word in ['giày', 'dép']):
            base_subcategory = "giày da nam"
        elif any(word in text_lower for word in ['váy', 'đầm', 'dress']):
            base_subcategory = "váy dạ hội nữ"
        elif any(word in text_lower for word in ['áo khoác']):
            base_subcategory = "áo khoác nam"
        elif any(word in text_lower for word in ['áo sơ mi']):
            base_subcategory = "áo sơ mi nam"
        else:
            base_subcategory = "thời trang nam"
        
        # 🎯 THÊM MÃ NHÀ CUNG CẤP VÀO SUBCATEGORY
        if hasattr(self, 'supplier_code') and self.supplier_code:
            subcategory = f"{base_subcategory} {self.supplier_code}"
        else:
            subcategory = base_subcategory
        
        base_description = f"""
Sản phẩm {product_name} được thiết kế dành cho phái mạnh hiện đại, mang đến sự lịch lãm và tinh tế trong từng chi tiết. Với chất liệu da bò cao cấp, sản phẩm không chỉ có độ bền vượt trội mà còn tạo nên vẻ ngoài sang trọng, phù hợp với nhiều hoàn cảnh sử dụng.

Đế giày được thiết kế đặc biệt giúp chống trượt hiệu quả, đảm bảo an toàn cho người dùng trong mọi điều kiện thời tiết. Công nghệ thoáng khí tiên tiến giúp đôi chân luôn khô ráo và thoải mái suốt cả ngày dài. Đường may tỉ mỉ, chắc chắn thể hiện sự tinh xảo trong từng công đoạn sản xuất.

Sản phẩm thích hợp cho cả môi trường công sở chuyên nghiệp lẫn những buổi gặp gỡ bạn bè, dạo phố cuối tuần. Dễ dàng phối đồ với quần âu, quần jeans hay các loại trang phục casual khác. Đây chính là sự lựa chọn hoàn hảo cho những ai đề cao chất lượng và phong cách thời trang nam tính.

Hãy sở hữu ngay {product_name} để trải nghiệm sự khác biệt về chất lượng và thiết kế. Cam kết mang đến cho khách hàng những sản phẩm tốt nhất với giá trị bền vững theo thời gian.
"""
        
        # 🎯 GHÉP TÊN SẢN PHẨM GỐC VÀO CUỐI MÔ TẢ VỚI FORMAT MỚI
        final_description = base_description.strip()
        if hasattr(self, 'original_product_name') and self.original_product_name:
            original_name = self.original_product_name.strip()
            if original_name and not final_description.endswith(original_name):
                final_description += f" | Tên sản phẩm: {original_name}"
        
        return {
            "category": category,
            "subcategory": subcategory,
            "gender": "nam",
            "style": "thời trang",
            "fashion_style": "classic",
            "material": "da bò",
            "occasion": "công sở, dạo phố",
            "features": ["chống trượt", "thoáng khí", "bền đẹp"],
            "product_description": final_description
        }

# Khởi tạo AI classifier
ai_classifier = AIClassifier()