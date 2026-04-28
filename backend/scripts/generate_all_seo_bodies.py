# backend/scripts/generate_all_seo_bodies.py
"""
Generate SEO body (đoạn văn 150-300 từ) cho danh mục bằng Gemini.
- Kiểm tra từng danh mục: đã có seo_body thì bỏ qua, chưa có thì tạo mới (không cần --force).
- --force: ghi đè cả khi đã có seo_body.
Lưu vào bảng category_seo_meta.

Cách chạy (từ project root, thư mục chứa backend/):
  python backend/scripts/generate_all_seo_bodies.py
  python backend/scripts/generate_all_seo_bodies.py --force    # Ghi đè cả khi đã có seo_body
  python backend/scripts/generate_all_seo_bodies.py --dry-run   # Chỉ liệt kê path, không gọi Gemini
  python backend/scripts/generate_all_seo_bodies.py --path giay-dep-nam/giay-tay-nam/giay-da-nam  # Chỉ 1 path

Hoặc từ thư mục backend:
  python -m scripts.generate_all_seo_bodies
"""

import sys
import os
import time
import argparse
import re
from typing import List, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.crud import product as crud_product
from app.services.category_seo_service import generate_category_seo_body


def _norm(s: Any) -> str:
    """Chuẩn hóa slug: strip + lowercase để khớp URL."""
    if s is None:
        return ""
    return (s or "").strip().lower()


def _has_seo_links(body: Any) -> bool:
    if not body:
        return False
    text = str(body).lower()
    if "/danh-muc/" in text or "danh-muc/" in text:
        return True
    if "danh-muc" in text and ("href" in text or "<a" in text or "&lt;a" in text):
        return True
    if "<a" not in text and "&lt;a" not in text and "href" not in text:
        return False
    return bool(re.search(r'href=[\"\\\']?[^\"\\\']*?/danh-muc/', text))


def _count_sibling_mentions(body: Any, sibling_names: Any) -> int:
    if not body or not sibling_names:
        return 0
    text = re.sub(r"\s+", " ", str(body).lower())
    count = 0
    for name in sibling_names or []:
        if not name:
            continue
        name_norm = re.sub(r"\s+", " ", str(name).strip().lower())
        if name_norm and name_norm in text:
            count += 1
    return count


def flatten_tree_to_paths(tree: List[Any]) -> List[Tuple[str, Any, Any]]:
    """Từ cây danh mục trả về list (level1_slug, level2_slug?, level3_slug?). Slug đã lowercase."""
    paths = []
    for c1 in tree:
        slug1 = _norm(c1.get("slug") or c1.get("name", ""))
        if not slug1:
            continue
        paths.append((slug1, None, None))
        for c2 in c1.get("children") or []:
            slug2 = _norm(c2.get("slug") or c2.get("name", ""))
            if not slug2:
                continue
            paths.append((slug1, slug2, None))
            for c3 in c2.get("children") or []:
                raw = c3.get("slug") if isinstance(c3, dict) else c3
                name = c3.get("name", raw) if isinstance(c3, dict) else raw
                slug3 = _norm(raw or name)
                if slug3:
                    paths.append((slug1, slug2, slug3))
    return paths


def main():
    parser = argparse.ArgumentParser(description="Generate SEO body cho tất cả danh mục (Gemini)")
    parser.add_argument("--force", action="store_true", help="Ghi đè cả khi đã có seo_body")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ in danh sách path, không gọi API")
    parser.add_argument("--delay", type=float, default=1.5, help="Số giây nghỉ giữa mỗi lần gọi Gemini (mặc định 1.5)")
    parser.add_argument("--path", type=str, default="", help="Chỉ generate 1 path, VD: giay-dep-nam/giay-tay-nam/giay-da-nam")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.path:
            # Chỉ 1 path: tách level1/level2/level3
            parts = [p.strip().lower() for p in args.path.split("/") if p.strip()]
            if not parts:
                print("❌ --path phải có ít nhất 1 segment (vd: giay-dep-nam/giay-tay-nam/giay-da-nam)")
                return
            level1 = parts[0]
            level2 = parts[1] if len(parts) > 1 else None
            level3 = parts[2] if len(parts) > 2 else None
            paths = [(level1, level2, level3)]
            print(f"📂 Chỉ xử lý 1 path: {args.path}")
        else:
            tree = crud_product.get_category_tree_from_products(db, is_active=True)
            paths = flatten_tree_to_paths(tree)
            print(f"📂 Tìm thấy {len(paths)} đường dẫn danh mục.")

        if args.dry_run:
            for p in paths:
                path_str = "/".join(x for x in p if x)
                print(f"  - {path_str}")
            return

        done = 0
        skipped = 0
        failed = 0
        for i, (level1, level2, level3) in enumerate(paths, 1):
            path_str = "/".join(x for x in (level1, level2, level3) if x)
            data = crud_product.get_category_seo_data(
                db,
                level1_slug=level1,
                level2_slug=level2,
                level3_slug=level3,
                is_active=True,
                image_limit=4,
            )
            if not data:
                print(f"  [{i}/{len(paths)}] ⚠️ Bỏ qua (không resolve): {path_str}")
                failed += 1
                continue

            full_name = data.get("full_name", "")
            breadcrumb_names = data.get("breadcrumb_names", [])
            product_count = data.get("product_count", 0)
            sample_names = data.get("sample_product_names") or []
            sibling_names = crud_product.get_category_sibling_names(
                db, level1_slug=level1, level2_slug=level2, level3_slug=level3, is_active=True
            )
            if data.get("seo_body") and not args.force:
                body = data.get("seo_body") or ""
                mentions = _count_sibling_mentions(body, sibling_names)
                if _has_seo_links(body) or mentions > 0:
                    print(f"  [{i}/{len(paths)}] ⏭️ Đã có SEO body và đã gắn link: {path_str}")
                    skipped += 1
                    continue
                if not sibling_names:
                    print(f"  [{i}/{len(paths)}] ⏭️ Đã có SEO body nhưng không có danh mục anh em: {path_str}")
                    skipped += 1
                    continue

            body = generate_category_seo_body(
                category_name=full_name,
                breadcrumb_names=breadcrumb_names,
                product_count=product_count,
                sample_product_names=sample_names,
                related_category_names=sibling_names if sibling_names else None,
            )
            if not body:
                print(f"  [{i}/{len(paths)}] ❌ Gemini không trả về: {path_str}")
                failed += 1
                if args.delay > 0:
                    time.sleep(args.delay)
                continue

            category_path = "/".join(_norm(x) for x in (level1, level2, level3) if x)
            crud_product.set_category_seo_body(db, category_path=category_path, seo_body=body)
            done += 1
            print(f"  [{i}/{len(paths)}] ✅ {path_str} ({len(body)} ký tự)")

            if args.delay > 0:
                time.sleep(args.delay)

        print()
        print(f"✅ Hoàn tất: {done} generated, {skipped} skipped (đã có), {failed} failed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
