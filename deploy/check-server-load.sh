#!/usr/bin/env bash
# Kiem tra process / RAM / CPU / disk / DB / port dang nang tren VPS.
# Usage: bash deploy/check-server-load.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "========== LOAD / UPTIME =========="
uptime

echo ""
echo "========== RAM + SWAP =========="
free -h
swapon --show 2>/dev/null || echo "(khong co swap)"

echo ""
echo "========== DISK =========="
df -h / /var 2>/dev/null | sort -u

echo ""
echo "========== PM2 =========="
pm2 list 2>/dev/null || echo "(pm2 khong co hoac loi)"

echo ""
echo "========== TOP CPU (10 process) =========="
ps aux --sort=-%cpu | head -11

echo ""
echo "========== TOP RAM (10 process) =========="
ps aux --sort=-%mem | head -11

echo ""
echo "========== PORTS (3000 3001 8000 8001 80 443) =========="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp | grep -E '3000|3001|8000|8001|:80|:443' || echo "(khong co port match)"
else
  netstat -tlnp 2>/dev/null | grep -E '3000|3001|8000|8001|:80|:443' || true
fi

echo ""
echo "========== POSTGRES CONNECTIONS =========="
if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
  sudo -u postgres psql -P pager=off -c \
    "SELECT datname, count(*) AS conn FROM pg_stat_activity GROUP BY datname ORDER BY conn DESC;" \
    2>/dev/null || echo "(khong ket noi duoc postgres)"
  echo ""
  echo "--- Query dang chay (khong idle, > 2s) ---"
  sudo -u postgres psql -P pager=off -c \
    "SELECT pid, datname, now()-query_start AS dur, left(query,100) AS q
     FROM pg_stat_activity
     WHERE state <> 'idle' AND query NOT ILIKE '%pg_stat_activity%'
       AND now()-query_start > interval '2 seconds'
     ORDER BY dur DESC
     LIMIT 12;" \
    2>/dev/null || true
else
  echo "(bo qua — khong co postgres/sudo)"
fi

echo ""
echo "========== OOM gan day =========="
if command -v dmesg >/dev/null 2>&1; then
  dmesg -T 2>/dev/null | grep -iE 'oom|killed process' | tail -5 || echo "(khong co OOM)"
else
  echo "(bo qua dmesg)"
fi

echo ""
echo "========== HEALTH 188 (neu chay) =========="
for url in \
  "http://127.0.0.1:8001/health" \
  "http://127.0.0.1:8001/health/storefront" \
  "http://127.0.0.1:3001/robots.txt" \
  "http://127.0.0.1:3000/"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || echo "000")
  echo "  ${url} → ${code}"
done

echo ""
echo "========== GOI Y DOC KET QUA =========="
echo "  - Load > so CPU (vd. > 8 tren 8 core) = qua tai."
echo "  - postgres SELECT/count nhieu dong = DB nang (menu/catalog)."
echo "  - 188-api RAM > 2G = API/import/anh dang nang."
echo "  - next-server + npm run build = deploy dang nang."
echo "  - Swap USED tang nhieu = thieu RAM tam thoi."
echo "  - /health/storefront != 200 = pool DB sap treo (UptimeRobot: https://188.com.vn/health/storefront)."
echo "  - Monitor VPS: bash deploy/monitor-storefront.sh (cron */2 * * * * tuỳ chọn)."
