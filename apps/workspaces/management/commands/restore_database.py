"""
Lệnh khôi phục cơ sở dữ liệu và diễn tập phục hồi (Spec Mục 12 & AC18).
Hỗ trợ PostgreSQL và SQLite, kiểm tra tính toàn vẹn SHA256 trước khi khôi phục,
hỗ trợ database đích độc lập để diễn tập an toàn và kiểm tra tính toàn vẹn quan hệ.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Khôi phục CSDL từ file backup và kiểm chứng toàn vẹn dữ liệu (AC18)."

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_file",
            type=str,
            help="Đường dẫn đến file backup (.sqlite3 hoặc .dump).",
        )
        parser.add_argument(
            "--target-db",
            type=str,
            required=True,
            help="Tên CSDL hoặc đường dẫn file SQLite đích để khôi phục (cách ly, an toàn diễn tập).",
        )
        parser.add_argument(
            "--skip-checksum",
            action="store_true",
            help="Bỏ qua bước xác minh mã SHA256 từ manifest.",
        )

    def handle(self, *args, **options):
        backup_path = Path(options["backup_file"]).resolve()
        target_db = options["target_db"]
        skip_checksum = options["skip_checksum"]

        if not backup_path.exists():
            raise CommandError(f"File sao lưu '{backup_path}' không tồn tại.")

        start_time = time.time()
        self.stdout.write(self.style.NOTICE(f"Bắt đầu quy trình phục hồi từ '{backup_path.name}' sang target '{target_db}'..."))

        # 1. Xác thực mã băm SHA256 nếu có manifest
        manifest_file = backup_path.with_name(f"{backup_path.stem}.manifest.json")
        if not skip_checksum and manifest_file.exists():
            self._verify_checksum(backup_path, manifest_file)

        # 2. Thực hiện khôi phục
        if backup_path.suffix in [".sqlite3", ".db"]:
            stats = self._restore_sqlite(backup_path, target_db)
        elif backup_path.suffix in [".dump", ".sql"]:
            stats = self._restore_postgresql(backup_path, target_db)
        else:
            raise CommandError(f"Định dạng file '{backup_path.suffix}' không được hỗ trợ.")

        duration = time.time() - start_time
        self.stdout.write(
            self.style.SUCCESS(
                f"\nPhục hồi CSDL thành công trong {duration:.2f} giây!\n"
                f" - Target: {target_db}\n"
                f" - Thống kê kiểm chứng quan hệ:\n"
                + "\n".join([f"   * {k}: {v}" for k, v in stats.items()])
            )
        )

    def _verify_checksum(self, backup_path: Path, manifest_path: Path):
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            expected_hash = manifest_data.get("sha256_checksum")
            if not expected_hash:
                return

            hasher = hashlib.sha256()
            with open(backup_path, "rb") as f:
                while chunk := f.read(65536):
                    hasher.update(chunk)
            actual_hash = hasher.hexdigest()

            if actual_hash != expected_hash:
                raise CommandError(
                    f"Toàn vẹn dữ liệu bị vi phạm! Mã SHA256 file backup ({actual_hash}) "
                    f"không khớp với manifest ({expected_hash})."
                )
            self.stdout.write(self.style.SUCCESS(f" [SHA256] Mã băm toàn vẹn trùng khớp: {actual_hash[:16]}..."))
        except json.JSONDecodeError:
            self.stdout.write(self.style.WARNING(" Không thể đọc manifest JSON, bỏ qua kiểm tra SHA256."))

    def _restore_sqlite(self, backup_path: Path, target_path_str: str) -> dict:
        target_file = Path(target_path_str).resolve()
        target_file.parent.mkdir(parents=True, exist_ok=True)

        if target_file.exists():
            target_file.unlink()

        shutil.copy2(backup_path, target_file)

        # Kiểm chứng dữ liệu đã phục hồi bằng kết nối độc lập
        conn = sqlite3.connect(str(target_file))
        cursor = conn.cursor()

        stats = {}
        for table in ["workspaces_workspace", "workspaces_brandprofile", "workspaces_package", "workspaces_contentitem", "workspaces_task"]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            except sqlite3.OperationalError:
                stats[table] = "N/A (bảng chưa tồn tại)"

        cursor.execute("PRAGMA foreign_key_check;")
        fk_violations = cursor.fetchall()
        stats["foreign_key_violations"] = len(fk_violations)
        conn.close()

        if stats["foreign_key_violations"] > 0:
            raise CommandError(f"Phục hồi thất bại: Phát hiện {stats['foreign_key_violations']} vi phạm ràng buộc khóa ngoại!")

        return stats

    def _restore_postgresql(self, backup_path: Path, target_db_name: str) -> dict:
        user = os.environ.get("PGUSER", "postgres")
        host = os.environ.get("PGHOST", "localhost")
        port = str(os.environ.get("PGPORT", "5432"))
        password = os.environ.get("PGPASSWORD", "")

        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password

        cmd = [
            "pg_restore",
            "-h", host,
            "-p", port,
            "-U", user,
            "-d", target_db_name,
            "--clean",
            "--if-exists",
            "-v",
            str(backup_path),
        ]

        try:
            subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
            return {"target_database": target_db_name, "status": "pg_restore success"}
        except FileNotFoundError:
            raise CommandError("Lệnh 'pg_restore' không tìm thấy trong PATH.")
        except subprocess.CalledProcessError as err:
            raise CommandError(f"pg_restore thất bại: {err.stderr.strip()}")

