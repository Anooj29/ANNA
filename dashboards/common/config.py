"""Environment-driven configuration shared by all ANNA dashboards.

Mirrors the style of anna_robot/config.py so the whole project stays
consistent: sane defaults for local development, everything overridable
with environment variables, nothing hardcoded that a deployment would need
to touch source code to change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load variables from a .env file in the current working directory (the
# repo root, by convention) so one .env covers the robot and every
# dashboard. Safe to call even if no .env file exists.
load_dotenv()


@dataclass
class DashboardConfig:
    # "sqlite" (default - zero setup, one file on disk, great for local dev
    # on a single machine) or "postgres" (needed once multiple dashboards
    # on different machines must share the same live data).
    db_engine: str = "sqlite"
    sqlite_path: str = "anna_dashboard.db"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "anna_hospital"
    postgres_user: str = "anna"
    postgres_password: str = "anna_dev_password"

    # Shared with anna_robot.config.Config.known_faces_dir - both the robot
    # and this dashboard need to agree on where reference photos live.
    known_faces_dir: str = "known_faces"

    total_beds: int = 20
    patient_id_prefix: str = "ANP"

    receptionist_port: int = 8001
    clinician_port: int = 8002
    patient_port: int = 8003
    vision_port: int = 8004
    # Development credentials. Set both in .env before using this on a real
    # network; sessions are deliberately kept in the browser, not the DB.
    clinician_email: str = "doctor@anna.local"
    clinician_password: str = "change-me"
    session_secret: str = "replace-this-with-a-long-random-secret"
    robot_api_key: str = "change-robot-key"
    # The browser never receives this address or token: the vision dashboard
    # proxies the MJPEG stream after its own authenticated session check.
    robot_vision_stream_url: str = ""
    robot_vision_token: str = ""

    @property
    def database_url(self) -> str:
        if self.db_engine == "sqlite":
            return f"sqlite:///{self.sqlite_path}"
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        return cls(
            db_engine=os.environ.get("DB_ENGINE", cls.db_engine).strip().lower(),
            sqlite_path=os.environ.get("SQLITE_PATH", cls.sqlite_path),
            postgres_host=os.environ.get("POSTGRES_HOST", cls.postgres_host),
            postgres_port=int(os.environ.get("POSTGRES_PORT", cls.postgres_port)),
            postgres_db=os.environ.get("POSTGRES_DB", cls.postgres_db),
            postgres_user=os.environ.get("POSTGRES_USER", cls.postgres_user),
            postgres_password=os.environ.get("POSTGRES_PASSWORD", cls.postgres_password),
            known_faces_dir=os.environ.get("ROBOT_KNOWN_FACES_DIR", cls.known_faces_dir),
            total_beds=int(os.environ.get("HOSPITAL_TOTAL_BEDS", cls.total_beds)),
            patient_id_prefix=os.environ.get("PATIENT_ID_PREFIX", cls.patient_id_prefix),
            receptionist_port=int(os.environ.get("RECEPTIONIST_PORT", cls.receptionist_port)),
            clinician_port=int(os.environ.get("CLINICIAN_PORT", cls.clinician_port)),
            patient_port=int(os.environ.get("PATIENT_PORT", cls.patient_port)),
            vision_port=int(os.environ.get("VISION_PORT", cls.vision_port)),
            clinician_email=os.environ.get("CLINICIAN_EMAIL", cls.clinician_email).strip().lower(),
            clinician_password=os.environ.get("CLINICIAN_PASSWORD", cls.clinician_password),
            session_secret=os.environ.get("DASHBOARD_SESSION_SECRET", cls.session_secret),
            robot_api_key=os.environ.get("ROBOT_API_KEY", cls.robot_api_key),
            robot_vision_stream_url=os.environ.get("ROBOT_VISION_STREAM_URL", cls.robot_vision_stream_url).strip(),
            robot_vision_token=os.environ.get("ROBOT_VISION_STREAM_TOKEN", cls.robot_vision_token),
        )


config = DashboardConfig.from_env()
