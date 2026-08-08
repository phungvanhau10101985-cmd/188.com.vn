"""Persist / load job đăng sản phẩm thủ công + AI (JSON trong temp_uploads)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

_SAFE_JOB_ID = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)


def _jobs_root() -> Path:
    backend = Path(__file__).resolve().parents[2]
    d = backend / "temp_uploads" / "manual_product_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def persist_job(job_id: str, state: Dict[str, Any]) -> None:
    if not _SAFE_JOB_ID.match(job_id or ""):
        return
    path = _jobs_root() / f"{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_job(job_id: str) -> Optional[Dict[str, Any]]:
    if not _SAFE_JOB_ID.match(job_id or ""):
        return None
    path = _jobs_root() / f"{job_id}.json"
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_jobs(
    *,
    active_only: bool = True,
    limit: int = 30,
    created_by: Optional[int] = None,
) -> list[Dict[str, Any]]:
    """Liệt kê job (mới nhất trước) — dùng khôi phục phiên sau mất điện."""
    _DONE = frozenset({"done"})
    root = _jobs_root()
    rows: list[Dict[str, Any]] = []
    paths = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in paths:
        if path.suffix == ".tmp" or path.name.endswith(".json.tmp"):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(state, dict):
            continue
        if created_by is not None and state.get("created_by") != created_by:
            continue
        status = str(state.get("status") or "").strip()
        if active_only and status in _DONE:
            continue
        rows.append(state)
        if len(rows) >= max(1, min(limit, 100)):
            break
    return rows
