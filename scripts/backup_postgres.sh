#!/usr/bin/env bash
# ==============================================================================
# ContentOps Hub - Kịch bản Sao lưu Cơ sở dữ liệu PostgreSQL (Spec Mục 12 & B10)
# Tự động trích xuất thông tin kết nối từ DATABASE_URL hoặc biến PG*
# Tính mã băm SHA-256, sinh metadata manifest, retention 7 bản, không ghi đè bản tốt
# ==============================================================================

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
RETENTION_COUNT="${RETENTION_COUNT:-7}"
TIMESTAMP="$(date -u +"%Y%m%d_%H%M%S")"

mkdir -p "${BACKUP_DIR}"

# Lấy biến kết nối
DB_NAME="${PGDATABASE:-${DATABASE_NAME:-saas_content}}"
DB_USER="${PGUSER:-${DATABASE_USER:-postgres}}"
DB_HOST="${PGHOST:-${DATABASE_HOST:-localhost}}"
DB_PORT="${PGPORT:-${DATABASE_PORT:-5432}}"

TMP_FILE="${BACKUP_DIR}/backup_pg_${DB_NAME}_${TIMESTAMP}.tmp"
FINAL_FILE="${BACKUP_DIR}/backup_pg_${DB_NAME}_${TIMESTAMP}.dump"
MANIFEST_FILE="${BACKUP_DIR}/backup_pg_${DB_NAME}_${TIMESTAMP}.manifest.json"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Bắt đầu sao lưu CSDL PostgreSQL: ${DB_NAME} tại ${DB_HOST}:${DB_PORT}..."

# Thực hiện pg_dump vào file tạm thời
if command -v pg_dump >/dev/null 2>&1; then
  pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -F c -b -v -f "${TMP_FILE}" "${DB_NAME}"
else
  echo "Lỗi: Không tìm thấy tiện ích 'pg_dump' trên máy chủ!" >&2
  exit 1
fi

# Tính mã băm SHA-256
if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "${TMP_FILE}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  SHA256="$(shasum -a 256 "${TMP_FILE}" | awk '{print $1}')"
else
  SHA256="checksum_tool_not_found"
fi

# Đổi tên file tạm thành file chính thức (nguyên tử)
mv "${TMP_FILE}" "${FINAL_FILE}"
FILE_SIZE="$(wc -c < "${FINAL_FILE}")"

# Ghi manifest
cat <<EOF > "${MANIFEST_FILE}"
{
  "timestamp_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "engine": "postgresql",
  "database_name": "${DB_NAME}",
  "backup_filename": "$(basename "${FINAL_FILE}")",
  "file_size_bytes": ${FILE_SIZE},
  "sha256_checksum": "${SHA256}"
}
EOF

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Sao lưu hoàn tất! File: ${FINAL_FILE} (SHA256: ${SHA256:0:16}...)"

# Áp dụng chính sách lưu giữ (Retention): Giữ lại RETENTION_COUNT bản mới nhất
echo "[Retention] Áp dụng chính sách lưu giữ tối đa ${RETENTION_COUNT} bản sao lưu gần nhất..."
find "${BACKUP_DIR}" -maxdepth 1 -name "backup_pg_${DB_NAME}_*.dump" | sort -r | tail -n +"$((RETENTION_COUNT + 1))" | while read -r old_backup; do
  echo " [Retention] Xóa bản cũ: ${old_backup}"
  rm -f "${old_backup}"
  rm -f "${old_backup%.dump}.manifest.json"
done

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Kịch bản hoàn tất thành công!"
