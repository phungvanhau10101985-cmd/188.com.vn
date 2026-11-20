"""Ngưỡng CPU/RAM cả máy: khách đông thì việc nền chờ."""

from __future__ import annotations

import app.services.host_pressure as pressure


def test_iowait_counts_as_busy():
    previous = pressure.cpu_idle_total("cpu 100 0 0 100 0 0 0 0")
    current = pressure.cpu_idle_total("cpu 100 0 0 100 100 0 0 0")
    assert previous is not None and current is not None
    assert pressure.cpu_used_pct(previous, current) == 100.0


def test_idle_cpu_is_not_busy():
    previous = pressure.cpu_idle_total("cpu 0 0 0 100 0 0 0 0")
    current = pressure.cpu_idle_total("cpu 0 0 0 200 0 0 0 0")
    assert previous is not None and current is not None
    assert pressure.cpu_used_pct(previous, current) == 0.0


def test_ram_uses_memavailable_not_memfree():
    text = "\n".join(
        [
            "MemTotal: 10000000 kB",
            "MemFree: 1000000 kB",
            "MemAvailable: 4000000 kB",
        ]
    )
    assert pressure.ram_used_pct_from_meminfo(text) == 60.0


def test_blocks_at_85_and_resumes_at_80():
    assert pressure.decide_blocked(False, 84.9, 10.0) is False
    assert pressure.decide_blocked(False, 85.0, 10.0) is True
    assert pressure.decide_blocked(False, 10.0, 90.0) is True
    assert pressure.decide_blocked(True, 82.0, 10.0) is True
    assert pressure.decide_blocked(True, 80.0, 80.0) is False
    assert pressure.decide_blocked(True, None, 70.0) is False


def test_host_blocks_background_can_read_previous_state(monkeypatch):
    pressure.reset_for_tests()
    monkeypatch.setattr(pressure, "pressure_enabled", lambda: True)
    monkeypatch.setattr(pressure, "_linux_proc", lambda: True)
    monkeypatch.setattr(pressure, "_ensure_sampler", lambda: None)
    monkeypatch.setattr(pressure, "_read_ram_used_pct", lambda: 10.0)
    assert pressure.host_blocks_background() is False
    assert pressure.host_blocks_background() is False


def test_missing_sample_does_not_block_by_itself():
    assert pressure.decide_blocked(False, None, 10.0) is False
    assert pressure.decide_blocked(False, None, None) is False
