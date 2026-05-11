"""Báo cáo chi tiết bản địa hóa ảnh cho admin — từ product_info.image_localization."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from app.models.product import Product
from app.services.image_localization_service import normalize_image_url

_BUCKET_ORDER = {"colors": 0, "images": 1, "gallery": 2, "main_image": 3}


def _parse_product_info(product: Product) -> Dict[str, Any]:
    pi = product.product_info
    if isinstance(pi, dict):
        return pi
    if isinstance(pi, str) and pi.strip():
        try:
            parsed = json.loads(pi)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _categorize(status: str, message: str, detail: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(category_key, label_vi)"""
    msg = message or ""
    mlow = msg.lower()
    st = (status or "").lower()
    if st == "deleted":
        return "deleted", "Đã xóa ảnh"
    if st == "error":
        return "error", "Lỗi xử lý"
    if st == "kept":
        if "cdn 188" in mlow or "đã ở cdn" in mlow:
            return "kept_cdn", "Giữ nguyên (đã ở CDN site)"
        return "kept_other", "Giữ nguyên (không đổi file)"
    if st == "processed":
        sp = None
        if isinstance(detail, dict):
            sp = detail.get("split_parts")
        if isinstance(sp, list) and sp:
            methods = {str(x.get("method") or "") for x in sp if isinstance(x, dict)}
            has_ai = "ai_image" in methods
            has_local = "local_draw" in methods
            if has_ai and has_local:
                return "local_pipeline", "Ảnh dài (ghép): trộn AI ảnh và vẽ local"
            if has_ai and not has_local:
                return "ai_image", "Ảnh dài (ghép): AI ảnh (Gemini/GPT)"
            if has_local and not has_ai:
                return "local_draw", "Ảnh dài (ghép): OCR + DeepSeek + vẽ local"
        u = msg.upper()
        if "GEMINI" in u or "GPT" in u or "OPENAI" in u or "NANO BANANA" in u:
            return "ai_image", "Model AI ảnh (Gemini / GPT)"
        if "deepseek" in mlow or "vẽ lại" in mlow or "local ocr" in mlow:
            return "local_draw", "OCR + dịch + vẽ lại (local)"
        if "split" in mlow or "ghép" in mlow:
            return "local_pipeline", "Ảnh dài: cắt / xử lý / ghép"
        return "processed_other", "Đã xử lý (khác)"
    return "unknown", st or "?"


def build_image_localization_report(product: Product) -> Dict[str, Any]:
    info = _parse_product_info(product)
    loc = info.get("image_localization")
    if not isinstance(loc, dict):
        loc = {}

    results_raw = loc.get("results")
    if not isinstance(results_raw, dict):
        results_raw = {}

    originals_raw = loc.get("originals")
    originals_list: List[Dict[str, Any]] = (
        [x for x in originals_raw if isinstance(x, dict)] if isinstance(originals_raw, list) else []
    )

    url_to_ref: Dict[str, Dict[str, Any]] = {}
    for o in originals_list:
        u = o.get("url")
        if isinstance(u, str) and u.strip():
            url_to_ref[normalize_image_url(u.strip())] = {
                "bucket": o.get("bucket"),
                "index": o.get("index"),
            }

    summary: Dict[str, int] = {
        "total": 0,
        "deleted": 0,
        "error": 0,
        "ai_image": 0,
        "local_draw": 0,
        "local_pipeline": 0,
        "processed_other": 0,
        "kept_cdn": 0,
        "kept_other": 0,
        "unknown": 0,
    }

    items: List[Dict[str, Any]] = []
    for url_key, payload in results_raw.items():
        if not isinstance(payload, dict):
            continue
        norm_url = normalize_image_url(str(url_key))
        st = str(payload.get("status") or "")
        msg = str(payload.get("message") or "")
        detail = payload.get("detail") if isinstance(payload.get("detail"), dict) else None
        cat, label_vi = _categorize(st, msg, detail)
        ref = url_to_ref.get(norm_url, {})
        bucket = ref.get("bucket")
        idx = ref.get("index")
        summary["total"] += 1
        if cat in summary:
            summary[cat] += 1
        else:
            summary["unknown"] += 1

        items.append(
            {
                "original_url": norm_url,
                "final_url": payload.get("final_url"),
                "status": st,
                "category": cat,
                "label_vi": label_vi,
                "message": msg,
                "detail": detail,
                "bucket": bucket,
                "index": idx,
            }
        )

    def sort_key(it: Dict[str, Any]) -> Tuple[int, int, str]:
        b = str(it.get("bucket") or "")
        i = it.get("index")
        ii = int(i) if isinstance(i, int) else 999
        return (_BUCKET_ORDER.get(b, 99), ii, it.get("original_url") or "")

    items.sort(key=sort_key)

    return {
        "product_id": product.product_id,
        "db_status": product.image_localization_status,
        "db_language": product.image_localization_language,
        "db_error": product.image_localization_error,
        "report_language": loc.get("language"),
        "report_processed_at": loc.get("processed_at"),
        "has_report": bool(results_raw),
        "summary": summary,
        "items": items,
    }
