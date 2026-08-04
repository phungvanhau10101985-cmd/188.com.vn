#!/usr/bin/env python3
"""Gửi email cảnh báo ops đồng bộ từ shell (monitor/watchdog)."""
from __future__ import annotations

import sys

from app.services.ops_health_alert import collect_heavy_process_hints, send_ops_health_alert_sync


def main() -> int:
    kind = (sys.argv[1] if len(sys.argv) > 1 else "storefront_down").strip()
    title = (sys.argv[2] if len(sys.argv) > 2 else "Storefront không healthy").strip()
    detail = (sys.argv[3] if len(sys.argv) > 3 else "").strip()
    # CLI kết thúc ngay sau main(); phải gửi đồng bộ thay vì daemon thread,
    # nếu không email có thể bị huỷ khi Python process exit.
    send_ops_health_alert_sync(
        kind,
        title,
        detail=detail or title,
        heavy_hints=collect_heavy_process_hints(),
        action="Chạy block lệnh SSH trong email (free-api-now + health-check).",
        force=True,
    )
    print("ops alert queued:", kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
