"""Báo cáo Excel import ghi lý do bỏ qua từng dòng."""

from openpyxl import load_workbook

from app.services.import_excel_report import write_import_excel_job_report


def test_report_writes_skip_reason_column(tmp_path, monkeypatch):
    job_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    target = tmp_path / f"{job_id}-report.xlsx"
    monkeypatch.setattr(
        "app.services.import_excel_report.import_job_report_path",
        lambda jid: target if jid == job_id else None,
    )

    written = write_import_excel_job_report(
        job_id,
        {
            "created": 1499,
            "updated": 0,
            "deleted": 0,
            "skipped_count": 1,
            "total_processed": 2,
            "success_rate": "50.0%",
            "skipped_rows": [
                {
                    "row": 193,
                    "source_id": "A975332308644",
                    "reason": "Mã cột A đã có trên web — giữ nguyên sản phẩm cũ, không ghi đè, không tạo mới.",
                    "kept_product_id": "A975332308644a188D7885",
                }
            ],
            "errors": ["Dòng 10: thiếu ảnh"],
            "warnings": [],
        },
    )

    assert written is True
    wb = load_workbook(target)
    sheet = wb["Bỏ qua"]
    assert [cell.value for cell in sheet[1]] == [
        "Dòng",
        "Mã cột A",
        "Lý do bỏ qua",
        "Sản phẩm đang giữ",
    ]
    assert sheet["A2"].value == 193
    assert sheet["B2"].value == "A975332308644"
    assert "không ghi đè" in sheet["C2"].value
    assert sheet["D2"].value == "A975332308644a188D7885"
    assert wb["Lỗi"]["A2"].value == "Dòng 10: thiếu ảnh"


def test_report_skipped_when_nothing_to_report(tmp_path, monkeypatch):
    job_id = "11111111-2222-3333-4444-555555555555"
    target = tmp_path / "unused.xlsx"
    monkeypatch.setattr(
        "app.services.import_excel_report.import_job_report_path",
        lambda _jid: target,
    )
    assert write_import_excel_job_report(job_id, {"created": 1, "skipped_rows": []}) is False
    assert not target.exists()
