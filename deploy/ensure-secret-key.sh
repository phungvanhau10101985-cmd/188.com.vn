#!/usr/bin/env bash
# Đảm bảo backend/.env có SECRET_KEY mạnh.
# - Lần đầu / key yếu (trống, fallback cũ, placeholder) → generate ngẫu nhiên và lưu .env
# - Key hợp lệ đã có → giữ nguyên (không rotate mỗi deploy)
#
# Gọi tự động từ deploy/update-vps.sh hoặc tay:
#   bash deploy/ensure-secret-key.sh
set -euo pipefail

ROOT="${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
ENV_FILE="${ROOT}/backend/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "    (bỏ qua ensure-secret-key — chưa có ${ENV_FILE})"
  exit 0
fi

PYTHON="${ROOT}/backend/.venv/bin/python"
if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
fi
if [[ -z "${PYTHON}" ]]; then
  echo "    (bỏ qua ensure-secret-key — chưa có python)"
  exit 0
fi

export ENV_FILE
"${PYTHON}" <<'PY'
import os
import re
import secrets
import shutil
from datetime import datetime
from pathlib import Path

env_file = Path(os.environ["ENV_FILE"])
historical = "H8$kL3!pQ7@mR2#sV5%wZ9^yB1*nJ4(cF6_gH0)dA+eQ~lO{iU[Y}8P]3rT|5W"
blocked = {
    "",
    historical,
    "your-secret-key-change-in-production",
}


def read_secret_key(text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^\s*SECRET_KEY=(.*)$", line)
        if match:
            value = match.group(1).strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            return value
    return ""


def is_weak(key: str) -> bool:
    if not key or key in blocked:
        return True
    if "change-this" in key:
        return True
    return False


def upsert_secret_key(text: str, new_key: str) -> str:
    lines = text.splitlines()
    replaced = False
    out: list[str] = []
    for line in lines:
        if re.match(r"^\s*SECRET_KEY=", line):
            out.append(f"SECRET_KEY={new_key}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.append(f"SECRET_KEY={new_key}")
    trailing_newline = text.endswith("\n")
    body = "\n".join(out)
    return body + ("\n" if trailing_newline or not body.endswith("\n") else "")


text = env_file.read_text(encoding="utf-8")
current = read_secret_key(text)

if not is_weak(current):
    print("✓ SECRET_KEY: giữ nguyên (đã cấu hình)")
    raise SystemExit(0)

new_key = secrets.token_urlsafe(48)
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = env_file.with_name(f".env.bak-secret-key-{stamp}")
shutil.copy2(env_file, backup)

env_file.write_text(upsert_secret_key(text, new_key), encoding="utf-8")
print("✓ SECRET_KEY: đã generate key mới và lưu backend/.env")
print(f"  backup: {backup.name}")
if current:
    print("  ⚠️  Key cũ bị coi là yếu — mọi phiên JWT / cookie tin cậy sẽ hết hiệu lực sau restart API.")
else:
    print("  ℹ️  Lần đầu cấu hình — không ảnh hưởng deploy sau (key giữ cố định).")
PY
