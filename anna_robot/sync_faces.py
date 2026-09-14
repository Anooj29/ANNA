import os
import logging
import requests
from datetime import datetime
from typing import List, Tuple
import psycopg2

from .config import Config

logger = logging.getLogger("sync_faces")

class FaceSync:
    def __init__(self, config: Config):
        self.config = config
        # Use photo_server_host if provided, otherwise fallback to postgres_host for backward compatibility
        host = config.photo_server_host or config.postgres_host
        self.server_url = f"http://{host}:8001/known_faces"
        self.last_sync_file = os.path.join(config.known_faces_dir, ".last_sync")

    def _get_last_sync_time(self) -> datetime:
        if os.path.exists(self.last_sync_file):
            try:
                with open(self.last_sync_file, "r") as f:
                    return datetime.fromisoformat(f.read().strip())
            except Exception:
                pass
        return datetime.min

    def _set_last_sync_time(self, t: datetime):
        with open(self.last_sync_file, "w") as f:
            f.write(t.isoformat())

    def sync(self) -> int:
        """Checks for new patients and downloads their reference photos. Returns count of new faces."""
        last_sync = self._get_last_sync_time()
        logger.info("Checking for new faces since %s...", last_sync)

        try:
            # Connect to the Postgres database (supports AWS RDS with SSL)
            conn = psycopg2.connect(
                dbname=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                host=self.config.postgres_host,
                port=5432,
                sslmode="require"
            )
            with conn.cursor() as cur:
                # Find patients registered after the last sync
                cur.execute(
                    "SELECT full_name, photo_path FROM patients WHERE registered_at > %s",
                    (last_sync,)
                )
                new_patients = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.error("Failed to check for new faces in DB: %s", e)
            return 0

        if not new_patients:
            return 0

        added_count = 0
        for name, photo_path in new_patients:
            # Extract the folder name from the path (e.g., "known_faces/Anna/reference.jpg" -> "Anna")
            # The photo_path is stored as a relative path from the project root.
            parts = photo_path.split(os.sep)
            # Usually known_faces/Name/reference.jpg
            if len(parts) >= 2:
                folder_name = parts[1] # This is the "Anna" part
                # Construct the URL to the photo on the laptop
                url = f"{self.server_url}/{folder_name}/reference.jpg"
                
                try:
                    logger.info("Downloading face for %s from %s", name, url)
                    resp = requests.get(url, timeout=5)
                    if resp.status_code == 200:
                        # Save locally
                        local_dir = os.path.join(self.config.known_faces_dir, folder_name)
                        os.makedirs(local_dir, exist_ok=True)
                        with open(os.path.join(local_dir, "reference.jpg"), "wb") as f:
                            f.write(resp.content)
                        added_count += 1
                    else:
                        logger.warning("Failed to download photo for %s: HTTP %d", name, resp.status_code)
                except Exception as e:
                    logger.error("Error downloading photo for %s: %s", name, e)

        if added_count > 0:
            self._set_last_sync_time(datetime.now())
            logger.info("Successfully synced %d new face(s).", added_count)
        
        return added_count
