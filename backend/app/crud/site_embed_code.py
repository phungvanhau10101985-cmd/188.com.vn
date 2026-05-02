import re
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.site_embed_code import SiteEmbedCode
from app.schemas.site_embed_code import SiteEmbedCodeAdminItem, SiteEmbedCodeCreate, SiteEmbedCodeUpdate
from app.services.site_embed_templates import collect_expanded_fragments


def row_to_admin_item(row: SiteEmbedCode) -> SiteEmbedCodeAdminItem:
    c = (row.content or "").strip()
    secret = False
    out = c
    cat = (row.category or "").lower()
    plat = (row.platform or "").lower()
    if cat == "capi_token" and plat in ("facebook", "tiktok"):
        secret = bool(c)
        out = ""
    return SiteEmbedCodeAdminItem(
        id=row.id,
        platform=row.platform,
        category=row.category,
        title=row.title,
        placement=row.placement,
        content=out,
        hint=row.hint,
        is_active=bool(row.is_active),
        sort_order=int(row.sort_order or 0),
        secret_configured=secret,
    )


def get_facebook_pixel_id_and_capi_access_token(db: Session) -> Tuple[Optional[str], Optional[str]]:
    """Pixel ID (số) + token CAPI từ bảng site_embed_codes (đang bật)."""
    pix = (
        db.query(SiteEmbedCode)
        .filter(
            SiteEmbedCode.platform == "facebook",
            SiteEmbedCode.category == "pixel",
            SiteEmbedCode.is_active.is_(True),
        )
        .order_by(SiteEmbedCode.sort_order.asc(), SiteEmbedCode.id.asc())
        .first()
    )
    tok = (
        db.query(SiteEmbedCode)
        .filter(
            SiteEmbedCode.platform == "facebook",
            SiteEmbedCode.category == "capi_token",
            SiteEmbedCode.is_active.is_(True),
        )
        .order_by(SiteEmbedCode.sort_order.asc(), SiteEmbedCode.id.asc())
        .first()
    )
    pid = re.sub(r"\D", "", (pix.content or "")) if pix else ""
    access = (tok.content or "").strip() if tok else ""
    return (pid or None, access or None)


# (platform, category, title, placement, hint, sort_order)
_DEFAULT_ROWS: tuple = (
    ("google", "ga4", "Google Analytics 4 — GA4 / gtag.js", "head", "Chỉ nhập Measurement ID: G-XXXX (không cần dán script).", 10),
    ("google", "gtm", "Google Tag Manager — container", "head", "Chỉ nhập Container ID: GTM-XXXX — hệ thống chèn đủ head + body.", 20),
    ("google", "ads", "Google Ads — thẻ toàn cục (Remarketing động / catalogue + chuyển đổi)", "head", "Chỉ nhập một mã AW-XXXXXXXX — dùng cho chuyển đổi và tiếp thị lại động Retail (kết nối feed Merchant Center trong Google Ads).", 30),
    ("google", "search_console", "Google Search Console — xác minh chủ sở hữu", "head", "Chỉ nhập chuỗi xác minh (content) trong Search Console — hoặc dán meta tag đầy đủ.", 40),
    (
        "google",
        "merchant_center",
        "Google Merchant Center — xác minh chủ sở hữu website",
        "head",
        "Merchant Center → Xác minh URL website: chọn Thẻ HTML — chỉ dán chuỗi trong thuộc tính content (hoặc dán full meta).",
        42,
    ),
    ("google", "other", "Google — mã khác (AdSense,...)", "head", "Chỉ dán full HTML/script nếu không thuộc các mục trên.", 50),
    ("facebook", "pixel", "Meta Pixel — Remarketing động / Advantage+ catalogue", "head", "Chỉ nhập Pixel ID (số): dùng chung cho chuyển đổi, tiếp thị động, đối tượng tùy chỉnh.", 60),
    ("facebook", "capi_token", "Meta — Conversion API — Access Token (server)", "head", "Chỉ dán token từ Events Manager → Cài đặt → Conversion API. Không hiện trên web; dùng cho API máy chủ.", 59),
    ("facebook", "domain", "Meta — xác minh Domain / Meta Business Suite", "head", "Chỉ nhập mã trong thẻ meta facebook-domain-verification.", 70),
    ("facebook", "chat", "Meta — Chat Plugin (Facebook)", "body_close", "Chỉ nhập Page ID (số).", 80),
    (
        "nanoai",
        "embed",
        "NanoAI — Chat / widget nhúng",
        "body_close",
        "Dán mã nhúng (script/widget) từ bảng điều khiển NanoAI — thường là một hoặc nhiều thẻ script.",
        84,
    ),
    ("tiktok", "pixel", "TikTok — Pixel Web (Remarketing động / catalogue)", "head", "Chỉ nhập TikTok Pixel ID (Events Manager) — không cần dán base code đầy đủ.", 88),
    ("tiktok", "capi_token", "TikTok — Events API — Access Token (server)", "head", "Token gửi sự kiện server-side TikTok Events API (không hiện HTML). Ghép Pixel + Events API mạnh hơn cho remarketing.", 87),
    ("zalo", "chat", "Zalo — Chat / Widget Official Account", "body_close", "Chỉ nhập OA ID (chuỗi số của Official Account).", 90),
    ("zalo", "other", "Zalo — mã khác (ZNS,...)", "body_close", "Dán full HTML nếu cần khung tùy biến.", 100),
    ("other", "custom", "Mã tùy chỉnh — trong head (thẻ HTML head)", "head", "Bất kỳ script/link/meta không thuộc mục trên.", 200),
    ("other", "custom", "Mã tùy chỉnh — đầu thân trang (body)", "body_open", "Ngay sau khi mở thẻ body.", 210),
    ("other", "custom", "Mã tùy chỉnh — cuối body (trước khi đóng body)", "body_close", "Trước script cuối trang.", 220),
)


def ensure_default_embed_codes(db: Session) -> int:
    """Chèn các dòng mẫu một lần nếu bảng đang trống; luôn bổ sung preset mới khi codebase thêm (vd: capi_token)."""
    added = 0
    count = db.query(SiteEmbedCode).count()
    if count == 0:
        for platform, category, title, placement, hint, sort_order in _DEFAULT_ROWS:
            row = SiteEmbedCode(
                platform=platform,
                category=category,
                title=title,
                placement=placement,
                content="",
                hint=hint,
                is_active=True,
                sort_order=sort_order,
            )
            db.add(row)
            added += 1
        db.commit()
    merged = _merge_missing_embed_presets(db)
    return added + merged


def _merge_missing_embed_presets(db: Session) -> int:
    """Thêm các dòng preset mới theo phiên bản code (định danh platform + category + title)."""
    n = 0
    for platform, category, title, placement, hint, sort_order in _DEFAULT_ROWS:
        exists = (
            db.query(SiteEmbedCode)
            .filter(
                SiteEmbedCode.platform == platform,
                SiteEmbedCode.category == category,
                SiteEmbedCode.title == title,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            SiteEmbedCode(
                platform=platform,
                category=category,
                title=title,
                placement=placement,
                content="",
                hint=hint,
                is_active=True,
                sort_order=sort_order,
            )
        )
        n += 1
    if n:
        db.commit()
    return n


def deactivate_nanoai_try_on_embeds(db: Session) -> int:
    """Tắt và xóa snippet các dòng nanoai/try_on (mục admin đã gỡ)."""
    rows = (
        db.query(SiteEmbedCode)
        .filter(
            SiteEmbedCode.platform == "nanoai",
            SiteEmbedCode.category == "try_on",
        )
        .all()
    )
    n = 0
    for row in rows:
        if row.is_active or (row.content or "").strip():
            row.is_active = False
            row.content = ""
            n += 1
    if n:
        db.commit()
    return n


def list_embed_codes(db: Session, include_inactive: bool = True) -> List[SiteEmbedCode]:
    q = db.query(SiteEmbedCode).order_by(SiteEmbedCode.sort_order.asc(), SiteEmbedCode.id.asc())
    if not include_inactive:
        q = q.filter(SiteEmbedCode.is_active.is_(True))
    return q.all()


def get_embed_code(db: Session, embed_id: int) -> Optional[SiteEmbedCode]:
    return db.query(SiteEmbedCode).filter(SiteEmbedCode.id == embed_id).first()


def create_embed_code(db: Session, data: SiteEmbedCodeCreate) -> SiteEmbedCode:
    row = SiteEmbedCode(
        platform=data.platform.strip().lower()[:32],
        category=(data.category or "custom").strip()[:64],
        title=data.title.strip()[:255],
        placement=_normalize_placement(data.placement),
        content=(data.content or "").strip(),
        hint=(data.hint or "").strip() or None,
        is_active=data.is_active,
        sort_order=data.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_embed_code(db: Session, embed_id: int, data: SiteEmbedCodeUpdate) -> Optional[SiteEmbedCode]:
    row = get_embed_code(db, embed_id)
    if not row:
        return None
    payload = data.model_dump(exclude_unset=True)
    if "platform" in payload and payload["platform"] is not None:
        row.platform = str(payload["platform"]).strip().lower()[:32]
    if "category" in payload and payload["category"] is not None:
        row.category = str(payload["category"]).strip()[:64]
    if "title" in payload and payload["title"] is not None:
        row.title = str(payload["title"]).strip()[:255]
    if "placement" in payload and payload["placement"] is not None:
        row.placement = _normalize_placement(str(payload["placement"]))
    if "content" in payload and payload["content"] is not None:
        s = (payload["content"] or "").strip()
        if (row.category or "").lower() == "capi_token" and (row.platform or "").lower() in ("facebook", "tiktok") and not s:
            # Giữ token cũ khi admin gửi rỗng (không lộ ra GET)
            pass
        else:
            row.content = s
    if "hint" in payload:
        row.hint = (payload["hint"] or "").strip() or None
    if "is_active" in payload and payload["is_active"] is not None:
        row.is_active = bool(payload["is_active"])
    if "sort_order" in payload and payload["sort_order"] is not None:
        row.sort_order = int(payload["sort_order"])
    db.commit()
    db.refresh(row)
    return row


def delete_embed_code(db: Session, embed_id: int) -> bool:
    row = get_embed_code(db, embed_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def _normalize_placement(p: str) -> str:
    p = (p or "").strip().lower()
    if p in ("head", "body_open", "body_close"):
        return p
    if p in ("body-start", "body_start", "start"):
        return "body_open"
    if p in ("body-end", "body_end", "end"):
        return "body_close"
    return "head"


def collect_public_snippets(db: Session, validate_placement: bool = True):
    rows = (
        db.query(SiteEmbedCode)
        .filter(SiteEmbedCode.is_active.is_(True))
        .order_by(SiteEmbedCode.sort_order.asc(), SiteEmbedCode.id.asc())
        .all()
    )
    head, body_open, body_close = collect_expanded_fragments(rows)
    return head, body_open, body_close
