#!/usr/bin/env bash
# Đo tải listing 2–3 ngày: loadavg, CPU 188-api, COUNT đồng thời, warm failed.
# Không restart PM2, không đụng thu-do-online / worksheet-worker.
#
# Cron: bash deploy/install-listing-load-monitor-cron.sh
set -u

LOG="${LISTING_LOAD_LOG:-/var/log/188-listing-load.log}"
ts="$(date '+%Y-%m-%d %H:%M:%S')"
load="$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || echo '?')"

cpu="?"
mem="?"
if command -v pm2 >/dev/null 2>&1; then
  read -r cpu mem <<EOF
$(pm2 jlist 2>/dev/null | python3 -c '
import json, sys
try:
    apps = json.load(sys.stdin)
except Exception:
    print("? ?")
    raise SystemExit(0)
for a in apps:
    if a.get("name") == "188-api":
        mon = a.get("monit") or {}
        cpu = mon.get("cpu", "?")
        mem = mon.get("memory", 0)
        try:
            mem_mb = int(mem) // (1024 * 1024)
        except Exception:
            mem_mb = "?"
        print(cpu, mem_mb)
        break
else:
    print("? ?")
' 2>/dev/null)
EOF
fi

count_n="$(sudo -u postgres psql -d 188comvn -At -c "
SELECT count(*)
FROM pg_stat_activity
WHERE datname = '188comvn'
  AND state = 'active'
  AND query ILIKE '%count(products.id)%'
  AND query NOT ILIKE '%pg_stat_activity%';
" 2>/dev/null || echo "?")"

warm_n="0"
if [[ -f /root/.pm2/logs/188-api-error.log ]]; then
  warm_n="$(grep -c 'outfit visual warm failed' /root/.pm2/logs/188-api-error.log 2>/dev/null || true)"
  warm_n="${warm_n:-0}"
fi

echo "${ts} load=${load} api_cpu=${cpu}% api_mem_mb=${mem} count_active=${count_n} warm_failed=${warm_n}" >> "${LOG}"
