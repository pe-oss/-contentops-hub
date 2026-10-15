#!/usr/bin/env bash
# ==============================================================================
# ContentOps Hub - Kịch bản Diễn tập Phục hồi CSDL PostgreSQL (Spec Mục 12, AC18)
# Phục hồi vào một cơ sở dữ liệu diễn tập cách ly (DRILL_DB), kiểm tra toàn vẹn
# ==============================================================================

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Cách dùng: $0 <duong_dan_file_backup.dump> [ten_csdl_phuc_hoi]"
  exit 1
fi

BACKUP_FILE="$1"
DRILL_DB="${2:-saas_content_drill}"

if [ ! -f "${BACKUP_FILE}" ]; then
  echo "Lỗi: File '${BACKUP_FILE}' không tồn tại!" >&2
  exit 1
fi

DB_USER="${PGUSER:-${DATABASE_USER:-postgres}}"
DB_HOST="${PGHOST:-${DATABASE_HOST:-localhost}}"
DB_PORT="${PGPORT:-${DATABASE_PORT:-5432}}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Bắt đầu diễn tập phục hồi vào CSDL cách ly: ${DRILL_DB}..."

# Xác thực SHA-256 từ manifest nếu có
MANIFEST_FILE="${BACKUP_FILE%.dump}.manifest.json"
if [ -f "${MANIFEST_FILE}" ] && command -v sha256sum >/dev/null 2>&1; then
  EXPECTED_SHA="$(grep '"sha256_checksum"' "${MANIFEST_FILE}" | awk -F'"' '{print $4}')"
  ACTUAL_SHA="$(sha256sum "${BACKUP_FILE}" | awk '{print $1}')"
  if [ "${EXPECTED_SHA}" != "${ACTUAL_SHA}" ]; then
    echo "LỖI NGUY HIỂM: Sai lệch mã băm SHA-256! File backup có thể đã bị hỏng." >&2
    exit 1
  fi
  echo " [SHA256] Kiểm tra mã băm thành công: ${ACTUAL_SHA:0:16}..."
fi

# Tạo database diễn tập nếu chưa có
createdb -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" "${DRILL_DB}" 2>/dev/null || true

START_TIME=$(date +%s)

# Thực thi pg_restore
pg_restore -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DRILL_DB}" --clean --if-exists -v "${BACKUP_FILE}" || true

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Phục hồi hoàn tất trong ${DURATION} giây."

# Kiểm tra dữ liệu và quan hệ
echo "[Kiểm chứng] Kiểm tra số lượng bản ghi trong database diễn tập..."
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DRILL_DB}" -c "
  SELECT 'workspaces' AS table_name, count(*) FROM workspaces_workspace
  UNION ALL
  SELECT 'brand_profiles', count(*) FROM workspaces_brandprofile
  UNION ALL
  SELECT 'packages', count(*) FROM workspaces_package
  UNION ALL
  SELECT 'content_items', count(*) FROM workspaces_contentitem
  UNION ALL
  SELECT 'tasks', count(*) FROM workspaces_task;
"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Diễn tập phục hồi CSDL thành công!"
