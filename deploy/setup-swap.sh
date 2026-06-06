#!/usr/bin/env bash
# Tao swap tren VPS (Ubuntu/Debian). Idempotent — chay lai an toan.
#
# Usage:
#   sudo bash deploy/setup-swap.sh
#   sudo bash deploy/setup-swap.sh 4G
#
set -euo pipefail

SWAP_SIZE="${1:-${SWAP_SIZE:-4G}}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAPPINESS="${SWAPPINESS:-10}"

_swap_mb() {
  case "${SWAP_SIZE}" in
    2G|2g) echo 2048 ;;
    4G|4g) echo 4096 ;;
    8G|8g) echo 8192 ;;
    *) echo 4096 ;;
  esac
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chay voi sudo: sudo bash deploy/setup-swap.sh"
  exit 1
fi

echo "==> Swap hien tai"
swapon --show 2>/dev/null || echo "(chua co swap)"
free -h | head -2

if swapon --show 2>/dev/null | grep -qF "${SWAP_FILE}"; then
  echo
  echo "✓ ${SWAP_FILE} da bat — khong tao lai."
  exit 0
fi

if [[ -f "${SWAP_FILE}" ]]; then
  echo
  echo "==> Kich hoat ${SWAP_FILE} co san"
  chmod 600 "${SWAP_FILE}"
  mkswap "${SWAP_FILE}" 2>/dev/null || true
  swapon "${SWAP_FILE}"
else
  MB="$(_swap_mb)"
  echo
  echo "==> Tao ${SWAP_FILE} (~${MB} MB)"
  if ! fallocate -l "${SWAP_SIZE}" "${SWAP_FILE}" 2>/dev/null; then
    dd if=/dev/zero of="${SWAP_FILE}" bs=1M count="${MB}" status=none
  fi
  chmod 600 "${SWAP_FILE}"
  mkswap "${SWAP_FILE}"
  swapon "${SWAP_FILE}"
fi

if ! grep -qF "${SWAP_FILE}" /etc/fstab 2>/dev/null; then
  echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
  echo "→ Da them vao /etc/fstab (giu sau reboot)"
fi

if [[ -f /proc/sys/vm/swappiness ]]; then
  sysctl -w vm.swappiness="${SWAPPINESS}" >/dev/null
  echo "vm.swappiness=${SWAPPINESS}" > /etc/sysctl.d/99-swap.conf
  echo "→ vm.swappiness=${SWAPPINESS}"
fi

echo
echo "==> Ket qua"
swapon --show
free -h | head -2
echo "✓ Xong."
