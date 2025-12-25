"""app.py

Minimal application startup script: performs a DB backup (if configured) and seeds
an initial pending admin user (no default password). Uses logging rather than prints.
"""

import logging
import os

import streamlit as st

from core.auth import seed_admin_if_empty
from core.db import backup_db, get_db_path, get_backup_dir


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting app. DB path=%s backups=%s", get_db_path(), get_backup_dir())

    try:
        backup_path = backup_db()
        if backup_path:
            logger.info("DB backup created: %s", backup_path)
    except Exception:
        logger.exception("DB backup failed")

    try:
        seed_admin_if_empty()
    except Exception:
        logger.exception("Seeding initial admin failed")

    # Minimal Streamlit UI bootstrap
    st.title("GE Application")
    st.write("Welcome. Please log in.")


if __name__ == "__main__":
    main()
