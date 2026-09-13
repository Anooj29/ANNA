"""Background utility to synchronize local session data to AWS PostgreSQL."""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any

import psycopg2
from psycopg2.extras import Json

# --- CONFIGURATION ---
# It is recommended to move these to environment variables or a config file.
DB_CONFIG = {
    "dbname": "postgres",
    "user": "postgres_anna",
    "password": "Dishant2006",
    "host": "database-1.criue6qwy4lg.eu-north-1.rds.amazonaws.com",
    "port": "5432",
    "sslmode": "require",
}
SESSIONS_DIR = "sessions"
# ---------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sync_sessions")

def sync_session_to_db(conn, folder_path: str, data: Dict[str, Any]) -> None:
    """Inserts session data into the PostgreSQL table."""
    with conn.cursor() as cur:
        query = """
            INSERT INTO patient_sessions
            (patient_name, emotion, temperature, pulse, ecg, health_report, answers, timestamp)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            data.get("name", "--"),
            data.get("emotion", "--"),
            data.get("temperature", "--"),
            data.get("pulse", "--"),
            data.get("ecg", "--"),
            data.get("health_report", "--"),
            Json(data.get("answers", {})),
            data.get("timestamp", datetime.now().isoformat()),
        )
        cur.execute(query, params)
    conn.commit()

def main() -> None:
    if not os.path.isdir(SESSIONS_DIR):
        logger.error("Sessions directory '%s' not found.", SESSIONS_DIR)
        return

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Connected to AWS PostgreSQL.")
    except Exception:
        logger.exception("Failed to connect to AWS PostgreSQL. Exiting.")
        return

    try:
        # Scan for session folders
        for folder_name in sorted(os.listdir(SESSIONS_DIR)):
            folder_path = os.path.join(SESSIONS_DIR, folder_name)
            if not os.path.isdir(folder_path):
                continue

            # Check if already synced
            if os.path.exists(os.path.join(folder_path, ".synced")):
                continue

            # Read data.json
            data_file = os.path.join(folder_path, "data.json")
            if not os.path.exists(data_file):
                logger.warning("No data.json found in %s. Skipping.", folder_path)
                continue

            try:
                with open(data_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                sync_session_to_db(conn, folder_path, data)

                # Mark as synced
                with open(os.path.join(folder_path, ".synced"), "w") as f:
                    f.write("synced")

                logger.info("Successfully synced session: %s", folder_name)
            except Exception:
                logger.exception("Failed to sync session %s.", folder_name)

    finally:
        conn.close()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    main()
