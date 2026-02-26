"""
Brahmastra Backup System
=========================
Automated backup of database + config files.
Compressed tar.gz backups with configurable retention.

Features:
    - Auto-backup every 6 hours (configurable)
    - Compressed .tar.gz with timestamps
    - Keep last N backups (default: 10)
    - Manual trigger via API
    - Restore capability
"""

import os
import time
import tarfile
import shutil
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("brahmastra.backup")


# ── Configuration ────────────────────────────────────────────────────────────
BACKUP_DIR = os.getenv("BACKUP_DIR", "/home/ubuntu/brahmastra/backups")
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
BACKUP_RETENTION = int(os.getenv("BACKUP_RETENTION", "10"))

# Files/dirs to back up
BACKEND_DIR = os.getenv("BACKEND_BASE_DIR", "/home/ubuntu/brahmastra/backend")
BACKUP_TARGETS = [
    os.path.join(BACKEND_DIR, "brahmastra.db"),
    os.path.join(BACKEND_DIR, ".env"),
]


class BackupManager:
    """Manages automated and manual backups of critical system files."""

    def __init__(self):
        self._backup_dir = Path(BACKUP_DIR)
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._last_backup: Optional[str] = None
        self._backup_count = 0
        self._lock = threading.Lock()
        self._start_time = time.time()
        self._scheduler_running = False
        logger.info(f"Backup manager initialized. Dir: {BACKUP_DIR}")

    def create_backup(self, label: str = "auto") -> dict:
        """Create a compressed backup of all target files."""
        with self._lock:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"brahmastra_backup_{label}_{timestamp}.tar.gz"
            filepath = self._backup_dir / filename

            try:
                files_backed_up = []
                with tarfile.open(str(filepath), "w:gz") as tar:
                    for target in BACKUP_TARGETS:
                        if os.path.exists(target):
                            arcname = os.path.basename(target)
                            tar.add(target, arcname=arcname)
                            files_backed_up.append(arcname)
                            logger.info(f"Backed up: {target}")
                        else:
                            logger.warning(f"Backup target not found: {target}")

                # Get file size
                size_bytes = filepath.stat().st_size if filepath.exists() else 0
                size_kb = round(size_bytes / 1024, 1)

                self._last_backup = str(filepath)
                self._backup_count += 1

                # Enforce retention
                self._enforce_retention()

                result = {
                    "success": True,
                    "filename": filename,
                    "path": str(filepath),
                    "size_kb": size_kb,
                    "files": files_backed_up,
                    "timestamp": timestamp,
                    "label": label,
                }
                logger.info(f"Backup created: {filename} ({size_kb} KB, {len(files_backed_up)} files)")
                return result

            except Exception as e:
                logger.error(f"Backup failed: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": timestamp,
                }

    def list_backups(self) -> List[dict]:
        """List all available backups."""
        backups = []
        if not self._backup_dir.exists():
            return backups

        for f in sorted(self._backup_dir.glob("brahmastra_backup_*.tar.gz"), reverse=True):
            stat = f.stat()
            backups.append({
                "filename": f.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "path": str(f),
            })
        return backups

    def restore_backup(self, filename: str) -> dict:
        """Restore from a specific backup file."""
        filepath = self._backup_dir / filename
        if not filepath.exists():
            return {"success": False, "error": f"Backup not found: {filename}"}

        try:
            # Extract to a temp dir first
            restore_dir = self._backup_dir / "restore_temp"
            restore_dir.mkdir(exist_ok=True)

            with tarfile.open(str(filepath), "r:gz") as tar:
                tar.extractall(str(restore_dir))

            # Copy restored files to their original locations
            restored_files = []
            for item in restore_dir.iterdir():
                dest = os.path.join(BACKEND_DIR, item.name)
                # Create backup of current file before overwriting
                if os.path.exists(dest):
                    shutil.copy2(dest, dest + ".pre_restore")
                shutil.copy2(str(item), dest)
                restored_files.append(item.name)

            # Cleanup temp
            shutil.rmtree(str(restore_dir), ignore_errors=True)

            logger.info(f"Restored from: {filename}, files: {restored_files}")
            return {
                "success": True,
                "filename": filename,
                "restored_files": restored_files,
                "note": "Restart the service for changes to take effect",
            }

        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return {"success": False, "error": str(e)}

    def get_status(self) -> dict:
        """Get backup system status."""
        backups = self.list_backups()
        return {
            "enabled": True,
            "backup_dir": str(self._backup_dir),
            "total_backups": len(backups),
            "total_created": self._backup_count,
            "last_backup": self._last_backup,
            "interval_hours": BACKUP_INTERVAL_HOURS,
            "retention": BACKUP_RETENTION,
            "disk_usage_kb": sum(b["size_kb"] for b in backups),
            "recent_backups": backups[:5],
            "scheduler_running": self._scheduler_running,
        }

    def _enforce_retention(self):
        """Remove oldest backups if we exceed retention limit."""
        backups = sorted(
            self._backup_dir.glob("brahmastra_backup_*.tar.gz"),
            key=lambda f: f.stat().st_mtime,
        )
        while len(backups) > BACKUP_RETENTION:
            oldest = backups.pop(0)
            oldest.unlink()
            logger.info(f"Removed old backup: {oldest.name}")

    def start_scheduler(self):
        """Start the background backup scheduler."""
        if self._scheduler_running:
            return

        def _run():
            self._scheduler_running = True
            logger.info(f"Backup scheduler started (every {BACKUP_INTERVAL_HOURS}h)")
            while True:
                time.sleep(BACKUP_INTERVAL_HOURS * 3600)
                logger.info("Scheduled backup starting...")
                self.create_backup(label="scheduled")

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()


# Singleton
backup_manager = BackupManager()
