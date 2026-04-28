#!/usr/bin/env python3
"""
Đẩy ảnh đang nằm trên filesystem (backend/app/static/...) lên Bunny Storage,
rồi cập nhật URL trong database (products, categories, SEO meta, review).

Chạy từ thư mục backend:

  cd backend
  python scripts/migrate_images_to_bunny.py --dry-run
  python scripts/migrate_images_to_bunny.py

Biến môi trường (backend/.env):
  BUNNY_STORAGE_ZONE_NAME=188-com-vn-cdn
  BUNNY_STORAGE_ACCESS_KEY=...           # không commit
  BUNNY_CDN_PUBLIC_BASE=https://188comvn.b-cdn.net   # Pull Zone (custom host: sau DNS → cùng Pull Zone)

Đồng bộ frontend: NEXT_PUBLIC_CDN_URL trùng BUNNY_CDN_PUBLIC_BASE (hoặc domain trỏ Pull Zone).
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env():
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT.parent / ".env")
    except ImportError:
        pass


def _img_ext_ok(name: str) -> bool:
    return name.lower().rsplit(".", 1)[-1] in (
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp",
        "avif",
        "svg",
        "bmp",
    )


def resolve_local_under_static(static_dir: Path, raw: str) -> Optional[Path]:
    """Map URL/path trong DB sang file local trong app/static."""
    raw = (raw or "").strip()
    if not raw or raw.startswith("data:"):
        return None
    if any(x in raw.lower() for x in ("bunny", "b-cdn.net")):
        return None

    u = urlparse(raw) if raw.startswith(("http://", "https://")) else None
    path_only = raw
    base_hint = os.getenv("BUNNY_CDN_PUBLIC_BASE", "").strip().rstrip("/")
    if u and u.scheme and u.netloc:
        if base_hint and raw.startswith(base_hint):
            return None
        path_only = u.path or ""
    path_only = unquote(path_only.split("#")[0].split("?")[0])

    # /static/uploads/foo.jpg -> uploads/foo relative to static_dir
    if "/static/" in path_only:
        rel = path_only.split("/static/", 1)[1].lstrip("/")
    elif path_only.startswith("/static/"):
        rel = path_only[len("/static/") :].lstrip("/")
    elif path_only.startswith("/uploads/"):
        rel = path_only.lstrip("/")
    elif path_only.startswith("uploads/"):
        rel = path_only
    else:
        return None

    candidate = static_dir / rel
    try:
        r = candidate.resolve()
    except OSError:
        return None
    if not r.exists() or not r.is_file():
        return None
    if _img_ext_ok(r.name):
        return r
    return None


def iter_product_image_urls(rows) -> List[str]:
    out: List[str] = []

    def from_json(blob: Any) -> None:
        if isinstance(blob, str) and blob.strip():
            out.append(blob.strip())
        elif isinstance(blob, list):
            for it in blob:
                if isinstance(it, str) and it.strip():
                    out.append(it.strip())
                elif isinstance(it, dict):
                    for key in ("url", "src", "image"):
                        v = it.get(key)
                        if isinstance(v, str) and v.strip():
                            out.append(v.strip())

    for p in rows:
        if getattr(p, "main_image", None):
            s = str(p.main_image).strip()
            if s:
                out.append(s)
        from_json(getattr(p, "images", None))
        from_json(getattr(p, "gallery", None))
    return out


def collect_unique_paths(static_dir: Path, urls: List[str]) -> Tuple[Dict[Path, List[str]], List[str]]:
    """path_resolved -> [db url strings chỉ vào đúng file đó]."""
    m: Dict[Path, List[str]] = defaultdict(list)
    bad: List[str] = []

    seen_u: Set[str] = set()
    for u in urls:
        if not u or u in seen_u:
            continue
        seen_u.add(u)
        loc = resolve_local_under_static(static_dir, u)
        if not loc:
            continue
        r = loc.resolve()
        if u not in m[r]:
            m[r].append(u)
    return dict(m), bad


def posix_rel_from_static(static_dir: Path, resolved: Path) -> str:
    try:
        rel = resolved.resolve().relative_to(static_dir.resolve())
    except ValueError:
        return resolved.name.replace("\\", "/")
    return rel.as_posix()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in kế hoạch, không upload / không commit DB")
    args = parser.parse_args()

    load_env()
    os.chdir(ROOT)

    zone = os.getenv("BUNNY_STORAGE_ZONE_NAME", "").strip()
    key = os.getenv("BUNNY_STORAGE_ACCESS_KEY", "").strip()
    cdn_base = os.getenv("BUNNY_CDN_PUBLIC_BASE", "").strip().rstrip("/")

    if not args.dry_run and (not zone or not key or not cdn_base):
        print("Thiếu BUNNY_STORAGE_ZONE_NAME / BUNNY_STORAGE_ACCESS_KEY / BUNNY_CDN_PUBLIC_BASE trong .env")
        sys.exit(2)

    static_dir = (ROOT / "app" / "static").resolve()
    prefix = os.getenv("BUNNY_UPLOAD_PATH_PREFIX", "site").strip().strip("/") or "site"

    from sqlalchemy.orm import Session

    from app.db.session import SessionLocal
    from app.models.category import Category
    from app.models.category_seo import CategorySeoMeta
    from app.models.cart import CartItem
    from app.models.order import OrderItem
    from app.models.product import Product
    from app.models.product_review import ProductReview
    from app.services.bunny_storage import build_public_object_url, upload_file_to_zone

    db: Session = SessionLocal()
    try:
        urls: List[str] = []

        products = db.query(Product).all()
        urls.extend(iter_product_image_urls(products))

        for cat in db.query(Category).all():
            if cat.image:
                urls.append(cat.image.strip())

        for meta in db.query(CategorySeoMeta).all():
            for i in ("image_1", "image_2", "image_3", "image_4"):
                v = getattr(meta, i, None)
                if isinstance(v, str) and v.strip():
                    urls.append(v.strip())

        for rv in db.query(ProductReview).all():
            imgs = getattr(rv, "images", None) or []
            if isinstance(imgs, list):
                for it in imgs:
                    if isinstance(it, str) and it.strip():
                        urls.append(it.strip())

        for oi in db.query(OrderItem).all():
            if oi.product_image and str(oi.product_image).strip():
                urls.append(str(oi.product_image).strip())

        for ci in db.query(CartItem).all():
            if ci.product_image and str(ci.product_image).strip():
                urls.append(str(ci.product_image).strip())

        path_map, _ = collect_unique_paths(static_dir, urls)
        total_files = len(path_map)

        url_to_final: Dict[str, str] = {}

        upload_order: List[Tuple[Path, List[str]]] = sorted(path_map.items(), key=lambda x: str(x[0]))

        print(f"[info] Static dir: {static_dir}")
        print(f"[info] File ảnh local duy nhất (từ URL trong DB): {total_files}")

        for lp, originals in upload_order:
            rel = posix_rel_from_static(static_dir, lp)
            remote_rel = f"{prefix}/{rel}"
            if args.dry_run:
                tgt = build_public_object_url(cdn_base or "https://CDN_NOT_SET", remote_rel)
                for o in originals:
                    url_to_final[o] = tgt
                print(f"  dry-run  PUT {remote_rel}")
                continue

            data = lp.read_bytes()
            upload_file_to_zone(
                zone_name=zone,
                access_key=key,
                remote_path=remote_rel.replace("\\", "/"),
                data=data,
            )
            tgt = build_public_object_url(cdn_base, remote_rel)
            for o in originals:
                url_to_final[o] = tgt
            print(f"  ok  {remote_rel} -> {tgt}")

        if not upload_order:
            print("[info] Không có URL ảnh local nào map được tới file trong app/static. Kết thúc.")
            return

        changed = {
            "products": 0,
            "categories": 0,
            "seo_meta": 0,
            "reviews": 0,
            "order_items": 0,
            "cart_items": 0,
        }

        def rep(s: Optional[str]) -> Optional[str]:
            if not s:
                return s
            t = url_to_final.get(s.strip())
            return t if t else s

        def rewrite_json_urls(val: Any) -> Any:
            """Mọi chuỗi trùng key url_to_final được thay (nested list/dict)."""
            if isinstance(val, str):
                return url_to_final.get(val, val)
            if isinstance(val, list):
                return [rewrite_json_urls(v) for v in val]
            if isinstance(val, dict):
                return {k: rewrite_json_urls(v) for k, v in val.items()}
            return val

        if args.dry_run:
            print(f"[dry-run] Sẽ ghi nhận URL CDN trên `{cdn_base}/{prefix}/…` — không upload, không ghi DB.")
            return


        for p in products:
            upd = False
            if p.main_image:
                nm = rep(str(p.main_image))
                if nm and nm != str(p.main_image):
                    p.main_image = nm
                    upd = True
            nim = rewrite_json_urls(getattr(p, "images", None))
            ng = rewrite_json_urls(getattr(p, "gallery", None))
            if nim != p.images:
                p.images = nim
                upd = True
            if ng != p.gallery:
                p.gallery = ng
                upd = True
            if upd:
                changed["products"] += 1

        for cat in db.query(Category).all():
            if cat.image:
                nc = rep(cat.image)
                if nc and nc != cat.image:
                    cat.image = nc
                    changed["categories"] += 1

        for meta in db.query(CategorySeoMeta).all():
            upm = False
            for fld in ("image_1", "image_2", "image_3", "image_4"):
                v = getattr(meta, fld, None)
                if isinstance(v, str):
                    nv = rep(v)
                    if nv and nv != v:
                        setattr(meta, fld, nv)
                        upm = True
            if upm:
                changed["seo_meta"] += 1

        for rv in db.query(ProductReview).all():
            nim = rewrite_json_urls(getattr(rv, "images", None))
            if nim != getattr(rv, "images", None):
                rv.images = nim
                changed["reviews"] += 1

        for oi in db.query(OrderItem).all():
            if oi.product_image:
                ni = rep(str(oi.product_image))
                if ni and ni != str(oi.product_image):
                    oi.product_image = ni
                    changed["order_items"] += 1

        for ci in db.query(CartItem).all():
            if ci.product_image:
                ni = rep(str(ci.product_image))
                if ni and ni != str(ci.product_image):
                    ci.product_image = ni
                    changed["cart_items"] += 1

        db.commit()
        print(
            f"[done] Cập nhật DB — products:{changed['products']} cats:{changed['categories']} seo:{changed['seo_meta']} reviews:{changed['reviews']} order_items:{changed['order_items']} cart_items:{changed['cart_items']}"
        )

    finally:
        db.close()


if __name__ == "__main__":
    main()
