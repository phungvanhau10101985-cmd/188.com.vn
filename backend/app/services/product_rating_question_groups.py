"""
Nhóm đánh giá (rating_group_id / group_rating) và nhóm câu hỏi (question_group_id / group_question)
cho luồng import link — suy luận từ tên hiển thị + taxonomy đầy đủ + alias.

- rating: ghép ngữ cảnh từ category/sub/sub-sub (và raw_*), slug_seo, JSON product_info.category,
  khach_hang_vi (nếu có), rồi khớp chuỗi con (cụm chính + alias; ưu tiên cụm dài).

- question: theo FIND kiểu Excel trên BH2 (= tên sản phẩm):
    IFERROR(IFERROR(IFERROR(
      IF(find("nam nữ", BH2)>0, 99, ""),
      IF(find("nam", BH2)>0, 100, "")),
      IF(find("nữ", BH2)>0, 88, "")),
      99)

- Fallback: nếu không gán được nhóm đánh giá (rating) bằng luật:
  gọi Gemini 2.5 Flash trước (IMPORT_LINK_GEMINI_GROUPS_FALLBACK_ENABLED + GEMINI_API_KEY),
  rồi mới thử DeepSeek nếu Gemini không trả mã hợp lệ.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

_RATING_GROUPS_RAW: Iterable[Tuple[str, int]] = (
    ("áo da nam", 1),
    ("đồ ngủ nam", 2),
    ("áo giữ nhiệt nữ", 3),
    ("bikini nữ", 4),
    ("vest nam", 5),
    ("váy đầm đầm maxi nữ", 6),
    ("váy đầm maxi nữ", 6),
    ("áo phông nữ", 7),
    ("áo dài nữ", 8),
    ("áo da nữ", 9),
    ("vest nữ", 10),
    ("dép tăng chiều cao nữ", 11),
    ("áo jean nam", 12),
    ("dép xăng đan nam", 13),
    ("giày lười nữ", 14),
    ("giày lười nam", 15),
    ("dép lê nam", 16),
    ("quần jean nữ", 17),
    ("giày sneaker nam", 18),
    ("giày trung niên nữ", 19),
    ("martin nam", 20),
    ("giày dép nam", 21),
    ("sandal nam", 22),
    ("giày thể thao nam", 23),
    ("giày dép nữ", 24),
    ("quần jean nam", 25),
    ("dây lưng nam", 26),
    ("giày sneaker nữ", 27),
    ("giày da nữ", 28),
    ("áo sơ mi nam", 29),
    ("giày da nam", 30),
    ("boot nam", 30),
    ("áo lót nam", 31),
    ("giày tăng chiều cao nam", 32),
    ("martin nữ", 33),
    ("giày bệt nữ", 34),
    ("giày cao gót nữ", 35),
    ("giày thể thao nữ", 36),
    ("sandal nữ", 37),
    ("set đồ bộ nam", 38),
    ("đồ bộ nam", 38),
    ("áo lót nữ", 39),
    ("váy đầm liền thân dự tiệc nữ", 40),
    ("váy đầm liền thân nam nữ", 41),
    ("set đồ bộ nam nữ", 42),
    ("đồ bộ nam nữ", 61),
    ("áo len nam nữ", 43),
    ("quần nam nữ", 44),
    ("áo khoác nam nữ", 45),
    ("quần nam", 46),
    ("áo len nữ", 47),
    ("áo thun nữ", 48),
    ("áo khoác nam", 49),
    ("áo len nam", 50),
    ("áo thun nam", 51),
    ("túi xách nam", 52),
    ("ví nam", 53),
    ("chân váy đầm nữ", 54),
    ("đồ ngủ nữ", 55),
    ("áo gió nữ", 56),
    ("quần nữ", 57),
    ("áo sơ mi nữ", 58),
    ("váy đầm liền thân nữ", 59),
    ("áo khoác nữ", 60),
    ("set đồ bộ nữ", 61),
    ("đồ bộ nữ", 61),
    ("đồng hồ nữ nữ", 62),
    ("đồng hồ nam nam nữ", 63),
    ("đồng hồ nam nam", 64),
    ("dép lê nữ", 65),
    ("dép lê nam nữ", 65),
    ("boot nữ", 66),
    ("giày tăng chiều cao nữ", 67),
    ("ví nữ", 68),
    ("túi xách nữ", 69),
    ("lắc tay nữ", 70),
    ("lắc tay nam", 71),
    ("vòng cổ nữ", 72),
    ("vòng cổ nam", 73),
    ("mũ nữ", 74),
    ("nhẫn nữ", 75),
    ("trang sức nữ", 75),
    ("nhẫn nam", 76),
    ("nhẫn nam nữ", 77),
    ("bông tai nữ", 78),
    ("hàng sale", 79),
    ("áo lông nữ", 80),
    ("áo lông nam", 81),
    ("áo nỉ nam", 82),
    ("áo nỉ nữ", 83),
    ("áo lông nam nữ", 80),
    ("vest nam nữ", 5),
    ("áo sơ mi nam nữ", 29),
    ("giày thể thao nam nữ", 23),
    ("máy hút bụi", 84),
    ("áo hai dây nữ", 85),
)

# Cụm từ đồng nghĩa / cách gọi thực tế trên tên SP (không liền với cụm chuẩn trong bảng trên).
_RATING_ALIASES_RAW: Iterable[Tuple[str, int]] = (
    ("sandal cao gót nữ", 35),
    ("giày sandal cao gót nữ", 35),
    ("sandal gót nữ", 35),
    ("dép sandal nữ", 37),
    ("sandal xỏ ngón nữ", 37),
    ("sandal quai hậu nữ", 37),
    ("giày sandal nữ", 37),
    ("sneaker nữ", 27),
    ("giày sneaker nữ", 27),
    ("sneaker nam", 18),
    ("boot cổ thấp nữ", 66),
    ("boot cổ cao nữ", 66),
    ("túi đeo chéo nữ", 69),
    ("balo nữ", 69),
)

_WS_RE = re.compile(r"\s+")
_SLUG_SPLIT_RE = re.compile(r"[/\\_\-]+")


def _norm_ctx(text: str) -> str:
    return _WS_RE.sub(" ", (text or "").strip()).casefold()


def _rating_phrases_sorted() -> Tuple[Tuple[str, int], ...]:
    """Alias trước, cụm chính sau — trùng key thì bảng chính giữ gid."""
    m: Dict[str, int] = {}
    for phrase, gid in (*_RATING_ALIASES_RAW, *_RATING_GROUPS_RAW):
        key = phrase.strip().casefold()
        if key:
            m[key] = gid
    return tuple(sorted(((p, gid) for p, gid in m.items()), key=lambda x: (-len(x[0]), x[0])))


_RATING_SORTED = _rating_phrases_sorted()

RATING_GROUP_ID_WHITELIST: frozenset[int] = frozenset(
    gid for _, gid in (*_RATING_GROUPS_RAW, *_RATING_ALIASES_RAW)
)


def rating_group_catalog_text_for_prompt() -> str:
    """Danh sách một dòng một id cho prompt DeepSeek (nhãn = cụm VN ngắn nhất trong bảng chính)."""
    canon: Dict[int, str] = {}
    for phrase, gid in _RATING_GROUPS_RAW:
        q = phrase.strip()
        if not q:
            continue
        nq = len(_norm_ctx(q))
        cur = canon.get(gid)
        if cur is None or nq < len(_norm_ctx(cur)):
            canon[gid] = q
    missing = sorted(RATING_GROUP_ID_WHITELIST - set(canon))
    for mid in missing:
        canon[mid] = f"(id={mid})"
    return "\n".join(f"{gid}: {canon[gid]}" for gid in sorted(canon))


def _slug_as_words(slug: str) -> str:
    if not (slug or "").strip():
        return ""
    t = _SLUG_SPLIT_RE.sub(" ", slug)
    return _WS_RE.sub(" ", t).strip()


def build_import_rating_context_text(product_data: Dict[str, Any]) -> str:
    """Gom mọi nguồn chữ có ích cho khớp nhóm đánh giá (taxonomy + slug + JSON)."""
    parts: List[str] = []

    def add(val: Any) -> None:
        s = str(val or "").strip()
        if s:
            parts.append(s)

    if not isinstance(product_data, dict):
        return ""

    for key in (
        "category",
        "subcategory",
        "sub_subcategory",
        "raw_category",
        "raw_subcategory",
        "raw_sub_subcategory",
        "name",
        "material",
        "style",
        "color",
        "occasion",
        "features",
        "weight",
    ):
        add(product_data.get(key))

    for sk in ("slug_seo", "full_slug", "cat3_full_slug"):
        raw = product_data.get(sk)
        if raw:
            add(_slug_as_words(str(raw)))

    pi = product_data.get("product_info")
    if isinstance(pi, dict):
        inner = pi.get("product_info")
        if isinstance(inner, dict):
            cat = inner.get("category")
            if isinstance(cat, dict):
                add(cat.get("level_1"))
                add(cat.get("level_2"))
                add(cat.get("level_3"))
            add(inner.get("target_audience_suggestion_vi"))
        meta = pi.get("import_taxonomy_meta")
        if isinstance(meta, dict):
            add(meta.get("khach_hang_vi"))

    cat1 = str(product_data.get("category") or "").strip()
    cf1 = cat1.casefold()
    gender_tail = ""
    if cf1.endswith(" nữ"):
        gender_tail = "nữ"
    elif cf1.endswith(" nam"):
        gender_tail = "nam"
    if gender_tail:
        for key in ("subcategory", "sub_subcategory", "raw_subcategory", "raw_sub_subcategory"):
            seg = str(product_data.get(key) or "").strip()
            seg_cf = seg.casefold()
            if seg and gender_tail not in seg_cf:
                parts.append(f"{seg} {gender_tail}")

    return " ".join(parts)


_GENERIC_RATING_PHRASES = frozenset({"giày dép nam", "giày dép nữ"})
# Nếu cụm dài nhất chỉ là "giày dép nam|nữ" nhưng có cụm khác (vd sandal nam) chỉ ngắn hơn vài ký tự → ưu tiên cụm cụ thể.
_SPECIFICITY_DEBOOST_MAX_GAP = 2


def infer_rating_group_id_from_text(context: str) -> int:
    hay = _norm_ctx(context)
    if not hay:
        return 0
    matched: List[Tuple[str, int]] = []
    for phrase, gid in _RATING_SORTED:
        if phrase in hay:
            matched.append((phrase, gid))
    if not matched:
        return 0

    maxlen = max(len(p) for p, _ in matched)
    specifics = [(p, g) for p, g in matched if p not in _GENERIC_RATING_PHRASES]
    if specifics:
        best_spec_len = max(len(p) for p, _ in specifics)
        if maxlen - best_spec_len <= _SPECIFICITY_DEBOOST_MAX_GAP:
            p_best, g_best = max(specifics, key=lambda x: (len(x[0]), x[0]))
            return g_best

    p_best, g_best = max(matched, key=lambda x: (len(x[0]), x[0]))
    return g_best


def infer_rating_group_id(*, name: str, category: str = "", subcategory: str = "", sub_subcategory: str = "") -> int:
    """Tương thích cũ: chỉ 3 cấp + tên (không slug/raw/JSON)."""
    return infer_rating_group_id_from_text(
        " ".join((category or "", subcategory or "", sub_subcategory or "", name or ""))
    )


def infer_question_group_id_from_product_name(product_name: str) -> int:
    """
    Bám công thức Excel (FIND trên ô tên):
    nam nữ → 99, nam → 100, nữ → 88, mặc định → 99.
    """
    t = _norm_ctx(product_name or "")
    if not t:
        return 99
    if "nam nữ" in t:
        return 99
    if "nam" in t:
        return 100
    if "nữ" in t:
        return 88
    return 99


def apply_import_rating_question_groups_to_product_data(
    product_data: dict,
    warnings: Optional[List[str]] = None,
) -> None:
    """
    Gán group_rating / group_question (rule-first). Nếu group_rating == 0,
    fallback AI một lần theo whitelist (Gemini trước, DeepSeek dự phòng).
    """
    if not isinstance(product_data, dict):
        return

    pname = str(product_data.get("name") or "").strip()
    ctx = build_import_rating_context_text(product_data)
    rid = infer_rating_group_id_from_text(ctx)
    qid = infer_question_group_id_from_product_name(pname)

    if rid == 0:
        try:
            from app.services.import_link_gemini_groups import gemini_fallback_import_groups

            dr, dq, fw = gemini_fallback_import_groups(ctx, pname)
            if warnings is not None:
                warnings.extend(fw)
            if dr is not None:
                rid = dr
            if dq is not None:
                qid = dq
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"gemini_groups: lỗi không mong đợi — {type(exc).__name__}: {exc}")

    if rid == 0:
        try:
            from app.core.config import settings as _settings
            from app.services.import_link_deepseek_groups import deepseek_fallback_import_groups

            fb = getattr(_settings, "IMPORT_LINK_DEEPSEEK_GROUPS_FALLBACK_ENABLED", False)
            has_key = bool((_settings.DEEPSEEK_API_KEY or "").strip())
            if fb and not has_key and warnings is not None and pname:
                warnings.append("deepseek_groups: thiếu DEEPSEEK_API_KEY — không fallback nhóm đánh giá.")
            if fb and has_key and pname:
                dr, dq, fw = deepseek_fallback_import_groups(ctx, pname)
                if warnings is not None:
                    warnings.extend(fw)
                if dr is not None:
                    rid = dr
                if dq is not None:
                    qid = dq
        except Exception as exc:
            if warnings is not None:
                warnings.append(f"deepseek_groups: lỗi không mong đợi — {type(exc).__name__}: {exc}")

    if rid > 0:
        product_data["group_rating"] = rid

    product_data["group_question"] = qid

