"""
Fallback DeepSeek khi luật từ-khóa không gán được nhóm đánh giá (group_rating).

Chỉ gọi khi rule-based trả group_rating == 0; không bịa mã — chỉ chọn trong whitelist.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

from app.core.config import settings
from app.services.import_link_deepseek_taxonomy import _extract_json_object
from app.services.product_rating_question_groups import (
    RATING_GROUP_ID_WHITELIST,
    rating_group_catalog_text_for_prompt,
)

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 45
_PROMPT_BLOCKS_MAX_CHARS = 100_000

_VALID_QUESTION: Set[int] = {88, 99, 100}


def deepseek_fallback_import_groups(
    context_text: str,
    product_name: str,
) -> Tuple[Optional[int], Optional[int], List[str]]:
    """
    Gọi DeepSeek chọn một mã rating + question trong whitelist.
    Trả (rating_group_id | None, question_group_id | None, warnings).
    """
    warns: List[str] = []

    key = (getattr(settings, "DEEPSEEK_API_KEY", "") or "").strip()
    if not key:
        return None, None, warns

    if not getattr(settings, "IMPORT_LINK_DEEPSEEK_GROUPS_FALLBACK_ENABLED", False):
        return None, None, warns

    catalog = rating_group_catalog_text_for_prompt()
    ctx = (context_text or "").strip()
    pname = (product_name or "").strip()
    if len(catalog) > _PROMPT_BLOCKS_MAX_CHARS:
        catalog = catalog[: _PROMPT_BLOCKS_MAX_CHARS] + "\n...[truncated]"

    whitelist_ids = ",".join(str(i) for i in sorted(RATING_GROUP_ID_WHITELIST))
    sys = (
        "Bạn gán hai mã cố định cho một sản phẩm thương mại Việt Nam.\n\n"
        "Quy tắc nhóm **câu hỏi** (question_group_id), chỉ một trong ba số sau:\n"
        "- **99**: không phân biệt giới hoặc unisex nam-nữ trong tên/ngữ cảnh (hoặc không suy được).\n"
        "- **100**: sản phẩm dành **nam** (hoặc từ chỉ nam rõ ràng).\n"
        "- **88**: sản phẩm dành **nữ** (hoặc từ chỉ nữ rõ ràng).\n\n"
        "Quy tắc nhóm **đánh giá** (rating_group_id):\n"
        "- Chọn **exactly một** id số trong bảng có dạng `id:ví-dụ cụm` sau đây (chỉ số trong whitelist).\n"
        "- Ưu tiên đúng **loại hàng + giới** theo NGỮ CẢNH (danh mục, tên).\n\n"
        "Đầu ra: **JSON thuần** một object, không markdown:\n"
        '{"rating_group_id": <int whitelist>, "question_group_id": 88 hoặc 99 hoặc 100}\n'
    )

    usr = (
        f"WHITELIST rating_group_id (chỉ được chọn một số trong tập): [{whitelist_ids}]\n\n"
        "Bảng chi tiết (id : nhãn):\n"
        f"{catalog}\n\n"
        "NGỮ CẢNH (taxonomy + slug + JSON + tên, có thể lẫn ngoại ngữ):\n"
        f"{ctx[:40000]}\n\n"
        f"TÊN SẢN PHẨM:\n{pname[:2000]}\n"
    )

    url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-chat"
    allowed = RATING_GROUP_ID_WHITELIST

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.1,
                "messages": [{"role": "system", "content": sys}, {"role": "user", "content": usr}],
                "max_tokens": 220,
            },
            timeout=_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        warns.append(f"deepseek_groups: lỗi mạng: {exc}")
        return None, None, warns

    if not resp.ok:
        warns.append(f"deepseek_groups: HTTP {resp.status_code} {resp.text[:400]}")
        return None, None, warns

    try:
        body: Dict[str, Any] = resp.json()
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_object(content)
    except (TypeError, ValueError, IndexError, KeyError, Exception) as exc:
        warns.append(f"deepseek_groups: không đọc được JSON — {exc}")
        return None, None, warns

    def _pull_int(keys: Tuple[str, ...]) -> Optional[int]:
        for k in keys:
            if k not in parsed:
                continue
            raw = parsed.get(k)
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

    r_id = _pull_int(("rating_group_id", "group_rating"))
    q_id = _pull_int(("question_group_id", "group_question"))

    out_r = r_id if r_id is not None and r_id in allowed else None
    out_q = q_id if q_id is not None and q_id in _VALID_QUESTION else None

    if out_r is None:
        warns.append("deepseek_groups: model không trả rating_group_id hợp lệ trong whitelist.")
    if out_q is None and q_id is not None:
        warns.append("deepseek_groups: question_group_id không trong {88,99,100}, bỏ qua.")

    if out_r is not None:
        logger.info("deepseek_groups: rating_group_id=%s question_group_id=%s", out_r, out_q)
    return out_r, out_q, warns
