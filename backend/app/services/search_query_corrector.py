# backend/app/services/search_query_corrector.py - Gemini sửa cụm từ tìm kiếm
"""Dùng Gemini 2.0 Flash để sửa cụm từ tìm kiếm khi thiếu dấu, sai chữ."""

import logging
import json
from typing import Optional, List

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def correct_search_query_via_ai(query: str, gender_context: Optional[str] = None) -> Optional[str]:
    """
    Gọi Gemini 2.0 Flash để chuẩn hóa cụm từ tìm kiếm tiếng Việt.
    Trả về cụm từ đã sửa (có dấu, đúng chính tả) hoặc None nếu lỗi.
    """
    if not query or not query.strip():
        return None
    if not getattr(settings, "AI_SEARCH_CORRECTION_ENABLED", True):
        logger.info("AI search correction disabled by config")
        print("[AI-CORRECT] disabled by config")
        return None
    api_key = getattr(settings, "GEMINI_API_KEY", None) or ""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
    if not api_key or len(api_key) < 10:
        logger.info("GEMINI_API_KEY chưa cấu hình - bỏ qua sửa từ khóa bằng AI")
        print("[AI-CORRECT] missing GEMINI_API_KEY")
        return None
    logger.info("Calling Gemini for search query correction: %s", query.strip())
    print(f"[AI-CORRECT] calling Gemini for: {query.strip()}")
    gender_note = f"\nGiới tính/đối tượng ưu tiên: {gender_context}." if gender_context else ""
    prompt = f"""Bạn là trợ lý chuẩn hóa từ khóa tìm kiếm sản phẩm trên web thương mại điện tử (giày dép, áo quần, túi ví).
Nhiệm vụ: Sửa cụm từ sau thành tiếng Việt có dấu đúng chuẩn, phù hợp tìm kiếm sản phẩm.{gender_note}
- Thêm dấu nếu thiếu (vd: "cao long nam de" -> "cao lông nam đế")
- Sửa lỗi chính tả phổ biến, ưu tiên lỗi gõ gần phím (m/n, s/x, d/gi/r...)
- Giữ nguyên ý nghĩa, không thêm bớt từ
- Với cụm liên quan giới tính, ưu tiên "nam/nữ" thay vì suy diễn kiểu khác
- Nếu gặp "giày nan" thì sửa thành "giày nam" (không đổi thành "giày đan")
- Chỉ trả về cụm từ đã sửa, không giải thích, không markdown

Cụm từ cần sửa: "{query.strip()}"

Trả về cụm từ đã chuẩn hóa:"""
    try:
        url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 100, "temperature": 0.1},
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        content = (parts[0].get("text") or "").strip()
        if not content or content == query.strip():
            return None
        corrected = content[:500]
        logger.info("Gemini corrected query: %s -> %s", query.strip(), corrected)
        print(f"[AI-CORRECT] Gemini corrected: {query.strip()} -> {corrected}")
        return corrected
    except Exception as e:
        logger.warning("Gemini correct search query failed: %s", e)
        print(f"[AI-CORRECT] Gemini error: {e}")
        return None


def propose_search_queries_via_ai(query: str, gender_context: Optional[str] = None, limit: int = 3) -> List[str]:
    if not query or not query.strip():
        return []
    if not getattr(settings, "AI_SEARCH_CORRECTION_ENABLED", True):
        return []
    api_key = getattr(settings, "GEMINI_API_KEY", None) or ""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
    if not api_key or len(api_key) < 10:
        return []
    gender_note = f"\nGiới tính/đối tượng ưu tiên: {gender_context}." if gender_context else ""
    prompt = f"""Bạn là trợ lý gợi ý từ khóa tìm kiếm sản phẩm (giày dép, áo quần, túi ví).{gender_note}
Hãy đề xuất {limit} cụm từ khóa khả năng người dùng muốn tìm dựa trên cụm sau.
- Chỉ trả về mảng JSON gồm {limit} chuỗi.
- Không giải thích, không markdown, không ký tự thừa.

Cụm từ gốc: "{query.strip()}"

Trả về JSON:"""
    try:
        url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 120, "temperature": 0.2},
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return []
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return []
        content = (parts[0].get("text") or "").strip()
        if not content:
            return []
        raw = []
        try:
            # Xử lý JSON trả về từ Gemini (có thể có markdown ```json ... ```)
            if content.startswith("```json"):
                content = content.replace("```json", "", 1)
            if content.endswith("```"):
                content = content.replace("```", "", 1)
                
            parsed = json.loads(content)
            if isinstance(parsed, list):
                raw = parsed
        except Exception:
            lines = [l.strip(" -•\t") for l in content.splitlines() if l.strip()]
            raw = lines
        seen = set()
        result: List[str] = []
        q_lower = query.strip().lower()
        for item in raw:
            if not item or not isinstance(item, str):
                continue
            cleaned = item.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key == q_lower or key in seen:
                continue
            seen.add(key)
            result.append(cleaned)
            if len(result) >= limit:
                break
        return result[:limit]
    except Exception:
        return []


def suggest_category_matches_via_ai(query: str, categories_json: str, limit: int = 3) -> List[dict]:
    if not query or not query.strip() or not categories_json:
        return []
    if not getattr(settings, "AI_SEARCH_CORRECTION_ENABLED", True):
        return []
    api_key = getattr(settings, "GEMINI_API_KEY", None) or ""
    model = getattr(settings, "GEMINI_MODEL", "gemini-2.0-flash")
    if not api_key or len(api_key) < 10:
        return []
    prompt = f"""Người dùng tìm "{query.strip()}" nhưng không có sản phẩm.
Danh sách danh mục (JSON): {categories_json}
Hãy chọn ra {limit} danh mục phù hợp nhất.
Chỉ trả về mảng JSON gồm các object có đúng 2 khóa: "id" và "name".
Không thêm bất kỳ ký tự nào khác."""
    try:
        url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 200, "temperature": 0.2},
        }
        resp = requests.post(url, json=payload, timeout=3)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return []
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return []
        content = (parts[0].get("text") or "").strip()
        # Xử lý JSON trả về từ Gemini (có thể có markdown ```json ... ```)
        if content.startswith("```json"):
            content = content.replace("```json", "", 1)
        if content.endswith("```"):
            content = content.replace("```", "", 1)
        
        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict)]
        except json.JSONDecodeError:
            pass
            
        return []
    except Exception:
        return []
