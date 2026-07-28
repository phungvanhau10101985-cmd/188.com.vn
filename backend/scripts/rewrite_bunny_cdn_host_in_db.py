#!/usr/bin/env python3
"""
Đổi host CDN cũ trong DB: 188comvn.b-cdn.net → cdn.188.com.vn (giữ path/query).

Ví dụ:
  https://188comvn.b-cdn.net/balo-hoc-sinh-..._68b3.jpg
  → https://cdn.188.com.vn/balo-hoc-sinh-..._68b3.jpg

Cũng xử lý http:// và //188comvn.b-cdn.net/...

Bảng chính:
  - products (main_image, images, gallery, colors, product_info, description, video_link)
  - categories (image, size_guide_image_url)
  - category_seo_meta (image_1..4, seo_body, seo_description)
  - product_reviews (images)
  - order_items / cart_items (product_image)
  - home_hero_category_groups (tiles) — tùy chọn
  - product_import_drafts (product_data) — --include-drafts
  - users.avatar — --include-users

Chạy trên server:

  cd /var/www/188.com.vn/backend
  source .venv/bin/activate
  python scripts/rewrite_bunny_cdn_host_in_db.py --audit
  python scripts/rewrite_bunny_cdn_host_in_db.py --dry-run
  python scripts/rewrite_bunny_cdn_host_in_db.py --yes
  python scripts/rewrite_bunny_cdn_host_in_db.py --yes --include-drafts --include-hero --include-users

DATABASE_URL lấy từ backend/.env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(BACKEND_ROOT, ".env"))
except ImportError:
    pass

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.product import Product  # noqa: E402

OLD_HOST = "188comvn.b-cdn.net"
DEFAULT_NEW_BASE = "https://cdn.188.com.vn"


def _new_base(cli_base: Optional[str]) -> str:
    env = (os.getenv("BUNNY_CDN_PUBLIC_BASE") or "").strip().rstrip("/")
    if cli_base:
        return cli_base.strip().rstrip("/")
    if env and "b-cdn.net" not in env.lower():
        return env
    return DEFAULT_NEW_BASE


def rewrite_url(raw: Any, new_base: str) -> Any:
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s or OLD_HOST not in s.lower():
        return raw

    try:
        with_scheme = s if s.startswith(("http://", "https://")) else (f"https:{s}" if s.startswith("//") else s)
        if not with_scheme.startswith(("http://", "https://")):
            # plain string replace fallback
            out = s
            for old in (
                f"https://{OLD_HOST}",
                f"http://{OLD_HOST}",
                f"//{OLD_HOST}",
            ):
                out = out.replace(old, new_base).replace(old.lower(), new_base)
            return out if out != s else raw

        parsed = urlparse(with_scheme)
        if (parsed.hostname or "").lower() != OLD_HOST:
            # host khác nhưng chuỗi chứa old host (HTML) — string replace
            out = s
            for old in (
                f"https://{OLD_HOST}",
                f"http://{OLD_HOST}",
                f"//{OLD_HOST}",
            ):
                out = out.replace(old, new_base)
            return out

        suffix = parsed.path or ""
        if parsed.query:
            suffix += f"?{parsed.query}"
        if parsed.fragment:
            suffix += f"#{parsed.fragment}"
        return f"{new_base}{suffix}"
    except Exception:
        out = s
        for old in (
            f"https://{OLD_HOST}",
            f"http://{OLD_HOST}",
            f"//{OLD_HOST}",
        ):
            out = out.replace(old, new_base)
        return out


def rewrite_deep(value: Any, new_base: str) -> Tuple[Any, int]:
    """Trả (value_mới, số_chuỗi_đã_đổi)."""
    changed = 0
    if isinstance(value, str):
        nxt = rewrite_url(value, new_base)
        if nxt != value:
            return nxt, 1
        return value, 0
    if isinstance(value, list):
        out: List[Any] = []
        for item in value:
            ni, c = rewrite_deep(item, new_base)
            changed += c
            out.append(ni)
        return out, changed
    if isinstance(value, dict):
        out_d: Dict[str, Any] = {}
        for k, v in value.items():
            nv, c = rewrite_deep(v, new_base)
            changed += c
            out_d[k] = nv
        return out_d, changed
    return value, 0


def audit_counts(db: Session) -> Dict[str, int]:
    like = f"%{OLD_HOST}%"

    def q(sql: str) -> int:
        return int(db.execute(text(sql), {"p": like}).scalar() or 0)

    return {
        "products.main_image": q("SELECT count(*) FROM products WHERE main_image ILIKE :p"),
        "products.video_link": q("SELECT count(*) FROM products WHERE video_link ILIKE :p"),
        "products.description": q("SELECT count(*) FROM products WHERE description ILIKE :p"),
        "products.images_json": q("SELECT count(*) FROM products WHERE images::text ILIKE :p"),
        "products.gallery_json": q("SELECT count(*) FROM products WHERE gallery::text ILIKE :p"),
        "products.colors_json": q("SELECT count(*) FROM products WHERE colors::text ILIKE :p"),
        "products.product_info_json": q("SELECT count(*) FROM products WHERE product_info::text ILIKE :p"),
        "categories.image": q("SELECT count(*) FROM categories WHERE image ILIKE :p"),
        "categories.size_guide_image_url": q(
            "SELECT count(*) FROM categories WHERE size_guide_image_url ILIKE :p"
        ),
        "category_seo_meta": q(
            """
            SELECT count(*) FROM category_seo_meta
            WHERE image_1 ILIKE :p OR image_2 ILIKE :p OR image_3 ILIKE :p OR image_4 ILIKE :p
               OR coalesce(seo_body,'') ILIKE :p OR coalesce(seo_description,'') ILIKE :p
            """
        ),
        "product_reviews.images": q("SELECT count(*) FROM product_reviews WHERE images::text ILIKE :p"),
        "order_items.product_image": q("SELECT count(*) FROM order_items WHERE product_image ILIKE :p"),
        "cart_items.product_image": q("SELECT count(*) FROM cart_items WHERE product_image ILIKE :p"),
        "home_hero.tiles": q(
            "SELECT count(*) FROM home_hero_category_groups WHERE tiles::text ILIKE :p"
        ),
        "product_import_drafts": q(
            "SELECT count(*) FROM product_import_drafts WHERE product_data::text ILIKE :p"
        ),
        "users.avatar": q("SELECT count(*) FROM users WHERE avatar ILIKE :p"),
    }


def sql_replace_varchar(db: Session, table: str, column: str, new_base: str, *, dry_run: bool) -> int:
    like = f"%{OLD_HOST}%"
    n = int(
        db.execute(
            text(f"SELECT count(*) FROM {table} WHERE {column} ILIKE :p"),
            {"p": like},
        ).scalar()
        or 0
    )
    if dry_run or n == 0:
        return n
    # REPLACE giữ nguyên path; xử lý https/http
    db.execute(
        text(
            f"""
            UPDATE {table}
            SET {column} = REPLACE(
                  REPLACE(
                    REPLACE({column}, 'https://{OLD_HOST}', :nb),
                    'http://{OLD_HOST}', :nb
                  ),
                  '//{OLD_HOST}', :nb
                )
            WHERE {column} ILIKE :p
            """
        ),
        {"nb": new_base, "p": like},
    )
    return n


def migrate_products(db: Session, new_base: str, *, dry_run: bool, limit: Optional[int]) -> Dict[str, int]:
    like = f"%{OLD_HOST}%"
    sql_ids = text(
        """
        SELECT id FROM products
        WHERE main_image ILIKE :p
           OR video_link ILIKE :p
           OR coalesce(description,'') ILIKE :p
           OR images::text ILIKE :p
           OR gallery::text ILIKE :p
           OR colors::text ILIKE :p
           OR product_info::text ILIKE :p
        ORDER BY id
        """
        + (" LIMIT :lim" if limit else "")
    )
    params: Dict[str, Any] = {"p": like}
    if limit:
        params["lim"] = limit
    ids = [row[0] for row in db.execute(sql_ids, params).fetchall()]
    rows = db.query(Product).filter(Product.id.in_(ids)).order_by(Product.id).all() if ids else []

    products_touched = 0
    strings_changed = 0
    samples: List[str] = []

    for p in rows:
        row_changed = 0

        if p.main_image:
            nxt = rewrite_url(p.main_image, new_base)
            if nxt != p.main_image:
                if len(samples) < 5:
                    samples.append(f"product#{p.id} main_image:\n  {p.main_image}\n  → {nxt}")
                if not dry_run:
                    p.main_image = nxt
                row_changed += 1

        if p.video_link:
            nxt = rewrite_url(p.video_link, new_base)
            if nxt != p.video_link:
                if not dry_run:
                    p.video_link = nxt
                row_changed += 1

        if p.description:
            nxt, c = rewrite_deep(p.description, new_base)
            if c:
                if not dry_run:
                    p.description = nxt
                row_changed += c

        for field, flag in (
            ("images", True),
            ("gallery", True),
            ("colors", True),
            ("product_info", True),
        ):
            cur = getattr(p, field)
            if cur is None:
                continue
            nxt, c = rewrite_deep(cur, new_base)
            if c:
                if not dry_run:
                    setattr(p, field, nxt)
                    flag_modified(p, field)
                row_changed += c

        if row_changed:
            products_touched += 1
            strings_changed += row_changed

    if not dry_run and products_touched:
        db.commit()

    for s in samples:
        print(s)
    return {"products_rows": products_touched, "products_string_changes": strings_changed}


def migrate_sql_tables(db: Session, new_base: str, *, dry_run: bool) -> Dict[str, int]:
    stats: Dict[str, int] = {}
    pairs = [
        ("categories", "image"),
        ("categories", "size_guide_image_url"),
        ("category_seo_meta", "image_1"),
        ("category_seo_meta", "image_2"),
        ("category_seo_meta", "image_3"),
        ("category_seo_meta", "image_4"),
        ("category_seo_meta", "seo_body"),
        ("category_seo_meta", "seo_description"),
        ("order_items", "product_image"),
        ("cart_items", "product_image"),
    ]
    for table, col in pairs:
        try:
            n = sql_replace_varchar(db, table, col, new_base, dry_run=dry_run)
            stats[f"{table}.{col}"] = n
        except Exception as exc:
            stats[f"{table}.{col}_error"] = -1
            print(f"WARN {table}.{col}: {exc}")
    if not dry_run:
        db.commit()
    return stats


def migrate_reviews(db: Session, new_base: str, *, dry_run: bool) -> Dict[str, int]:
    like = f"%{OLD_HOST}%"
    rows = db.execute(
        text("SELECT id, images FROM product_reviews WHERE images::text ILIKE :p"),
        {"p": like},
    ).fetchall()
    touched = 0
    changes = 0
    for rid, images in rows:
        nxt, c = rewrite_deep(images, new_base)
        if not c:
            continue
        touched += 1
        changes += c
        if not dry_run:
            db.execute(
                text("UPDATE product_reviews SET images = CAST(:img AS json) WHERE id = :id"),
                {"img": json.dumps(nxt, ensure_ascii=False), "id": rid},
            )
    if not dry_run and touched:
        db.commit()
    return {"product_reviews_rows": touched, "product_reviews_changes": changes}


def migrate_hero(db: Session, new_base: str, *, dry_run: bool) -> Dict[str, int]:
    like = f"%{OLD_HOST}%"
    try:
        rows = db.execute(
            text("SELECT id, tiles FROM home_hero_category_groups WHERE tiles::text ILIKE :p"),
            {"p": like},
        ).fetchall()
    except Exception as exc:
        print(f"WARN home_hero: {exc}")
        return {"home_hero_rows": 0}
    touched = 0
    changes = 0
    for rid, tiles in rows:
        nxt, c = rewrite_deep(tiles, new_base)
        if not c:
            continue
        touched += 1
        changes += c
        if not dry_run:
            db.execute(
                text("UPDATE home_hero_category_groups SET tiles = CAST(:t AS json) WHERE id = :id"),
                {"t": json.dumps(nxt, ensure_ascii=False), "id": rid},
            )
    if not dry_run and touched:
        db.commit()
    return {"home_hero_rows": touched, "home_hero_changes": changes}


def migrate_drafts(db: Session, new_base: str, *, dry_run: bool) -> Dict[str, int]:
    like = f"%{OLD_HOST}%"
    try:
        rows = db.execute(
            text("SELECT id, product_data FROM product_import_drafts WHERE product_data::text ILIKE :p"),
            {"p": like},
        ).fetchall()
    except Exception as exc:
        print(f"WARN drafts: {exc}")
        return {"drafts_rows": 0}
    touched = 0
    changes = 0
    for rid, pdata in rows:
        nxt, c = rewrite_deep(pdata, new_base)
        if not c:
            continue
        touched += 1
        changes += c
        if not dry_run:
            db.execute(
                text("UPDATE product_import_drafts SET product_data = CAST(:d AS json) WHERE id = :id"),
                {"d": json.dumps(nxt, ensure_ascii=False), "id": rid},
            )
    if not dry_run and touched:
        db.commit()
    return {"drafts_rows": touched, "drafts_changes": changes}


def migrate_users(db: Session, new_base: str, *, dry_run: bool) -> Dict[str, int]:
    n = sql_replace_varchar(db, "users", "avatar", new_base, dry_run=dry_run)
    if not dry_run:
        db.commit()
    return {"users.avatar": n}


def main() -> int:
    parser = argparse.ArgumentParser(description="Rewrite 188comvn.b-cdn.net → cdn.188.com.vn in DB")
    parser.add_argument("--audit", action="store_true", help="Chỉ đếm số bản ghi còn host cũ")
    parser.add_argument("--dry-run", action="store_true", help="Chạy migrate nhưng không commit")
    parser.add_argument("--yes", action="store_true", help="Commit thay đổi")
    parser.add_argument("--new-base", default="", help=f"CDN base mới (mặc định {DEFAULT_NEW_BASE})")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn số products (0 = all)")
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--include-hero", action="store_true")
    parser.add_argument("--include-users", action="store_true")
    args = parser.parse_args()

    if not args.audit and not args.dry_run and not args.yes:
        parser.error("Chọn --audit, --dry-run hoặc --yes")

    new_base = _new_base(args.new_base or None)
    print(f"OLD host: {OLD_HOST}")
    print(f"NEW base: {new_base}")

    db = SessionLocal()
    try:
        if args.audit:
            counts = audit_counts(db)
            total = sum(counts.values())
            print("=== AUDIT (rows containing old host) ===")
            for k, v in counts.items():
                if v:
                    print(f"  {k}: {v}")
            print(f"TOTAL row-hits: {total}")
            return 0

        dry = bool(args.dry_run) and not args.yes
        mode = "DRY-RUN" if dry else "COMMIT"
        print(f"Mode: {mode}")

        stats: Dict[str, int] = {}
        stats.update(
            migrate_products(
                db,
                new_base,
                dry_run=dry,
                limit=args.limit or None,
            )
        )
        stats.update(migrate_sql_tables(db, new_base, dry_run=dry))
        stats.update(migrate_reviews(db, new_base, dry_run=dry))
        if args.include_hero:
            stats.update(migrate_hero(db, new_base, dry_run=dry))
        if args.include_drafts:
            stats.update(migrate_drafts(db, new_base, dry_run=dry))
        if args.include_users:
            stats.update(migrate_users(db, new_base, dry_run=dry))

        print("=== RESULT ===")
        for k, v in stats.items():
            if v:
                print(f"  {k}: {v}")

        if dry:
            print("Dry-run xong — chưa ghi DB. Chạy lại với --yes để commit.")
        else:
            print("Đã commit. Chạy --audit để xác nhận còn 0.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
