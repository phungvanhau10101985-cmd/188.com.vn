"""Ghi lại backend/assets/taxonomy_import_template.xlsx từ taxonomy_admin (đủ cột mọi sheet).

Chạy sau khi sửa schema mẫu trong app/api/endpoints/taxonomy_admin.py:
  python scripts/write_taxonomy_template_asset.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.endpoints.taxonomy_admin import write_taxonomy_schema_template_to_disk  # noqa: E402


def main() -> None:
    p = write_taxonomy_schema_template_to_disk()
    print(f"Wrote {p}")


if __name__ == "__main__":
    main()
