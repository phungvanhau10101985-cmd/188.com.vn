#!/usr/bin/env bash
# Backup dữ liệu & cấu hình quan trọng 188.com.vn trên VPS.
# (Kết hợp thêm Full Snapshot trên panel VPS để khôi phục cả máy ảo.)
#
# Usage (từ root repo trên VPS):
#   chmod +x deploy/backup-vps.sh
#   bash deploy/backup-vps.sh
#
# Biến tuỳ chọn:
#   BACKUP_ROOT=/var/backups/188.com.vn   thư mục gốc lưu backup
#   BACKUP_RETENTION_DAYS=14              xóa tarball cũ hơn N ngày (0 = không xóa)
#   BACKUP_INCLUDE_NGINX=1                backup cấu hình Nginx (mặc định 1)
#   BACKUP_INCLUDE_SSL=1                  backup Let's Encrypt (mặc định 1)
#   BACKUP_INCLUDE_CRONTAB=1              backup crontab user hiện tại (mặc định 1)
#   BACKUP_SKIP_DB=1                      bỏ qua pg_dump
#   BACKUP_INCLUDE_CACHE=1                backup cả bảng cache (mặc định bỏ qua data cache)
#   BACKUP_EXTRA_EXCLUDE_TABLES="t1,t2"   thêm bảng loại trừ (phân tách bằng dấu phẩy)
#   POSTGRES_DB_NAME=188comvn             override tên DB nếu không đọc được từ .env
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="${PROJECT_ROOT}/backend"
FRONTEND="${PROJECT_ROOT}/frontend"
ENV_FILE="${BACKEND}/.env"

BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/188.com.vn}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
BACKUP_INCLUDE_NGINX="${BACKUP_INCLUDE_NGINX:-1}"
BACKUP_INCLUDE_SSL="${BACKUP_INCLUDE_SSL:-1}"
BACKUP_INCLUDE_CRONTAB="${BACKUP_INCLUDE_CRONTAB:-1}"
BACKUP_INCLUDE_CACHE="${BACKUP_INCLUDE_CACHE:-0}"
POSTGRES_DB_NAME="${POSTGRES_DB_NAME:-188comvn}"

# Bảng cache/snapshot — app tự tạo lại khi khách vào / search (chỉ loại data, giữ schema).
DEFAULT_BACKUP_EXCLUDE_TABLES=(
  guest_home_recommendation_snapshots
  user_home_recommendation_snapshots
  product_search_cache
  listing_facet_cache
  category_menu_cache
  user_cohort_view_pool_cache
  listing_import_queue_snapshots
  listing_import_queue_revocations
)

STAMP="$(date +%Y%m%d-%H%M%S)"
DAY_STAMP="$(date +%Y%m%d)"
WORK_DIR="${BACKUP_ROOT}/${DAY_STAMP}-${STAMP}"
ARCHIVE="${BACKUP_ROOT}/backup-188-${STAMP}.tar.gz"

log() { echo "==> $*"; }
warn() { echo "⚠️  $*" >&2; }
ok() { echo "✅ $*"; }

read_database_url() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    return 1
  fi
  local raw
  raw=$(grep -m1 '^DATABASE_URL=' "${ENV_FILE}" | cut -d= -f2- | tr -d '\r' || true)
  raw="${raw#\"}"
  raw="${raw%\"}"
  raw="${raw#\'}"
  raw="${raw%\'}"
  [[ -n "${raw}" ]] || return 1
  printf '%s' "${raw}"
}

parse_db_name_from_url() {
  local url="$1"
  local tail="${url##*/}"
  local dbname="${tail%%\?*}"
  if [[ -z "${dbname}" ]] || [[ "${dbname}" == "${url}" ]]; then
    return 1
  fi
  printf '%s' "${dbname}"
}

backup_exclude_tables() {
  [[ "${BACKUP_INCLUDE_CACHE}" == "1" ]] && return 0

  local -a tables=("${DEFAULT_BACKUP_EXCLUDE_TABLES[@]}")
  local extra="${BACKUP_EXTRA_EXCLUDE_TABLES:-}"
  if [[ -n "${extra}" ]]; then
    local IFS=,
    local -a more=()
    read -r -a more <<<"${extra}"
    tables+=("${more[@]}")
  fi

  local t seen="" out=()
  for t in "${tables[@]}"; do
    t="${t// /}"
    [[ -n "${t}" ]] || continue
    [[ ",${seen}," == *",${t},"* ]] && continue
    seen="${seen},${t}"
    out+=("${t}")
  done

  printf '%s\n' "${out[@]}"
}

write_backup_db_notes() {
  local notes="${WORK_DIR}/database.notes.txt"
  {
    echo "backup_mode=essential_data"
    echo "cache_data_included=${BACKUP_INCLUDE_CACHE}"
    if [[ "${BACKUP_INCLUDE_CACHE}" == "1" ]]; then
      echo "excluded_tables=none"
    else
      echo "excluded_tables_data_only:"
      backup_exclude_tables
    fi
    echo ""
    echo "Cache/snapshot tables are excluded from data dump; schema is kept."
    echo "After restore, caches rebuild when users visit home / search."
  } >"${notes}"
}

run_pg_dump() {
  local target_db="$1"
  local dump_file="$2"
  local log_file="$3"
  shift 3
  local -a exclude_args=("$@")
  pg_dump "${exclude_args[@]}" "${target_db}" >"${dump_file}" 2>"${log_file}"
}

backup_postgres() {
  [[ "${BACKUP_SKIP_DB:-0}" == "1" ]] && { warn "Bỏ qua pg_dump (BACKUP_SKIP_DB=1)"; return 0; }

  local db_url db_name dump_file="${WORK_DIR}/database.sql"
  local -a exclude_args=()
  db_url="$(read_database_url || true)"
  if [[ -n "${db_url}" ]]; then
    case "${db_url}" in
      postgresql:*|postgres:*|postgresql+*) ;;
      *)
        warn "DATABASE_URL không phải PostgreSQL — bỏ qua pg_dump"
        return 0
        ;;
    esac
    db_name="$(parse_db_name_from_url "${db_url}" || true)"
    [[ -n "${db_name}" ]] && POSTGRES_DB_NAME="${db_name}"
  fi

  mkdir -p "${WORK_DIR}"
  write_backup_db_notes

  if [[ "${BACKUP_INCLUDE_CACHE}" == "1" ]]; then
    log "PostgreSQL dump (đầy đủ, gồm cache): ${POSTGRES_DB_NAME}"
  else
    log "PostgreSQL dump (chỉ dữ liệu quan trọng, bỏ data cache): ${POSTGRES_DB_NAME}"
    local table
    while IFS= read -r table; do
      [[ -n "${table}" ]] || continue
      exclude_args+=(--exclude-table-data="${table}")
      echo "    - bỏ data: ${table}"
    done < <(backup_exclude_tables)
  fi

  if [[ -n "${db_url}" ]] && command -v pg_dump >/dev/null 2>&1; then
    if run_pg_dump "${db_url}" "${dump_file}" "${WORK_DIR}/database.dump.log" "${exclude_args[@]}"; then
      ok "pg_dump qua DATABASE_URL → database.sql ($(du -h "${dump_file}" | awk '{print $1}'))"
      return 0
    fi
    warn "pg_dump DATABASE_URL thất bại — thử sudo -u postgres (xem database.dump.log)"
  fi

  if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
    if run_pg_dump "${POSTGRES_DB_NAME}" "${dump_file}" "${WORK_DIR}/database.dump.log" "${exclude_args[@]}"; then
      ok "pg_dump sudo -u postgres → database.sql ($(du -h "${dump_file}" | awk '{print $1}'))"
      return 0
    fi
  fi

  warn "Không dump được database — kiểm tra PostgreSQL và DATABASE_URL trong backend/.env"
  return 0
}

copy_if_exists() {
  local src="$1"
  local dest="$2"
  if [[ -e "${src}" ]]; then
    mkdir -p "$(dirname "${dest}")"
    cp -a "${src}" "${dest}"
    return 0
  fi
  return 1
}

backup_env_and_pm2() {
  log "File cấu hình & PM2"
  mkdir -p "${WORK_DIR}/config"

  copy_if_exists "${ENV_FILE}" "${WORK_DIR}/config/backend.env" && ok "backend/.env" || warn "Thiếu backend/.env"
  copy_if_exists "${FRONTEND}/.env.local" "${WORK_DIR}/config/frontend.env.local" && ok "frontend/.env.local" || true
  copy_if_exists "${FRONTEND}/.env.production" "${WORK_DIR}/config/frontend.env.production" || true
  copy_if_exists "${PROJECT_ROOT}/deploy/ecosystem.config.cjs" "${WORK_DIR}/config/ecosystem.config.cjs" || true

  if command -v pm2 >/dev/null 2>&1; then
    pm2 save >/dev/null 2>&1 || true
    local pm2_home="${PM2_HOME:-$HOME/.pm2}"
    copy_if_exists "${pm2_home}/dump.pm2" "${WORK_DIR}/config/pm2-dump.pm2" && ok "pm2 dump.pm2" || warn "Chưa có pm2 dump.pm2 (chạy: pm2 save)"
    if pm2 jlist >"${WORK_DIR}/config/pm2-jlist.json" 2>/dev/null; then
      ok "pm2 jlist.json"
    fi
  else
    warn "Chưa cài pm2 — bỏ qua dump PM2"
  fi
}

backup_nginx() {
  [[ "${BACKUP_INCLUDE_NGINX}" == "1" ]] || return 0
  log "Nginx"
  mkdir -p "${WORK_DIR}/nginx"

  if [[ -d /etc/nginx ]]; then
    if [[ -d /etc/nginx/sites-available ]]; then
      cp -a /etc/nginx/sites-available "${WORK_DIR}/nginx/" 2>/dev/null || true
    fi
    if [[ -d /etc/nginx/sites-enabled ]]; then
      cp -a /etc/nginx/sites-enabled "${WORK_DIR}/nginx/" 2>/dev/null || true
    fi
    copy_if_exists /etc/nginx/nginx.conf "${WORK_DIR}/nginx/nginx.conf" || true
    ok "Nginx config"
  else
    warn "Không tìm thấy /etc/nginx"
  fi
}

backup_ssl() {
  [[ "${BACKUP_INCLUDE_SSL}" == "1" ]] || return 0
  log "SSL (Let's Encrypt)"
  if [[ -d /etc/letsencrypt ]]; then
    mkdir -p "${WORK_DIR}/ssl"
    # Chỉ copy cert liên quan 188 (tránh tarball quá lớn nếu VPS nhiều site)
    if [[ -d /etc/letsencrypt/live ]]; then
      for domain in 188.com.vn www.188.com.vn api.188.com.vn; do
        if [[ -d "/etc/letsencrypt/live/${domain}" ]]; then
          mkdir -p "${WORK_DIR}/ssl/live"
          cp -aL "/etc/letsencrypt/live/${domain}" "${WORK_DIR}/ssl/live/" 2>/dev/null || \
            sudo cp -aL "/etc/letsencrypt/live/${domain}" "${WORK_DIR}/ssl/live/" 2>/dev/null || true
        fi
      done
      if [[ -d /etc/letsencrypt/renewal ]]; then
        mkdir -p "${WORK_DIR}/ssl/renewal"
        cp -a /etc/letsencrypt/renewal/*188* "${WORK_DIR}/ssl/renewal/" 2>/dev/null || \
          sudo cp -a /etc/letsencrypt/renewal/*188* "${WORK_DIR}/ssl/renewal/" 2>/dev/null || true
      fi
    fi
    ok "SSL certs (188*)"
  else
    warn "Không tìm thấy /etc/letsencrypt"
  fi
}

backup_crontab() {
  [[ "${BACKUP_INCLUDE_CRONTAB}" == "1" ]] || return 0
  log "Crontab"
  if crontab -l >"${WORK_DIR}/config/crontab.txt" 2>/dev/null; then
    ok "crontab user $(whoami)"
  else
    warn "User $(whoami) chưa có crontab"
    : >"${WORK_DIR}/config/crontab.txt"
  fi
}

write_manifest() {
  local manifest="${WORK_DIR}/MANIFEST.txt"
  {
    echo "188.com.vn VPS backup"
    echo "created_at=$(date -Iseconds 2>/dev/null || date)"
    echo "hostname=$(hostname 2>/dev/null || echo unknown)"
    echo "project_root=${PROJECT_ROOT}"
    echo "postgres_db=${POSTGRES_DB_NAME}"
    if command -v git >/dev/null 2>&1 && git -C "${PROJECT_ROOT}" rev-parse HEAD &>/dev/null; then
      echo "git_branch=$(git -C "${PROJECT_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
      echo "git_commit=$(git -C "${PROJECT_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
    fi
    echo ""
    echo "Contents:"
    find "${WORK_DIR}" -type f ! -path "${manifest}" | sort
  } >"${manifest}"
  ok "MANIFEST.txt"
}

create_archive() {
  log "Nén tarball: ${ARCHIVE}"
  mkdir -p "${BACKUP_ROOT}"
  tar -czf "${ARCHIVE}" -C "${BACKUP_ROOT}" "$(basename "${WORK_DIR}")"
  ok "Archive: ${ARCHIVE} ($(du -h "${ARCHIVE}" | awk '{print $1}'))"
}

prune_old_backups() {
  [[ "${BACKUP_RETENTION_DAYS}" =~ ^[0-9]+$ ]] || return 0
  [[ "${BACKUP_RETENTION_DAYS}" -gt 0 ]] || return 0
  log "Dọn backup cũ hơn ${BACKUP_RETENTION_DAYS} ngày"
  find "${BACKUP_ROOT}" -maxdepth 1 -name 'backup-188-*.tar.gz' -mtime "+${BACKUP_RETENTION_DAYS}" -print -delete 2>/dev/null || true
  find "${BACKUP_ROOT}" -maxdepth 1 -type d -name '20*' -mtime "+${BACKUP_RETENTION_DAYS}" -print -exec rm -rf {} + 2>/dev/null || true
}

main() {
  log "Backup 188.com.vn — ${STAMP}"
  log "Project: ${PROJECT_ROOT}"
  log "Output:  ${BACKUP_ROOT}"

  mkdir -p "${WORK_DIR}"

  backup_postgres
  backup_env_and_pm2
  backup_nginx
  backup_ssl
  backup_crontab
  write_manifest
  create_archive
  prune_old_backups

  echo ""
  ok "Backup hoàn tất"
  echo "    File: ${ARCHIVE}"
  echo "    Tải về máy: scp root@IP_VPS:${ARCHIVE} ./"
  echo ""
  warn "File chứa mật khẩu (.env) — lưu an toàn, không upload công khai."
  if [[ "${BACKUP_INCLUDE_CACHE}" == "1" ]]; then
    echo "    DB dump: đầy đủ (gồm cache). BACKUP_INCLUDE_CACHE=0 để bỏ data cache."
  else
    echo "    DB dump: chỉ dữ liệu quan trọng — bảng cache tự tạo lại sau restore."
  fi
  echo "    Khôi phục DB: psql <dbname> < database.sql (sau khi giải nén)"
  echo "    Khôi phục cả VPS: dùng Full Snapshot trên panel + file backup này"
}

main "$@"
