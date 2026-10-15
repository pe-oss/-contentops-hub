"""
Lệnh sao lưu cơ sở dữ liệu (Spec Mục 12 & Milestone B10).
Hỗ trợ PostgreSQL và SQLite, tính checksum SHA256, lưu manifest,
áp dụng chính sách retention 7 bản và không bao giờ ghi đè nếu sao lưu thất bại.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Sao lưu CSDL tự động kèm tính toàn vẹn SHA256 và chính sách lưu giữ 7 bản."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=os.environ.get("BACKUP_DIR", "backups"),
            help="Thư mục chứa bản sao lưu (mặc định: backups/).",
        )
        parser.add_argument(
            "--retention-count",
            type=int,
            default=7,
            help="Số lượng bản sao lưu gần nhất được giữ lại (mặc định: 7 bản).",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        retention_count = options["retention_count"]

        db_config = settings.DATABASES["default"]
        engine = db_config.get("ENGINE", "")
        timestamp_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        self.stdout.write(self.style.NOTICE(f"[{datetime.utcnow().isoformat()}Z] Bắt đầu sao lưu CSDL..."))

        if "postgresql" in engine or "psycopg2" in engine:
            backup_path, manifest_path = self._backup_postgresql(db_config, output_dir, timestamp_str)
        elif "sqlite3" in engine:
            backup_path, manifest_path = self._backup_sqlite(db_config, output_dir, timestamp_str)
        else:
            raise CommandError(f"Database engine '{engine}' chưa được hỗ trợ sao lưu tự động.")

        self._apply_retention(output_dir, retention_count)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sao lưu CSDL hoàn tất!\n"
                f" - File backup: {backup_path}\n"
                f" - Manifest:    {manifest_path}\n"
                f" - Retention:   {retention_count} bản gần nhất."
            )
        )
        return str(backup_path)

    def _backup_sqlite(self, db_config, output_dir: Path, timestamp_str: str):
        from django.db import connection
        db_name = connection.settings_dict.get("NAME") or db_config.get("NAME")
        if not db_name or db_name == ":memory:":
            raise CommandError("Không thể sao lưu SQLite CSDL in-memory (:memory:).")

        db_file = Path(db_name).resolve()
        if not db_file.exists():
            raise CommandError(f"File CSDL SQLite '{db_file}' không tồn tại.")

        final_backup_file = output_dir / f"backup_sqlite_{timestamp_str}.sqlite3"
        tmp_backup_file = output_dir / f"backup_sqlite_{timestamp_str}.tmp"

        try:
            src_conn = sqlite3.connect(str(db_file))
            dst_conn = sqlite3.connect(str(tmp_backup_file))
            with dst_conn:
                src_conn.backup(dst_conn)
            dst_conn.close()
            src_conn.close()

            sha256 = self._compute_sha256(tmp_backup_file)
            if final_backup_file.exists():
                final_backup_file.unlink()
            tmp_backup_file.rename(final_backup_file)

            manifest = {
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "engine": "sqlite3",
                "original_database": str(db_file.name),
                "backup_filename": final_backup_file.name,
                "file_size_bytes": final_backup_file.stat().st_size,
                "sha256_checksum": sha256,
            }
            manifest_file = output_dir / f"backup_sqlite_{timestamp_str}.manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return final_backup_file, manifest_file
        except Exception as exc:
            if tmp_backup_file.exists():
                tmp_backup_file.unlink()
            raise CommandError(f"Lỗi sao lưu SQLite: {exc}")

    def _backup_postgresql(self, db_config, output_dir: Path, timestamp_str: str):
        db_name = db_config.get("NAME")
        user = db_config.get("USER", os.environ.get("PGUSER", "postgres"))
        host = db_config.get("HOST", os.environ.get("PGHOST", "localhost"))
        port = str(db_config.get("PORT", os.environ.get("PGPORT", "5432")))
        password = db_config.get("PASSWORD", os.environ.get("PGPASSWORD", ""))

        final_backup_file = output_dir / f"backup_pg_{db_name}_{timestamp_str}.dump"
        tmp_backup_file = output_dir / f"backup_pg_{db_name}_{timestamp_str}.tmp"

        env = os.environ.copy()
        if password:
            env["PGPASSWORD"] = password

        cmd = [
            "pg_dump",
            "-h", host,
            "-p", port,
            "-U", user,
            "-F", "c",
            "-b",
            "-v",
            "-f", str(tmp_backup_file),
            db_name,
        ]

        try:
            subprocess.run(cmd, env=env, capture_output=True, text=True, check=True)
            sha256 = self._compute_sha256(tmp_backup_file)
            tmp_backup_file.rename(final_backup_file)

            manifest = {
                "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                "engine": "postgresql",
                "database_name": db_name,
                "backup_filename": final_backup_file.name,
                "file_size_bytes": final_backup_file.stat().st_size,
                "sha256_checksum": sha256,
            }
            manifest_file = output_dir / f"backup_pg_{db_name}_{timestamp_str}.manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            return final_backup_file, manifest_file
        except FileNotFoundError:
            raise CommandError("Lệnh 'pg_dump' không tìm thấy trong PATH môi trường hệ thống.")
        except subprocess.CalledProcessError as err:
            if tmp_backup_file.exists():
                tmp_backup_file.unlink()
            raise CommandError(f"pg_dump thất bại: {err.stderr.strip()}")

    def _compute_sha256(self, filepath: Path) -> str:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _apply_retention(self, output_dir: Path, retention_count: int):
        backup_files = sorted(
            [f for f in output_dir.glob("backup_*.*") if not f.name.endswith(".manifest.json") and not f.name.endswith(".tmp")],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if len(backup_files) > retention_count:
            files_to_remove = backup_files[retention_count:]
            for old_file in files_to_remove:
                old_file.unlink(missing_ok=True)
                manifest = old_file.with_name(f"{old_file.stem}.manifest.json")
                manifest.unlink(missing_ok=True)
                self.stdout.write(self.style.WARNING(f" [Retention] Đã xóa bản sao lưu cũ: {old_file.name}"))

