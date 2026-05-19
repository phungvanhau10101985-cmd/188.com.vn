"""Tạo file Excel mẫu giống API export draft 1688; chạy: python scripts/export_1688_excel_preview.py [url]"""
import json
import os
import sys
from datetime import datetime

import pandas as pd

from app.api.endpoints.import_1688 import (
    _excel_export_columns_and_vi_headers,
    _excel_row_from_product,
)
from app.services.import_1688_scraper import scrape_1688_product
from app.services.import_vipomall_scraper import is_vipomall_import_url, scrape_vipomall_for_import

DEFAULT_URL = "https://detail.1688.com/offer/920080333655.html?offerId=920080333655"


def shorten(v: object, lim: int = 72) -> str:
    if isinstance(v, (dict, list)):
        s = json.dumps(v, ensure_ascii=False)
    else:
        s = str(v)
    s = s.replace("\n", " ")
    return s[:lim] + ("…" if len(s) > lim else "")


def main() -> None:
    url = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL).strip()
    if is_vipomall_import_url(url):
        _, product_data, warnings = scrape_vipomall_for_import(url)
    else:
        _, product_data, warnings = scrape_1688_product(url)

    columns, vietnamese_headers = _excel_export_columns_and_vi_headers()
    row = _excel_row_from_product(product_data)
    df = pd.DataFrame([row], columns=columns)

    export_dir = os.path.join("app", "static", "uploads")
    os.makedirs(export_dir, exist_ok=True)
    filename = f"sample_1688_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(export_dir, filename)

    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Products", index=False, startrow=0)
        ws = writer.sheets["Products"]
        ws.insert_rows(2)
        for idx, header in enumerate(vietnamese_headers, 1):
            ws.cell(row=2, column=idx, value=header)

    print("WARNINGS:", warnings)
    print("FILE:", os.path.abspath(filepath))
    print("\n=== Preview (dòng 1 = key EN, dòng 2 = tiêu đề VN trong Excel) ===\n")
    image_cols = (
        "gallery_images",
        "detail_images",
        "product_info",
    )
    for col_key, vn in zip(columns, vietnamese_headers):
        v = row.get(col_key, "")
        if col_key in image_cols:
            print(f"{vn} ({col_key}):")
            print(shorten(v, 220))
            print()
        elif col_key in ("main_image", "product_url"):
            print(f"{vn}: {v}")
        else:
            print(f"{vn}: {shorten(v, 100)}")


if __name__ == "__main__":
    main()
