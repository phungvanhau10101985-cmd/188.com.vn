"""Kiểm tra nhanh tab catalog Google Sheet."""
from app.services.google_sheets_sku_sync import _escape_sheet_title, _get_sheets_service, _sheet_title_for_gid

SPREAD = "1iRaVEHjRupYRiB6sVv87m43EaZlR_I1laCuCL77CzRw"
GID = 1079257836


def main() -> None:
    svc = _get_sheets_service()
    title = _sheet_title_for_gid(svc, SPREAD, GID)
    t = _escape_sheet_title(title)
    meta = svc.spreadsheets().get(spreadsheetId=SPREAD).execute()
    for s in meta.get("sheets", []):
        p = s.get("properties") or {}
        if p.get("sheetId") == GID:
            g = p.get("gridProperties") or {}
            print(f"tab: {p.get('title')}")
            print(f"grid: {g.get('rowCount')} rows x {g.get('columnCount')} cols")
            break
    for rng, label in (
        (f"{t}!A1:E2", "header"),
        (f"{t}!A3:E3", "row1"),
        (f"{t}!A30464:E30464", "last"),
    ):
        r = svc.spreadsheets().values().get(spreadsheetId=SPREAD, range=rng).execute()
        print(label, ":", r.get("values"))


if __name__ == "__main__":
    main()
