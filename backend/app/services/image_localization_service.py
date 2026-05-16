import hashlib
import base64
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.product import Product

logger = logging.getLogger(__name__)

# Playwright Sync API không chạy an toàn trong asyncio loop (uvicorn/Jupyter). Dồn vào 1 worker thread.
_GEMINI_PW_EXECUTOR: Optional[ThreadPoolExecutor] = None
_GEMINI_PW_EXEC_LOCK = threading.Lock()


def _gemini_pw_dispatch(fn: Callable[[], Any], *, timeout_sec: Optional[float] = None) -> Any:
    global _GEMINI_PW_EXECUTOR
    ms = int(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_TIMEOUT_MS", 180000) or 180000)
    to = timeout_sec if timeout_sec is not None else max(300.0, ms / 1000.0 * 5)
    with _GEMINI_PW_EXEC_LOCK:
        if _GEMINI_PW_EXECUTOR is None:
            _GEMINI_PW_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini_pw")
    fut = _GEMINI_PW_EXECUTOR.submit(fn)
    return fut.result(timeout=to)


def _normalize_playwright_cookie(cookie: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Chuẩn hoá cookie export (Chrome/JSON) → field Playwright chấp nhận."""
    if not isinstance(cookie, dict):
        return None
    name = str(cookie.get("name") or "").strip()
    if not name:
        return None
    value = cookie.get("value")
    if value is None:
        return None
    value = str(value)
    domain = str(cookie.get("domain") or ".google.com").strip() or ".google.com"
    if domain.startswith("http://") or domain.startswith("https://"):
        try:
            domain = urlparse(domain).hostname or ".google.com"
        except Exception:
            domain = ".google.com"
    path = str(cookie.get("path") or "/").strip() or "/"

    out: Dict[str, Any] = {"name": name, "value": value, "domain": domain, "path": path}

    exp = cookie.get("expires")
    if exp is None and cookie.get("expirationDate") is not None:
        try:
            exp = int(float(cookie["expirationDate"]))
        except (TypeError, ValueError):
            exp = None
    if exp is None and cookie.get("expiry") is not None:
        try:
            exp = int(float(cookie["expiry"]))
        except (TypeError, ValueError):
            exp = None
    if exp is not None:
        try:
            out["expires"] = int(exp)
        except (TypeError, ValueError):
            pass

    if isinstance(cookie.get("httpOnly"), bool):
        out["httpOnly"] = cookie["httpOnly"]
    if isinstance(cookie.get("secure"), bool):
        out["secure"] = cookie["secure"]

    ss = cookie.get("sameSite")
    if isinstance(ss, str) and ss.strip():
        sm = ss.strip().lower()
        mp = {
            "strict": "Strict",
            "lax": "Lax",
            "none": "None",
            "unspecified": "Lax",
            "no_restriction": "None",
        }
        if sm in mp:
            out["sameSite"] = mp[sm]

    return out


def resolve_allows_ai_image_models(
    product: Optional[Product],
    *,
    job_override: Optional[bool] = None,
) -> bool:
    """
    Cho phép gọi Gemini/GPT Image trong job hiện tại.

    - job_override=False: cấm hoàn toàn (chỉ OCR + DeepSeek + vẽ local), bất kể explicit_only.
    - job_override=True: bật AI ảnh cho batch (vẫn cần key/cookie tùy chế độ).
    - job_override=None: mặc định — nếu IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY thì chỉ AI khi SP có
      product_info.image_localization.allow_ai_models; nếu không bật explicit_only thì cho phép AI.
    """
    if job_override is False:
        return False
    if job_override is True:
        return True
    if not getattr(settings, "IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY", False):
        return True
    if product is None:
        return False
    info = product.product_info if isinstance(product.product_info, dict) else {}
    loc = info.get("image_localization")
    if isinstance(loc, dict) and loc.get("allow_ai_models") is True:
        return True
    return False


def _has_chinese_text_blocks(blocks: List[Any]) -> bool:
    pattern = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]")
    for item in blocks or []:
        text = item.get("text", "") if isinstance(item, dict) else (item[0] if item else "")
        if text and pattern.search(str(text)):
            return True
    return False


def _output_jpeg_quality() -> int:
    return int(getattr(settings, "IMAGE_LOCALIZATION_OUTPUT_JPEG_QUALITY", 95) or 95)


def _encode_image_bytes(image_data: Any, filename: str = "image.jpg") -> bytes:
    import cv2

    q = max(70, min(100, _output_jpeg_quality()))
    ok, encoded = cv2.imencode(".jpg", image_data, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        raise ImageLocalizationError("Không encode được ảnh sau xử lý")
    return encoded.tobytes()


_brand_logo_bgra_template: Optional[Any] = None
_brand_logo_template_unavailable: bool = False


def _get_brand_logo_bgra_template() -> Optional[Any]:
    """PNG logo (BGRA) gốc; scale theo từng ảnh khi dán. None = tắt hoặc không đọc được."""
    global _brand_logo_bgra_template, _brand_logo_template_unavailable
    if _brand_logo_template_unavailable:
        return None
    if _brand_logo_bgra_template is not None:
        return _brand_logo_bgra_template
    if not getattr(settings, "IMAGE_LOCALIZATION_BRAND_LOGO_ENABLED", True):
        _brand_logo_template_unavailable = True
        return None
    path = (getattr(settings, "IMAGE_LOCALIZATION_BRAND_LOGO_PATH", "") or "").strip()
    if not path or not os.path.isfile(path):
        logger.info("Logo bản địa hóa: không có file %s — bỏ overlay.", path or "(rỗng)")
        _brand_logo_template_unavailable = True
        return None
    import cv2

    logo = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if logo is None:
        logger.warning("Logo bản địa hóa: không decode được %s", path)
        _brand_logo_template_unavailable = True
        return None
    if logo.ndim == 2:
        logo = cv2.cvtColor(logo, cv2.COLOR_GRAY2BGRA)
    elif logo.shape[2] == 3:
        logo = cv2.cvtColor(logo, cv2.COLOR_BGR2BGRA)
    _brand_logo_bgra_template = logo
    return logo


def apply_brand_logo_top_right_bgr(image_bgr: Any) -> Any:
    """
    Dán logo lên góc phải phía trên (giống banner mẫu). Chỉ gọi cho ảnh đã xử lý, trước encode/upload.
    """
    import cv2
    import numpy as np

    logo0 = _get_brand_logo_bgra_template()
    if logo0 is None or image_bgr is None:
        return image_bgr
    if not hasattr(image_bgr, "shape") or image_bgr.ndim != 3 or image_bgr.shape[2] < 3:
        return image_bgr
    h, w = int(image_bgr.shape[0]), int(image_bgr.shape[1])
    if h < 16 or w < 48:
        return image_bgr
    try:
        frac = float(getattr(settings, "IMAGE_LOCALIZATION_BRAND_LOGO_MAX_WIDTH_FRAC", 0.22))
    except (TypeError, ValueError):
        frac = 0.22
    frac = max(0.05, min(0.9, frac))
    max_w = max(8, int(w * frac))
    lh, lw = int(logo0.shape[0]), int(logo0.shape[1])
    scale = min(1.0, max_w / float(max(lw, 1)))
    new_w = max(1, int(lw * scale))
    new_h = max(1, int(lh * scale))
    logo = (
        logo0
        if (new_w == lw and new_h == lh)
        else cv2.resize(logo0, (new_w, new_h), interpolation=cv2.INTER_AREA)
    )
    lh, lw = int(logo.shape[0]), int(logo.shape[1])
    try:
        mfrac = float(getattr(settings, "IMAGE_LOCALIZATION_BRAND_LOGO_MARGIN_FRAC", 0.012))
    except (TypeError, ValueError):
        mfrac = 0.012
    mfrac = max(0.0, min(0.2, mfrac))
    margin = max(4, int(min(h, w) * mfrac))
    x1 = w - lw - margin
    y1 = margin
    if x1 < 0 or y1 < 0 or y1 + lh > h or x1 + lw > w:
        return image_bgr
    roi = image_bgr[y1 : y1 + lh, x1 : x1 + lw]
    if logo.shape[2] == 4:
        alpha = logo[:, :, 3:4].astype(np.float32) / 255.0
        lbgr = logo[:, :, :3].astype(np.float32)
        blended = (1.0 - alpha) * roi.astype(np.float32) + alpha * lbgr
        image_bgr[y1 : y1 + lh, x1 : x1 + lw] = blended.astype(np.uint8)
    else:
        image_bgr[y1 : y1 + lh, x1 : x1 + lw] = logo[:, :, :3]
    return image_bgr


def _apply_brand_logo_to_image_bytes(image_bytes: bytes, filename: str = "") -> bytes:
    """Decode → logo (nếu bật) → luôn encode JPEG (đồng bộ định dạng đăng Bunny)."""
    import cv2
    import numpy as np

    if not image_bytes:
        return image_bytes
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes
    logo = _get_brand_logo_bgra_template()
    if logo is not None:
        apply_brand_logo_top_right_bgr(img)
    q = max(70, min(100, _output_jpeg_quality()))
    ok, encoded = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
    if not ok:
        return image_bytes
    return encoded.tobytes()


def _split_part_method(action: str, message: str) -> str:
    """Phân loại cách xử lý một phần ảnh sau split (cho báo cáo)."""
    msg_l = (message or "").lower()
    u = (message or "").upper()
    if action == "deleted":
        return "deleted"
    if action == "kept":
        return "kept"
    if action != "processed":
        return "unknown"
    if any(x in u for x in ("GEMINI", "GPT", "OPENAI", "NANO BANANA")):
        return "ai_image"
    if "deepseek" in msg_l or "vẽ lại" in msg_l or "local ocr" in msg_l:
        return "local_draw"
    return "processed_other"


def _split_merge_detail_vi(trail: List[Dict[str, Any]]) -> Tuple[str, str]:
    """
    (dòng tóm tắt ngắn, dòng chi tiết đầy đủ bằng tiếng Việt).
    """
    labels = {
        "ai_image": "model AI ảnh (Gemini/GPT) sinh/chỉnh cả khung ảnh",
        "local_draw": "OCR: DeepSeek dịch chữ + vẽ lại chữ lên ảnh (local)",
        "kept": "giữ nguyên pixel phần đó",
        "deleted": "đánh dấu xóa (không dùng khi ghép thành công)",
        "unknown": "đã xử lý (không phân loại được)",
        "processed_other": "đã xử lý (khác)",
    }
    segs_short = []
    segs_long = []
    for e in sorted(trail, key=lambda x: int(x.get("part_index", 0))):
        i = int(e.get("part_index", 0)) + 1
        n = int(e.get("total_parts", len(trail)))
        m = str(e.get("method") or "unknown")
        segs_short.append(f"P{i}/{n}: {labels.get(m, m)}")
        raw_msg = (e.get("message") or "").strip()
        extra = f' — "{raw_msg[:120]}{"…" if len(raw_msg) > 120 else ""}"' if raw_msg else ""
        segs_long.append(f"Phần {i}/{n}: {labels.get(m, m)}{extra}")
    return " · ".join(segs_short), "; ".join(segs_long)


def _merge_localized_split_parts_with_grid(
    parts: Dict[int, Any],
    total_parts: int,
    orig_shapes: Dict[int, Tuple[int, int]],
) -> Any:
    """
    Resize từng phần về đúng (H, W) của crop lúc cắt rồi vstack.
    Giúp các mép dọc của từng dải thẳng hàng (cùng lưới pixel) dù model trả ảnh khác kích thước.
    """
    import cv2
    import numpy as np

    ordered: List[Any] = []
    for i in range(total_parts):
        img = parts.get(i)
        if img is None:
            raise ValueError("Thiếu phần ảnh khi ghép split")
        sh = orig_shapes.get(i)
        if sh is None:
            raise ValueError(f"Thiếu orig_shapes cho phần {i}")
        oh, ow = int(sh[0]), int(sh[1])
        m = img
        if len(m.shape) == 2:
            m = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        elif len(m.shape) == 3 and m.shape[2] == 4:
            m = cv2.cvtColor(m, cv2.COLOR_BGRA2BGR)
        m = m.astype("uint8")
        th, tw = m.shape[:2]
        if (th, tw) != (oh, ow):
            m = cv2.resize(m, (ow, oh), interpolation=cv2.INTER_AREA)
        ordered.append(m)
    widths = {x.shape[1] for x in ordered}
    if len(widths) != 1:
        parts_adj = {i: ordered[i] for i in range(total_parts)}
        return _vstack_localized_split_parts(parts_adj, total_parts)
    return np.vstack(ordered)


def _vstack_localized_split_parts(parts: Dict[int, Any], total_parts: int) -> Any:
    """
    Ghép dọc các phần sau split khi không có đủ orig_shapes, hoặc các phần không cùng W sau chỉnh.
    Dùng chiều rộng lớn nhất và pad bên phải (nền trắng) để np.vstack hợp lệ.
    """
    import cv2
    import numpy as np

    ordered = [parts[i] for i in range(total_parts)]
    mats = []
    for img in ordered:
        if img is None:
            raise ValueError("Thiếu phần ảnh khi ghép split")
        m = img
        if len(m.shape) == 2:
            m = cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)
        elif len(m.shape) == 3 and m.shape[2] == 4:
            m = cv2.cvtColor(m, cv2.COLOR_BGRA2BGR)
        mats.append(m.astype("uint8"))
    max_w = max(m.shape[1] for m in mats)
    padded = []
    for m in mats:
        _h, w = m.shape[:2]
        if w < max_w:
            m = cv2.copyMakeBorder(m, 0, 0, 0, max_w - w, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        padded.append(m)
    return np.vstack(padded)


LANGUAGE_LABELS = {
    "vi": "Vietnamese",
    "en": "English",
    "th": "Thai",
    "id": "Indonesian",
}


@dataclass
class ImageRef:
    bucket: str
    index: Optional[int]
    url: str


@dataclass
class ImageProcessResult:
    original_url: str
    final_url: Optional[str]
    status: str
    message: str = ""
    # Lưu product_info.image_localization.results[].detail (vd. split_parts).
    detail: Optional[Dict[str, Any]] = None


def image_process_result_to_stash(res: ImageProcessResult) -> Dict[str, Any]:
    d: Dict[str, Any] = {"final_url": res.final_url, "status": res.status, "message": res.message}
    if res.detail:
        d["detail"] = res.detail
    return d


class ImageLocalizationError(RuntimeError):
    pass


class ImageLocalizationFatalDependencyError(ImageLocalizationError):
    pass


_FATAL_DEPENDENCY_MARKERS = (
    "IMAGE_LOCALIZATION_FATAL_DEPENDENCY",
    "FatalDependencyError",
    "insufficient balance",
    "payment required",
    "resource_exhausted",
    "resource exhausted",
    "quota exceeded",
    "billing not enabled",
    "billing_disabled",
    "deepseek_missing_key",
)


def is_image_localization_fatal_dependency_error(exc: BaseException) -> bool:
    msg = f"{exc.__class__.__name__}: {exc}"
    return any(marker.lower() in msg.lower() for marker in _FATAL_DEPENDENCY_MARKERS)


def _raise_if_fatal_dependency(exc: BaseException) -> None:
    if is_image_localization_fatal_dependency_error(exc):
        raise ImageLocalizationFatalDependencyError(str(exc)) from exc


def ensure_runtime_dir() -> Path:
    path = Path(settings.IMAGE_LOCALIZATION_RUNTIME_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_gcp_vision_credentials_json_path(runtime: Path) -> str:
    """
    Trả đường dẫn tuyệt đối tới JSON service account dùng cho Cloud Vision.
    Tránh OCR lỗi [Errno 2] khi GCP_KEY_FILE rỗng hoặc path tương đối sai cwd trên VPS.
    """
    configured = (getattr(settings, "IMAGE_LOCALIZATION_GCP_KEY_FILE", None) or "").strip()
    backend_root = Path(__file__).resolve().parents[2]

    searched: List[str] = []
    uniq_try: List[Path] = []

    def enqueue(p: Path) -> None:
        try:
            rp = p.expanduser()
            try:
                rp = rp.resolve(strict=False)
            except TypeError:
                rp = rp.resolve()
        except Exception:
            return
        s = str(rp)
        if s not in searched:
            searched.append(s)
        uniq_try.append(rp)

    if configured:
        cp = Path(configured).expanduser()
        if cp.is_file():
            return str(cp.resolve())
        enqueue(cp)
        if not cp.is_absolute():
            enqueue(backend_root / configured)
            enqueue(Path.cwd() / configured)

    for name in ("gcp-vision-service-account.json", "phungvanmanh.json"):
        enqueue((runtime / name).resolve())
    enqueue((runtime / "credentials" / "service-account-key.json").resolve())

    for cand in uniq_try:
        try:
            if cand.is_file():
                return str(cand.resolve())
        except Exception:
            continue

    raise ImageLocalizationError(
        "Không tìm thấy JSON service account Google Cloud Vision "
        "(đường dẫn rỗng hoặc file không tồn tại). "
        "Trên VPS hãy: (1) đặt IMAGE_LOCALIZATION_GCP_KEY_FILE=<đường dẫn tuyệt đối tới file .json>; "
        "hoặc (2) sao chép service account vào "
        f"{runtime / 'gcp-vision-service-account.json'}; "
        "hoặc (3) đặt GOOGLE_APPLICATION_CREDENTIALS trỏ tới file đó. "
        "File local mẫu: backend/runtime/image_localization/gcp-vision-service-account.json (không commit — gitignore)."
    )


def normalize_image_url(url: str) -> str:
    s = (url or "").strip()
    if s.startswith("//"):
        return f"https:{s}"
    return s


def is_188_cdn_url(url: str) -> bool:
    try:
        host = urlparse(normalize_image_url(url)).netloc.lower()
    except Exception:
        return False
    public_host = urlparse(settings.BUNNY_CDN_PUBLIC_BASE).netloc.lower()
    return bool(host and (host == public_host or "188.com.vn" in host or "188comvn.b-cdn.net" in host))


def parse_cookie_text(raw: str) -> List[Dict[str, Any]]:
    """Accept JSON cookie export or a Cookie header string."""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and isinstance(parsed.get("cookies"), list):
            parsed = parsed["cookies"]
        if isinstance(parsed, list):
            cookies = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                value = str(item.get("value") or "")
                if not name:
                    continue
                cookie = {
                    "name": name,
                    "value": value,
                    "domain": item.get("domain") or ".google.com",
                    "path": item.get("path") or "/",
                }
                if item.get("expiry") is not None:
                    cookie["expiry"] = int(item["expiry"])
                cookies.append(cookie)
            return cookies
    except Exception:
        pass

    cookies = []
    for part in text.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        if not name:
            continue
        cookies.append({"name": name, "value": value.strip(), "domain": ".google.com", "path": "/"})
    return cookies


def save_gemini_cookie(raw_cookie: str) -> int:
    cookies = parse_cookie_text(raw_cookie)
    if not cookies:
        raise ValueError("Cookie Gemini không hợp lệ hoặc trống")
    runtime = ensure_runtime_dir()
    cookie_file = Path(settings.IMAGE_LOCALIZATION_GEMINI_COOKIE_FILE)
    if not cookie_file.is_absolute():
        cookie_file = runtime / cookie_file
    cookie_file.parent.mkdir(parents=True, exist_ok=True)
    cookie_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(cookies)


def load_gemini_cookies() -> List[Dict[str, Any]]:
    cookie_file = Path(settings.IMAGE_LOCALIZATION_GEMINI_COOKIE_FILE)
    if not cookie_file.is_absolute():
        cookie_file = ensure_runtime_dir() / cookie_file
    if not cookie_file.exists():
        return []
    try:
        data = json.loads(cookie_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _raw_cookie_expires_unix(cookie: Dict[str, Any]) -> Optional[int]:
    """Thời điểm hết hạn (Unix sec) của một object cookie export; None = session/thiếu metadata."""
    exp = cookie.get("expires")
    if exp is None and cookie.get("expirationDate") is not None:
        try:
            exp = int(float(cookie["expirationDate"]))
        except (TypeError, ValueError):
            exp = None
    if exp is None and cookie.get("expiry") is not None:
        try:
            exp = int(float(cookie["expiry"]))
        except (TypeError, ValueError):
            exp = None
    if exp is None:
        return None
    try:
        return int(exp)
    except (TypeError, ValueError):
        return None


def analyze_gemini_stored_cookie_expiry() -> Dict[str, Any]:
    """
    Phân tích file cookie đã lưu: chỉ báo `all_expired` khi mọi mục đều có expires và đều đã qua `now`.
    Nếu thiếu metadata hạn của bất kỳ mục nào → không kết luận hết hạn (tránh báo sai).
    """
    cookies = load_gemini_cookies()
    rows = [c for c in cookies if isinstance(c, dict) and str(c.get("name") or "").strip()]
    if not rows:
        return {
            "cookie_count": 0,
            "all_expired": False,
            "expiry_known_for_all": False,
        }
    now = int(time.time())
    timestamps: List[int] = []
    for c in rows:
        ts = _raw_cookie_expires_unix(c)
        if ts is None:
            return {
                "cookie_count": len(rows),
                "all_expired": False,
                "expiry_known_for_all": False,
            }
        timestamps.append(ts)
    all_expired = bool(timestamps) and all(ts < now for ts in timestamps)
    return {
        "cookie_count": len(rows),
        "all_expired": all_expired,
        "expiry_known_for_all": True,
    }


def gemini_deploy_cookie_blocked_message(cookie_analysis: Dict[str, Any]) -> Optional[str]:
    """Thông báo lỗi triển khai khi file cookie chỉ toàn cookie đã quá expires."""
    if not cookie_analysis.get("all_expired"):
        return None
    return (
        "Cookie Gemini trong file đã hết hạn (expires). "
        "Dán cookie mới trong admin hoặc mở trình duyệt một lần (headed), đăng nhập Gemini để làm mới phiên/profile."
    )


def _language_prompt(language: str) -> str:
    target = LANGUAGE_LABELS.get(language, language or "Vietnamese")
    return f"""ROLE: E-commerce Image Localization Agent

Translate every Chinese text element in the attached product image into {target}. Preserve product details, layout, dimensions, aspect ratio, text placement, original colors, and image quality. Remove website URLs and domains from the image. Convert Chinese weight units to metric during translation. Return only the processed image file, with no explanation."""


def _mime_for_image_filename(filename: str) -> str:
    ext = (os.path.splitext(filename)[1] or ".jpg").lower()
    if ext in (".png",):
        return "image/png"
    if ext in (".webp",):
        return "image/webp"
    if ext in (".gif",):
        return "image/gif"
    return "image/jpeg"


def _sanitize_model_id(raw: Optional[str], fallback: str) -> str:
    s = (raw or "").strip()
    if not s or len(s) > 120:
        return fallback
    if not re.match(r"^[a-zA-Z0-9_.\-]+$", s):
        return fallback
    return s


def _normalize_gemini_image_size(raw: Optional[str]) -> Optional[str]:
    """Google imageConfig.imageSize — chỉ 2K / 4K. Giá trị cũ 512 / 1K được nâng lên 2K."""
    if not raw or not str(raw).strip():
        return None
    k = str(raw).strip().upper().replace(" ", "")
    if k in ("512", "0.5K", "1K"):
        return "2K"
    if k in ("2K",):
        return "2K"
    if k in ("4K",):
        return "4K"
    return None


def _normalize_openai_image_quality(raw: Optional[str]) -> Optional[str]:
    """Chỉ high / auto; low và medium không còn hỗ trợ → high."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if s in ("low", "medium"):
        return "high"
    if s in ("high", "auto"):
        return s
    return None


def _normalize_openai_image_size(raw: Optional[str], model: str) -> Optional[str]:
    """Bỏ kích cỡ vuông nhỏ; giữ auto và preset lớn (tương đương tinh thần 2K/4K Gemini)."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    allowed = {
        "auto",
        "1024x1792",
        "1792x1024",
        "1536x1024",
        "1024x1536",
    }
    if s in allowed:
        return s
    if "gpt-image-2" in model.lower() and re.fullmatch(r"\d+x\d+", s):
        wp, hp = s.lower().split("x", 1)
        try:
            wi, hi = int(wp), int(hp)
            if wi <= 1024 and hi <= 1024:
                return None
        except ValueError:
            return None
        return s
    return None


def _extract_first_image_bytes_from_gemini_generate_response(data: Dict[str, Any]) -> Optional[bytes]:
    """Parse v1beta generateContent JSON (camelCase hoặc snake_case)."""
    import base64

    cands = data.get("candidates") or []
    if not cands:
        return None
    parts = ((cands[0].get("content") or {}).get("parts")) or []
    for part in parts:
        if not isinstance(part, dict):
            continue
        inline = part.get("inline_data") or part.get("inlineData")
        if not isinstance(inline, dict):
            continue
        mime = str(inline.get("mime_type") or inline.get("mimeType") or "").lower()
        raw_b64 = inline.get("data")
        if raw_b64 and "image" in mime:
            try:
                return base64.b64decode(raw_b64)
            except Exception:
                continue
    for part in reversed(parts):
        if not isinstance(part, dict):
            continue
        inline = part.get("inline_data") or part.get("inlineData")
        if not isinstance(inline, dict):
            continue
        raw_b64 = inline.get("data")
        if not raw_b64:
            continue
        try:
            return base64.b64decode(raw_b64)
        except Exception:
            continue
    return None


_GEMINI_AI_GENERATE_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiApiImageAdapter:
    """Gemini Native Image (Nano Banana) qua REST — cần GEMINI_API_KEY; không dùng cookie trình duyệt."""

    def __init__(
        self,
        language: str,
        *,
        image_model: Optional[str] = None,
        image_size: Optional[str] = None,
        inference_tier: Optional[str] = None,
    ):
        self.language = language or "vi"
        default_model = (
            (getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "") or "gemini-3-pro-image-preview").strip()
            or "gemini-3-pro-image-preview"
        )
        if image_model and str(image_model).strip():
            self._image_model = _sanitize_model_id(str(image_model).strip(), default_model)
        else:
            self._image_model = _sanitize_model_id(default_model, "gemini-3-pro-image-preview")
        self._image_size = _normalize_gemini_image_size(image_size)
        # Pipeline AI ảnh: chỉ tier standard đầy đủ — không Flex / queue giá rẻ.
        self._inference_tier = "standard"
        if self._image_size is None:
            ds = getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", "") or ""
            ds = ds.strip().upper().replace(" ", "")
            ds = ds if ds in ("2K", "4K") else "2K"
            self._image_size = _normalize_gemini_image_size(ds) or "2K"

    def check_auth(self) -> Dict[str, Any]:
        key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        return {
            "ready": len(key) >= 10,
            "key_configured": bool(key),
            "model": self._image_model,
            "inference_tier": self._inference_tier,
        }

    def close(self) -> None:
        return None

    def process(self, image_bytes: bytes, filename: str, source_url: str) -> Tuple[str, Optional[bytes], str]:
        import base64

        api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
        if len(api_key) < 10:
            raise ImageLocalizationError("Thiếu GEMINI_API_KEY cho chế độ Gemini API.")
        model = self._image_model
        timeout = max(30, int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_TIMEOUT_SEC", 300) or 300))
        url = f"{_GEMINI_AI_GENERATE_BASE}/models/{model}:generateContent"
        prompt = _language_prompt(self.language)
        mime = _mime_for_image_filename(filename)
        b64 = base64.b64encode(image_bytes).decode("ascii")
        gen_cfg: Dict[str, Any] = {"responseModalities": ["TEXT", "IMAGE"]}
        eff_size = self._image_size
        if eff_size:
            gen_cfg["imageConfig"] = {"imageSize": eff_size}
        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": mime, "data": b64}},
                    ],
                }
            ],
            "generationConfig": gen_cfg,
        }
        res = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
        if res.status_code != 200:
            raise ImageLocalizationError(
                f"Gemini API ảnh lỗi HTTP {res.status_code}: {(res.text or '')[:500]}"
            )
        try:
            body = res.json()
        except Exception as exc:
            raise ImageLocalizationError(f"Gemini API trả JSON không đọc được: {exc}") from exc
        fb = body.get("promptFeedback") or {}
        br = fb.get("blockReason") or fb.get("block_reason")
        if br:
            raise ImageLocalizationError(f"Gemini API từ chối prompt: {br}")
        out = _extract_first_image_bytes_from_gemini_generate_response(body)
        if not out:
            raise ImageLocalizationError(
                "Gemini API không trả ảnh (kiểm tra model sinh ảnh, ví dụ gemini-3-pro-image-preview)."
            )
        return "processed", out, "Gemini API (Nano Banana) đã xử lý ảnh"


class OpenAiGptImageAdapter:
    """OpenAI GPT Image — POST /v1/images/edits (cần OPENAI_API_KEY)."""

    def __init__(
        self,
        language: str,
        *,
        image_model: Optional[str] = None,
        image_quality: Optional[str] = None,
        image_size: Optional[str] = None,
        inference_tier: Optional[str] = None,
    ):
        self.language = language or "vi"
        default_model = (
            (getattr(settings, "IMAGE_LOCALIZATION_OPENAI_IMAGE_MODEL", "") or "gpt-image-2").strip() or "gpt-image-2"
        )
        if image_model and str(image_model).strip():
            self._model = _sanitize_model_id(str(image_model).strip(), default_model)
        else:
            self._model = _sanitize_model_id(default_model, "gpt-image-2")
        self._quality = _normalize_openai_image_quality(image_quality)
        self._size = _normalize_openai_image_size(image_size, self._model)
        self._inference_tier = "standard"
        if self._quality is None:
            dq = getattr(settings, "IMAGE_LOCALIZATION_OPENAI_DEFAULT_IMAGE_QUALITY", "high") or "high"
            self._quality = _normalize_openai_image_quality(str(dq))
            if self._quality is None:
                self._quality = "high"

    def check_auth(self) -> Dict[str, Any]:
        key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
        return {
            "ready": len(key) >= 10,
            "key_configured": bool(key),
            "model": self._model,
            "inference_tier": self._inference_tier,
            "openai_flex_removed": True,
        }

    def close(self) -> None:
        return None

    def process(self, image_bytes: bytes, filename: str, source_url: str) -> Tuple[str, Optional[bytes], str]:
        import base64
        import io

        key = (getattr(settings, "OPENAI_API_KEY", "") or "").strip()
        if len(key) < 10:
            raise ImageLocalizationError("Thiếu OPENAI_API_KEY cho chế độ GPT Image.")
        model = self._model
        timeout = max(60, int(getattr(settings, "IMAGE_LOCALIZATION_OPENAI_IMAGE_TIMEOUT_SEC", 300) or 300))
        mime = _mime_for_image_filename(filename)
        safe_name = os.path.basename(filename) or "product.jpg"
        if "." not in safe_name:
            safe_name = f"{safe_name}.jpg"
        prompt = _language_prompt(self.language)
        url = "https://api.openai.com/v1/images/edits"
        buf = io.BytesIO(image_bytes)
        buf.seek(0)
        files = {"image": (safe_name, buf, mime)}
        data: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": "1",
        }
        is_g2 = "gpt-image-2" in model.lower()
        if is_g2:
            data["size"] = self._size or "auto"
        elif self._size:
            data["size"] = self._size
        if self._quality:
            data["quality"] = self._quality
        if not is_g2:
            data["input_fidelity"] = "high"
        res = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            files=files,
            data=data,
            timeout=timeout,
        )
        if res.status_code != 200:
            detail = (res.text or "")[:800]
            try:
                err_obj = res.json().get("error") or {}
                if isinstance(err_obj, dict) and err_obj.get("message"):
                    detail = str(err_obj.get("message"))[:800]
            except Exception:
                pass
            raise ImageLocalizationError(f"OpenAI images/edits lỗi HTTP {res.status_code}: {detail}")
        try:
            body = res.json()
        except Exception as exc:
            raise ImageLocalizationError(f"OpenAI trả JSON không đọc được: {exc}") from exc
        rows = body.get("data") or []
        if not rows:
            raise ImageLocalizationError("OpenAI không trả data ảnh.")
        b64 = rows[0].get("b64_json")
        if not b64:
            raise ImageLocalizationError("OpenAI không trả b64_json (kiểm tra model GPT Image).")
        try:
            out = base64.b64decode(b64)
        except Exception as exc:
            raise ImageLocalizationError(f"Không decode base64 ảnh OpenAI: {exc}") from exc
        return "processed", out, "OpenAI GPT Image đã xử lý ảnh"


def build_gemini_image_adapter(
    language: str,
    mode: Optional[str] = None,
    *,
    gemini_image_model: Optional[str] = None,
    gemini_image_size: Optional[str] = None,
    openai_image_model: Optional[str] = None,
    openai_image_quality: Optional[str] = None,
    openai_image_size: Optional[str] = None,
    inference_tier: Optional[str] = None,
    playwright_headless: Optional[bool] = None,
) -> Any:
    m = (mode or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MODE", "web") or "web").strip().lower()
    if m == "api":
        return GeminiApiImageAdapter(
            language,
            image_model=gemini_image_model,
            image_size=gemini_image_size,
            inference_tier=inference_tier,
        )
    if m == "openai":
        return OpenAiGptImageAdapter(
            language,
            image_model=openai_image_model,
            image_quality=openai_image_quality,
            image_size=openai_image_size,
            inference_tier=inference_tier,
        )
    return GeminiWebImageAdapter(language, playwright_headless_override=playwright_headless)


class GeminiWebImageAdapter:
    """Playwright adapter for Gemini image localization."""

    def __init__(self, language: str, *, playwright_headless_override: Optional[bool] = None):
        self.language = language
        self._playwright_headless_override = playwright_headless_override
        self._playwright = None
        self._context = None
        self._page = None
        self._gemini_sso_click_attempts = 0
        self._google_accounts_row_click_attempts = 0

    def _effective_playwright_headless(self) -> bool:
        if self._playwright_headless_override is not None:
            return bool(self._playwright_headless_override)
        return bool(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_HEADLESS", True))

    def has_auth_hint(self) -> bool:
        if load_gemini_cookies():
            return True
        profile = self._chrome_profile_path()
        return (profile / "gemini_logged_in.marker").exists() or (profile / "Default").exists()

    def check_auth(self) -> Dict[str, Any]:
        cookies = load_gemini_cookies()
        cookie_count = len(cookies)
        profile = self._chrome_profile_path()
        cookie_analysis = analyze_gemini_stored_cookie_expiry()
        profile_logged_in_explicit = (profile / "gemini_logged_in.marker").exists()
        profile_has_data = profile_logged_in_explicit or (profile / "Default").exists()
        blocked = gemini_deploy_cookie_blocked_message(cookie_analysis)
        stale_cookie_deploy = cookie_count > 0 and bool(cookie_analysis.get("all_expired")) and not profile_logged_in_explicit
        if stale_cookie_deploy:
            ready = False
        else:
            ready = bool(cookie_count > 0) or profile_has_data
        requires_cookie_or_login_marker_for_headless = cookie_count == 0 and not profile_logged_in_explicit
        return {
            "cookie_count": cookie_count,
            "cookie_configured": bool(cookies),
            "cookies_all_expired": bool(cookie_analysis.get("all_expired")),
            "cookie_expiry_known_for_all": bool(cookie_analysis.get("expiry_known_for_all")),
            "cookie_deploy_block_reason": blocked if stale_cookie_deploy else None,
            "profile_path": str(profile),
            "profile_marker": profile_has_data,
            "profile_logged_in_marker": profile_logged_in_explicit,
            "requires_cookie_or_login_marker_for_headless": requires_cookie_or_login_marker_for_headless,
            "ready": ready,
        }

    def process(self, image_bytes: bytes, filename: str, source_url: str) -> Tuple[str, Optional[bytes], str]:
        suffix = Path(filename).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        ms = int(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_TIMEOUT_MS", 180000) or 180000)
        base_timeout = max(300.0, ms / 1000.0 * 5)
        login_extra_sec = (
            float(
                int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MANUAL_LOGIN_WAIT_MS", 900000) or 900000)
            )
            / 1000.0
            if not self._effective_playwright_headless()
            else 0.0
        )
        timeout_sec = base_timeout + login_extra_sec

        def _run() -> Tuple[str, Optional[bytes], str]:
            try:
                page = self._ensure_page()
                prompt = _language_prompt(self.language)
                before_images = self._image_count(page)
                self._upload_image(page, tmp_path)
                self._submit_prompt(page, prompt)
                output = self._wait_for_generated_image(page, before_images, source_url)
                return "processed", output, "Gemini Playwright đã xử lý ảnh"
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        return _gemini_pw_dispatch(_run, timeout_sec=timeout_sec)

    def _chrome_profile_path(self) -> Path:
        if settings.IMAGE_LOCALIZATION_CHROME_PROFILE_PATH:
            return Path(settings.IMAGE_LOCALIZATION_CHROME_PROFILE_PATH)
        return ensure_runtime_dir() / "chrome-profile"

    def _ensure_page(self):
        if self._page is not None:
            return self._page
        self._gemini_sso_click_attempts = 0
        self._google_accounts_row_click_attempts = 0
        profile = self._chrome_profile_path()
        cookies = load_gemini_cookies()
        cand = analyze_gemini_stored_cookie_expiry()
        blocked = gemini_deploy_cookie_blocked_message(cand)
        profile_login_marker_exists = (profile / "gemini_logged_in.marker").exists()
        stale_cookie_deploy = len(cookies) > 0 and bool(cand.get("all_expired")) and not profile_login_marker_exists
        if stale_cookie_deploy and blocked:
            raise ImageLocalizationError(f"[Triển khai] {blocked}")
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise ImageLocalizationError("Backend chưa cài Playwright. Chạy: pip install playwright && playwright install chromium") from exc

        self._playwright_timeout = PlaywrightTimeoutError
        profile.mkdir(parents=True, exist_ok=True)
        headless = self._effective_playwright_headless()
        if headless and len(cookies) == 0 and not profile_login_marker_exists:
            raise ImageLocalizationError(
                "[Triển khai] Chế độ ẩn trình duyệt (headless) bắt buộc có cookie Gemini đã lưu (Cookie Gemini → Lưu) "
                "hoặc profile đã có gemini_logged_in.marker (đăng nhập thành công một lần khi Hiện cửa sổ). "
                "Nạp xong rồi bấm Chạy lại."
            )
        timeout_ms = int(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_TIMEOUT_MS", 180000) or 180000)
        login_wait_ms = int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MANUAL_LOGIN_WAIT_MS", 900000) or 900000)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            str(profile),
            headless=headless,
            viewport={"width": 1366, "height": 900},
            user_agent=getattr(settings, "IMPORT_1688_USER_AGENT", None) or None,
            accept_downloads=True,
            args=["--disable-blink-features=AutomationControlled", "--disable-notifications"],
        )
        self._context.set_default_timeout(timeout_ms)
        skip_json_cookies = (
            profile_login_marker_exists
            and bool(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_SKIP_JSON_COOKIES_WHEN_PROFILE_MARKER", False))
            and len(cookies) > 0
        )
        if skip_json_cookies:
            logger.info(
                "Đã có gemini_logged_in.marker và IMAGE_LOCALIZATION_GEMINI_SKIP_JSON_COOKIES_WHEN_PROFILE_MARKER=true — "
                "bỏ qua merge cookie từ file JSON để không ghi đè phiên profile."
            )
        else:
            self._add_cookies()
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.goto("https://gemini.google.com/app", wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            self._page.wait_for_load_state("domcontentloaded", timeout=min(12000, timeout_ms))
        except Exception:
            pass
        if not headless:
            try:
                self._page.bring_to_front()
            except Exception:
                pass

        settle_ms = int(min(max(25000.0, timeout_ms * 0.5), 90000.0))
        settle = self._settle_gemini_ui(self._page, settle_ms)
        logger.info(
            "Gemini sau khi tải: settle=%s (chờ tối đa %sms) — chỉ chạy pipeline khi có ô nhập hoặc đã chờ đăng nhập headed.",
            settle,
            settle_ms,
        )

        if settle == "ready":
            try:
                if not headless:
                    self._page.bring_to_front()
            except Exception:
                pass
            return self._page

        expired_file_hint = blocked
        if expired_file_hint:
            raise ImageLocalizationError(f"[Triển khai] {expired_file_hint}")

        if headless:
            raise ImageLocalizationError(
                "[Triển khai] Headless: đã có cookie nhưng Gemini chưa hiện ô nhập (phiên hết hạn hoặc cookie thiếu domain). "
                "Dán cookie mới trong admin hoặc chọn Hiện cửa sổ để đăng nhập."
            )

        logger.info(
            "Gemini (hiện cửa sổ): chưa có ô nhập (settle=%s) — thử bấm Sign in (SSO profile) hoặc đăng nhập tay trong Chromium.",
            settle,
        )
        self._try_click_gemini_sign_in_for_sso(self._page)
        self._try_click_google_accounts_account_row(self._page)
        self._page.wait_for_timeout(2200)
        settle_sso = self._settle_gemini_ui(self._page, min(settle_ms, 35000))
        if settle_sso == "ready":
            try:
                self._page.bring_to_front()
            except Exception:
                pass
            return self._page

        self._wait_until_gemini_logged_in(self._page, login_wait_ms)

        if not self._gemini_prompt_editor_visible(self._page):
            raise ImageLocalizationError(
                "Gemini vẫn chưa có ô nhập sau khi chờ — hoàn thành đăng nhập Google rồi Chạy lại."
            )
        try:
            self._page.bring_to_front()
        except Exception:
            pass
        return self._page

    def _gemini_prompt_editor_visible(self, page) -> bool:
        """
        Chỉ true khi **đã đăng nhập** Gemini: Gemini marketing vẫn có ô 'Ask Gemini' khi có nút Sign In — không tính là ready.
        """
        try:
            if self._gemini_on_google_accounts_url(page):
                return False
            if self._sign_in_ui_visible(page):
                return False
            return self._prompt_locator(page).count() > 0
        except Exception:
            return False

    @staticmethod
    def _gemini_on_google_accounts_url(page) -> bool:
        """Đang ở trang OAuth/đăng nhập Google (chưa về Gemini app)."""
        try:
            u = (page.url or "").lower()
            return (
                "accounts.google.com" in u
                or "google.com/v3/signin" in u
                or "signin/oauth" in u
                or ("/signin/" in u and "google." in u)
            )
        except Exception:
            return False

    def _settle_gemini_ui(self, page, timeout_ms: int) -> str:
        """
        Chờ UI ổn định. Tránh lỗi: chưa Sign in, chưa có editor, trang đang load → _looks_logged_out=False → return sớm.
        Trả về: ready | logged_out | unsettled
        """
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            try:
                if self._gemini_prompt_editor_visible(page):
                    return "ready"
                if self._looks_logged_out(page):
                    return "logged_out"
            except Exception:
                pass
            page.wait_for_timeout(450)
            try:
                page.wait_for_load_state("networkidle", timeout=1800)
            except Exception:
                pass
        if self._gemini_prompt_editor_visible(page):
            return "ready"
        if self._looks_logged_out(page):
            return "logged_out"
        return "unsettled"

    def _wait_until_gemini_logged_in(self, page, wait_ms: int) -> None:
        logger.info(
            "Gemini (hiện cửa sổ): chưa đăng nhập — đăng nhập trong Chromium; chờ tối đa %.1f phút.",
            wait_ms / 60000.0,
        )
        deadline = time.monotonic() + wait_ms / 1000.0
        nav_interval = 55.0
        last_nav = time.monotonic()
        playwright_timeout_ms = int(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_TIMEOUT_MS", 180000) or 180000)

        while time.monotonic() < deadline:
            try:
                if self._gemini_prompt_editor_visible(page):
                    logger.info("Gemini (hiện cửa sổ): đã có ô nhập prompt — tiếp tục pipeline.")
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                    return
            except Exception:
                pass
            self._try_click_google_accounts_account_row(page)
            self._try_click_gemini_sign_in_for_sso(page)
            page.wait_for_timeout(2500)
            if time.monotonic() - last_nav >= nav_interval:
                try:
                    self._try_click_google_accounts_account_row(page)
                    self._try_click_gemini_sign_in_for_sso(page)
                    page.goto(
                        "https://gemini.google.com/app",
                        wait_until="domcontentloaded",
                        timeout=playwright_timeout_ms,
                    )
                    page.wait_for_timeout(1500)
                    try:
                        page.bring_to_front()
                    except Exception:
                        pass
                except Exception:
                    pass
                last_nav = time.monotonic()

        raise ImageLocalizationError(
            f"Hết thời gian chờ đăng nhập Gemini (~{max(1, int(wait_ms / 60000))} phút). "
            "Hoàn thành đăng nhập rồi Chạy lại, hoặc lưu cookie qua admin để chạy ẩn trình duyệt."
        )

    def _sign_in_ui_visible(self, page) -> bool:
        """Nút/link đăng nhập Google/Gemini (kể cả khi có ô Ask Gemini không đăng nhập)."""
        try:
            if self._gemini_on_google_accounts_url(page):
                return True
            if page.locator('a[href*="accounts.google.com"][href*="signin"]').count() > 0:
                return True
            if page.locator('a[href*="ServiceLogin"]').count() > 0:
                return True
            if page.locator('[aria-label*="Sign in"]').count() > 0:
                return True
            if page.locator('[aria-label*="sign in"]').count() > 0:
                return True
            if page.locator('[data-test-id*="sign-in"], [jsname*="signIn"]').count() > 0:
                return True
            if page.get_by_role("link", name=re.compile(r"sign\s*in", re.I)).count() > 0:
                return True
            if page.get_by_role("button", name=re.compile(r"sign\s*in|đăng nhập", re.I)).count() > 0:
                return True
            if (
                page.locator('[role="banner"] >> a:has-text("Sign in"), [role="banner"] >> button:has-text("Sign In"), '
                '[role="banner"] >> a:has-text("Sign In"), [role="banner"] >> button:has-text("Sign in")').count()
                > 0
            ):
                return True
            if page.locator('button:has-text("Sign In")').count() > 0:
                return True
            if page.locator('button:has-text("Sign in")').count() > 0:
                return True
        except Exception:
            pass
        return False

    def _try_click_gemini_sign_in_for_sso(self, page) -> None:
        """
        Headed: bấm Sign in trên gemini/google.com để kích hoạt SSO khi Chromium profile
        đã có phiên Google — thường đăng nhập tự động không cần gõ lại.
        """
        if self._effective_playwright_headless():
            return
        if self._gemini_sso_click_attempts >= 4:
            return
        try:
            u = (page.url or "").lower()
        except Exception:
            u = ""
        # Chỉ bấm trên trang Gemini — tránh nhầm trên accounts.google.com / chọn TK.
        if "gemini.google" not in u and "bard.google" not in u:
            return
        if self._gemini_prompt_editor_visible(page):
            return
        if not self._sign_in_ui_visible(page):
            return
        self._gemini_sso_click_attempts += 1
        logger.info(
            "Gemini (headed): bấm Sign in để SSO (lần %s/4, profile Chromium đã đăng nhập Google thì Gemini sẽ vào luôn).",
            self._gemini_sso_click_attempts,
        )
        try:
            page.bring_to_front()
        except Exception:
            pass
        selectors = (
            '[role="banner"] a[href*="accounts.google.com"][href*="signin"]',
            '[role="banner"] a[href*="accounts.google.com"]',
            'header >> a[href*="accounts.google.com"][href*="signin"]',
            '[role="navigation"] a[href*="accounts.google.com"][href*="signin"]',
            '[role="banner"] button:has-text("Sign In")',
            '[role="banner"] button:has-text("Sign in")',
            'button:has-text("Sign In"):visible',
            'button:has-text("Sign in"):visible',
            'a[href*="ServiceLogin"]',
        )
        for sel in selectors:
            try:
                base = page.locator(sel)
                if base.count() < 1:
                    continue
                el = base.first
                el.scroll_into_view_if_needed(timeout=4000)
                el.click(timeout=12000)
                page.wait_for_timeout(1600)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=min(25000, 12000))
                except Exception:
                    pass
                return
            except Exception:
                continue
        try:
            page.get_by_role("link", name=re.compile(r"^\s*sign\s*in\s*$", re.I)).first.click(timeout=9000)
            page.wait_for_timeout(1600)
        except Exception as exc:
            logger.warning("Không click được Sign in SSO: %s", exc)

    def _try_click_google_accounts_account_row(self, page) -> None:
        """
        Headed: đang accounts.google.com (chọn TK) — bấm vào **dòng tài khoản** (screenshot: tên + email + "Signed out").
        Ưu tiên IMAGE_LOCALIZATION_GOOGLE_ACCOUNT_EMAIL; không có thì thử hàng chứa "Signed out" / @ / data-email.
        """
        if self._effective_playwright_headless():
            return
        if not self._gemini_on_google_accounts_url(page):
            return
        if self._google_accounts_row_click_attempts >= 20:
            return
        try:
            page.bring_to_front()
        except Exception:
            pass

        configured = (getattr(settings, "IMAGE_LOCALIZATION_GOOGLE_ACCOUNT_EMAIL", "") or "").strip()

        def _escape_attr_css(v: str) -> str:
            return v.replace("\\", "\\\\").replace('"', '\\"')

        self._google_accounts_row_click_attempts += 1
        logger.info(
            "Google Accounts (headed): thử chọn dòng tài khoản (%s/20)%s.",
            self._google_accounts_row_click_attempts,
            f" — email .env: {configured}" if configured else " — ưu tiên Signed out / data-email",
        )

        if configured:
            esc = _escape_attr_css(configured)
            for sel in (f'[data-email="{esc}"]', f'[data-identifier="{esc}"]'):
                try:
                    loc = page.locator(sel)
                    if loc.count() < 1:
                        continue
                    loc.first.scroll_into_view_if_needed(timeout=4000)
                    loc.first.click(timeout=10000)
                    page.wait_for_timeout(1200)
                    return
                except Exception:
                    continue
            try:
                page.get_by_role("link", name=re.compile(re.escape(configured), re.I)).first.click(timeout=9000)
                page.wait_for_timeout(1200)
                return
            except Exception:
                pass
            try:
                page.get_by_text(configured, exact=True).first.click(timeout=9000)
                page.wait_for_timeout(1200)
                return
            except Exception:
                pass

        signed_out_rx = re.compile(r"signed\s+out|đã\s+đăng\s+xuất", re.I)
        for meth in (
            lambda: page.get_by_role("option").filter(has_text=signed_out_rx).first.click(timeout=9000),
            lambda: page.get_by_role("listitem").filter(has_text=signed_out_rx).first.click(timeout=9000),
            lambda: page.locator("[data-identifier]").filter(has_text=signed_out_rx).first.click(timeout=9000),
        ):
            try:
                meth()
                page.wait_for_timeout(1200)
                return
            except Exception:
                continue

        try:
            loc = page.locator("[data-email]").filter(has_text=re.compile(r".+@.+\..+"))
            if loc.count() > 0:
                loc.first.click(timeout=9000)
                page.wait_for_timeout(1200)
                return
        except Exception:
            pass

        try:
            page.locator('[role="listbox"] [role="option"]').filter(has_text=re.compile(r"@")).first.click(timeout=9000)
            page.wait_for_timeout(1200)
        except Exception as exc:
            logger.debug("Chưa click được dòng tài khoản Google Accounts: %s", exc)

    def _add_cookies(self) -> None:
        cookies = load_gemini_cookies()
        if not cookies or self._context is None:
            return
        normalized: List[Dict[str, Any]] = []
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            nc = _normalize_playwright_cookie(cookie)
            if nc:
                normalized.append(nc)
        if not normalized:
            return
        try:
            self._context.add_cookies(normalized)
        except Exception as exc:
            logger.warning("add_cookies batch lỗi (%s) — thử từng cookie", exc)
            for c in normalized:
                try:
                    self._context.add_cookies([c])
                except Exception as e2:
                    logger.warning("Bỏ cookie %s@%s: %s", c.get("name"), c.get("domain"), e2)

    def _looks_logged_out(self, page) -> bool:
        """Đang có luồng đăng nhập (Sign In / OAuth) — không dùng 'có ô text' một mình làm dấu hiệu đã login."""
        try:
            if self._gemini_on_google_accounts_url(page):
                return True
            if self._sign_in_ui_visible(page):
                return True
        except Exception:
            pass
        text = ""
        try:
            text = page.locator("body").inner_text(timeout=5000).lower()
        except Exception:
            text = ""
        logged_out_markers = ("sign in", "đăng nhập", "use gemini with your google account")
        markers_hit = bool(text) and any(marker in text for marker in logged_out_markers)
        try:
            has_editor = self._prompt_locator(page).count() > 0
        except Exception:
            has_editor = False
        return markers_hit and not has_editor

    def _prompt_locator(self, page):
        locators = [
            'div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"]',
            'textarea',
            '[role="textbox"]',
        ]
        for selector in locators:
            loc = page.locator(selector)
            if loc.count() > 0:
                return loc.last
        return page.locator('div[contenteditable="true"]').last

    def _image_count(self, page) -> int:
        """Chỉ đếm ảnh đủ lớn ngoài header — tránh baseline sai vì avatar/Material icon."""
        return len(self._gemini_eligible_image_urls(page))

    def _gemini_eligible_image_urls(self, page) -> List[str]:
        """Ảnh ứng viên trong nội dung Gemini: loại avatar, toolbar, icon nhỏ."""
        try:
            raw = page.evaluate(
                r"""() => {
                    const imgs = Array.from(document.querySelectorAll('body img'));
                    const out = [];
                    const seen = new Set();
                    for (const img of imgs) {
                        try {
                            if (img.closest('[role="banner"], header')) continue;
                            if (img.closest('aside[role="complementary"], nav[role="navigation"]')) continue;
                            const mtb = img.closest('[class*="mat-toolbar"]');
                            if (mtb && mtb.closest('[role="banner"], header')) continue;
                            const rect = img.getBoundingClientRect();
                            const vw = window.innerWidth || document.documentElement.clientWidth || 0;
                            const rtop = rect.top;
                            const rleft = rect.left;
                            const nw = img.naturalWidth || 0;
                            const nh = img.naturalHeight || 0;
                            const rw = rect.width || 0;
                            const rh = rect.height || 0;
                            const w = nw || rw;
                            const h = nh || rh;
                            if (w < 140 || h < 140) continue;
                            if (vw > 400 && rtop < 96 && rleft > vw - 260 && w < 360 && h < 360) continue;
                            const src = String(img.currentSrc || img.src || '').trim();
                            if (!src || seen.has(src)) continue;
                            const sl = src.toLowerCase();
                            if (/googleusercontent\.com\/a(\/|-)/.test(sl)) continue;
                            if (sl.includes('googleusercontent.com') && w < 280 && h < 280) continue;
                            if (sl.includes('gstatic.com') && w < 320) continue;
                            const alt = String(img.alt || '').toLowerCase();
                            if (alt.includes('profile') || alt.includes('avatar') || alt.includes('account')) continue;
                            seen.add(src);
                            out.push(src);
                        } catch (e) {}
                    }
                    return out;
                }"""
            )
            return list(raw) if isinstance(raw, list) else []
        except Exception:
            return []

    def _upload_image(self, page, image_path: str) -> None:
        """
        Giao diện Gemini Material: thường cần bấm '+' mở menu rồi 'Tải tệp lên' / 'Upload file'.
        Fallback: input file ẩn hoặc nút Attach cũ.
        """
        try:
            self._gemini_click_plus_then_upload_via_menu(page, image_path)
            return
        except Exception:
            logger.debug("_gemini_click_plus_then_upload_via_menu thất bại, thử các cách khác", exc_info=True)

        input_file = page.locator('input[type="file"]')
        if input_file.count() > 0:
            input_file.last.set_input_files(image_path)
            return

        upload_buttons = [
            'button[aria-label*="Upload"]',
            'button[aria-label*="Attach"]',
            'button[aria-label*="Add"]',
            'button:has-text("Upload")',
            'button:has-text("Tải")',
            'button:has-text("Thêm")',
        ]
        for selector in upload_buttons:
            button = page.locator(selector)
            if button.count() == 0:
                continue
            try:
                with page.expect_file_chooser(timeout=8000) as chooser_info:
                    button.last.click()
                chooser_info.value.set_files(image_path)
                return
            except Exception:
                continue
        raise ImageLocalizationError(
            "Không tìm thấy nút/input upload ảnh trên Gemini (+ → Tải tệp lên hoặc input file ẩn)."
        )

    def _gemini_click_plus_then_upload_via_menu(self, page, image_path: str) -> None:
        clicked_plus = False
        plus_by_text = page.locator("button").filter(has_text=re.compile(r"^\s*\+\s*$"))
        try:
            if plus_by_text.count() > 0:
                plus_by_text.last.click(timeout=6500)
                clicked_plus = True
        except Exception:
            clicked_plus = False

        if not clicked_plus:
            for pat in (
                r"^thêm$",
                r"add( to prompt)?",
                r"attach",
                r"expand more",
                r"more options",
            ):
                try:
                    page.get_by_role("button", name=re.compile(pat, re.I)).last.click(timeout=4500)
                    clicked_plus = True
                    break
                except Exception:
                    continue

        if not clicked_plus:
            for sel in (
                'button[aria-label*="Thêm" i][aria-haspopup]',
                'button[aria-label*="Add" i][aria-haspopup]',
                'button[aria-label*="Attach" i][aria-haspopup]',
            ):
                loc = page.locator(sel)
                try:
                    if loc.count() > 0:
                        loc.last.click(timeout=4500)
                        clicked_plus = True
                        break
                except Exception:
                    continue

        if not clicked_plus:
            raise ImageLocalizationError("Không thấy nút + / menu đính kèm Gemini để upload")

        page.wait_for_timeout(600)

        try:
            page.locator('input[type="file"]').first.set_input_files(image_path, timeout=3500)
            return
        except Exception:
            pass

        last_err: Optional[Exception] = None
        with page.expect_file_chooser(timeout=18000) as chooser_info:
            clicked_menu = False
            for menuitem_pat in (
                re.compile(r"tải\s*tệp\s*lên|upload\s*file|^upload\b|đính\s*tệp|attach\s*file", re.I),
            ):
                try:
                    page.get_by_role("menuitem", name=menuitem_pat).first.click(timeout=8000)
                    clicked_menu = True
                    break
                except Exception as e:
                    last_err = e
                    continue

            if not clicked_menu:
                for label in ("Tải tệp lên", "Upload file", "Upload", "Đính tệp", "Attach file"):
                    try:
                        page.get_by_text(label, exact=True).first.click(timeout=6000)
                        clicked_menu = True
                        break
                    except Exception as e:
                        last_err = e
                        continue

            if not clicked_menu:
                try:
                    page.get_by_text(re.compile(r"tải\s+tệp\s+lên|upload\s+file", re.I)).first.click(timeout=6000)
                    clicked_menu = True
                except Exception as e:
                    last_err = e

            if not clicked_menu:
                raise ImageLocalizationError(
                    "Đã mở menu '+' nhưng không bấm được mục Tải tệp lên / Upload file."
                ) from last_err

        chooser_info.value.set_files(image_path)

    def _submit_prompt(self, page, prompt: str) -> None:
        editor = self._prompt_locator(page)
        try:
            editor.click()
            editor.fill(prompt)
        except Exception:
            editor.click()
            page.keyboard.insert_text(prompt)

        submit_selectors = [
            'button[aria-label*="Send"]',
            'button[aria-label*="Submit"]',
            'button[aria-label*="Gửi"]',
            'button:has-text("Send")',
            'button:has-text("Gửi")',
        ]
        for selector in submit_selectors:
            button = page.locator(selector)
            if button.count() > 0:
                try:
                    button.last.click()
                    return
                except Exception:
                    pass
        page.keyboard.press("Enter")

    def _wait_for_generated_image(self, page, before_images: int, source_url: str) -> bytes:
        timeout_ms = int(getattr(settings, "IMAGE_LOCALIZATION_PLAYWRIGHT_TIMEOUT_MS", 180000) or 180000)
        deadline = time.monotonic() + timeout_ms / 1000
        last_error = ""
        while time.monotonic() < deadline:
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            candidates = self._candidate_image_sources(page, before_images)
            best: Optional[bytes] = None
            best_len = 0
            for src in reversed(candidates):
                try:
                    data = self._read_image_src(page, src, source_url)
                    if data and len(data) > best_len:
                        best_len = len(data)
                        best = data
                except Exception as exc:
                    last_error = str(exc)
            if best is not None and best_len > 1024:
                return best
            page.wait_for_timeout(3000)
        raise ImageLocalizationError(f"Gemini không trả ảnh kết quả trong thời gian chờ. {last_error}".strip())

    def _candidate_image_sources(self, page, before_images: int) -> List[str]:
        urls = self._gemini_eligible_image_urls(page)
        cut = max(0, int(before_images))
        return urls[cut:] if cut < len(urls) else []

    def _read_image_src(self, page, src: str, referer: str) -> bytes:
        if src.startswith("data:"):
            _, b64 = src.split(",", 1)
            return base64.b64decode(b64)
        if src.startswith("blob:"):
            b64 = page.evaluate(
                """async (url) => {
                    const res = await fetch(url);
                    const blob = await res.blob();
                    const buf = await blob.arrayBuffer();
                    let binary = '';
                    const bytes = new Uint8Array(buf);
                    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
                    return btoa(binary);
                }""",
                src,
            )
            return base64.b64decode(b64)
        headers = {"Referer": referer or "https://gemini.google.com/"}
        if self._context is not None:
            res = self._context.request.get(src, headers=headers, timeout=60000)
            if not res.ok:
                raise ImageLocalizationError(f"Tải ảnh Gemini lỗi HTTP {res.status}")
            return res.body()
        res = requests.get(src, headers=headers, timeout=60)
        res.raise_for_status()
        return res.content

    def close(self) -> None:
        if self._playwright is None and self._context is None and self._page is None:
            return

        def _do() -> None:
            try:
                if self._context is not None:
                    self._context.close()
            finally:
                self._context = None
                self._page = None
                if self._playwright is not None:
                    self._playwright.stop()
                    self._playwright = None

        try:
            _gemini_pw_dispatch(_do, timeout_sec=120)
        except Exception as exc:
            logger.warning("GeminiWebImageAdapter.close: %s", exc)


class _LegacySheetsAdapter:
    def extract_urls_from_data(self, data: Any) -> List[str]:
        if data is None:
            return []
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
        if isinstance(data, tuple):
            return [str(x).strip() for x in data if str(x).strip()]
        if isinstance(data, str):
            s = data.strip()
            if not s:
                return []
            try:
                raw = json.loads(s)
                if isinstance(raw, list):
                    return [str(x).strip() for x in raw if str(x).strip()]
            except Exception:
                pass
            return re.findall(r"https?://[^\s\]\"')]+|//[^\s\]\"')]+", s)
        return []


class LegacyImageLocalizationPipeline:
    """Run the old Google Vision/classifier/split/local pipeline against DB image URLs."""

    def __init__(self, language: str, gemini: Any, *, allows_ai_image_models: bool = True):
        self.language = language
        self.gemini = gemini
        self.allows_ai_image_models = bool(allows_ai_image_models)
        self._modules = self._prepare_modules()
        self.ImageMerger = self._modules["ImageMerger"]
        self.ImageSplitter = self._modules["ImageSplitter"]
        self.OCRProcessor = self._modules["OCRProcessor"]
        self.TextTranslator = self._modules["TextTranslator"]
        self.ImageProcessor = self._modules["ImageProcessor"]
        self.image_classifier = self._modules["image_classifier"]
        self.sheets = _LegacySheetsAdapter()

    @staticmethod
    def available() -> bool:
        return Path(settings.IMAGE_LOCALIZATION_TOOL_DIR).exists()

    def _prepare_modules(self) -> Dict[str, Any]:
        tool_dir = Path(settings.IMAGE_LOCALIZATION_TOOL_DIR)
        if not tool_dir.exists():
            raise ImageLocalizationError(f"Không tìm thấy image localization tool: {tool_dir}")
        tool_dir_s = str(tool_dir)
        if tool_dir_s not in sys.path:
            sys.path.insert(0, tool_dir_s)

        import importlib

        module_names = [
            "config",
            "image_merger",
            "image_splitter",
            "ocr_processor",
            "text_translator",
            "image_processor",
            "image_classifier",
            "error_handler",
            "text_overlap_detector",
            "bunny_uploader",
            "gemini_post_checker",
            "gemini_processor",
            "playwright_shim",
            "utils_logger",
        ]
        for mod_name in module_names:
            loaded = sys.modules.get(mod_name)
            loaded_file = Path(getattr(loaded, "__file__", "") or "") if loaded else None
            if loaded_file and tool_dir not in loaded_file.parents:
                del sys.modules[mod_name]

        config_mod = importlib.import_module("config")
        runtime = ensure_runtime_dir()
        gcp_key = resolve_gcp_vision_credentials_json_path(runtime)
        overrides = {
            "BASE_DIR": runtime,
            "CREDENTIALS_PATH": gcp_key,
            "TEMP_DIR": str(runtime / "temp_images"),
            "TEMP_IMAGES_DIR": str(runtime / "temp_images"),
            "DOWNLOADS_DIR": str(runtime / "downloads"),
            "LOGS_DIR": str(runtime / "logs"),
            "CACHE_DIR": str(runtime / "processed_images_cache"),
            "CHROME_PROFILE_PATH": str(
                Path(settings.IMAGE_LOCALIZATION_CHROME_PROFILE_PATH)
                if settings.IMAGE_LOCALIZATION_CHROME_PROFILE_PATH
                else runtime / "chrome-profile"
            ),
            "GCP_KEY_FILE": gcp_key,
            "DEEPSEEK_API_KEY": settings.DEEPSEEK_API_KEY,
            "DEEPSEEK_URL": settings.DEEPSEEK_API_URL,
            "BUNNY_API_KEY": settings.BUNNY_STORAGE_ACCESS_KEY,
            "STORAGE_ZONE_NAME": settings.BUNNY_STORAGE_ZONE_NAME,
            "BUNNY_STORAGE_HOSTNAME": "storage.bunnycdn.com",
            "BATCH_SIZE": max(1, int(getattr(settings, "IMAGE_LOCALIZATION_BATCH_SIZE", 10) or 10)),
            "OCR_SMART_RETRY_MAX_SLOW_WAITS": max(
                0, int(getattr(settings, "IMAGE_LOCALIZATION_OCR_MAX_SLOW_WAITS", 0) or 0)
            ),
        }
        for key, value in overrides.items():
            setattr(config_mod, key, value)
        for dirname in ("TEMP_DIR", "TEMP_IMAGES_DIR", "DOWNLOADS_DIR", "LOGS_DIR", "CACHE_DIR", "CHROME_PROFILE_PATH"):
            try:
                Path(getattr(config_mod, dirname)).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        modules = {}
        for mod_name in ("image_merger", "image_splitter", "ocr_processor", "text_translator", "image_processor", "image_classifier"):
            mod = importlib.import_module(mod_name)
            for key, value in overrides.items():
                if hasattr(mod, key):
                    setattr(mod, key, value)
            modules[mod_name] = mod
        return {
            "ImageMerger": modules["image_merger"].ImageMerger,
            "ImageSplitter": modules["image_splitter"].ImageSplitter,
            "OCRProcessor": modules["ocr_processor"].OCRProcessor,
            "TextTranslator": modules["text_translator"].TextTranslator,
            "ImageProcessor": modules["image_processor"].ImageProcessor,
            "image_classifier": modules["image_classifier"].image_classifier,
        }

    def process_urls(self, product: Product, urls: List[str], should_cancel=None) -> Dict[str, ImageProcessResult]:
        results: Dict[str, ImageProcessResult] = {}
        merger = self.ImageMerger()
        splitter = self.ImageSplitter()
        ocr = self.OCRProcessor()
        translator = self.TextTranslator()
        img_proc = self.ImageProcessor()

        batches = merger.merge_all_images_in_batches(urls, [], [], 0, self.sheets)
        for url, info in (batches.get("column_mapping") or {}).items():
            status = info.get("status")
            if status == "SKIPPED_188":
                results[normalize_image_url(url)] = ImageProcessResult(normalize_image_url(url), normalize_image_url(url), "kept", "Ảnh đã ở CDN 188")
            elif status in {"TOO_SMALL", "DOWNLOAD_FAILED"}:
                msg = "Ảnh quá nhỏ/thumbnail" if status == "TOO_SMALL" else "Tải ảnh lỗi/404"
                results[normalize_image_url(url)] = ImageProcessResult(normalize_image_url(url), None, "deleted", msg)

        if should_cancel and should_cancel():
            raise ImageLocalizationError("Job đã bị hủy")

        all_ocr: Dict[int, List[Any]] = {}
        for batch in batches.get("batches", []):
            if should_cancel and should_cancel():
                raise ImageLocalizationError("Job đã bị hủy")
            with open(batch["merged_path"], "rb") as f:
                all_ocr[batch["batch_index"]] = self._normalize_ocr(ocr.process_image(f.read()))

        split_results = splitter.process_all_batches(batches, all_ocr)
        split_buffer: Dict[str, Dict[str, Any]] = {}

        for part_url, data in split_results.items():
            if should_cancel and should_cancel():
                raise ImageLocalizationError("Job đã bị hủy")
            orig_url = normalize_image_url(data.get("original_url") or part_url)
            if orig_url in results and results[orig_url].status == "deleted":
                continue
            is_split = bool(data.get("is_split_part"))
            if is_split and orig_url not in split_buffer:
                split_buffer[orig_url] = {
                    "parts": {},
                    "orig_shapes": {},
                    "part_trail": [],
                    "total_parts": int(data.get("total_parts") or 1),
                    "modified": False,
                    "deleted": False,
                    "delete_message": None,
                    "filename": (data.get("filename") or "image.jpg").split("_part")[0],
                }

            if is_split:
                buf = split_buffer[orig_url]
                pi = int(data.get("part_index") or 0)
                raw = data.get("image_data")
                if raw is not None and getattr(raw, "shape", None) is not None:
                    buf["orig_shapes"][pi] = (int(raw.shape[0]), int(raw.shape[1]))

            action, final_image, message = self._process_image_part(data, translator, img_proc)
            if is_split:
                buf = split_buffer[orig_url]
                if action == "deleted":
                    buf["deleted"] = True
                    if not buf.get("delete_message") and message:
                        buf["delete_message"] = (
                            f"Phần {int(data.get('part_index') or 0) + 1}/{int(data.get('total_parts') or 1)}: {message}"
                        )
                elif not buf["deleted"]:
                    pi = int(data.get("part_index") or 0)
                    tp = int(data.get("total_parts") or 1)
                    buf["parts"][pi] = final_image
                    if action == "processed":
                        buf["modified"] = True
                    trail = buf.setdefault("part_trail", [])
                    trail.append(
                        {
                            "part_index": pi,
                            "total_parts": tp,
                            "action": action,
                            "method": _split_part_method(action, message),
                            "message": (message or "")[:500],
                        }
                    )
            else:
                if action == "deleted":
                    results[orig_url] = ImageProcessResult(orig_url, None, "deleted", message)
                elif action == "processed":
                    final_bytes = _encode_image_bytes(
                        apply_brand_logo_top_right_bgr(final_image),
                        data.get("filename") or "image.jpg",
                    )
                    final_url = self._upload_bytes(product, final_bytes, data.get("filename") or "image.jpg")
                    results[orig_url] = ImageProcessResult(orig_url, final_url, "processed", message)
                else:
                    results[orig_url] = ImageProcessResult(orig_url, orig_url, "kept", message)

        for orig_url, info in split_buffer.items():
            if info["deleted"]:
                detail = info.get("delete_message") or ""
                msg = (
                    detail
                    if detail
                    else "Một phần ảnh dài bị yêu cầu xóa (không có message chi tiết — xem log pipeline)."
                )
                results[orig_url] = ImageProcessResult(orig_url, None, "deleted", msg)
                continue
            if not info["modified"]:
                results[orig_url] = ImageProcessResult(orig_url, orig_url, "kept", "Ảnh dài không cần xử lý")
                continue
            parts = info["parts"]
            if len(parts) != info["total_parts"]:
                results[orig_url] = ImageProcessResult(orig_url, orig_url, "kept", "Thiếu phần ảnh sau split, giữ ảnh gốc")
                continue
            try:
                orig_shapes = info.get("orig_shapes") or {}
                total_p = info["total_parts"]
                if len(orig_shapes) == total_p and all(i in orig_shapes for i in range(total_p)):
                    merged = _merge_localized_split_parts_with_grid(parts, total_p, orig_shapes)
                else:
                    merged = _vstack_localized_split_parts(parts, total_p)
            except Exception as exc:
                logger.warning("Ghép split lỗi (%s), giữ ảnh gốc: %s", orig_url, exc)
                results[orig_url] = ImageProcessResult(orig_url, orig_url, "kept", f"Ghép phần ảnh lỗi: {exc}")
                continue
            final_bytes = _encode_image_bytes(
                apply_brand_logo_top_right_bgr(merged),
                info["filename"] + ".jpg",
            )
            final_url = self._upload_bytes(product, final_bytes, info["filename"] + ".jpg")
            trail = sorted(
                info.get("part_trail") or [],
                key=lambda x: int(x.get("part_index", 0)),
            )
            short_vi, long_vi = _split_merge_detail_vi(trail)
            msg = "Đã split, xử lý và ghép lại ảnh dài. " + short_vi + " — " + long_vi
            detail = {"split_parts": trail, "split_detail_vi": long_vi}
            results[orig_url] = ImageProcessResult(
                orig_url, final_url, "processed", msg, detail=detail
            )

        for url in urls:
            normalized = normalize_image_url(url)
            results.setdefault(normalized, ImageProcessResult(normalized, normalized, "kept", "Không cần xử lý"))
        return results

    def process_single_image(
        self,
        product: Product,
        url: str,
        image_bytes: bytes,
        filename: str,
    ) -> ImageProcessResult:
        """
        Một URL, không merge/split batch: OCR → classifier → Gemini/GPT chỉ khi type == gemini
        và allows_ai_image_models; nếu classifier yêu cầu AI nhưng không có chỉ định → DeepSeek+vẽ.
        """
        normalized = normalize_image_url(url)
        translator = self.TextTranslator()
        img_proc = self.ImageProcessor()
        ocr = self.OCRProcessor()
        try:
            norm_ocr = self._normalize_ocr(ocr.process_image(image_bytes))
        except Exception as exc:
            logger.warning("Fallback từng ảnh: OCR lỗi %s (%s)", normalized, exc)
            return ImageProcessResult(normalized, normalized, "error", f"OCR lỗi: {exc}")
        try:
            image = self._decode_image_bytes(image_bytes)
        except Exception as exc:
            return ImageProcessResult(normalized, normalized, "error", f"Decode ảnh lỗi: {exc}")
        data = {
            "image_data": image,
            "ocr_results": norm_ocr,
            "original_url": normalized,
            "filename": filename,
            "is_split_part": False,
        }
        try:
            action, final_image, message = self._process_image_part(data, translator, img_proc)
        except Exception as exc:
            logger.exception("Fallback từng ảnh: xử lý nội bộ lỗi %s", normalized)
            return ImageProcessResult(normalized, normalized, "error", str(exc))
        if action == "deleted":
            return ImageProcessResult(normalized, None, "deleted", message)
        if action == "processed":
            final_bytes = _encode_image_bytes(apply_brand_logo_top_right_bgr(final_image), filename)
            final_url = self._upload_bytes(product, final_bytes, filename)
            return ImageProcessResult(normalized, final_url, "processed", message)
        return ImageProcessResult(normalized, normalized, "kept", message)

    def _process_image_part(self, data: Dict[str, Any], translator: Any, img_proc: Any) -> Tuple[str, Any, str]:
        norm_ocr = self._normalize_ocr(data.get("ocr_results") or [])
        cls = self.image_classifier.classify_image(norm_ocr, [], data.get("original_url") or "")
        image = data["image_data"]
        filename = data.get("filename") or "image.jpg"
        if cls.get("type") == "delete":
            return "deleted", None, f"Xóa theo classifier: {cls.get('details', {}).get('detected_keyword') or 'keyword'}"
        if cls.get("type") == "keep":
            return "kept", image, "Không có chữ Trung cần xử lý"
        if cls.get("type") == "gemini":
            if not self.allows_ai_image_models:
                logger.info(
                    "Classifier=yêu cầu Gemini/GPT nhưng không có chỉ định AI — dùng DeepSeek+vẽ: %s",
                    (data.get("original_url") or "")[:120],
                )
                return self._process_local(data, translator, img_proc, data.get("original_url") or "")
            return self._run_gemini_image_edit(data, translator, img_proc, image, filename)

        local_res = self._process_local(data, translator, img_proc, data.get("original_url") or "")
        if (
            self.allows_ai_image_models
            and local_res[0] == "kept"
            and "Local overlap cao" in (local_res[2] or "")
        ):
            logger.info(
                "Local overlap cao — leo thang Gemini/GPT: %s",
                (data.get("original_url") or "")[:120],
            )
            gem_res = self._run_gemini_image_edit(data, translator, img_proc, image, filename)
            if gem_res[0] in ("processed", "deleted"):
                return gem_res
        return local_res

    def _run_gemini_image_edit(
        self,
        data: Dict[str, Any],
        translator: Any,
        img_proc: Any,
        image: Any,
        filename: str,
    ) -> Tuple[str, Any, str]:
        """Gọi Gemini hoặc GPT Image (adapter); tái sử dụng cho classifier gemini và leo thang sau overlap local."""
        url = data.get("original_url") or ""
        if not self.allows_ai_image_models:
            return "kept", image, "Không gọi Gemini/GPT (chưa chỉ định AI ảnh)"
        fail_suffix = ""
        try:
            status, output_bytes, msg = self.gemini.process(
                _encode_image_bytes(image, filename), filename, url
            )
            if status == "deleted":
                return "deleted", None, msg
            if output_bytes:
                processed = self._decode_image_bytes(output_bytes)
                post_ocr = self._post_check_ocr(output_bytes)
                if _has_chinese_text_blocks(post_ocr):
                    loc = self._process_local(
                        {"image_data": processed, "ocr_results": post_ocr}, translator, img_proc, url
                    )
                    if loc[0] == "processed":
                        return loc
                return "processed", processed, msg
            fail_suffix = " (không nhận được bytes ảnh từ model; kiểm tra chế độ API/Web/OpenAI và quota)"
        except Exception as exc:
            logger.warning("Gemini/GPT ảnh lỗi: %s", exc)
            fail_suffix = f" — {exc}"
        return "kept", image, f"Gemini/GPT không tạo ảnh dùng được{fail_suffix}"

    def _process_local(self, data: Dict[str, Any], translator: Any, img_proc: Any, url: str) -> Tuple[str, Any, str]:
        valid_ocr = []
        for item in self._normalize_ocr(data.get("ocr_results") or []):
            bbox = item.get("bbox") or []
            if len(bbox) >= 4:
                valid_ocr.append({"text": item.get("text", ""), "bbox": [int(x) for x in bbox[:4]]})
        translated = translator.classify_and_process_blocks(valid_ocr, url)
        if translated is None:
            return "deleted", None, "Xóa theo keyword cấm trong local translator"
        if not translated:
            return "kept", data["image_data"], "Không có block local cần xử lý"
        processed_blocks, ignore_blocks = translated
        max_ratio = 0.0
        try:
            _, max_ratio = img_proc.check_processed_overlap(
                processed_blocks,
                data["image_data"].shape[1],
                data["image_data"].shape[0],
                0.01,
            )
            abort_th = getattr(settings, "IMAGE_LOCALIZATION_LOCAL_OVERLAP_ABORT_THRESHOLD", None)
            if abort_th is not None and max_ratio > float(abort_th):
                return (
                    "kept",
                    data["image_data"],
                    f"Local overlap cao ({max_ratio:.0%} > {float(abort_th):.0%}), giữ ảnh gốc — "
                    "tắt IMAGE_LOCALIZATION_LOCAL_OVERLAP_ABORT_THRESHOLD hoặc tăng ngưỡng nếu muốn vẫn vẽ.",
                )
            if max_ratio > 0.01 and abort_th is None:
                logger.info(
                    "Local: overlap bbox ước lượng tối đa %.1f%% — vẫn vẽ (không đặt IMAGE_LOCALIZATION_LOCAL_OVERLAP_ABORT_THRESHOLD)",
                    max_ratio * 100,
                )
        except Exception:
            pass
        final = img_proc.process_image_with_text(data["image_data"], processed_blocks, ignore_blocks)
        if final is not None:
            msg = "Đã xử lý local OCR + DeepSeek + vẽ lại chữ"
            if max_ratio > 0.01:
                msg += (
                    f" — các khối chữ dự kiến đè nhau ~{max_ratio:.0%} "
                    "(đã vẽ theo thứ tự inpaint; để giữ ảnh gốc khi đè nặng hãy đặt IMAGE_LOCALIZATION_LOCAL_OVERLAP_ABORT_THRESHOLD)."
                )
            return "processed", final, msg
        return "kept", data["image_data"], "Local không tạo ảnh kết quả"

    def _post_check_ocr(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        try:
            return self._normalize_ocr(self.OCRProcessor().process_image(image_bytes))
        except Exception as exc:
            logger.warning("Hậu kiểm OCR lỗi: %s", exc)
            return []

    @staticmethod
    def _normalize_ocr(ocr_results: List[Any]) -> List[Dict[str, Any]]:
        normalized = []
        for item in ocr_results or []:
            if isinstance(item, dict):
                text = str(item.get("text", ""))
                bbox = item.get("bbox", [])
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                text = str(item[0])
                bbox = item[1]
            else:
                continue
            try:
                bbox_list = [int(float(x)) for x in list(bbox)[:4]]
            except Exception:
                bbox_list = []
            normalized.append({"text": text, "bbox": bbox_list})
        return normalized

    @staticmethod
    def _decode_image_bytes(image_bytes: bytes) -> Any:
        import cv2
        import numpy as np

        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            raise ImageLocalizationError("Không decode được ảnh Gemini trả về")
        return img

    def _upload_bytes(self, product: Product, image_bytes: bytes, filename: str) -> str:
        ext = ".jpg"
        digest = hashlib.sha1(image_bytes).hexdigest()[:12]
        safe_code = re.sub(r"[^a-zA-Z0-9_-]+", "-", product.product_id or product.code or "product").strip("-") or "product"
        remote_name = f"{safe_code}-{self.language}-{int(time.time())}-{digest}{ext}"
        prefix = settings.BUNNY_UPLOAD_PATH_PREFIX.strip("/") or "site"
        remote_path = f"{prefix}/localized-images/{safe_code}/{remote_name}"
        zone = settings.BUNNY_STORAGE_ZONE_NAME
        key = settings.BUNNY_STORAGE_ACCESS_KEY
        if not zone or not key:
            raise ImageLocalizationError("Thiếu BUNNY_STORAGE_ZONE_NAME hoặc BUNNY_STORAGE_ACCESS_KEY")
        res = requests.put(
            f"https://storage.bunnycdn.com/{zone}/{remote_path}",
            headers={"AccessKey": key, "Content-Type": "application/octet-stream"},
            data=image_bytes,
            timeout=60,
        )
        if res.status_code not in (200, 201, 409):
            raise ImageLocalizationError(f"Upload Bunny lỗi {res.status_code}: {res.text[:200]}")
        return f"{settings.BUNNY_CDN_PUBLIC_BASE.rstrip('/')}/{remote_path}"


class ProductImageLocalizationService:
    def __init__(
        self,
        language: str = "vi",
        force: bool = False,
        dry_run: bool = False,
        gemini_mode: Optional[str] = None,
        gemini_image_model: Optional[str] = None,
        gemini_image_size: Optional[str] = None,
        openai_image_model: Optional[str] = None,
        openai_image_quality: Optional[str] = None,
        openai_image_size: Optional[str] = None,
        inference_tier: Optional[str] = None,
        allow_ai_image_models: Optional[bool] = None,
        playwright_headless: Optional[bool] = None,
    ):
        self.language = language or "vi"
        self.force = force
        self.dry_run = dry_run
        self.allow_ai_image_models_override = allow_ai_image_models
        gm = (gemini_mode or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_MODE", "web") or "web").strip().lower()
        self.gemini_mode = gm if gm in ("web", "api", "openai") else "web"
        self.session = requests.Session()
        self.inference_tier = "standard"  # Chỉ pipeline chất lượng đầy đủ; flex không còn dùng trong adapter.
        self.gemini = build_gemini_image_adapter(
            self.language,
            self.gemini_mode,
            gemini_image_model=gemini_image_model,
            gemini_image_size=gemini_image_size,
            openai_image_model=openai_image_model,
            openai_image_quality=openai_image_quality,
            openai_image_size=openai_image_size,
            inference_tier=self.inference_tier,
            playwright_headless=playwright_headless,
        )

    def close(self) -> None:
        self.gemini.close()

    def _allows_ai_image(self, product: Product) -> bool:
        return resolve_allows_ai_image_models(product, job_override=self.allow_ai_image_models_override)

    def _claim_product_for_processing(self, db: Session, product: Product) -> bool:
        status_filter = (
            Product.image_localization_status.is_(None)
            | (Product.image_localization_status != "processing")
        )
        if not self.force:
            status_filter = (
                Product.image_localization_status.is_(None)
                | (Product.image_localization_status.in_(["", "pending", "failed"]))
            )

        claimed = (
            db.query(Product)
            .filter(Product.id == product.id)
            .filter(status_filter)
            .update(
                {
                    Product.image_localization_status: "processing",
                    Product.image_localization_language: self.language,
                    Product.image_localization_error: None,
                },
                synchronize_session=False,
            )
        )
        db.commit()
        if not claimed:
            db.refresh(product)
            return False
        db.refresh(product)
        return True

    def process_product(self, db: Session, product: Product, should_cancel=None) -> Dict[str, Any]:
        if should_cancel and should_cancel():
            raise ImageLocalizationError("Job đã bị hủy")

        if not self._claim_product_for_processing(db, product):
            current_status = (product.image_localization_status or "").strip() or "pending"
            msg = (
                "Bỏ qua vì sản phẩm đang được job bản địa hóa khác xử lý."
                if current_status == "processing"
                else f"Bỏ qua vì trạng thái hiện tại là {current_status}."
            )
            return {"status": "skipped", "processed_images": 0, "message": msg}

        refs = self._collect_refs(product)
        unique_urls = []
        seen = set()
        for ref in refs:
            u = normalize_image_url(ref.url)
            if not u or u in seen or u == "DELETED":
                continue
            seen.add(u)
            unique_urls.append(u)

        if not unique_urls:
            product.image_localization_status = "skipped"
            product.image_localization_language = self.language
            product.image_localization_error = "Sản phẩm không có URL ảnh ở O/P/Q/T"
            db.commit()
            return {"status": "skipped", "processed_images": 0, "message": product.image_localization_error}

        limit = max(0, int(getattr(settings, "IMAGE_LOCALIZATION_MAX_IMAGES_PER_PRODUCT", 80) or 80))
        if limit:
            unique_urls = unique_urls[:limit]

        results: Dict[str, ImageProcessResult] = {}
        if settings.IMAGE_LOCALIZATION_FULL_PIPELINE_ENABLED and LegacyImageLocalizationPipeline.available():
            allow_ai = self._allows_ai_image(product)
            try:
                results = LegacyImageLocalizationPipeline(
                    self.language,
                    self.gemini,
                    allows_ai_image_models=allow_ai,
                ).process_urls(
                    product,
                    unique_urls,
                    should_cancel=should_cancel,
                )
            except Exception as exc:
                _raise_if_fatal_dependency(exc)
                logger.exception(
                    "Full pipeline lỗi (%s), fallback từng ảnh (Gemini/GPT chỉ khi có chỉ định AI) cho %s",
                    exc,
                    product.product_id,
                )
                fallback_pl = LegacyImageLocalizationPipeline(
                    self.language,
                    self.gemini,
                    allows_ai_image_models=allow_ai,
                )
                results = {}
                for url in unique_urls:
                    if should_cancel and should_cancel():
                        raise ImageLocalizationError("Job đã bị hủy")
                    if not self.force and is_188_cdn_url(url):
                        results[url] = ImageProcessResult(url, url, "kept", "Ảnh đã ở CDN 188")
                        continue
                    try:
                        image_bytes, filename = self._download(url)
                        results[url] = fallback_pl.process_single_image(product, url, image_bytes, filename)
                    except Exception as exc2:
                        _raise_if_fatal_dependency(exc2)
                        logger.exception("Lỗi bản địa hóa ảnh %s cho product %s", url, product.product_id)
                        results[url] = ImageProcessResult(url, url, "error", str(exc2))
        else:
            for url in unique_urls:
                if should_cancel and should_cancel():
                    raise ImageLocalizationError("Job đã bị hủy")
                if not self.force and is_188_cdn_url(url):
                    results[url] = ImageProcessResult(url, url, "kept", "Ảnh đã ở CDN 188")
                    continue
                try:
                    results[url] = self._process_one(product, url)
                except Exception as exc:
                    _raise_if_fatal_dependency(exc)
                    logger.exception("Lỗi bản địa hóa ảnh %s cho product %s", url, product.product_id)
                    results[url] = ImageProcessResult(url, url, "error", str(exc))

        failed = [r for r in results.values() if r.status == "error"]
        changed = [r for r in results.values() if r.final_url and r.final_url != r.original_url]
        if failed and not changed:
            product.image_localization_status = "failed"
            product.image_localization_error = failed[0].message[:2000]
            db.commit()
            return {"status": "failed", "processed_images": 0, "message": product.image_localization_error}

        if not self.dry_run:
            self._apply_results(product, results)
            self._stash_originals(product, refs, results)
            product.image_localization_status = "localized"
            product.image_localization_language = self.language
            product.image_localized_at = datetime.now(timezone.utc)
            product.image_localization_error = failed[0].message[:2000] if failed else None
            db.commit()
            db.refresh(product)

        return {
            "status": "localized",
            "processed_images": len(changed),
            "failed_images": len(failed),
            "message": f"Đã cập nhật {len(changed)} ảnh" + (f", lỗi {len(failed)} ảnh" if failed else ""),
        }

    def _process_one(self, product: Product, url: str) -> ImageProcessResult:
        if not self._allows_ai_image(product):
            if LegacyImageLocalizationPipeline.available():
                image_bytes, filename = self._download(url)
                pl = LegacyImageLocalizationPipeline(
                    self.language,
                    self.gemini,
                    allows_ai_image_models=False,
                )
                return pl.process_single_image(product, url, image_bytes, filename)
            return ImageProcessResult(
                url,
                url,
                "kept",
                "Chế độ chỉ AI khi có chỉ định: bật IMAGE_LOCALIZATION_AI_IMAGE_EXPLICIT_ONLY nhưng thiếu "
                "allow_ai_image_models (job) hoặc product_info.image_localization.allow_ai_models=true; "
                "hoặc không có pipeline Vision/DeepSeek (IMAGE_LOCALIZATION_TOOL_DIR).",
            )
        image_bytes, filename = self._download(url)
        status, output_bytes, message = self.gemini.process(image_bytes, filename, url)
        if status == "deleted":
            return ImageProcessResult(url, None, "deleted", message)
        if status == "kept" and output_bytes == image_bytes:
            return ImageProcessResult(url, url, "kept", message)
        if output_bytes is None:
            return ImageProcessResult(url, url, "kept", message)
        final_url = self._upload_to_bunny(output_bytes, filename, product)
        return ImageProcessResult(url, final_url, "processed", message)

    def _download(self, url: str) -> Tuple[bytes, str]:
        normalized = normalize_image_url(url)
        headers = {"User-Agent": getattr(settings, "IMPORT_1688_USER_AGENT", "Mozilla/5.0")}
        res = self.session.get(normalized, headers=headers, timeout=45)
        res.raise_for_status()
        content_type = (res.headers.get("content-type") or "").lower()
        if "image" not in content_type and not re.search(r"\.(jpe?g|png|webp|gif)(?:$|\?)", normalized, re.I):
            raise ImageLocalizationError(f"URL không phải ảnh: {normalized}")
        parsed_name = os.path.basename(urlparse(normalized).path) or "image.jpg"
        if "." not in parsed_name:
            parsed_name = f"{parsed_name}.jpg"
        return res.content, parsed_name

    def _upload_to_bunny(self, image_bytes: bytes, source_filename: str, product: Product) -> str:
        image_bytes = _apply_brand_logo_to_image_bytes(image_bytes, source_filename)
        zone = settings.BUNNY_STORAGE_ZONE_NAME
        key = settings.BUNNY_STORAGE_ACCESS_KEY
        if not zone or not key:
            raise ImageLocalizationError("Thiếu BUNNY_STORAGE_ZONE_NAME hoặc BUNNY_STORAGE_ACCESS_KEY")
        ext = ".jpg"
        digest = hashlib.sha1(image_bytes).hexdigest()[:12]
        safe_code = re.sub(r"[^a-zA-Z0-9_-]+", "-", product.product_id or product.code or "product").strip("-") or "product"
        filename = f"{safe_code}-{self.language}-{int(time.time())}-{digest}{ext}"
        prefix = settings.BUNNY_UPLOAD_PATH_PREFIX.strip("/") or "site"
        remote_path = f"{prefix}/localized-images/{safe_code}/{filename}"
        upload_url = f"https://storage.bunnycdn.com/{zone}/{remote_path}"
        res = self.session.put(
            upload_url,
            headers={"AccessKey": key, "Content-Type": "application/octet-stream"},
            data=image_bytes,
            timeout=60,
        )
        if res.status_code not in (200, 201, 409):
            raise ImageLocalizationError(f"Upload Bunny lỗi {res.status_code}: {res.text[:200]}")
        return f"{settings.BUNNY_CDN_PUBLIC_BASE.rstrip('/')}/{remote_path}"

    def _collect_refs(self, product: Product) -> List[ImageRef]:
        refs: List[ImageRef] = []
        colors = product.colors if isinstance(product.colors, list) else []
        for idx, color in enumerate(colors):
            if isinstance(color, dict) and isinstance(color.get("img"), str):
                refs.append(ImageRef("colors", idx, color["img"]))
        images = product.images if isinstance(product.images, list) else []
        for idx, url in enumerate(images):
            if isinstance(url, str):
                refs.append(ImageRef("images", idx, url))
        gallery = product.gallery if isinstance(product.gallery, list) else []
        for idx, url in enumerate(gallery):
            if isinstance(url, str):
                refs.append(ImageRef("gallery", idx, url))
        if isinstance(product.main_image, str) and product.main_image.strip():
            refs.append(ImageRef("main_image", None, product.main_image))
        return refs

    def _apply_results(self, product: Product, results: Dict[str, ImageProcessResult]) -> None:
        def replacement(url: str) -> Optional[str]:
            r = results.get(normalize_image_url(url))
            if not r:
                return url
            return r.final_url

        colors = []
        for item in product.colors if isinstance(product.colors, list) else []:
            if isinstance(item, dict) and isinstance(item.get("img"), str):
                nxt = dict(item)
                new_url = replacement(item["img"])
                if new_url:
                    nxt["img"] = new_url
                    colors.append(nxt)
                else:
                    nxt.pop("img", None)
                    colors.append(nxt)
            else:
                colors.append(item)
        product.colors = colors

        images = product.images if isinstance(product.images, list) else []
        product.images = [new_url for url in images for new_url in [replacement(url)] if new_url]
        gallery = product.gallery if isinstance(product.gallery, list) else []
        product.gallery = [new_url for url in gallery for new_url in [replacement(url)] if new_url]
        if product.main_image:
            product.main_image = replacement(product.main_image)

    def _stash_originals(self, product: Product, refs: List[ImageRef], results: Dict[str, ImageProcessResult]) -> None:
        info = product.product_info if isinstance(product.product_info, dict) else {}
        loc = info.get("image_localization")
        if not isinstance(loc, dict):
            loc = {}
        loc.update(
            {
                "language": self.language,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "originals": [
                    {"bucket": r.bucket, "index": r.index, "url": normalize_image_url(r.url)}
                    for r in refs
                    if normalize_image_url(r.url) in results
                ],
                "results": {url: image_process_result_to_stash(res) for url, res in results.items()},
            }
        )
        info["image_localization"] = loc
        product.product_info = info


def products_pending_localization(db: Session, product_ids: Optional[Iterable[str]], force: bool, limit: int) -> List[Product]:
    query = db.query(Product)
    pending_filter = (
        Product.image_localization_status.is_(None)
        | (Product.image_localization_status.in_(["", "pending", "failed"]))
    )
    if product_ids:
        ids = [str(x).strip() for x in product_ids if str(x).strip()]
        query = query.filter(Product.product_id.in_(ids))
        if not force:
            query = query.filter(pending_filter)
    elif not force:
        query = query.filter(pending_filter)
    query = query.filter(
        (Product.image_localization_status.is_(None))
        | (Product.image_localization_status != "processing")
    )
    query = query.order_by(Product.id.asc())
    if limit and limit > 0:
        query = query.limit(limit)
    return list(query.all())

