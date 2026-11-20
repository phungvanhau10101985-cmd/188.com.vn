"""Cảnh báo trang trạng thái máy — không đụng DB."""

from app.services.server_status_snapshot import build_warnings, reset_cpu_sample_for_tests


def test_low_ram_and_cpu_warn():
    warnings = build_warnings(
        mem_available_mb=1500,
        min_available_mb=2000,
        cpu_used_pct=90,
        ram_used_pct=40,
        block_pct=85,
        localization_waiting=True,
        localization_error="hết bộ nhớ",
        error_lines=["Có 2 lỗi HTTP 5xx trong 6 giờ qua."],
    )
    texts = [item["text"] for item in warnings]
    assert any("1500MB" in text for text in texts)
    assert any("CPU" in text for text in texts)
    assert any("chờ RAM" in text for text in texts)
    assert any("hết bộ nhớ" in text for text in texts)
    assert any("5xx" in text for text in texts)


def test_quiet_machine_has_no_warning():
    reset_cpu_sample_for_tests()
    warnings = build_warnings(
        mem_available_mb=3000,
        min_available_mb=2000,
        cpu_used_pct=20,
        ram_used_pct=50,
        block_pct=85,
        localization_waiting=False,
        localization_error=None,
        error_lines=[],
    )
    assert warnings == []
