#!/usr/bin/env bash
# Tao / nang cap swap tren VPS (Ubuntu/Debian). Mac dinh 8G.
#
# Usage:
#   sudo bash deploy/setup-swap.sh
#   sudo bash deploy/setup-swap.sh 8G
#
set -euo pipefail

SWAP_SIZE="${1:-${SWAP_SIZE:-8G}}"
SWAP_FILE="${SWAP_FILE:-/swapfile}"
SWAPPINESS="${SWAPPINESS:-10}"

_swap_mb() {
  case "${SWAP_SIZE}" in
    2G|2g) echo 2048 ;;
    4G|4g) echo 4096 ;;
    6G|6g) echo 6144 ;;
    8G|8g) echo 8192 ;;
    *) echo 8192 ;;
  esac
}

_finish_fstab_swappiness() {
  if ! grep -qF "${SWAP_FILE}" /etc/fstab 2>/dev/null; then
    echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
    echo "→ Da them vao /etc/fstab (giu sau reboot)"
  fi
  if [[ -f /proc/sys/vm/swappiness ]]; then
    sysctl -w vm.swappiness="${SWAPPINESS}" >/dev/null
    echo "vm.swappiness=${SWAPPINESS}" > /etc/sysctl.d/99-swap.conf
    echo "→ vm.swappiness=${SWAPPINESS}"
  fi
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Chay voi sudo: sudo bash deploy/setup-swap.sh"
  exit 1
fi

TARGET_MB="$(_swap_mb)"

echo "==> Swap hien tai (muc tieu ${SWAP_SIZE} / ~${TARGET_MB} MB)"
swapon --show 2>/dev/null || echo "(chua co swap)"
free -h | head -2

CURRENT_MB=0
if [[ -f "${SWAP_FILE}" ]]; then
  CURRENT_MB=$(( $(stat -c%s "${SWAP_FILE}" 2>/dev/null || echo 0) / 1048576 ))
fi

SWAP_ON=0
swapon --show 2>/dev/null | grep -qF "${SWAP_FILE}" && SWAP_ON=1

if [[ "${SWAP_ON}" == "1" ]] && [[ "${CURRENT_MB}" -ge $((TARGET_MB - 64)) ]]; then
  echo
  echo "✓ ${SWAP_FILE} ~${CURRENT_MB} MB — da dat ${TARGET_MB} MB."
  _finish_fstab_swappiness
  swapon --show
  free -h | head -2
  exit 0
fi

if [[ "${SWAP_ON}" == "1" ]]; then
  echo
  echo "==> Nang cap ${SWAP_FILE}: ~${CURRENT_MB} MB → ${TARGET_MB} MB"
  swapoff "${SWAP_FILE}"
fi

rm -f "${SWAP_FILE}"
echo "==> Tao ${SWAP_FILE} (${SWAP_SIZE})"
if ! fallocate -l "${SWAP_SIZE}" "${SWAP_FILE}" 2>/dev/null; then
  dd if=/dev/zero of="${SWAP_FILE}" bs=1M count="${TARGET_MB}" status=none
fi
chmod 600 "${SWAP_FILE}"
if ! mkswap "${SWAP_FILE}"; then
  echo "❌ mkswap that bai — kiem tra df -h / va quyen ghi ${SWAP_FILE}"
  exit 1
fi
if ! swapon "${SWAP_FILE}"; then
  echo "❌ swapon that bai — mot so VPS/LXC chan swap file."
  echo "   Thu: dmesg | tail -5 ; df -h / ; ls -lh ${SWAP_FILE}"
  echo "   Hoac bat swap trong panel nha cung cap."
  exit 1
fi
_finish_fstab_swappiness

echo
echo "==> Ket qua"
swapon --show
free -h | head -2
echo "✓ Xong."
