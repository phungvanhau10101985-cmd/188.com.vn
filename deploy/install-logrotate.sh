#!/usr/bin/env bash
# Cài logrotate cho log 188 (xoay mỗi ngày, giữ 7 ngày, tự xóa bản cũ).
# Usage trên VPS: cd /var/www/188.com.vn && bash deploy/install-logrotate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/deploy/logrotate-188.com.vn.conf"
DEST="/etc/logrotate.d/188.com.vn"
KEEP_DAYS="${LOG_KEEP_DAYS:-7}"

if [[ ! -f "${SRC}" ]]; then
  echo "❌ Không tìm thấy ${SRC}"
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "❌ Cần chạy bằng root (ssh root@VPS)"
  exit 1
fi

tmp="$(mktemp)"
# Windows checkout có thể còn CRLF
sed 's/\r$//' "${SRC}" >"${tmp}"
if [[ "${KEEP_DAYS}" != "7" ]]; then
  sed -i \
    -e "s/rotate 7/rotate ${KEEP_DAYS}/" \
    -e "s/-mtime +7/-mtime +${KEEP_DAYS}/" \
    "${tmp}"
fi

install -m 644 "${tmp}" "${DEST}"
rm -f "${tmp}"

echo "==> Đã cài ${DEST} (giữ ${KEEP_DAYS} ngày, xoay daily)"
if ! /usr/sbin/logrotate -d "${DEST}" >/tmp/188-logrotate-debug.txt 2>&1; then
  echo "⚠️  logrotate -d exit ≠ 0 — xem /tmp/188-logrotate-debug.txt"
  tail -n 30 /tmp/188-logrotate-debug.txt
  exit 1
fi
echo "✓ Cú pháp logrotate OK"
echo "    Cron hệ thống: /etc/cron.daily/logrotate"
echo "    File xoay: *.log-YYYYMMDD rồi .gz; quá ${KEEP_DAYS} ngày thì xóa"
