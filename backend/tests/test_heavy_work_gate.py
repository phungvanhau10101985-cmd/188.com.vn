"""Lượt việc nặng: cào ưu tiên, nguồn hàng chạy tiếp, không hoãn sang buổi tối."""

from __future__ import annotations

import json
import threading
import time

import pytest

import app.services.heavy_work_gate as gate
import app.services.host_pressure as pressure


@pytest.fixture
def isolated_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "GATE_DIR", tmp_path)
    monkeypatch.setenv("HEAVY_WORK_GATE_ENABLED", "1")
    gate.reset_for_tests()
    yield gate
    gate.reset_for_tests()


def test_disabled_gate_does_not_exclude(isolated_gate, monkeypatch):
    monkeypatch.setenv("HEAVY_WORK_GATE_ENABLED", "0")
    crawl = isolated_gate.poll_heavy_work("listing_crawl", camp=False)
    stock = isolated_gate.poll_heavy_work("source_stock", camp=False)
    assert crawl is not None
    assert stock is not None


def test_stock_keeps_running_beside_localization(isolated_gate):
    stock = isolated_gate.poll_heavy_work("source_stock", camp=False)
    imgloc = isolated_gate.poll_heavy_work("image_localization", camp=False)
    try:
        assert stock is not None
        assert imgloc is not None
    finally:
        stock.release()
        imgloc.release()


def test_crawl_blocks_stock_then_stock_resumes(isolated_gate):
    crawl = isolated_gate.poll_heavy_work("listing_crawl", camp=False)
    imgloc = isolated_gate.poll_heavy_work("image_localization", camp=False)
    stock = isolated_gate.poll_heavy_work("source_stock", camp=False)
    try:
        assert crawl is not None
        assert imgloc is not None
        assert stock is None
    finally:
        crawl.release()
        imgloc.release()

    resumed = isolated_gate.poll_heavy_work("source_stock", camp=False)
    assert resumed is not None
    resumed.release()


def test_waiting_crawl_takes_browser_before_stock(isolated_gate):
    stock = isolated_gate.poll_heavy_work("source_stock", camp=False)
    got = {}

    def crawl() -> None:
        with isolated_gate.heavy_work_slot("listing_crawl", poll_seconds=0.05):
            got["crawl"] = True
            time.sleep(0.25)

    worker = threading.Thread(target=crawl)
    worker.start()
    time.sleep(0.12)
    stock.release()
    time.sleep(0.12)
    again = isolated_gate.poll_heavy_work("source_stock", camp=False)
    try:
        assert again is None
        assert got.get("crawl") is True
    finally:
        if again is not None:
            again.release()
        worker.join(timeout=3)
        assert not worker.is_alive()


def test_localization_yields_turn_to_outfit_queue(isolated_gate):
    outfit = isolated_gate.poll_heavy_work("outfit_visual", camp=False)
    assert isolated_gate.poll_heavy_work("image_localization", camp=True) is None
    outfit.release()

    outfit_again = isolated_gate.poll_heavy_work("outfit_visual", camp=True)
    imgloc = isolated_gate.poll_heavy_work("image_localization", camp=True)
    try:
        assert outfit_again is None
        assert imgloc is not None
    finally:
        if imgloc is not None:
            imgloc.release()
        isolated_gate.clear_camp("outfit_visual")
        isolated_gate.clear_camp("image_localization")


def test_two_crawls_do_not_overlap(isolated_gate):
    state = {"n": 0, "max": 0}
    lock = threading.Lock()

    def run() -> None:
        with isolated_gate.heavy_work_slot("listing_crawl", poll_seconds=0.02):
            with lock:
                state["n"] += 1
                state["max"] = max(state["max"], state["n"])
            time.sleep(0.2)
            with lock:
                state["n"] -= 1

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert state["max"] == 1
    assert state["n"] == 0


def test_stale_hold_is_reclaimed_without_waiting_for_evening(isolated_gate):
    stock = isolated_gate.poll_heavy_work("source_stock", camp=False)
    stock._stop.set()
    stock._thread.join(timeout=2)
    path = isolated_gate.GATE_DIR / "hold__browser.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["heartbeat"] = 0
    path.write_text(json.dumps(data), encoding="utf-8")

    crawl = isolated_gate.poll_heavy_work("listing_crawl", camp=False)
    try:
        assert crawl is not None
        held = json.loads(path.read_text(encoding="utf-8"))
        assert held["role"] == "listing_crawl"
    finally:
        if crawl is not None:
            crawl.release()


def test_busy_host_makes_every_new_background_task_wait(isolated_gate, monkeypatch):
    monkeypatch.setattr(pressure, "host_blocks_background", lambda: True)
    assert isolated_gate.poll_heavy_work("source_stock", camp=False) is None
    assert isolated_gate.poll_heavy_work("listing_crawl", camp=False) is None
    assert isolated_gate.poll_heavy_work("image_localization", camp=False) is None
    assert isolated_gate.poll_heavy_work("outfit_visual", camp=False) is None
