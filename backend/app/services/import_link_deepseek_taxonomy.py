"""
Gán danh mục cấp 1–3 cho draft import từ link (1688 / Hibox): đọc taxonomy từ bảng `categories`,
gọi DeepSeek (OpenAI-compatible) theo **tên sản phẩm**. Chỉ ghi được bộ ba đã **có sẵn** trong taxonomy
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

_CJK_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]")


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


def build_taxonomy_context_blob(product_data: Dict[str, Any]) -> str:
    """Gom mô tả + excerpt thông số Hibox để đưa vào prompt (không chỉ dựa vào title)."""
    parts: List[str] = []
    d = (product_data.get("description") or "").strip()
    if d:
        parts.append(d)
    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        spec = pi.get("specifications")
        if isinstance(spec, dict):
            ex = (spec.get("hibox_specs_excerpt") or "").strip()
            if ex and ex not in d:
                parts.append(ex)
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
    khi đó bắt buộc biết giới trước khi gán DeepSeek (text hoặc ảnh Gemini).
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
    """Ghi lỗi phân loại taxonomy (thiếu giới tính / Gemini không kết luận) — admin đọc draft + warnings."""
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
    supplier_gender_hint: nếu apply đã suy ra (text hoặc Gemini ảnh), truyền vào để không đọc lại sai thứ tự.
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
        "Nhiệm vụ: đọc BẢNG DANH MỤC, **TÊN** và **NGỮ CẢNH THÔNG SỐ/MÔ TẢ** (có thể tiếng Mông Cổ, Nga…); "
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
        f"TÊN SẢN PHẨM:\n{name}\n\n"
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

    Nếu taxonomy có cả nhánh Nam/Nữ cho cùng loại cat1 mà text không cho biết giới tính → gọi Gemini (ảnh đại diện).
    Không xác định được giới → ghi lỗi vào product_info.import_taxonomy_meta và không gán danh mục.
    """
    warnings: List[str] = []
    if _should_skip_existing(product_data):
        return warnings
    if not settings.IMPORT_LINK_DEEPSEEK_TAXONOMY_ENABLED:
        return warnings

    name = (product_data.get("name") or "").strip()
    ctx = build_taxonomy_context_blob(product_data)

    triples = load_active_category_triples(db)
    if not triples:
        warnings.append(
            "deepseek_taxonomy: chưa có nhánh cat3 active trong bảng categories — import taxonomy_import.xlsx trước."
        )
        return warnings

    needs_gender = taxonomy_has_ambiguous_gender_cat1(triples)
    merged_hint: Optional[str] = None
    gemini_err: Optional[str] = None

    if needs_gender:
        merged_hint = infer_supplier_gender_hint(f"{name}\n{ctx}")
        if merged_hint is None:
            from app.services.import_link_gemini_image_gender import infer_gender_from_product_image_gemini

            img_url = pick_product_hero_image_url(product_data)
            if img_url:
                gh_img, gemini_err = infer_gender_from_product_image_gemini(img_url, name)
                if gh_img:
                    merged_hint = gh_img
                    pi = product_data.get("product_info")
                    if isinstance(pi, dict):
                        meta = pi.setdefault("import_taxonomy_meta", {})
                        if isinstance(meta, dict):
                            meta["gender_source"] = "gemini_vision"
                            meta["gender_image_url"] = img_url[:500]
            else:
                gemini_err = "Không có ảnh đại diện (main_image / images[0]) để Gemini phân tích giới tính."

        if merged_hint is None:
            msg = gemini_err or (
                "Taxonomy có nhánh Nam/Nữ song không xác định được giới tính từ thông số và ảnh đại diện."
            )
            record_import_taxonomy_error(product_data, msg)
            warnings.append(f"deepseek_taxonomy: {msg}")
            return warnings

    triple, tw = classify_product_taxonomy_deepseek(
        db,
        name,
        context_text=ctx,
        supplier_gender_hint=merged_hint,
    )
    warnings.extend(tw)
    if not triple:
        return warnings

    khach = (triple.get("khach_hang") or "").strip() or None
    ten_vi = (triple.get("ten_tieng_viet") or "").strip()

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
    _merge_description_vi(product_data, str(triple.get("mo_ta_vi") or ""))
    if ten_vi:
        labs = collect_variant_color_labels(product_data)
        disp_vi = append_colors_suffix_to_vi_name(ten_vi, labs)
        _merge_vietnamese_display_into_product_info(product_data, ten_vi, disp_vi)
        # Tên hiển thị / đăng sản phẩm dùng cột `name` (ProductCreate), không chỉ JSON product_info.
        vi_display = (disp_vi or ten_vi).strip()
        if vi_display:
            product_data["name"] = vi_display[:500]
    _merge_excel_web_listing_blocks(product_data, triple)
    return warnings
