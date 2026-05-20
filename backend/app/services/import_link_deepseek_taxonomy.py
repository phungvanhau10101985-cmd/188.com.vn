"""
Gán danh mục cấp 1–3: đọc taxonomy từ bảng `categories`, gọi DeepSeek theo **chinese_name** (file import)
hoặc tên Việt. Chỉ ghi được bộ ba đã **có sẵn** trong taxonomy
(import taxonomy_import.xlsx) — không tạo nhánh mới trong DB và không chấp nhận chuỗi do model bịa ngoài danh sách.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.category import Category
from app.utils.slug import create_slug

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 90
_MAX_BLOCK_CHARS = 112_000
_MAX_CONTEXT_CHARS = 9000
_GEMINI_TIMEOUT_SEC = 55
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")
_NON_VI_SOURCE_RE = re.compile(r"[\u0400-\u052f\u1800-\u18af]")


def _norm_label(text: str) -> str:
    """Chuẩn hoá khoảng trắng; giữ nguyên chữ có dấu như trong DB."""
    return re.sub(r"\s+", " ", (text or "").strip())


def _cat1_is_gendered_male(cat1: str) -> bool:
    return (cat1 or "").strip().endswith(" Nam")


def _cat1_is_gendered_female(cat1: str) -> bool:
    return (cat1 or "").strip().endswith(" Nữ")


def infer_supplier_gender_hint(text: str) -> Optional[str]:
    """
    Suy luận giới tính từ mô tả/thông số NCC (Hibox tiếng Mông Cổ, v.v.).
    Trả 'female' | 'male' | None.
    """
    raw = text or ""
    if not raw.strip():
        return None

    # Trường chuẩn Hibox: «Холбогдох Хүйс» (Giới tính áp dụng)
    for pat in (
        r"Холбогдох\s+Хүйс\s*[:：]\s*([^\n\r]+)",
        r"Холбогдох\s+Хүйс\s+([^\n\r]+)",
    ):
        m = re.search(pat, raw, re.I)
        if m:
            val = m.group(1)
            if re.search(r"эмэгтэй", val, re.I):
                return "female"
            if re.search(r"эрэгтэй", val, re.I):
                return "male"

    f_score = 0
    m_score = 0
    if re.search(r"эмэгтэй", raw, re.I):
        f_score += 3
    if re.search(r"эрэгтэй", raw, re.I):
        m_score += 3
    if re.search(r"(女士|女款|女式)", raw):
        f_score += 2
    if re.search(r"(男士|男款|男式)", raw):
        m_score += 2
    if re.search(r"(?i)\b(women|woman|female|ladies|lady's)\b", raw):
        f_score += 1
    if re.search(r"(?i)\b(men|man's|male|gentleman)\b", raw):
        m_score += 1
    if re.search(r"(?i)(женск|женская|женские)", raw):
        f_score += 2
    if re.search(r"(?i)(мужск|мужская|мужские)", raw):
        m_score += 2
    if re.search(r"(?i)(giới tính\s*[:：]\s*nữ|dành cho nữ|phụ nữ\b)", raw):
        f_score += 2
    if re.search(r"(?i)(giới tính\s*[:：]\s*nam|dành cho nam)(\s|,|$)", raw):
        m_score += 2

    if f_score > m_score:
        return "female"
    if m_score > f_score:
        return "male"
    return None


def filter_triples_by_gender_hint(
    triples: List[Dict[str, str]],
    hint: Optional[str],
) -> Tuple[List[Dict[str, str]], bool]:
    """
    Giữ nhánh cat1 phù hợp giới (suffix « Nam » / « Nữ »). Cat1 trung tính giữ nguyên.
    Trả (danh sách, đã_fallback): nếu lọc rỗng → trả triples gốc và báo fallback.
    """
    if not hint or not triples:
        return triples, False
    out: List[Dict[str, str]] = []
    for t in triples:
        c1 = t.get("cat1") or ""
        if hint == "female":
            if _cat1_is_gendered_male(c1):
                continue
        elif hint == "male":
            if _cat1_is_gendered_female(c1):
                continue
        out.append(t)
    if not out:
        return triples, True
    return out, False


def _violates_gender_hint(hint: Optional[str], cat1: str) -> bool:
    if not hint:
        return False
    if hint == "female" and _cat1_is_gendered_male(cat1):
        return True
    if hint == "male" and _cat1_is_gendered_female(cat1):
        return True
    return False


def _nonempty_product_field(product_data: Dict[str, Any], key: str) -> str:
    s = (product_data.get(key) or "").strip()
    if s.lower() in ("nan", "none", "null"):
        return ""
    return s


def resolve_taxonomy_source_title(product_data: Dict[str, Any]) -> str:
    """
    Tiêu đề ưu tiên cho phân loại taxonomy: cột chinese_name (file import / DB),
    sau đó mới tên tiếng Việt.
    """
    cn = _nonempty_product_field(product_data, "chinese_name")
    if cn:
        return cn
    return _nonempty_product_field(product_data, "name")


def build_taxonomy_context_blob(product_data: Dict[str, Any]) -> str:
    """Gom mô tả + excerpt thông số NCC để đưa vào prompt (không chỉ dựa vào title)."""
    parts: List[str] = []
    cn = _nonempty_product_field(product_data, "chinese_name")
    vi = _nonempty_product_field(product_data, "name")
    if cn:
        parts.append(f"Tên tiếng Trung (nguồn phân loại — cột chinese_name / import): {cn}")
    if vi and vi != cn:
        parts.append(f"Tên tiếng Việt (tham khảo): {vi}")
    d = (product_data.get("description") or "").strip()
    if d:
        parts.append(d)
    for key in (
        "category",
        "subcategory",
        "sub_subcategory",
        "raw_category",
        "raw_subcategory",
        "raw_sub_subcategory",
        "material",
        "style",
        "color",
        "occasion",
        "features",
        "weight",
    ):
        val = product_data.get(key)
        if val is None:
            continue
        text = json.dumps(val, ensure_ascii=False) if isinstance(val, (list, dict)) else str(val)
        text = _scrub_placeholder_str(text)
        if text:
            parts.append(f"{key}: {text}")
    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        spec = pi.get("specifications")
        if isinstance(spec, dict):
            ex = (spec.get("supplier_specs_excerpt") or spec.get("hibox_specs_excerpt") or "").strip()
            if ex and ex not in d:
                parts.append(ex)
        for key in ("product_info", "variants", "market_info"):
            obj = pi.get(key)
            if isinstance(obj, (dict, list)) and obj:
                parts.append(f"product_info.{key}: {json.dumps(obj, ensure_ascii=False)[:3000]}")
    blob = "\n\n".join(parts).strip()
    return blob[:_MAX_CONTEXT_CHARS]


def _gender_root_slug(cat1: str) -> str:
    """Chuỗi slug gốc của cat1 có hậu tố Nam/Nữ (vd Giày dép Nam → giay-dep)."""
    s = (cat1 or "").strip()
    for suf in (" Nam", " Nữ"):
        if s.endswith(suf):
            return create_slug(_norm_label(s[: -len(suf)].strip()))
    return ""


def taxonomy_has_ambiguous_gender_cat1(triples: List[Dict[str, str]]) -> bool:
    """
    True nếu taxonomy có **cùng một loại** cat1 (ví dụ Giày dép) với cả bản Nam và Nữ —
    khi có hint giới tính thì lọc trước, nếu không DeepSeek tự chọn từ toàn bộ taxonomy.
    """
    roots: Dict[str, set] = defaultdict(set)
    for t in triples:
        c1 = t.get("cat1") or ""
        root = _gender_root_slug(c1)
        if not root:
            continue
        if _cat1_is_gendered_male(c1):
            roots[root].add("male")
        elif _cat1_is_gendered_female(c1):
            roots[root].add("female")
    return any(len(v) >= 2 for v in roots.values())


def pick_product_hero_image_url(product_data: Dict[str, Any]) -> str:
    u = (product_data.get("main_image") or "").strip()
    if u:
        return u
    imgs = product_data.get("images") or []
    if isinstance(imgs, list):
        for it in imgs:
            s = str(it).strip()
            if s:
                return s
    return ""


def record_import_taxonomy_error(product_data: Dict[str, Any], message: str) -> None:
    """Ghi lỗi phân loại taxonomy — admin đọc draft + warnings."""
    product_data["taxonomy_import_error"] = message
    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        meta = pi.setdefault("import_taxonomy_meta", {})
        if isinstance(meta, dict):
            meta["status"] = "taxonomy_gender_required_failed"
            meta["error"] = message


def _scrub_cjk(text: str) -> str:
    """Loại ký tự CJK khỏi chuỗi đầu ra (không được có trong JSON theo quy tắc)."""
    s = (text or "").strip()
    if not s:
        return ""
    return _CJK_RE.sub(" ", s).strip()


def _looks_untranslated_non_vi(text: str, source_name: str = "") -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _NON_VI_SOURCE_RE.search(t):
        return True
    src = (source_name or "").strip()
    return bool(src and t.casefold() == src.casefold() and _NON_VI_SOURCE_RE.search(src))


def _scrub_placeholder_str(text: str) -> str:
    """Loại placeholder kiểu pandas/Excel ('nan', 'none'…) khỏi chuỗi hiển thị web."""
    t = (text or "").strip()
    if not t:
        return ""
    low = t.lower()
    if low in ("nan", "none", "null", "undefined", "n/a"):
        return ""
    return t


def _clip_vi_field(raw: str, max_len: int) -> str:
    v = _scrub_cjk(str(raw or "")).strip()
    if len(v) > max_len:
        v = v[:max_len].strip()
    return v


# Quy tắc nghiệp vụ phân loại (khớp hướng dẫn taxonomy / Sheet — chỉ chọn bộ có trong bảng DB).
_TAXONOMY_CLASSIFICATION_RULES_VI = """
QUY TẮC PHÂN LOẠI (bắt buộc — áp dụng khi đọc TÊN sản phẩm, có thể có tiếng Trung):

ĐẦU RA JSON:
- Đúng 14 key: cat1, cat2, cat3, khach_hang, ten_tieng_viet, chat_lieu_vi, mo_ta_vi,
  thuong_hieu_vi, xuat_xu_vi, phong_cach_vi, dip_vi, trong_luong_vi, chieu_cao_got_vi, thong_so_kich_thuoc_vi.
- cat1/cat2/cat3: SAO CHÉP NGUYÊN VĂN một bộ hợp lệ từ BẢNG DANH MỤC (cat3 phải thuộc đúng dòng cat2 dưới đúng ## cat1).
- TUYỆT ĐỐI KHÔNG dùng ký tự tiếng Trung (hay Nhật/Hàn) trong BẤT KỲ giá trị JSON nào.
- khach_hang: tiếng Việt ngắn — gợi ý đối tượng (tuổi, giới, phong cách/nghề). Ví dụ: «Phù hợp Nữ 18–25 tuổi, sinh viên, phong cách trẻ trung.»
- ten_tieng_viet: tên sản phẩm tiếng Việt tự nhiên (≤220 ký tự), đúng loại hàng từ TÊN và NGỮ CẢNH.
  • **KHÔNG** ghi danh sách màu hay cụm «màu …» ở cuối (hệ thống tự ghép tên màu biến thể sau).
  • **KHÔNG** liệt kê đầy đủ các cỡ đặt hàng (S/M/L…) trong tên — chỉ thêm **số đo kích thước sản phẩm / form** khi NGỮ CẢNH có **một** con số hoặc cụm ngắn (vd. chiều dài tay áo cm, vòng eo áo).
  • **Giày dép / sandal / boot / cao gót**: nếu thông số có **chiều cao gót hoặc đế** (cm, hoặc inch → quy đổi gọn sang cm), ghép tự nhiên vào tên (vd. «gót 9 cm», «đế cao 3 cm», «đế bệt»); **không** bịa số.
  • **Túi xách / ví / ba lô / clutch**: nếu có **kích thước** (dài × rộng × cao, hoặc một cạnh cm), ghép gọn (vd. «25×18×10 cm», «khổ ~25 cm»); **không** bịa.
  • **Hàng khác** (vali, balô laptop…): nếu có kích thước/dung tích trong NGỮ CẢNH, có thể thêm cụm ngắn tương ứng.
- chat_lieu_vi: **chất liệu** tiếng Việt ngắn gọn (tối đa ~100 ký tự), chỉ điền khi suy ra được từ TÊN hoặc NGỮ CẢNH (vd. cotton, polyester, da PU, lụa…); có nhãn tiếng Anh «Material» trong thông số thì dịch/ghi lại bằng tiếng Việt; **không** đoán bừa — không có thông tin thì để chuỗi rỗng "".
- mo_ta_vi: **mô tả sản phẩm** tiếng Việt để đăng bán (plain text), khoảng 350–1200 ký tự, 2–5 đoạn (xuống dòng \\n giữa đoạn); dựa trên TÊN + NGỮ CẢNH: đặc điểm nổi bật, phom/form (nếu rõ), phù hợp ai/mùa (nếu suy ra được), chất liệu đã biết; có thể nhắc lại ngắn kích thước/gót nếu hữu ích nhưng **không** copy nguyên khối dài những gì đã gói trong ten_tieng_viet; **không** spam từ khóa, **không** liệt kê đầy đủ mọi màu/size đặt hàng (đã có biến thể); không HTML; không nhét JSON/markdown trong chuỗi.
- thuong_hieu_vi: thương hiệu / nhà cung (tiếng Việt hoặc phiên âm ngắn) nếu NGỮ CẢNH có; không có thì "".
- xuat_xu_vi: xuất xứ / nơi sản xuất tiếng Việt (vd «Trung Quốc», «Việt Nam») nếu suy ra được; không bịa — không có thì "".
- phong_cach_vi: kiểu dáng / phong cách tiếng Việt ngắn (vd «công sở», «casual», «cổ điển») khi có trong NGỮ CẢNH; không có thì "".
- dip_vi: dịp sử dụng tiếng Việt ngắn (vd «đi làm», «dự tiệc», «hằng ngày») khi có; không có thì "".
- trong_luong_vi: gợi ý trọng lượng tiếng Việt (vd «Khoảng 500 g», «~1,2 kg») chỉ khi NGỮ CẢNH có số — không bịa; không có thì "".
- chieu_cao_got_vi: chiều cao gót hoặc đế (tiếng Việt, vd «Gót khoảng 6 cm», «Đế bệt») chỉ khi NGỮ CẢNH có — không bịa; không có thì "" (đã có số trong tên thì có thể lặp ngắn cho đồng bộ tab thông tin).
- thong_so_kich_thuoc_vi: **tóm tắt thông số kích thước & form** tiếng Việt để đăng tab «Thông số» (tối đa ~900 ký tự), chỉ từ NGỮ CẢNH — **không** bịa.
  • Giày dép / sandal: nhóm gót (vd siêu cao >8 cm), form mũi, độ mở miệng / cổ giày, đế platform nếu có số, chiều cao cổ trước–sau nếu có.
  • Túi / vali / ví: kích thước dài×rộng×cao hoặc một số đo chính (cm).
  • Quần áo: số đo form quan trọng trong NGỮ CẢNH (vd chiều dài tay, eo…).
  Viết gọn 3–8 ý, có thể xuống dòng \\n giữa các ý; không liệt kê đủ size đặt hàng (đã ở biến thể).
- KHÔNG nhắc sản phẩm khác, KHÔNG gợi ý phối đồ/kết hợp hàng khác trong khach_hang.

RÀNG BUỘC DANH MỤC:
- CẤM tạo tên danh mục mới; CẤM ghi cat1/cat2/cat3 không trùng một dòng trong BẢNG (taxonomy đã import DB).
- Hệ thống chỉ ghi sản phẩm khi bộ ba trùng đúng một nhánh có sẵn — nếu model trả chuỗi lạ → bỏ qua, không tự thêm danh mục vào DB.
- Không tự bịa cat2/cat3 không có trong bảng.
- cat1 phải trùng chính xác một dòng ## cấp 1 trong bảng.

QUY TẮC cat1 (chọn đúng nhánh — khớp tên trong bảng):
- Giày, dép, sandal, boot… → chỉ «Giày dép Nam» HOẶC «Giày dép Nữ» (không xếp giày dép vào «Thời trang»).
- Quần áo, váy, trang phục mặc người → «Thời trang Nam» hoặc «Thời trang Nữ».
- Túi xách, ví, ba lô (đeo mang đồ) → «Túi xách Nam» hoặc «Túi xách Nữ» — KHÔNG dùng «Phụ kiện Nam/Nữ», KHÔNG dùng «Thời trang».
- Trang sức: dây chuyền, vòng cổ, lắc/vòng tay, nhẫn, khuyên tai/bông tai, charm, lắc chân → «Trang sức thời trang» — KHÔNG xếp vào «Phụ kiện Nữ».
- Đồng hồ → «Đồng hồ». Vali, túi du lịch lớn → «Vali túi du lịch».
- Phụ kiện điện thoại & công nghệ: ốp lưng, kính cường lực, cáp, tai nghe, túi laptop, đèn livestream… → «Phụ kiện điện thoại & công nghệ».
- Mỹ phẩm/làm đẹp: son, kem nền, serum, chống nắng, cọ makeup… → «Mỹ phẩm & làm đẹp».
- Đồ gia dụng/nhà bếp/phòng tắm/lưu trữ/gia dụng điện nhỏ → «Đồ gia dụng».
- Đồ chơi/mẹ bé → «Đồ chơi & mẹ bé». Thực phẩm/đồ uống → «Thực phẩm & đồ uống». TPCN → «Thực phẩm chức năng».
- Văn phòng phẩm/sách → «Văn phòng phẩm & sách». Thể thao/dã ngoại → «Thể thao & dã ngoại».
- Phụ kiện xe → «Phụ kiện xe máy & ô tô». Thú cưng → «Thú cưng». Nội thất/trang trí nhà → «Nội thất & trang trí nhà».
- «Phụ kiện Nam/Nữ»: mũ, thắt lưng, khăn, tất, kính (thời trang), cà vạt, phụ kiện tóc, ô… — không dùng nhánh này cho hàng công nghệ/mỹ phẩm/giày/túi đã nêu trên.

SANDAL NỮ — PHÂN NHÁNH cat3 (nếu bảng có các cat3 tương ứng):
- Gót/đế cao từ 7cm trở lên (có số đo trong tên hoặc mô tả rõ) → coi là sandal cao gót: cat3 phải là một trong các chuỗi kiểu «giày sandal cao gót nữ quai ngang» / «giày sandal cao gót nữ đính đá» / «giày sandal cao gót nữ hở mũi» **đúng với cat2** trong bảng (chỉ chọn nếu dòng đó tồn tại).
- Gót thấp hơn 7cm → nhánh dép sandal nữ / cat3 theo bảng (không ép vào sandal cao gót).

KIỂM TRA CUỐI:
- JSON đủ 14 key; không markdown bọc ngoài (trừ \\n trong mo_ta_vi / thong_so_kich_thuoc_vi).
- Mọi giá trị string không chứa chữ Trung/Nhật/Hàn.
- Bộ cat1–cat3 là một dòng hợp lệ trong bảng.
"""


def _norm_triple_key(cat1: str, cat2: str, cat3: str) -> str:
    return "|".join(
        [
            create_slug(_norm_label(cat1)),
            create_slug(_norm_label(cat2)),
            create_slug(_norm_label(cat3)),
        ]
    )


def load_active_category_triples(db: Session) -> List[Dict[str, str]]:
    rows = db.query(Category).filter(Category.is_active.is_(True)).all()
    by_id = {r.id: r for r in rows}
    out: List[Dict[str, str]] = []
    for c3 in rows:
        if (c3.level or 0) != 3:
            continue
        c2 = by_id.get(c3.parent_id) if c3.parent_id else None
        if not c2 or (c2.level or 0) != 2:
            continue
        c1 = by_id.get(c2.parent_id) if c2.parent_id else None
        if not c1 or (c1.level or 0) != 1:
            continue
        n1, n2, n3 = (c1.name or "").strip(), (c2.name or "").strip(), (c3.name or "").strip()
        if not (n1 and n2 and n3):
            continue
        out.append(
            {
                "cat1": n1,
                "cat2": n2,
                "cat3": n3,
                "full_slug": (c3.full_slug or "").strip(),
            }
        )
    return out


def _build_taxonomy_prompt_block(triples: List[Dict[str, str]]) -> Tuple[str, bool]:
    grouped: Dict[str, Dict[str, List[str]]] = defaultdict(lambda: defaultdict(list))
    for t in triples:
        grouped[t["cat1"]][t["cat2"]].append(t["cat3"])
    lines: List[str] = []
    for c1 in sorted(grouped.keys()):
        lines.append(f"## {c1}")
        for c2 in sorted(grouped[c1].keys()):
            for c3 in sorted(set(grouped[c1][c2])):
                lines.append(f"- {c2} > {c3}")
        lines.append("")
    block = "\n".join(lines).strip()
    truncated = False
    if len(block) > _MAX_BLOCK_CHARS:
        block = block[:_MAX_BLOCK_CHARS].rsplit("\n", 1)[0]
        truncated = True
    return block, truncated


def _build_snap_index(triples: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
    idx: Dict[str, Dict[str, str]] = {}
    for t in triples:
        k = _norm_triple_key(t["cat1"], t["cat2"], t["cat3"])
        idx[k] = t
    return idx


def _extract_json_object(content: str) -> Dict[str, Any]:
    t = (content or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```\w*\s*", "", t)
        t = re.sub(r"\s*```\s*$", "", t)
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", t)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, dict):
        raise ValueError("Không phải JSON object")
    return data


def _resolve_triple_only_from_taxonomy(
    cat1: str,
    cat2: str,
    cat3: str,
    triples: List[Dict[str, str]],
    snap_index: Dict[str, Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """
    Chỉ trả về bộ đã có trong `triples` (taxonomy DB). Không suy diễn nhánh mới.
    1) Khớp tên sau chuẩn hoá khoảng trắng (đúng chữ như DB).
    2) Khớp bộ slug đầy đủ cat1|cat2|cat3 (chống lệch khoảng trắng nhẹ).
    Không khớp chỉ theo cat3 — tránh gán nhầm nhánh.
    """
    n1, n2, n3 = _norm_label(cat1), _norm_label(cat2), _norm_label(cat3)
    if not (n1 and n2 and n3):
        return None
    for t in triples:
        if (
            _norm_label(t["cat1"]) == n1
            and _norm_label(t["cat2"]) == n2
            and _norm_label(t["cat3"]) == n3
        ):
            return t
    k = _norm_triple_key(n1, n2, n3)
    return snap_index.get(k)


_TRANSLATE_ONLY_SYSTEM_VI = """Bạn dịch / viết lại tin đăng sản phẩm thương mại điện tử sang tiếng Việt tự nhiên.
Đầu ra: DUY NHẤT một JSON (không markdown), không ký tự tiếng Trung/Nhật/Hàn trong giá trị string.
"""


def translate_product_listing_deepseek_only(
    product_name: str,
    supplier_description: str,
    *,
    context_text: str = "",
    description_only: bool = False,
) -> Tuple[str, str, List[str]]:
    """
    Gọi DeepSeek chỉ để có tên + mô tả tiếng Việt (không phân loại taxonomy).
    Dùng khi đã có danh mục sẵn, hoặc taxonomy lỗi / thiếu giới nhưng vẫn cần cột name + description Việt.
    """
    warnings: List[str] = []
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    if not key:
        warnings.append("deepseek_listing_translate: thiếu DEEPSEEK_API_KEY.")
        return "", "", warnings
    if not settings.IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED:
        return "", "", warnings

    name = (product_name or "").strip()
    desc = (supplier_description or "").strip()
    blob = (context_text or "").strip()[:_MAX_CONTEXT_CHARS]
    if not name and not desc and not blob:
        warnings.append("deepseek_listing_translate: không có tên hay mô tả để dịch.")
        return "", "", warnings

    if description_only:
        user_prompt = (
            "NHIỆM VỤ: Chỉ viết MO_TA_VI (không đổi tên).\n"
            "- Trả JSON đúng 2 key: ten_tieng_viet và mo_ta_vi.\n"
            '- ten_tieng_viet: luôn chuỗi rỗng "".\n'
            "- mo_ta_vi: mô tả đăng bán tiếng Việt 350–1200 ký tự, 2–5 đoạn, \\n giữa đoạn; không HTML;\n"
            "  không spam từ khóa; dựa trên TÊN + MÔ TẢ / NGỮ CẢNH bên dưới.\n\n"
            f"TÊN SẢN PHẨM (đã có bản Việt ở hệ thống — không trả trong JSON):\n{name}\n\n"
            f"MÔ TẢ / THÔNG SỐ NGUỒN:\n{(desc + chr(10) + blob).strip()}\n\n"
            'Trả về: {"ten_tieng_viet":"","mo_ta_vi":"..."}'
        )
    else:
        user_prompt = (
            "NHIỆM VỤ: Tên và mô tả tiếng Việt cho đăng bán.\n"
            '- ten_tieng_viet: tên SP tiếng Việt tự nhiên ≤220 ký tự (không liệt kê hết size/màu ở cuối).\n'
            "- mo_ta_vi: plain text tiếng Việt 350–1200 ký tự, 2–5 đoạn, \\n giữa đoạn; không HTML.\n"
            "- KHÔNG để tiếng Trung/Nhật/Hàn trong JSON.\n\n"
            "NGỮ CẢNH (có thể tiếng nước ngoài):\n"
            f"{blob}\n\n"
            f"TÊN NGUỒN:\n{name}\n\n"
            f"MÔ TẢ NGUỒN:\n{desc}\n\n"
            'Trả về JSON: {"ten_tieng_viet":"...","mo_ta_vi":"..."}'
        )

    url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-chat"

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": _TRANSLATE_ONLY_SYSTEM_VI.strip()},
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": 4096,
            },
            timeout=_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        warnings.append(f"deepseek_listing_translate: lỗi mạng: {exc}")
        return "", "", warnings

    if not resp.ok:
        warnings.append(f"deepseek_listing_translate: HTTP {resp.status_code} {resp.text[:400]}")
        return "", "", warnings

    try:
        body = resp.json()
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_object(content)
    except (json.JSONDecodeError, TypeError, ValueError, IndexError, KeyError) as exc:
        warnings.append(f"deepseek_listing_translate: không đọc JSON: {exc}")
        return "", "", warnings

    tv = _scrub_cjk(str(parsed.get("ten_tieng_viet") or "")).strip()
    if len(tv) > 220:
        tv = tv[:220].strip()
    mt_raw = str(parsed.get("mo_ta_vi") or "").strip()
    mt_vi = _scrub_cjk(mt_raw).strip()
    mt_vi = re.sub(r"[ \t]+\n", "\n", mt_vi)
    mt_vi = re.sub(r"\n{3,}", "\n\n", mt_vi).strip()
    if len(mt_vi) > 12000:
        mt_vi = mt_vi[:12000].strip()

    if description_only:
        tv = ""
    if not tv and not description_only and name:
        tv = _scrub_cjk(name).strip()[:220] or name[:220].strip()
    if description_only and not mt_vi:
        warnings.append("deepseek_listing_translate: mo_ta_vi rỗng sau description_only.")

    return tv, mt_vi, warnings


def _gemini_generate_json(prompt: str, *, max_tokens: int, warnings: List[str], label: str) -> Optional[Dict[str, Any]]:
    if not getattr(settings, "IMPORT_LINK_GEMINI_TAXONOMY_FALLBACK_ENABLED", True):
        return None
    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key or len(api_key) < 10:
        warnings.append(f"{label}: thiếu GEMINI_API_KEY.")
        return None
    model = (getattr(settings, "GEMINI_MODEL", "") or "gemini-2.5-flash").strip()
    url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.15},
    }
    try:
        resp = requests.post(url, json=payload, timeout=_GEMINI_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            block = data.get("promptFeedback") or data.get("error") or {}
            warnings.append(f"{label}: Gemini không có candidates — {str(block)[:400]}")
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        content = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict)).strip()
        return _extract_json_object(content)
    except requests.RequestException as exc:
        warnings.append(f"{label}: lỗi gọi Gemini: {exc}")
    except Exception as exc:
        warnings.append(f"{label}: không đọc JSON từ Gemini — {exc}")
    return None


def translate_product_listing_gemini_only(
    product_name: str,
    supplier_description: str,
    *,
    context_text: str = "",
    description_only: bool = False,
) -> Tuple[str, str, List[str]]:
    """
    Fallback Gemini 2.5 Flash để có tên/mô tả tiếng Việt khi DeepSeek rỗng hoặc giữ nguyên tên ngoại ngữ.
    """
    warnings: List[str] = []
    name = (product_name or "").strip()
    desc = (supplier_description or "").strip()
    blob = (context_text or "").strip()[:_MAX_CONTEXT_CHARS]
    if not name and not desc and not blob:
        return "", "", warnings

    if description_only:
        prompt = (
            "Bạn viết mô tả sản phẩm TMĐT bằng tiếng Việt.\n"
            "Chỉ trả JSON thuần đúng 2 key: ten_tieng_viet và mo_ta_vi.\n"
            'ten_tieng_viet luôn là "".\n'
            "mo_ta_vi: plain text tiếng Việt 350-1200 ký tự, 2-5 đoạn, không HTML, không markdown.\n\n"
            f"TÊN SẢN PHẨM:\n{name}\n\n"
            f"MÔ TẢ / NGỮ CẢNH NGUỒN:\n{(desc + chr(10) + blob).strip()}\n\n"
            'Trả về: {"ten_tieng_viet":"","mo_ta_vi":"..."}'
        )
    else:
        prompt = (
            "Bạn dịch/viết lại tin đăng sản phẩm TMĐT sang tiếng Việt tự nhiên.\n"
            "Nguồn có thể là tiếng Mông Cổ, Trung, Nga, Anh hoặc ngôn ngữ khác.\n"
            "Chỉ trả JSON thuần đúng 2 key: ten_tieng_viet và mo_ta_vi.\n"
            "ten_tieng_viet: tên sản phẩm tiếng Việt tự nhiên <=220 ký tự, không giữ nguyên chữ Cyrillic/Mông Cổ.\n"
            "mo_ta_vi: plain text tiếng Việt 350-1200 ký tự, 2-5 đoạn, không HTML, không markdown.\n\n"
            f"NGỮ CẢNH:\n{blob}\n\n"
            f"TÊN NGUỒN:\n{name}\n\n"
            f"MÔ TẢ NGUỒN:\n{desc}\n\n"
            'Trả về JSON: {"ten_tieng_viet":"...","mo_ta_vi":"..."}'
        )

    parsed = _gemini_generate_json(prompt, max_tokens=4096, warnings=warnings, label="gemini_listing_translate")
    if not parsed:
        return "", "", warnings

    tv = _scrub_cjk(str(parsed.get("ten_tieng_viet") or "")).strip()
    if description_only:
        tv = ""
    if len(tv) > 220:
        tv = tv[:220].strip()
    if not description_only and _looks_untranslated_non_vi(tv, name):
        warnings.append("gemini_listing_translate: ten_tieng_viet rỗng hoặc còn chữ ngoại ngữ — bỏ qua tên.")
        tv = ""

    mt_vi = _scrub_cjk(str(parsed.get("mo_ta_vi") or "")).strip()
    mt_vi = re.sub(r"[ \t]+\n", "\n", mt_vi)
    mt_vi = re.sub(r"\n{3,}", "\n\n", mt_vi).strip()
    if len(mt_vi) > 12000:
        mt_vi = mt_vi[:12000].strip()
    return tv, mt_vi, warnings


def classify_product_taxonomy_deepseek(
    db: Session,
    product_name: str,
    *,
    context_text: str = "",
    supplier_gender_hint: Optional[str] = None,
) -> Tuple[Optional[Dict[str, str]], List[str]]:
    """
    Trả (dict canonical hoặc None, warnings).
    Dict gồm cat1, cat2, cat3, full_slug; có thể thêm khach_hang, ten_tieng_viet, chat_lieu_vi, mo_ta_vi,
    thuong_hieu_vi, xuat_xu_vi, phong_cach_vi, dip_vi, trong_luong_vi, chieu_cao_got_vi, thong_so_kich_thuoc_vi (tiếng Việt, không CJK).

    context_text: mô tả + thông số (vd Hibox) — để đọc giới tính «Холбогдох Хүйс» / Эмэгтэй, không chỉ title.
    supplier_gender_hint: nếu apply đã suy ra từ text/thông số, truyền vào để không đọc lại sai thứ tự.
        None = suy từ text trong classify như cũ.
    """
    warnings: List[str] = []
    key = (settings.DEEPSEEK_API_KEY or "").strip()
    if not key:
        warnings.append("deepseek_taxonomy: thiếu DEEPSEEK_API_KEY — bỏ qua phân loại.")
        return None, warnings
    if not settings.IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED:
        return None, warnings

    name = (product_name or "").strip()
    if not name:
        warnings.append("deepseek_taxonomy: tên sản phẩm trống.")
        return None, warnings

    blob_ctx = (context_text or "").strip()[:_MAX_CONTEXT_CHARS]
    gender_hint_eff = supplier_gender_hint
    if gender_hint_eff is None:
        gender_hint_eff = infer_supplier_gender_hint(f"{name}\n{blob_ctx}")

    triples = load_active_category_triples(db)
    if not triples:
        warnings.append(
            "deepseek_taxonomy: chưa có nhánh cat3 active trong bảng categories — import taxonomy_import.xlsx trước."
        )
        return None, warnings

    triples_use, fb = filter_triples_by_gender_hint(triples, gender_hint_eff)
    if fb:
        warnings.append(
            "deepseek_taxonomy: gợi ý giới tính từ NCC không khớp nhánh cat1 Nam/Nữ trong taxonomy — phân loại không lọc giới."
        )
    elif gender_hint_eff in ("female", "male"):
        logger.info("deepseek_taxonomy: supplier gender hint=%s → đã lọc nhánh cat1.", gender_hint_eff)

    block, truncated = _build_taxonomy_prompt_block(triples_use)
    if truncated:
        warnings.append(
            "deepseek_taxonomy: bảng danh mục quá dài — đã cắt bớt phần cuối trong prompt (có thể sai lệch)."
        )

    snap_index = _build_snap_index(triples_use)

    gender_lines = ""
    if gender_hint_eff == "female":
        gender_lines = (
            "\nRÀNG BUỘC GIỚI (ưu tiên thông số NCC): Sản phẩm dành cho **NỮ**. "
            "Trong bảng chỉ được chọn cat1 là nhánh **Nữ** (vd «Giày dép Nữ», «Thời trang Nữ», … có trong bảng). "
            "TUYỆT ĐỐI không chọn cat1 kết thúc bằng « Nam ».\n"
        )
    elif gender_hint_eff == "male":
        gender_lines = (
            "\nRÀNG BUỘC GIỚI (ưu tiên thông số NCC): Sản phẩm dành cho **NAM**. "
            "Chỉ được chọn cat1 nhánh **Nam** có trong bảng; không chọn cat1 kết thúc « Nữ ».\n"
        )

    system = (
        "Bạn là chuyên gia phân loại sản phẩm thương mại điện tử Việt Nam.\n\n"
        + _TAXONOMY_CLASSIFICATION_RULES_VI.strip()
        + "\n\n---\n"
        "Nhiệm vụ: đọc BẢNG DANH MỤC, **TÊN** (thường là tiếng Trung từ NCC) và **NGỮ CẢNH THÔNG SỐ/MÔ TẢ**; "
        "ưu tiên trường giới tính do NCC ghi (vd хүйс / Эмэгтэй = nữ; Эрэгтэй = nam). "
        "Chọn đúng một bộ cat1/cat2/cat3 **sao chép nguyên văn từ bảng**, điền đủ các trường tiếng Việt trong JSON (khách hàng, tên, chất liệu, mô tả, thương hiệu, xuất xứ, phong cách, dịp, trọng lượng, gót/đế…).\n"
        "Không dùng markdown; không giải thích ngoài JSON."
    )

    ctx_block = ""
    if blob_ctx:
        ctx_block = (
            "NGỮ CẢNH MÔ TẢ / THÔNG SỐ (đọc kỹ để biết giới tính & loại hàng):\n"
            f"{blob_ctx}\n\n"
        )

    user = (
        f"BẢNG DANH MỤC (mỗi ## là cat1; dòng «cat2 > cat3» là một nhánh hợp lệ):\n\n{block}\n\n"
        f"{gender_lines}"
        f"{ctx_block}"
        f"TÊN SẢN PHẨM (ưu tiên tiếng Trung / tên NCC gốc):\n{name}\n\n"
        "QUAN TRỌNG: cat1, cat2, cat3 phải là ba chuỗi xuất hiện nguyên văn trong bảng trên — không được phép là danh mục ngoài bảng.\n"
        'Trả về DUY NHẤT một JSON đủ 14 key (mo_ta_vi / thong_so_kich_thuoc_vi có thể dùng \\n giữa các ý):\n'
        '{"cat1":"...","cat2":"...","cat3":"...","khach_hang":"...","ten_tieng_viet":"...","chat_lieu_vi":"","mo_ta_vi":"...",'
        '"thuong_hieu_vi":"","xuat_xu_vi":"","phong_cach_vi":"","dip_vi":"","trong_luong_vi":"","chieu_cao_got_vi":"",'
        '"thong_so_kich_thuoc_vi":""}'
    )

    url = (settings.DEEPSEEK_API_URL or "").strip() or "https://api.deepseek.com/v1/chat/completions"
    model = (settings.DEEPSEEK_MODEL or "").strip() or "deepseek-chat"

    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.15,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 4096,
            },
            timeout=_TIMEOUT_SEC,
        )
    except requests.RequestException as exc:
        warnings.append(f"deepseek_taxonomy: lỗi mạng DeepSeek: {exc}")
        return None, warnings

    if not resp.ok:
        warnings.append(f"deepseek_taxonomy: HTTP {resp.status_code} {resp.text[:400]}")
        return None, warnings

    try:
        body = resp.json()
        content = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        parsed = _extract_json_object(content)
    except (json.JSONDecodeError, TypeError, ValueError, IndexError, KeyError) as exc:
        warnings.append(f"deepseek_taxonomy: không đọc được JSON từ model: {exc}")
        return None, warnings

    c1 = str(parsed.get("cat1") or "").strip()
    c2 = str(parsed.get("cat2") or "").strip()
    c3 = str(parsed.get("cat3") or "").strip()
    if not (c1 and c2 and c3):
        warnings.append("deepseek_taxonomy: model trả thiếu cat1/cat2/cat3.")
        return None, warnings
    if _CJK_RE.search(c1 + c2 + c3):
        warnings.append("deepseek_taxonomy: cat1–cat3 chứa ký tự CJK — vi phạm quy tắc, bỏ qua.")
        return None, warnings
    if "khach_hang" not in parsed:
        warnings.append("deepseek_taxonomy: model thiếu key khach_hang trong JSON.")
    if "ten_tieng_viet" not in parsed:
        warnings.append("deepseek_taxonomy: model thiếu key ten_tieng_viet trong JSON.")
    if "chat_lieu_vi" not in parsed:
        warnings.append("deepseek_taxonomy: model thiếu key chat_lieu_vi trong JSON (coi như rỗng).")
    if "mo_ta_vi" not in parsed:
        warnings.append("deepseek_taxonomy: model thiếu key mo_ta_vi trong JSON (coi như rỗng — giữ mô tả NCC).")

    canon = _resolve_triple_only_from_taxonomy(c1, c2, c3, triples_use, snap_index)
    if not canon:
        warnings.append(
            f"deepseek_taxonomy: bộ «{c1} / {c2} / {c3}» không trùng nhánh nào trong taxonomy hiện có — không gán danh mục (không tạo danh mục mới)."
        )
        return None, warnings

    if _violates_gender_hint(gender_hint_eff, canon.get("cat1") or ""):
        warnings.append(
            "deepseek_taxonomy: kết quả mâu thuẫn giới tính đã suy ra từ thông số/mô tả NCC — bỏ qua gán danh mục."
        )
        return None, warnings

    kh_raw = _scrub_cjk(str(parsed.get("khach_hang") or ""))
    if _CJK_RE.search(str(parsed.get("khach_hang") or "")):
        warnings.append("deepseek_taxonomy: đã loại ký tự CJK khỏi khach_hang (vi phạm quy tắc đầu ra).")

    tv_raw = _scrub_cjk(str(parsed.get("ten_tieng_viet") or "")).strip()
    if not tv_raw:
        warnings.append(
            "deepseek_taxonomy: model thiếu hoặc rỗng ten_tieng_viet — dùng tên NCC đã loại CJK."
        )
        tv_raw = _scrub_cjk(name).strip()
    if not tv_raw:
        tv_raw = name[:200].strip()
    if len(tv_raw) > 220:
        tv_raw = tv_raw[:220].strip()

    cl_raw = str(parsed.get("chat_lieu_vi") or "").strip()
    cl_vi = _scrub_cjk(cl_raw).strip()
    if len(cl_vi) > 100:
        cl_vi = cl_vi[:100].strip()

    mt_raw = str(parsed.get("mo_ta_vi") or "").strip()
    mt_vi = _scrub_cjk(mt_raw).strip()
    mt_vi = re.sub(r"[ \t]+\n", "\n", mt_vi)
    mt_vi = re.sub(r"\n{3,}", "\n\n", mt_vi).strip()
    if len(mt_vi) > 12000:
        mt_vi = mt_vi[:12000].strip()

    out: Dict[str, str] = dict(canon)
    if kh_raw:
        out["khach_hang"] = kh_raw
    out["ten_tieng_viet"] = tv_raw
    out["chat_lieu_vi"] = cl_vi
    out["mo_ta_vi"] = mt_vi
    out["thuong_hieu_vi"] = _clip_vi_field(str(parsed.get("thuong_hieu_vi") or ""), 120)
    out["xuat_xu_vi"] = _clip_vi_field(str(parsed.get("xuat_xu_vi") or ""), 80)
    out["phong_cach_vi"] = _clip_vi_field(str(parsed.get("phong_cach_vi") or ""), 120)
    out["dip_vi"] = _clip_vi_field(str(parsed.get("dip_vi") or ""), 120)
    out["trong_luong_vi"] = _clip_vi_field(str(parsed.get("trong_luong_vi") or ""), 80)
    out["chieu_cao_got_vi"] = _clip_vi_field(str(parsed.get("chieu_cao_got_vi") or ""), 80)
    ts_raw = str(parsed.get("thong_so_kich_thuoc_vi") or "").strip()
    ts_vi = _scrub_cjk(ts_raw).strip()
    ts_vi = re.sub(r"[ \t]+\n", "\n", ts_vi)
    ts_vi = re.sub(r"\n{4,}", "\n\n\n", ts_vi).strip()
    if len(ts_vi) > 900:
        ts_vi = ts_vi[:900].strip()
    out["thong_so_kich_thuoc_vi"] = ts_vi
    return out, warnings


def classify_product_taxonomy_gemini(
    db: Session,
    product_name: str,
    *,
    context_text: str = "",
    supplier_gender_hint: Optional[str] = None,
) -> Tuple[Optional[Dict[str, str]], List[str]]:
    """
    Fallback Gemini 2.5 Flash: chọn bộ cat1/cat2/cat3 có sẵn + tên/mô tả Việt.
    """
    warnings: List[str] = []
    if not getattr(settings, "IMPORT_LINK_GEMINI_TAXONOMY_FALLBACK_ENABLED", True):
        return None, warnings

    name = (product_name or "").strip()
    if not name:
        return None, warnings

    triples = load_active_category_triples(db)
    if not triples:
        return None, warnings

    blob_ctx = (context_text or "").strip()[:_MAX_CONTEXT_CHARS]
    gender_hint_eff = supplier_gender_hint
    if gender_hint_eff is None:
        gender_hint_eff = infer_supplier_gender_hint(f"{name}\n{blob_ctx}")

    triples_use, fb = filter_triples_by_gender_hint(triples, gender_hint_eff)
    if fb:
        warnings.append("gemini_taxonomy: gợi ý giới tính không khớp taxonomy — phân loại không lọc giới.")

    block, truncated = _build_taxonomy_prompt_block(triples_use)
    if truncated:
        warnings.append("gemini_taxonomy: bảng danh mục quá dài — đã cắt bớt phần cuối trong prompt.")

    gender_lines = ""
    if gender_hint_eff == "female":
        gender_lines = "\nRÀNG BUỘC GIỚI: sản phẩm dành NỮ; không chọn cat1 kết thúc bằng « Nam ».\n"
    elif gender_hint_eff == "male":
        gender_lines = "\nRÀNG BUỘC GIỚI: sản phẩm dành NAM; không chọn cat1 kết thúc bằng « Nữ ».\n"

    prompt = (
        "Bạn là chuyên gia phân loại sản phẩm TMĐT Việt Nam.\n"
        "Nguồn có thể là tiếng Mông Cổ, Trung, Nga, Anh hoặc ngôn ngữ khác.\n"
        "Chọn đúng một bộ cat1/cat2/cat3 SAO CHÉP NGUYÊN VĂN từ BẢNG DANH MỤC, không tạo danh mục mới.\n"
        "Đồng thời tạo tên/mô tả tiếng Việt tự nhiên; không giữ nguyên chữ Cyrillic/Mông Cổ trong tên Việt.\n\n"
        + _TAXONOMY_CLASSIFICATION_RULES_VI.strip()
        + "\n\n"
        f"BẢNG DANH MỤC:\n{block}\n\n"
        f"{gender_lines}"
        f"NGỮ CẢNH / THÔNG SỐ:\n{blob_ctx}\n\n"
        f"TÊN SẢN PHẨM:\n{name}\n\n"
        "Trả về DUY NHẤT một JSON đủ 14 key:\n"
        '{"cat1":"...","cat2":"...","cat3":"...","khach_hang":"...","ten_tieng_viet":"...","chat_lieu_vi":"","mo_ta_vi":"...",'
        '"thuong_hieu_vi":"","xuat_xu_vi":"","phong_cach_vi":"","dip_vi":"","trong_luong_vi":"","chieu_cao_got_vi":"",'
        '"thong_so_kich_thuoc_vi":""}'
    )

    parsed = _gemini_generate_json(prompt, max_tokens=4096, warnings=warnings, label="gemini_taxonomy")
    if not parsed:
        return None, warnings

    c1 = str(parsed.get("cat1") or "").strip()
    c2 = str(parsed.get("cat2") or "").strip()
    c3 = str(parsed.get("cat3") or "").strip()
    if not (c1 and c2 and c3):
        warnings.append("gemini_taxonomy: model trả thiếu cat1/cat2/cat3.")
        return None, warnings
    if _CJK_RE.search(c1 + c2 + c3):
        warnings.append("gemini_taxonomy: cat1–cat3 chứa ký tự CJK — bỏ qua.")
        return None, warnings

    canon = _resolve_triple_only_from_taxonomy(c1, c2, c3, triples_use, _build_snap_index(triples_use))
    if not canon:
        warnings.append(
            f"gemini_taxonomy: bộ «{c1} / {c2} / {c3}» không trùng nhánh taxonomy hiện có."
        )
        return None, warnings
    if _violates_gender_hint(gender_hint_eff, canon.get("cat1") or ""):
        warnings.append("gemini_taxonomy: kết quả mâu thuẫn giới tính đã suy ra — bỏ qua.")
        return None, warnings

    tv_raw = _scrub_cjk(str(parsed.get("ten_tieng_viet") or "")).strip()
    if _looks_untranslated_non_vi(tv_raw, name):
        warnings.append("gemini_taxonomy: ten_tieng_viet rỗng hoặc còn chữ ngoại ngữ.")
        tv_raw = ""
    if len(tv_raw) > 220:
        tv_raw = tv_raw[:220].strip()

    mt_vi = _scrub_cjk(str(parsed.get("mo_ta_vi") or "")).strip()
    mt_vi = re.sub(r"[ \t]+\n", "\n", mt_vi)
    mt_vi = re.sub(r"\n{3,}", "\n\n", mt_vi).strip()
    if len(mt_vi) > 12000:
        mt_vi = mt_vi[:12000].strip()

    out: Dict[str, str] = dict(canon)
    kh_raw = _scrub_cjk(str(parsed.get("khach_hang") or "")).strip()
    if kh_raw:
        out["khach_hang"] = kh_raw
    out["ten_tieng_viet"] = tv_raw
    out["chat_lieu_vi"] = _clip_vi_field(str(parsed.get("chat_lieu_vi") or ""), 100)
    out["mo_ta_vi"] = mt_vi
    out["thuong_hieu_vi"] = _clip_vi_field(str(parsed.get("thuong_hieu_vi") or ""), 120)
    out["xuat_xu_vi"] = _clip_vi_field(str(parsed.get("xuat_xu_vi") or ""), 80)
    out["phong_cach_vi"] = _clip_vi_field(str(parsed.get("phong_cach_vi") or ""), 120)
    out["dip_vi"] = _clip_vi_field(str(parsed.get("dip_vi") or ""), 120)
    out["trong_luong_vi"] = _clip_vi_field(str(parsed.get("trong_luong_vi") or ""), 80)
    out["chieu_cao_got_vi"] = _clip_vi_field(str(parsed.get("chieu_cao_got_vi") or ""), 80)
    ts_vi = _scrub_cjk(str(parsed.get("thong_so_kich_thuoc_vi") or "")).strip()
    ts_vi = re.sub(r"[ \t]+\n", "\n", ts_vi)
    ts_vi = re.sub(r"\n{4,}", "\n\n\n", ts_vi).strip()
    out["thong_so_kich_thuoc_vi"] = ts_vi[:900].strip() if len(ts_vi) > 900 else ts_vi
    return out, warnings


_MAX_COLORS_IN_DISPLAY_VI = 4


def collect_variant_color_labels(product_data: Dict[str, Any]) -> List[str]:
    """Tên màu từ colors hoặc product_info.variants.color_swatches; giữ thứ tự, bỏ trùng không phân biệt hoa thường."""
    raw = product_data.get("colors")
    out = _labels_from_flat_colors(raw)
    if out:
        return out
    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        var = pi.get("variants")
        if isinstance(var, dict):
            sw = var.get("color_swatches")
            if isinstance(sw, list):
                labels: List[str] = []
                seen_l: set[str] = set()
                for it in sw:
                    if not isinstance(it, dict):
                        continue
                    lab = str(it.get("label") or "").strip()
                    if not lab:
                        continue
                    k = lab.lower()
                    if k in seen_l:
                        continue
                    seen_l.add(k)
                    labels.append(lab)
                return labels
    return []


def _labels_from_flat_colors(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen_l: set[str] = set()
    for item in raw:
        lab = ""
        if isinstance(item, dict):
            v = item.get("name")
            if v is None or str(v).strip() == "":
                v = item.get("label")
            lab = str(v).strip() if v is not None else ""
        elif item is not None:
            lab = str(item).strip()
        if not lab:
            continue
        k = lab.lower()
        if k in seen_l:
            continue
        seen_l.add(k)
        out.append(lab)
    return out
def append_colors_suffix_to_vi_name(base_vi: str, labels: List[str]) -> str:
    """
    Hậu tố màu ở cuối tên tiếng Việt.
    Từ 4 màu trở lên → chỉ 4 phiên bản đầu; ít hơn 4 → lấy hết.
    """
    base = (base_vi or "").strip()
    if not labels:
        return base
    if len(labels) >= _MAX_COLORS_IN_DISPLAY_VI:
        pick = labels[:_MAX_COLORS_IN_DISPLAY_VI]
    else:
        pick = list(labels)
    suffix = ", ".join(pick)
    if not base:
        return suffix
    return f"{base} — {suffix}"


def _merge_vietnamese_display_into_product_info(
    product_data: Dict[str, Any],
    base_vi: str,
    display_vi: str,
) -> None:
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return
    inner = pi.get("product_info")
    if not isinstance(inner, dict):
        inner = {}
        pi["product_info"] = inner
    inner["name_vi"] = base_vi
    inner["display_name_vi"] = display_vi
    meta = pi.setdefault("import_taxonomy_meta", {})
    if isinstance(meta, dict):
        meta["name_vi_base"] = base_vi
        meta["display_name_vi"] = display_vi


def _merge_material_vi(product_data: Dict[str, Any], material_vi: str) -> None:
    """Gán cột material (≤100) + product_info.product_info.material_vi; rỗng → None / xóa key."""
    mv = (material_vi or "").strip()
    if len(mv) > 100:
        mv = mv[:100].strip()
    product_data["material"] = mv if mv else None
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return
    inner = pi.get("product_info")
    if not isinstance(inner, dict):
        inner = {}
        pi["product_info"] = inner
    if mv:
        inner["material_vi"] = mv
    else:
        inner.pop("material_vi", None)


def _merge_description_vi(product_data: Dict[str, Any], mo_ta_vi: str) -> None:
    """Thay `description` (pro_content) bằng mô tả tiếng Việt sinh từ DeepSeek khi có nội dung."""
    md = (mo_ta_vi or "").strip()
    if len(md) > 12000:
        md = md[:12000].strip()
    if not md:
        return
    prev = (product_data.get("description") or "").strip()
    product_data["description"] = md
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return
    inner = pi.get("product_info")
    if not isinstance(inner, dict):
        inner = {}
        pi["product_info"] = inner
    inner["description_vi_generated"] = True
    meta = pi.setdefault("import_taxonomy_meta", {})
    if isinstance(meta, dict) and prev and len(prev) > 80:
        meta["description_supplier_excerpt"] = prev[:4000]


def _sizes_join_vi(product_data: Dict[str, Any]) -> str:
    raw: Any = product_data.get("sizes")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        pi = product_data.get("product_info")
        if isinstance(pi, dict):
            var = pi.get("variants")
            if isinstance(var, dict):
                vs = var.get("sizes")
                if isinstance(vs, list) and len(vs) > 0:
                    raw = vs
                elif isinstance(vs, str) and vs.strip():
                    raw = vs
    if raw is None:
        return ""
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return ""
        if s.startswith("["):
            try:
                parsed = json.loads(s)
            except json.JSONDecodeError:
                return _scrub_placeholder_str(s)
            raw = parsed
        else:
            return _scrub_placeholder_str(s)
    if isinstance(raw, list):
        parts: List[str] = []
        for x in raw:
            t = _scrub_placeholder_str(str(x))
            if t:
                parts.append(t)
        return ", ".join(parts)
    return _scrub_placeholder_str(str(raw))


def _merge_excel_web_listing_blocks(product_data: Dict[str, Any], triple: Dict[str, Any]) -> None:
    """
    Ghép product_info (cột AK) theo mẫu Excel: product_info / specifications / variants / market_info
    để tab thông tin sản phẩm có nhãn & giá trị tiếng Việt, không để chuỗi «nan».
    """
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        pi = {}
        product_data["product_info"] = pi
    inner = pi.get("product_info")
    if not isinstance(inner, dict):
        inner = {}
        pi["product_info"] = inner

    def sp(v: Any) -> str:
        if v is None:
            return ""
        return _scrub_placeholder_str(str(v))

    code = sp(product_data.get("code") or product_data.get("sku"))
    if code:
        inner["sku"] = code
    else:
        inner.pop("sku", None)

    name_disp = sp(product_data.get("name"))
    if name_disp:
        inner["name"] = name_disp
    else:
        inner.pop("name", None)

    th = sp(triple.get("thuong_hieu_vi"))
    if not th:
        th = sp(product_data.get("brand_name"))
    if th:
        inner["brand"] = th
        product_data["brand_name"] = th[:120]
    else:
        inner.pop("brand", None)

    ox = sp(triple.get("xuat_xu_vi"))
    if not ox:
        ox = sp(product_data.get("origin"))
    if ox:
        inner["origin"] = ox
        product_data["origin"] = ox[:120]
    else:
        inner.pop("origin", None)

    inner["category"] = {"level_1": triple["cat1"], "level_2": triple["cat2"], "level_3": triple["cat3"]}

    spec_existing = pi.get("specifications")
    spec: Dict[str, Any] = dict(spec_existing) if isinstance(spec_existing, dict) else {}

    mat = sp(triple.get("chat_lieu_vi")) or sp(product_data.get("material")) or sp(inner.get("material_vi"))
    if mat:
        spec["upper_material"] = mat
        if not sp(product_data.get("material")):
            product_data["material"] = mat[:100] if len(mat) > 100 else mat
    else:
        spec.pop("upper_material", None)

    style_v = sp(triple.get("phong_cach_vi")) or sp(product_data.get("style"))
    if style_v:
        spec["style"] = style_v
        product_data["style"] = style_v[:100]
    else:
        spec.pop("style", None)

    dip_v = sp(triple.get("dip_vi")) or sp(product_data.get("occasion"))
    if dip_v:
        spec["occasion"] = dip_v
        product_data["occasion"] = dip_v[:100]
    else:
        spec.pop("occasion", None)

    tw = sp(triple.get("trong_luong_vi")) or sp(product_data.get("weight") or product_data.get("Weight"))
    if tw:
        spec["weight_note_vi"] = tw
    else:
        spec.pop("weight_note_vi", None)

    got = sp(triple.get("chieu_cao_got_vi"))
    if got:
        spec["heel_height"] = got
    else:
        spec.pop("heel_height", None)

    ts_dims = sp(triple.get("thong_so_kich_thuoc_vi"))
    if ts_dims:
        spec["thong_so_kich_thuoc_vi"] = ts_dims
    else:
        spec.pop("thong_so_kich_thuoc_vi", None)

    if spec:
        pi["specifications"] = spec
    else:
        pi.pop("specifications", None)

    colors_join = ", ".join(collect_variant_color_labels(product_data))
    sizes_join = _sizes_join_vi(product_data)

    var_existing = pi.get("variants")
    var_m: Dict[str, Any] = dict(var_existing) if isinstance(var_existing, dict) else {}
    if colors_join:
        var_m["colors"] = colors_join
        cj = colors_join.strip()
        if len(cj) > 500:
            cj = cj[:500].strip()
        product_data["color"] = cj
    else:
        var_m.pop("colors", None)
    if sizes_join:
        var_m["sizes"] = sizes_join
    if var_m:
        pi["variants"] = var_m
    else:
        pi.pop("variants", None)

    mk_existing = pi.get("market_info")
    mk: Dict[str, Any] = dict(mk_existing) if isinstance(mk_existing, dict) else {}
    stock_raw = product_data.get("available")
    if stock_raw is None:
        stock_raw = product_data.get("stock_quantity")
    if stock_raw is not None and sp(str(stock_raw)):
        try:
            mk["stock"] = int(stock_raw)
        except (TypeError, ValueError):
            pass
    if mk:
        pi["market_info"] = mk


def _apply_vi_listing_from_strings(
    product_data: Dict[str, Any],
    ten_vi: str,
    mo_ta_vi: str,
    *,
    merge_name: bool = True,
    merge_desc: bool = True,
) -> None:
    """Ghi `name` + `description` (cột E/F) từ chuỗi tiếng Việt đã có; bỏ qua merge nếu chuỗi rỗng."""
    if merge_desc and (mo_ta_vi or "").strip():
        _merge_description_vi(product_data, mo_ta_vi)
    if merge_name and (ten_vi or "").strip():
        tn = (ten_vi or "").strip()
        labs = collect_variant_color_labels(product_data)
        disp_vi = append_colors_suffix_to_vi_name(tn, labs)
        _merge_vietnamese_display_into_product_info(product_data, tn, disp_vi)
        vi_display = (disp_vi or tn).strip()
        if vi_display:
            product_data["name"] = vi_display[:500]


def _should_skip_existing(product_data: Dict[str, Any]) -> bool:
    if getattr(settings, "IMPORT_LINK_DEEPSEEK_TAXONOMY_FORCE", False):
        return False
    c1 = (product_data.get("category") or "").strip()
    c2 = (product_data.get("subcategory") or "").strip()
    c3 = (product_data.get("sub_subcategory") or "").strip()
    return bool(c1 and c2 and c3)


def _merge_product_info_categories(
    product_data: Dict[str, Any],
    cat1: str,
    cat2: str,
    cat3: str,
    khach_hang: Optional[str] = None,
) -> None:
    pi = product_data.get("product_info")
    if not isinstance(pi, dict):
        return
    inner = pi.get("product_info")
    if not isinstance(inner, dict):
        inner = {}
        pi["product_info"] = inner
    inner["category"] = {"level_1": cat1, "level_2": cat2, "level_3": cat3}
    if khach_hang:
        meta = pi.setdefault("import_taxonomy_meta", {})
        if isinstance(meta, dict):
            meta["khach_hang_vi"] = khach_hang
        inner.setdefault("target_audience_suggestion_vi", khach_hang)


def apply_deepseek_taxonomy_to_product_data(db: Session, product_data: Dict[str, Any]) -> List[str]:
    """
    Điền category / subcategory / sub_subcategory (+ slug_seo = full_slug cat3) vào product_data
    **chỉ khi** bộ ba trùng đúng một nhánh taxonomy đã có trong DB — không bao giờ tạo danh mục mới.

    Nếu taxonomy có cả nhánh Nam/Nữ cho cùng loại cat1 mà text không cho biết giới tính,
    vẫn để DeepSeek tự chọn từ toàn bộ taxonomy — không fallback sang Gemini.

    Đã có đủ bộ ba category sẵn → không phân loại lại nhưng vẫn dịch tên+mô tả.
    taxonomy lỗi / không nhánh hoặc `mo_ta_vi` trống từ bước phân loại → bổ sung bằng DeepSeek.
    """
    warnings: List[str] = []
    if not settings.IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED:
        return warnings

    name_vi = (product_data.get("name") or "").strip()
    title_src = resolve_taxonomy_source_title(product_data)
    desc_src = (product_data.get("description") or "").strip()
    ctx = build_taxonomy_context_blob(product_data)

    if _should_skip_existing(product_data):
        tv, mv, tw = translate_product_listing_deepseek_only(name_vi or title_src, desc_src, context_text=ctx)
        warnings.extend(tw)
        if tv or mv:
            _apply_vi_listing_from_strings(product_data, tv, mv)
            warnings.append(
                "deepseek_taxonomy: giữ nguyên danh mục đã có — đã cập nhật tên/mô tả tiếng Việt (nếu API trả được)."
            )
        return warnings

    if not title_src:
        warnings.append("deepseek_taxonomy: thiếu chinese_name và tên — bỏ qua phân loại.")
        return warnings

    triples = load_active_category_triples(db)
    if not triples:
        warnings.append(
            "deepseek_taxonomy: chưa có nhánh cat3 active trong bảng categories — import taxonomy_import.xlsx trước."
        )
        tv_nt, mv_nt, tw_nt = translate_product_listing_deepseek_only(name_vi or title_src, desc_src, context_text=ctx)
        warnings.extend(tw_nt)
        if tv_nt or mv_nt:
            _apply_vi_listing_from_strings(product_data, tv_nt, mv_nt)
            warnings.append("deepseek_listing_translate: đã dịch tên/mô tả Việt dù chưa có taxonomy.")
        return warnings

    needs_gender = taxonomy_has_ambiguous_gender_cat1(triples)
    merged_hint: Optional[str] = None

    if needs_gender:
        merged_hint = infer_supplier_gender_hint(f"{title_src}\n{name_vi}\n{ctx}")
        if merged_hint is None:
            warnings.append(
                "deepseek_taxonomy: không có gợi ý giới tính chắc chắn — DeepSeek sẽ tự chọn nhánh từ toàn bộ taxonomy."
            )

    if _nonempty_product_field(product_data, "chinese_name"):
        warnings.append(
            "deepseek_taxonomy: phân loại theo cột chinese_name (tên tiếng Trung từ file import)."
        )

    triple, tw = classify_product_taxonomy_deepseek(
        db,
        title_src,
        context_text=ctx,
        supplier_gender_hint=merged_hint,
    )
    warnings.extend(tw)
    if not triple:
        warnings.append("deepseek_taxonomy: DeepSeek không gán được bộ taxonomy hợp lệ — không fallback sang Gemini.")

    if not triple:
        tv_x, mv_x, tw_x = translate_product_listing_deepseek_only(name_vi or title_src, desc_src, context_text=ctx)
        warnings.extend(tw_x)
        if tv_x or mv_x:
            _apply_vi_listing_from_strings(product_data, tv_x, mv_x)
            warnings.append(
                "deepseek_listing_translate: taxonomy không gán được nhánh — chỉ cập nhật tên/mô tả tiếng Việt nếu có."
            )
        return warnings

    khach = (triple.get("khach_hang") or "").strip() or None
    ten_vi = (triple.get("ten_tieng_viet") or "").strip()
    if _looks_untranslated_non_vi(ten_vi, name_vi or title_src):
        warnings.append("deepseek_taxonomy: ten_tieng_viet rỗng hoặc còn chữ ngoại ngữ — giữ nguyên kết quả DeepSeek, không fallback Gemini.")

    product_data.pop("taxonomy_import_error", None)

    product_data["category"] = triple["cat1"]
    product_data["subcategory"] = triple["cat2"]
    product_data["sub_subcategory"] = triple["cat3"]
    fs = (triple.get("full_slug") or "").strip()
    if fs:
        product_data["slug_seo"] = fs

    product_data.setdefault("raw_category", "")
    product_data.setdefault("raw_subcategory", "")
    product_data.setdefault("raw_sub_subcategory", "")
    if not (product_data["raw_category"] or "").strip():
        product_data["raw_category"] = triple["cat1"]
    if not (product_data["raw_subcategory"] or "").strip():
        product_data["raw_subcategory"] = triple["cat2"]
    if not (product_data["raw_sub_subcategory"] or "").strip():
        product_data["raw_sub_subcategory"] = triple["cat3"]

    _merge_product_info_categories(product_data, triple["cat1"], triple["cat2"], triple["cat3"], khach)
    _merge_material_vi(product_data, str(triple.get("chat_lieu_vi") or ""))
    mo_from_classify = str(triple.get("mo_ta_vi") or "")
    _merge_description_vi(product_data, mo_from_classify)
    if ten_vi:
        labs = collect_variant_color_labels(product_data)
        disp_vi = append_colors_suffix_to_vi_name(ten_vi, labs)
        _merge_vietnamese_display_into_product_info(product_data, ten_vi, disp_vi)
        # Tên hiển thị / đăng sản phẩm dùng cột `name` (ProductCreate), không chỉ JSON product_info.
        vi_display = (disp_vi or ten_vi).strip()
        if vi_display:
            product_data["name"] = vi_display[:500]
    if not mo_from_classify.strip():
        desc_left = (product_data.get("description") or "").strip()
        nm_for_desc = (product_data.get("name") or title_src).strip()
        if desc_left:
            _td, md_fb, tw_fb = translate_product_listing_deepseek_only(
                nm_for_desc,
                desc_left,
                context_text=ctx,
                description_only=True,
            )
            warnings.extend(tw_fb)
            if md_fb:
                _merge_description_vi(product_data, md_fb)
    _merge_excel_web_listing_blocks(product_data, triple)
    return warnings
