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
    # PostgreSQL is the sole supported hospital database.
    db_engine: str = "postgres"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "anna_hospital"
    postgres_user: str = "anna"
    postgres_password: str = ""

    # Shared with anna_robot.config.Config.known_faces_dir - both the robot
    # and this dashboard need to agree on where reference photos live.
    known_faces_dir: str = "known_faces"

    total_beds: int = 20
    patient_id_prefix: str = "ANP"

    receptionist_port: int = 8001
    clinician_port: int = 8002
    patient_port: int = 8003
    # Development credentials. Set both in .env before using this on a real
    # network; sessions are deliberately kept in the browser, not the DB.
    clinician_email: str = "doctor@anna.local"
    clinician_password: str = ""
    session_secret: str = ""
    robot_api_key: str = ""
    cors_origins: tuple[str, ...] = ()
    secure_cookies: bool = False
    enable_demo_simulation: bool = False
    manual_check_minutes: int = 10
    robot_offline_timeout_seconds: int = 120

    @property
    def database_url(self) -> str:
        if self.db_engine != "postgres":
            raise RuntimeError("ANNA hospital software requires DB_ENGINE=postgres.")
        from sqlalchemy.engine import URL
        return URL.create(
            "postgresql+psycopg2", username=self.postgres_user,
            password=self.postgres_password, host=self.postgres_host,
            port=self.postgres_port, database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @classmethod
    def from_env(cls) -> "DashboardConfig":
        return cls(
            db_engine=os.environ.get("DB_ENGINE", cls.db_engine).strip().lower(),
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
            clinician_email=os.environ.get("CLINICIAN_EMAIL", cls.clinician_email).strip().lower(),
            clinician_password=os.environ.get("CLINICIAN_PASSWORD", cls.clinician_password),
            session_secret=os.environ.get("DASHBOARD_SESSION_SECRET", cls.session_secret),
            robot_api_key=os.environ.get("ROBOT_API_KEY", cls.robot_api_key),
            cors_origins=tuple(origin.strip() for origin in os.environ.get("CORS_ORIGINS", "").split(",") if origin.strip()),
            secure_cookies=os.environ.get("SECURE_COOKIES", "false").lower() == "true",
            enable_demo_simulation=os.environ.get("ENABLE_DEMO_SIMULATION", "false").lower() == "true",
            manual_check_minutes=int(os.environ.get("MANUAL_CHECK_MINUTES", "10")),
            robot_offline_timeout_seconds=int(os.environ.get("ROBOT_OFFLINE_TIMEOUT_SECONDS", "120")),
        )


config = DashboardConfig.from_env()
