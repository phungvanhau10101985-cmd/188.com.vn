#!/usr/bin/env bash
# Apply OOM long-term mitigations on VPS (one-shot).
set -euo pipefail
ROOT=/var/www/188.com.vn
ENVF="${ROOT}/backend/.env"

chmod +x "${ROOT}/deploy/watchdog-web.sh" "${ROOT}/deploy/watchdog-api.sh"

upsert() {
  local key="$1" val="$2" file="$3"
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}=.*|${key}=${val}|" "$file"
    echo "updated ${key}=${val}"
  else
    printf '\n%s=%s\n' "${key}" "${val}" >>"$file"
    echo "added ${key}=${val}"
  fi
}

upsert IMAGE_LOCALIZATION_WORKER_MAX_AS_MB 3200 "${ENVF}"
upsert IMAGE_LOCALIZATION_RESUME_MIN_AVAILABLE_MB 2800 "${ENVF}"
upsert IMAGE_LOCALIZATION_MAX_AUTO_RESUME_COUNT 6 "${ENVF}"
upsert IMAGE_LOCALIZATION_MERGE_MAX_PIXELS 25000000 "${ENVF}"
upsert IMAGE_LOCALIZATION_JOB_RESUME_ON_STARTUP true "${ENVF}"

CRON_LINE='*/2 * * * * cd /var/www/188.com.vn && bash deploy/watchdog-web.sh >> /var/log/188-watchdog-web.log 2>&1'
tmp="$(mktemp)"
crontab -l 2>/dev/null | grep -v 'watchdog-web.sh' >"${tmp}" || true
echo "${CRON_LINE}" >>"${tmp}"
crontab "${tmp}"
rm -f "${tmp}"
echo "crontab watchdog-web installed"
crontab -l | grep -E 'watchdog' || true

# Patch nanoai verify-edge-stack: auto-start thu-do-online when :3000 down
EDGE=/var/www/Thu-do-online/deploy/verify-edge-stack.sh
if [[ -f "${EDGE}" ]] && ! grep -q 'AUTOFIX_PM2_NANOAI' "${EDGE}"; then
  cp -a "${EDGE}" "${EDGE}.bak-oomfix"
  python3 - <<'PY'
from pathlib import Path
p = Path("/var/www/Thu-do-online/deploy/verify-edge-stack.sh")
text = p.read_text(encoding="utf-8")
needle = 'if ! curl -fsS --max-time 15 -o /dev/null "http://127.0.0.1:3000/"; then\n  fail "App không phản hồi http://127.0.0.1:3000/ — kiểm tra: pm2 status"\nelse\n  note "  OK: http://127.0.0.1:3000/"\nfi'
replacement = '''# AUTOFIX_PM2_NANOAI — tự kéo thu-do-online khi OOM/watchdog API làm mất app
if ! curl -fsS --max-time 15 -o /dev/null "http://127.0.0.1:3000/"; then
  note "  App :3000 down — thử pm2 start thu-do-online..."
  if [[ -f "${APP_DIR}/ecosystem.config.cjs" ]]; then
    if pm2 describe thu-do-online &>/dev/null; then
      pm2 restart thu-do-online --update-env >/dev/null 2>&1 || true
    else
      pm2 start "${APP_DIR}/ecosystem.config.cjs" --only thu-do-online >/dev/null 2>&1 || true
    fi
    sleep 3
  fi
  if curl -fsS --max-time 15 -o /dev/null "http://127.0.0.1:3000/"; then
    note "  OK: đã recover http://127.0.0.1:3000/"
    pm2 save >/dev/null 2>&1 || true
  else
    fail "App không phản hồi http://127.0.0.1:3000/ — kiểm tra: pm2 status"
  fi
else
  note "  OK: http://127.0.0.1:3000/"
fi'''
if needle not in text:
    raise SystemExit("needle not found in verify-edge-stack.sh")
p.write_text(text.replace(needle, replacement, 1), encoding="utf-8")
print("patched verify-edge-stack.sh")
PY
fi

cd "${ROOT}"
pm2 delete 188-api 2>/dev/null || true
pm2 start deploy/ecosystem.config.cjs --only 188-api
pm2 delete 188-web 2>/dev/null || true
pm2 start deploy/ecosystem.config.cjs --only 188-web
sleep 5
bash deploy/watchdog-web.sh
pm2 list
echo -n "api="; curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/health; echo
echo -n "web="; curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3001/robots.txt; echo
echo -n "nanoai="; curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/; echo
pm2 save
echo APPLY_OK
