# Implementation Plan: Update DB Credentials and Photo Server Configuration

## Overview
The goal is to remove hardcoded database credentials from `anna_robot/sync_faces.py`, introduce a separate configuration for the photo server host, and implement SSL for the AWS RDS connection.

## Requirements
- Update `anna_robot/config.py` to include `postgres_user`, `postgres_password`, and `photo_server_host`.
- Update `anna_robot/sync_faces.py` to use these configuration values.
- Implement SSL (`sslmode=require`) for the database connection in `anna_robot/sync_faces.py`.
- Use `photo_server_host` for photo downloads instead of `postgres_host`.
- Maintain backward compatibility where possible.

## Detailed Design

### 1. `anna_robot/config.py`
Modify the `Config` dataclass and the `from_env` method to support new configuration parameters.

- **Dataclass Changes**:
    - Add `postgres_user: str = "anna"`
    - Add `postgres_password: str = "anna_dev_password"`
    - Add `photo_server_host: Optional[str] = None`
- **`from_env` Changes**:
    - Load `postgres_user` from `POSTGRES_USER` environment variable.
    - Load `postgres_password` from `POSTGRES_PASSWORD` environment variable.
    - Load `photo_server_host` from `PHOTO_SERVER_HOST` environment variable.

### 2. `anna_robot/sync_faces.py`
Update the `FaceSync` class to use the new configuration and enable SSL.

- **`__init__` Method**:
    - Change the logic for `self.server_url`.
    - Use `config.photo_server_host` if it is set; otherwise, fallback to `config.postgres_host` to maintain backward compatibility.
    - `host = config.photo_server_host or config.postgres_host`
    - `self.server_url = f"http://{host}:8001/known_faces"`
- **`sync` Method**:
    - Update the `psycopg2.connect` call:
        - Replace `user="anna"` with `user=self.config.postgres_user`.
        - Replace `password="anna_dev_password"` with `password=self.config.postgres_password`.
        - Add `sslmode="require"` to the connection parameters.

## Implementation Steps

1.  **Update `anna_robot/config.py`**:
    - Add the new fields to the `Config` dataclass.
    - Update the `from_env` method to read these fields from environment variables.
2.  **Update `anna_robot/sync_faces.py`**:
    - Modify `FaceSync.__init__` to use the new host logic.
    - Modify `FaceSync.sync` to use configured credentials and SSL.

## Critical Files
- `anna_robot/config.py`
- `anna_robot/sync_faces.py`

## Potential Challenges
- **SSL Configuration**: Some environments might require specific SSL certificates for `sslmode=require`. For now, we will rely on the default `psycopg2` behavior which usually works with RDS if certificates are installed on the system or if `sslmode=require` is sufficient.
- **Backward Compatibility**: Using `config.photo_server_host or config.postgres_host` ensures that existing setups that only specify `POSTGRES_HOST` will still function.
