"""
Fallback Gemini khi luật từ-khóa không gán được nhóm đánh giá/câu hỏi.

Model dùng settings.GEMINI_MODEL, mặc định gemini-2.5-flash.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from app.core.config import settings
from app.services.product_rating_question_groups import (
    RATING_GROUP_ID_WHITELIST,
    rating_group_catalog_text_for_prompt,
)

logger = logging.getLogger(__name__)

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT_SEC = 35
_PROMPT_BLOCKS_MAX_CHARS = 100_000
_VALID_QUESTION: Set[int] = {88, 99, 100}


def _extract_json_object(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("Không tìm được JSON object trong phản hồi Gemini")
    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("Gemini không trả về object JSON")
    return parsed


def _pull_int(parsed: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[int]:
    for key in keys:
        if key not in parsed:
            continue
        raw = parsed.get(key)
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        if isinstance(raw, str) and raw.strip().isdigit():
            return int(raw.strip())
    return None


def gemini_fallback_import_groups(
    context_text: str,
    product_name: str,
) -> Tuple[Optional[int], Optional[int], List[str]]:
    """
    Gọi Gemini chọn một mã rating + question trong whitelist.
    Trả (rating_group_id | None, question_group_id | None, warnings).
    """
    warns: List[str] = []

    if not getattr(settings, "IMPORT_LINK_GEMINI_GROUPS_FALLBACK_ENABLED", True):
        return None, None, warns

    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key or len(api_key) < 10:
        return None, None, warns

    catalog = rating_group_catalog_text_for_prompt()
    if len(catalog) > _PROMPT_BLOCKS_MAX_CHARS:
        catalog = catalog[: _PROMPT_BLOCKS_MAX_CHARS] + "\n...[truncated]"

    ctx = (context_text or "").strip()
    pname = (product_name or "").strip()
    whitelist_ids = ",".join(str(i) for i in sorted(RATING_GROUP_ID_WHITELIST))

    prompt = (
        "Bạn gán hai mã cố định cho một sản phẩm TMĐT Việt Nam.\n"
        "Tên/ngữ cảnh có thể là tiếng Trung, Mông Cổ, Anh hoặc ngôn ngữ khác; hãy hiểu/diễn dịch sang loại hàng tiếng Việt trước khi chọn mã.\n\n"
        "Quy tắc question_group_id, chỉ một trong ba số:\n"
        "- 99: unisex/nam-nữ/không phân biệt giới hoặc không suy được.\n"
        "- 100: sản phẩm dành nam.\n"
        "- 88: sản phẩm dành nữ.\n\n"
        "Quy tắc rating_group_id:\n"
        "- Chọn exactly một id trong whitelist và bảng id:nhãn bên dưới.\n"
        "- Ưu tiên đúng loại hàng + giới theo tên, taxonomy, style, material, color và product_info.\n"
        "- Không tạo id mới.\n\n"
        "Đầu ra JSON thuần một object, không markdown:\n"
        '{"rating_group_id": <int whitelist>, "question_group_id": 88 hoặc 99 hoặc 100}\n\n'
        f"WHITELIST rating_group_id: [{whitelist_ids}]\n\n"
        f"Bảng chi tiết:\n{catalog}\n\n"
        f"NGỮ CẢNH (có thể gồm nhiều cột Excel/import):\n{ctx[:40000]}\n\n"
        f"TÊN SẢN PHẨM:\n{pname[:2000]}\n"
    )

    model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash").strip()
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 180, "temperature": 0.1},
    }

    try:
        resp = requests.post(url, json=payload, timeout=_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block = data.get("promptFeedback") or data.get("error") or {}
            warns.append(f"gemini_groups: không có candidates — {str(block)[:400]}")
            return None, None, warns

        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict)).strip()
        parsed = _extract_json_object(content)
    except requests.RequestException as exc:
        warns.append(f"gemini_groups: lỗi mạng/API: {exc}")
        return None, None, warns
    except Exception as exc:
        warns.append(f"gemini_groups: không đọc được JSON — {exc}")
        return None, None, warns

    r_id = _pull_int(parsed, ("rating_group_id", "group_rating"))
    q_id = _pull_int(parsed, ("question_group_id", "group_question"))

    out_r = r_id if r_id is not None and r_id in RATING_GROUP_ID_WHITELIST else None
    out_q = q_id if q_id is not None and q_id in _VALID_QUESTION else None

    if out_r is None:
        warns.append("gemini_groups: model không trả rating_group_id hợp lệ trong whitelist.")
    if out_q is None and q_id is not None:
        warns.append("gemini_groups: question_group_id không trong {88,99,100}, bỏ qua.")

    if out_r is not None:
        logger.info("gemini_groups: rating_group_id=%s question_group_id=%s", out_r, out_q)
    return out_r, out_q, warns
