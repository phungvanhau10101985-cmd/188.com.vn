from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from typing import Any

import pandas as pd

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
