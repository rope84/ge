"""core/db.py

Provides a sqlite connection factory with configurable DB path and backup utilities.
Environment variables:
 - GE_DB_PATH: path to sqlite database file (default: ./ge.db)
 - GE_BACKUP_DIR: directory where DB backups are stored (default: ./backups)

Includes backup rotation keeping the most recent 7 backups.
Uses logging instead of prints.
"""

from contextlib import contextmanager
import os
import sqlite3
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("GE_DB_PATH", "ge.db")
BACKUP_DIR = os.getenv("GE_BACKUP_DIR", "./backups")
BACKUP_KEEP = int(os.getenv("GE_BACKUPS_KEEP", "7"))


def get_db_path() -> str:
    return str(Path(DB_PATH).expanduser().resolve())


def get_backup_dir() -> str:
    return str(Path(BACKUP_DIR).expanduser().resolve())


@contextmanager
def conn() -> Iterator[sqlite3.Connection]:
    """Context manager yielding a sqlite3.Connection. Caller should not call commit/close.
    Commits any pending transactions and closes the connection on exit.
    """
    db_file = get_db_path()
    db_dir = Path(db_file).parent
    if not db_dir.exists():
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.exception("Failed to create DB directory: %s", db_dir)
    # ensure file exists (sqlite will create on connect)
    try:
        cn = sqlite3.connect(db_file, check_same_thread=False)
    except Exception:
        logger.exception("Failed to connect to database at %s", db_file)
        raise
    try:
        yield cn
        try:
            cn.commit()
        except Exception:
            logger.exception("Failed to commit transaction")
    finally:
        try:
            cn.close()
        except Exception:
            logger.exception("Failed to close DB connection")


def backup_db() -> Optional[str]:
    """Create a timestamped copy of the DB in the backup dir and rotate old backups.
    Returns the path to the created backup or None if no DB file exists.
    """
    db_file = Path(get_db_path())
    if not db_file.exists():
        logger.info("Database file does not exist, skipping backup: %s", db_file)
        return None

    backup_dir = Path(get_backup_dir())
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("Failed to create backup directory: %s", backup_dir)
        return None

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    backup_name = f"{db_file.stem}_{timestamp}{db_file.suffix}"
    backup_path = backup_dir / backup_name

    try:
        shutil.copy2(str(db_file), str(backup_path))
        logger.info("Database backed up to %s", backup_path)
    except Exception:
        logger.exception("Failed to copy DB to backup location: %s", backup_path)
        return None

    # rotate backups: keep most recent BACKUP_KEEP files
    try:
        backups = sorted([p for p in backup_dir.iterdir() if p.is_file() and p.name.startswith(db_file.stem)], key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[BACKUP_KEEP:]:
            try:
                old.unlink()
                logger.info("Removed old backup: %s", old)
            except Exception:
                logger.exception("Failed to remove old backup: %s", old)
    except Exception:
        logger.exception("Failed during backup rotation in %s", backup_dir)

    return str(backup_path)


# Optionally run a backup on import if env var set
if os.getenv("GE_BACKUP_ON_STARTUP", "false").lower() in ("1", "true", "yes"):
    try:
        backup_db()
    except Exception:
        logger.exception("Automatic DB backup on startup failed")
