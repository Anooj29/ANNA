@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  echo ANNA needs a .env file. Copy .env.example to .env and set PostgreSQL and session credentials.
  pause
  exit /b 1
)
if not exist ".venv-dashboard\Scripts\python.exe" (
  echo Creating ANNA dashboard Python environment...
  py -3.12 -m venv .venv-dashboard
  if errorlevel 1 (
    echo Python 3.12 is required. Install it and run this file again.
    pause
    exit /b 1
  )
)
".venv-dashboard\Scripts\python.exe" -c "import fastapi, alembic, cv2, bcrypt, psycopg2" >nul 2>&1
if errorlevel 1 (
  echo Installing ANNA hospital software dependencies...
  ".venv-dashboard\Scripts\python.exe" -m pip install -r requirements-dashboard.txt
  if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
  )
)

echo Checking PostgreSQL configuration and applying ANNA migrations...
".venv-dashboard\Scripts\python.exe" -m dashboards.init_db
if errorlevel 1 (
  echo Startup stopped. Review the error above and database/MIGRATIONS.md.
  pause
  exit /b 1
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
  echo Port 8000 is already in use. Close the other ANNA window or stop the program using port 8000, then run this file again.
  pause
  exit /b 1
)

set "ANNA_LAN_IP="
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "Get-NetIPConfiguration | Where-Object { $_.IPv4Address -and $_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway } | Select-Object -First 1 -ExpandProperty IPv4Address | Select-Object -ExpandProperty IPAddress"`) do set "ANNA_LAN_IP=%%I"
echo ANNA is starting. Keep this window open.
echo On this computer: http://127.0.0.1:8000
if defined ANNA_LAN_IP echo On a phone connected to the same Wi-Fi: http://%ANNA_LAN_IP%:8000
if not defined ANNA_LAN_IP echo To find the mobile address, run ipconfig and use this computer's Wi-Fi IPv4 address with port 8000.
echo If the phone cannot connect, allow Python on private networks in Windows Firewall.
".venv-dashboard\Scripts\python.exe" -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
if errorlevel 1 pause
endlocal
