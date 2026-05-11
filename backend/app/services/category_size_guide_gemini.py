"""
Sinh ảnh infographic hướng dẫn chọn size (Gemini image, mặc định gemini-3-pro-image-preview)
và upload Bunny; cập nhật categories.size_guide_image_url (cat1).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from app.core.config import settings
from app.services.image_localization_service import (
    _extract_first_image_bytes_from_gemini_generate_response,
    _normalize_gemini_image_size,
    _sanitize_model_id,
)

logger = logging.getLogger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Danh mục cấp 1 nên có bảng size (slug trong DB sau import taxonomy).
DEFAULT_SIZE_GUIDE_CAT1_SLUGS: Tuple[str, ...] = (
    "giay-dep-nam",
    "giay-dep-nu",
    "thoi-trang-nam",
    "thoi-trang-nu",
    "do-lot-nam",
    "do-lot-nu",
    "trang-phuc-bau-hau-san",
    "thoi-trang-tre-em",
    "the-thao-da-ngoai",
)

# Thông tin chung khung thị trường VN — mọi bảng thêm title nhẹ và số hóa cột nhãn tiếng Việt.
_SIZE_GUIDE_VIETNAM_188_VI: str = (
    "Đối tượng khách hàng và nền thương mại VIỆT NAM — sàn 188.com.vn. "
    "Tiêu đề infographic rõ có chữ nhỏ hoặc dòng phụ «188.com.vn — tham khảo chọn size». "
    "Không watermark; không nhãn hãng/quảng cáo; không tiếng Trung/Trung Quốc; không emoji. "
    "Ưu tiên SIZE KIỂU SỐ: các cột bảng dùng số và đơn vị rõ — cm là trụ chính, mm nếu cần. "
    "Quần áo: có thể thêm cỡ chữ và số đo cm (vai, ngực, eo…). "
    "Riêng GIÀY DÉP: CHỈ dùng nhãn tiếng Việt cho cỡ giày (vd «Cỡ giày (shop VN)» / «Size in trên tem hàng») — "
    "TUYỆT ĐỐI KHÔNG in tiêu đề cột EU, US, UK, USA hay từ tương đương lên infographic. "
    "Mỗi bảng nên có 1 ô chú thích ngắn: «Khách Việt thường thân nhỏ hơn khổ Âu/US — "
    "nếu giữa hai cỡ, thử cỡ lớn hơn khi ôm tay/ôm vai» và «Số chỉ mang tính tham khảo — xem chi tiết từng sản phẩm và bảng NCC». "
)


SIZE_GUIDE_PROMPTS_VI: Dict[str, str] = {
    "giay-dep-nam": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Hướng dẫn chọn size giày dép NAM — chuẩn người Việt, 188.com.vn». "
        + "Viết toàn TIẾNG VIỆT. Nền trắng, flat vector/minh họa line art — chân và thước kẻ. "
        + "BẢNG CHỈ HAI CỘT LỚN: (1) «Chiều dài chân (cm)» nền vàng — vạch 0.5cm trong khoảng thực tế khách nam Việt "
        "(khoảng 23–31cm tuỳ thiết kế). (2) «Cỡ giày (thường in trên tem hàng / shop Việt Nam)» — chỉ các con số 36–46 "
        "kiểu số như khách hay thấy ở cửa hàng trong nước, căn hàng với cm. "
        + "NGHIÊM CẤM: chữ EU, US, UK, USA, European, British, American hoặc tiêu đề cột ngoại — kể cả chữ nhỏ trong bảng. "
        + "Một dòng chú thích viền nhỏ dưới bảng (chữ nhỏ, một câu): «Một số hàng nhập có tem lạ — luôn lấy cm chân làm chuẩn khi chọn trên 188.com.vn». "
        + "Hướng dẫn đo: gót đến ngón dài nhất; chiều tối; mang vớ như khi mang giày. "
        + "«Các hãng lệch nhau — đối chiếu mô tả từng sản phẩm»."
    ),
    "giay-dep-nu": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Hướng dẫn chọn size giày dép NỮ — chuẩn người Việt, 188.com.vn». Tiếng Việt hoàn toàn. "
        + "Minh họa chân và thước. Bảng HAI CỘT CHÍNH: «Chiều dài chân (cm)» (nền nhấn) khoảng 22–30cm bước 0.5cm; "
        + "«Cỡ giày (tem / shop Việt Nam)» — chỉ số cỡ trong nước hay gặp, khớp từng hàng cm. "
        + "TUYỆT ĐỐI không xuất hiện nhãn cột hay tiêu đề EU US UK USA và tiếng nước ngoài tương đương. "
        + "Một chú thích nhỏ: «Tem nhập có thể khác — căn vào cm chân». "
        + "«Giày mũi hẹp / form ôm có thể cần +0.5 cỡ». Đo lúc tối và mang đúng tất khi đo."
    ),
    "thoi-trang-nam": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Size quần áo NAM — bảng số Việt Nam / form châu Á» (không chỉ kiểu S–XL một màu nhạt — phải có bảng số). "
        + "Bảng chính: hàng các size dạng số và chữ xen kẽ phổ biến VN, ví dụ cột "
        "'Cỡ 38 39 40 41 42' hoặc tương đương + cột đối chiếu S/M/L/XL; "
        + "đồng thời các cột số đo (cm): vòng ngực, vai, eo, mông và dài tay áo hoặc ống quần (ghi rõ chỗ đo). "
        + "Chú thích form châu Á: tay áo/ngực ôm — nếu bụng/ngực dày có thể tăng 1 cỡ. "
        + "Chú thích một dòng: «Sản phẩm trên 188 có thể dùng bảng NCC khác nhau». "
        + "Line art người với các mũi tên chỉ vị trí đo."
    ),
    "thoi-trang-nu": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Size thời trang NỮ — số và quy đổi form VN». "
        + "Một ma trận rõ có dải cỡ kiểu số (đánh số 36–44 hoặc theo vai/cm ngực từng loại váy/đầm/phông) "
        + "và các cột S/M/L/XL kèm số đo chi tiết cm: ngực, eo, hông (và tay nếu cần). "
        + "Đoạn chú thích: eo thon so với mông — chọn cỡ căn vai và ngực trước; khách eo dày ưu tiên đo eo. "
        + "Tone lịch sự, không hình cực chi tiết không cần thiết. Phù hàng may sẵn trên TMĐT VN."
    ),
    "do-lot-nam": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Đồ lót nam — cỡ và số vòng eo/hông (cm)». "
        + "Trụ vào các con số: vòng eo, vòng mông và quy sang «Size M-L-XL hoặc 2XL» phổ thông các lô trong nước. "
        + "Chú thích không hình nhạy cảm chỉ schematic; minh họa quần lót chỉ silhouette trung tính. "
        + "Ghép bảng 2 chiều: hàng cỡ và cột chỉ khoảng cm ví dụ 70–100; phù vóc Việt. "
        + "Dòng thoái: «Chọn theo ôm vừa — không chọn căng eo»."
    ),
    "do-lot-nu": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Áo và đồ lót nữ — thước số và cup». "
        + "Giải thích và bảng số: cm vòng đo dưới ngực + bảng chữ/quy chiếu cup A–E (chuẩn dạng bảng mua hàng trong nước). "
        + "Đồ họa kín đáo, không ảnh người thật không cần thiết. "
        + "Chú thích: cỡ tay và cup lệch từng hãng — ưu tiên cm vòng dưới ngực vừa mức; đọc bảng size NCC từng sản phẩm khi có. "
        + "Đích hướng tới shopper nữ Việt trên 188.com.vn."
    ),
    "trang-phuc-bau-hau-san": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Đồ bầu và sau sinh — chọn cỡ và số vòng». "
        + "Ma trận kết hợp số và chữ: theo tuần thai / giai đoạn sau sinh (tháng) "
        + "kèm cột chiều cao và cột vòng bụng (cm)/vòng dưới ngực (cm), quy sang cỡ số và dáng áo vừa hoặc rộng ôm thoáng khi có. "
        + "Đề xuất «tăng 1 cỡ nếu thân hay bụng lớn hơn ô trong bảng», «ưu tiên co giãn». "
        + "Đồ họa silhouette bầu trung lập. Chú thích: tham khảo từng SP trên sàn Việt."
    ),
    "thoi-trang-tre-em": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Trẻ em — chọn size theo tuổi và các dải chiều cao Việt Nam». "
        + "Bảng chủ đạo số học: các cột «Tuổi (tháng/tuổi)», «Chiều cao (cm)», «Cân nặng (kg)», "
        + "và một cột cỡ kiểu số phổ thông Á (vd 110, 120… hoặc 2 4 6 8 10 12…) kèm cột ví dụ S/M khi có. "
        + "Đây là cách các shop và phụ huynh Việt hay đối chiếu. "
        + "Chú thích một dòng: «Trẻ tăng nhanh — ưu tiên nhìn cỡ chiều cao và cm». "
        + "Đồ họa chibi trung lập không gắn logo một thương hiệu cụ thể; nền sáng."
    ),
    "the-thao-da-ngoai": (
        _SIZE_GUIDE_VIETNAM_188_VI
        + "Tiêu đề: «Đồ thể thao và dã ngoại — cỡ và số cho người Việt». "
        + "Ít nhất hai cụm bảng: (1) áo hoặc áo khoác theo cỡ và vòng ngực (cm); "
        + "(2) găng / mũ / vớ nếu cần — cỡ tay hoặc chu vi đầu (cm). "
        + "Ghi nhóm vải co giãn — chọn tay không quá bó khi chỉ mang thường ngày, không ép thi đấu. "
        + "Đồ họa thể thao tối giản; dòng nhỏ dưới cùng: «Tham khảo mô tả từng sản phẩm và NCC — 188.com.vn»."
    ),
}


def gemini_generate_image_from_text(
    prompt: str,
    *,
    image_model: Optional[str] = None,
    image_size: Optional[str] = None,
    timeout_sec: Optional[int] = None,
) -> bytes:
    """
    Text → ảnh (Gemini native image). Cần GEMINI_API_KEY; model mặc định IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL.
    """
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if len(api_key) < 10:
        raise RuntimeError("Thiếu GEMINI_API_KEY.")
    dm = (
        (image_model or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_IMAGE_MODEL", "") or "gemini-3-pro-image-preview")
        .strip()
        or "gemini-3-pro-image-preview"
    )
    model = _sanitize_model_id(dm, "gemini-3-pro-image-preview")
    eff_size = _normalize_gemini_image_size(image_size or getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_DEFAULT_IMAGE_SIZE", "2K"))
    if eff_size is None:
        eff_size = "2K"
    tout = timeout_sec if timeout_sec is not None else max(60, int(getattr(settings, "IMAGE_LOCALIZATION_GEMINI_API_TIMEOUT_SEC", 300) or 300))

    gen_cfg: Dict[str, Any] = {
        "responseModalities": ["TEXT", "IMAGE"],
        "imageConfig": {"imageSize": eff_size},
    }
    payload: Dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt.strip()}]}],
        "generationConfig": gen_cfg,
    }
    url = f"{_GEMINI_BASE}/models/{model}:generateContent"
    res = requests.post(url, params={"key": api_key}, json=payload, timeout=tout)
    if res.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {res.status_code}: {(res.text or '')[:400]}")
    body = res.json()
    fb = body.get("promptFeedback") or {}
    br = fb.get("blockReason") or fb.get("block_reason")
    if br:
        raise RuntimeError(f"Gemini từ chối prompt: {br}")
    out = _extract_first_image_bytes_from_gemini_generate_response(body)
    if not out:
        raise RuntimeError("Gemini không trả ảnh (kiểm tra model sinh ảnh).")
    return out


def upload_size_guide_bytes_to_bunny(image_bytes: bytes, *, cat1_slug: str, ext: str = ".png") -> str:
    zone = settings.BUNNY_STORAGE_ZONE_NAME
    key = settings.BUNNY_STORAGE_ACCESS_KEY
    if not zone or not key:
        raise RuntimeError("Thiếu BUNNY_STORAGE_ZONE_NAME hoặc BUNNY_STORAGE_ACCESS_KEY.")
    e = ext if ext.startswith(".") else f".{ext}"
    if e.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        e = ".png"
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", cat1_slug).strip("-") or "cat1"
    digest = hashlib.sha1(image_bytes).hexdigest()[:12]
    remote_name = f"size-guide-{safe_slug}-{int(time.time())}-{digest}{e}"
    prefix = settings.BUNNY_UPLOAD_PATH_PREFIX.strip("/") or "site"
    remote_path = f"{prefix}/category-size-guides/{remote_name}"
    res = requests.put(
        f"https://storage.bunnycdn.com/{zone}/{remote_path}",
        headers={"AccessKey": key, "Content-Type": "application/octet-stream"},
        data=image_bytes,
        timeout=120,
    )
    if res.status_code not in (200, 201, 409):
        raise RuntimeError(f"Bunny upload {res.status_code}: {(res.text or '')[:200]}")
    return f"{settings.BUNNY_CDN_PUBLIC_BASE.rstrip('/')}/{remote_path}"


def build_prompt_for_cat1_slug(slug: str) -> str:
    s = slug.strip().lower()
    base = SIZE_GUIDE_PROMPTS_VI.get(s)
    if not base:
        base = (
            _SIZE_GUIDE_VIETNAM_188_VI
            + f"Hướng dẫn chọn size infographic cho danh mục slug «{s}» trên TMĐT 188.com.vn: "
            "bảng số + cm chủ đạo; tiếng Việt; nền trắng; line art không logo hãng và không watermark; không tiếng Trung."
        )
    suffix = (
        " Bố cục thích hợp mobile (đọc được chữ trong ảnh khi pinch zoom). "
        "Đồ họa flat hiện đại đủ tương phản; chữ in hoa chỉ chỗ tiêu đề; không dùng các ký tự Trung không cần thiết."
    )
    return base.strip() + suffix


def generate_and_upload_cat1_size_guide(
    slug: str,
    *,
    image_model: Optional[str] = None,
    image_size: Optional[str] = None,
) -> Tuple[str, bytes]:
    """Trả về (public_cdn_url, raw_bytes đã sinh)."""
    prompt = build_prompt_for_cat1_slug(slug)
    raw = gemini_generate_image_from_text(prompt, image_model=image_model, image_size=image_size)
    url = upload_size_guide_bytes_to_bunny(raw, cat1_slug=slug, ext=".png")
    return url, raw


def generate_default_cat1_slugs() -> List[str]:
    return list(DEFAULT_SIZE_GUIDE_CAT1_SLUGS)
