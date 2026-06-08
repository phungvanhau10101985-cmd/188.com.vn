#!/usr/bin/env python3
"""Gửi email cảnh báo ops từ shell (monitor-storefront.sh)."""
from __future__ import annotations

import sys

from app.services.ops_health_alert import collect_heavy_process_hints, notify_ops_health_alert


def main() -> int:
    kind = (sys.argv[1] if len(sys.argv) > 1 else "storefront_down").strip()
    title = (sys.argv[2] if len(sys.argv) > 2 else "Storefront không healthy").strip()
    detail = (sys.argv[3] if len(sys.argv) > 3 else "").strip()
    notify_ops_health_alert(
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
