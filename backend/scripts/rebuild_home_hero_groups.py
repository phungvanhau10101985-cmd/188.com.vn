#!/usr/bin/env python3
"""Tính lại 4 nhóm tile hero trang chủ (2 Nam + 2 Nữ) từ lượt xem SP."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.crud.home_hero_category_cache import rebuild_home_hero_category_groups


def main() -> None:
    db = SessionLocal()
    try:
        summary = rebuild_home_hero_category_groups(db)
        print("OK:", summary)
    finally:
        db.close()


if __name__ == "__main__":
    main()
