import os
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

def backup_sqlite_database(
    db_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None
) -> Path:
    """
    Safely creates an atomic backup of the SQLite database using the SQLite backup API.
    Returns the Path to the verified backup file.
    """
    if db_path is None:
        from story_forecaster.db.session import DEFAULT_DB_FILE
        db_path = DEFAULT_DB_FILE

    db_path = Path(db_path).resolve()
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    if backup_dir is None:
        backup_dir = db_path.parent / "backups"
    backup_dir = Path(backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{db_path.stem}_{timestamp}.bak.db"
    backup_path = backup_dir / backup_filename

    # Use SQLite Online Backup API for safe transaction-safe copy
    src_conn = sqlite3.connect(str(db_path))
    try:
        dest_conn = sqlite3.connect(str(backup_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    # Verify backup integrity
    verify_conn = sqlite3.connect(str(backup_path))
    try:
        cursor = verify_conn.cursor()
        cursor.execute("PRAGMA quick_check")
        res = cursor.fetchone()
        if not res or res[0] != "ok":
            raise RuntimeError(f"Backup integrity check failed: {res}")
    finally:
        verify_conn.close()

    return backup_path
