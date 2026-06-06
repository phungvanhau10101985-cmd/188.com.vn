#!/usr/bin/env bash
# Thư viện dùng chung cho deploy/health-check.sh và deploy/update-vps.sh
# shellcheck shell=bash

health_curl_http_code() {
  local url="$1"
  local max_time="${2:-5}"
  local code=""
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time "${max_time}" "$url" 2>/dev/null) || true
  if [[ -z "${code}" ]]; then
    echo "000"
  else
    echo "${code}"
  fi
}

# Probe nhẹ — không COUNT(*), ít row hơn 48 SP full listing.
health_products_probe_url() {
  local api_port="$1"
  local limit="${HEALTH_PRODUCTS_LIMIT:-8}"
  echo "http://127.0.0.1:${api_port}/api/v1/products/?limit=${limit}&skip=0&is_active=true&skip_total=true"
}

health_curl_products_probe() {
  local api_port="$1"
  local max_attempts="${2:-${HEALTH_PRODUCTS_ATTEMPTS:-4}}"
  local wait_per="${3:-${HEALTH_PRODUCTS_WAIT_SEC:-30}}"
  local url
  url=$(health_products_probe_url "${api_port}")
  local code="000"
  local attempt
  for attempt in $(seq 1 "${max_attempts}"); do
    code=$(health_curl_http_code "${url}" "${wait_per}")
    if [[ "${code}" == "200" ]]; then
      echo "${code}"
      return 0
    fi
    if (( attempt < max_attempts )); then
      echo "    … products chưa 200 (mã ${code}), thử lại (${attempt}/${max_attempts})…" >&2
      sleep 3
    fi
  done
  echo "${code}"
}

health_terminate_idle_db_transactions() {
  local db_name="${POSTGRES_DB_NAME:-188comvn}"
  if ! command -v sudo >/dev/null 2>&1 || ! id postgres >/dev/null 2>&1; then
    echo "    (bỏ qua terminate idle — không có sudo/postgres)" >&2
    return 0
  fi
  local terminated
  terminated=$(sudo -u postgres psql -P pager=off -d "${db_name}" -tAc \
    "SELECT count(*) FROM (
       SELECT pg_terminate_backend(pid)
       FROM pg_stat_activity
       WHERE datname='${db_name}' AND state='idle in transaction' AND pid <> pg_backend_pid()
     ) t;" \
    2>/dev/null || echo "0")
  echo "    Đã terminate idle-in-transaction: ${terminated:-0}" >&2
}

health_curl_homepage_smoke() {
  local base_url="$1"
  local max_sec="${HEALTH_HOMEPAGE_CURL_MAX_SEC:-120}"
  local code_file
  code_file=$(mktemp)
  echo "    GET ${base_url}/ (SSR — timeout ${max_sec}s)…" >&2
  curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time "${max_sec}" \
    "${base_url}/" >"${code_file}" 2>/dev/null &
  local pid=$!
  local elapsed=0
  while kill -0 "${pid}" 2>/dev/null; do
    sleep 10
    elapsed=$((elapsed + 10))
    echo "    … vẫn đang render homepage (${elapsed}s / tối đa ${max_sec}s)" >&2
  done
  wait "${pid}" 2>/dev/null || true
  local code
  code=$(tr -d '[:space:]' <"${code_file}" 2>/dev/null || true)
  rm -f "${code_file}"
  if [[ -z "${code}" ]]; then
    echo "000"
  else
    echo "${code}"
  fi
}
