# Lưu trạng thái job import Excel ra file JSON — poll GET vẫn hoạt động sau pm2 restart
# (điều quan trọng khi có thể khởi động lại process giữa lúc import dài).

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

# job_id do uuid4 — chỉ cho phép dạng an toàn để không path traversal
_SAFE_JOB_ID = re.compile(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$", re.I)


def _jobs_root() -> Path:
    # backend/app/services -> backend/
    backend = Path(__file__).resolve().parents[2]
    d = backend / "temp_uploads" / "import_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def persist_import_job(job_id: str, state: Dict[str, Any]) -> None:
    if not _SAFE_JOB_ID.match(job_id or ""):
        return
    path = _jobs_root() / f"{job_id}.json"
    tmp = path.with_suffix(".json.tmp")
    payload = dict(state)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, path)


def load_import_job(job_id: str) -> Optional[Dict[str, Any]]:
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
