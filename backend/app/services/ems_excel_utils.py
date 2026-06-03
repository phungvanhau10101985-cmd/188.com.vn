from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any, Optional

import pandas as pd

_EXCEL_DATE_RE = re.compile(
    r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})",
    re.IGNORECASE,
)

_SS_NS = "{urn:schemas-microsoft-com:office:spreadsheet}"


def _read_xml_spreadsheet_rows(file_bytes: bytes) -> list[tuple[Any, ...]]:
    root = ET.fromstring(file_bytes)
    rows: list[tuple[Any, ...]] = []
    table = root.find(f".//{_SS_NS}Table")
    if table is None:
        return rows

    for row_el in table.findall(f"{_SS_NS}Row"):
        cells: dict[int, Any] = {}
        col_idx = 1
        for cell in row_el.findall(f"{_SS_NS}Cell"):
            index_attr = cell.get(f"{_SS_NS}Index")
            if index_attr:
                col_idx = int(index_attr)
            data_el = cell.find(f"{_SS_NS}Data")
            value: Any = None
            if data_el is not None and data_el.text is not None:
                data_type = data_el.get(f"{_SS_NS}Type") or "String"
                text = data_el.text.strip()
                if data_type == "Number":
                    try:
                        value = float(text)
                        if value == int(value):
                            value = int(value)
                    except ValueError:
                        value = text
                else:
                    value = text
            cells[col_idx] = value
            col_idx += 1

        if not cells:
            rows.append(tuple())
            continue
        max_col = max(cells)
        row_tuple = tuple(cells.get(i) for i in range(1, max_col + 1))
        rows.append(row_tuple)
    return rows


def parse_excel_date_cell(value: Any) -> Optional[date]:
    """Đọc ngày từ ô Excel: datetime, chuỗi «Ngày trả tiền: 02/06/2026», v.v."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    if len(text) >= 10 and text[4:5] == "-":
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    match = _EXCEL_DATE_RE.search(text)
    if not match:
        return None
    day, month, year = match.groups()
    y = int(year)
    if y < 100:
        y += 2000
    try:
        return date(y, int(month), int(day))
    except ValueError:
        return None


def read_spreadsheet_rows(file_bytes: bytes, filename: str = "") -> list[tuple[Any, ...]]:
    stripped = file_bytes.lstrip()
    if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
        return _read_xml_spreadsheet_rows(file_bytes)

    lower = (filename or "").lower()
    if lower.endswith(".xls"):
        df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="xlrd")
    else:
        df = pd.read_excel(io.BytesIO(file_bytes), header=None, engine="openpyxl")
    return [tuple(row) for row in df.itertuples(index=False, name=None)]
