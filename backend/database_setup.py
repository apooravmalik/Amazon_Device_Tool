# backend/database_setup.py
import sqlite3
import os
from logger import get_logger

logger = get_logger(__name__)

SQLITE_DB_PATH = "building_schedules.db"

def init_sqlite_db():
    """
    Ensures the SQLite database and all tables exist
    without deleting existing data.
    """
    try:
        with sqlite3.connect(SQLITE_DB_PATH) as conn:
            logger.info("Connecting to database... ensuring tables exist.")

            # Table for building schedules
            conn.execute("""
                CREATE TABLE IF NOT EXISTS building_times (
                    building_id INTEGER PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for ignored proevents
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ignored_proevents (
                    proevent_id INTEGER PRIMARY KEY,
                    building_frk INTEGER NOT NULL,
                    device_prk INTEGER NOT NULL,
                    ignore_on_arm BOOLEAN NOT NULL DEFAULT 0,
                    ignore_on_disarm BOOLEAN NOT NULL DEFAULT 0
                )
            """)

            # Table for ProEvent state history
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proevent_state_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proevent_id INTEGER NOT NULL,
                    building_frk INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Table for our snapshots
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_state_snapshot (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    building_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    original_state INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(building_id, device_id)
                )
            """)

            conn.commit()
        logger.info("SQLite database tables verified successfully.")

    except Exception as e:
        logger.error(f"Error initializing SQLite database: {e}")
        raise

if __name__ == "__main__":
    init_sqlite_db()
    print("\nDatabase setup complete (safe mode).")