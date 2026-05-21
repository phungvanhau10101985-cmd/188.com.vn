"""
Lọc offer 1688 **chưa có PDP thật** trên vipomall.vn, xuất Excel import Hibox.

Đầu vào: .xlsx giống batch admin (cột Link / Link SP + Giá Tệ / China price).
Đầu ra: chỉ các dòng chưa có trên Vipomall; cột Link đổi sang https://hibox.mn/v/abb-{offerId}.

Chạy từ thư mục backend (cần Playwright):

  cd backend
  set PYTHONPATH=.
  python scripts/filter_1688_not_on_vipomall.py ..\\222222222222222.xlsx -o ..\\out_not_on_vipomall.xlsx
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.services.import_1688_scraper import extract_offer_id
from app.services.import_hibox_scraper import normalize_product_import_url
from app.services.import_link_excel_batch import parse_link_import_excel
from app.services.vipomall_source_stock import probe_vipomall_1688_offer_listed


def _hibox_url_for_offer(offer_id: str) -> str:
    return f"https://hibox.mn/v/abb-{offer_id}"


def filter_rows(parsed: List[Dict[str, Any]], *, skip_probe: bool) -> tuple[List[Dict[str, Any]], List[str]]:
    kept: List[Dict[str, Any]] = []
    notes: List[str] = []
    for it in parsed:
        row_no = it.get("excel_row")
        url = normalize_product_import_url(str(it.get("url") or ""))
        oid = extract_offer_id(url) or ""
        if not oid.isdigit():
            notes.append(f"Dòng {row_no}: bỏ — không đọc được offerId 1688 từ URL.")
            continue
        if skip_probe:
            listed = False
            detail = None
        else:
            listed, detail = probe_vipomall_1688_offer_listed(oid)
        if listed:
            notes.append(f"Dòng {row_no}: offer {oid} đã có trên Vipomall — bỏ qua.")
            continue
        if detail:
            notes.append(f"Dòng {row_no}: offer {oid} — Vipomall probe: {detail}")
        out = dict(it)
        out["url"] = _hibox_url_for_offer(oid)
        out["offer_id_1688"] = oid
        out["vipomall_url"] = f"https://vipomall.vn/san-pham/{oid}?platform_type=10"
        kept.append(out)
    return kept, notes


def _write_listing_excel(rows: List[Dict[str, Any]], out_path: Path) -> None:
    """Hai dòng nhãn EN/VI tối thiểu cho parse_link_import_excel / batch admin."""
    data_rows = []
    for r in rows:
        ov = r.get("overlays") if isinstance(r.get("overlays"), dict) else {}
        data_rows.append(
            {
                "ID SP": ov.get("product_id") or "",
                "Link SP": r.get("url") or "",
                "shop_name_chinese": ov.get("shop_name_chinese") or "",
                "China price": ov.get("pro_lower_price") or "",
                "chinese_name": ov.get("chinese_name") or "",
            }
        )
    df = pd.DataFrame(data_rows)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False, startrow=0)
        ws = writer.sheets["Sheet1"]
        ws.insert_rows(1)
        headers_en = ["ID SP", "", "Link SP", "shop_name_chinese", "China price", "chinese_name"]
        headers_vi = ["Mã SP", "", "Link SP", "Shop Trung Quốc", "Giá Tệ", "Tên tiếng Trung"]
        for col_idx, (en, vi) in enumerate(zip(headers_en, headers_vi), 1):
            ws.cell(row=1, column=col_idx, value=en)
            ws.cell(row=2, column=col_idx, value=vi)


def main() -> None:
    ap = argparse.ArgumentParser(description="Lọc offer 1688 chưa có trên vipomall.vn → Excel Hibox.")
    ap.add_argument("input_xlsx", type=Path, help="File .xlsx có cột Link + Giá Tệ")
    ap.add_argument("-o", "--output", type=Path, required=True, help="File .xlsx đầu ra (import admin)")
    ap.add_argument(
        "--skip-vipomall-probe",
        action="store_true",
        help="Không mở Vipomall (giữ mọi dòng có offerId, chỉ đổi link sang Hibox).",
    )
    args = ap.parse_args()
    inp = args.input_xlsx.resolve()
    if not inp.is_file():
        raise SystemExit(f"Không tìm thấy file: {inp}")

    parsed, pskip = parse_link_import_excel(inp)
    kept, notes = filter_rows(parsed, skip_probe=args.skip_vipomall_probe)
    notes.extend(pskip)

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if kept:
        _write_listing_excel(kept, out)
    else:
        _write_listing_excel([], out)

    print(f"Đã đọc {len(parsed)} dòng link hợp lệ.")
    print(f"Giữ {len(kept)} dòng chưa có (hoặc không xác nhận được) trên Vipomall.")
    print(f"File: {out}")
    if notes:
        print("\nGhi chú:")
        for n in notes[:40]:
            print(" -", n)
        if len(notes) > 40:
            print(f" … và {len(notes) - 40} dòng ghi chú khác.")


if __name__ == "__main__":
    main()
