cmake_minimum_required(VERSION 3.13)
project(AnnaHealthcareRobot NONE)

# -----------------------------------------------------------------------------
# This is a pure-Python project. CMake is used here as a convenience
# build/run/install wrapper, and because `face_recognition`'s dependency
# `dlib` compiles a native C++ extension using CMake under the hood - so a
# working `cmake` binary (and a C++ toolchain) must already be on the system
# PATH before `pip install -r requirements.txt` is run.
#
# Typical usage:
#   mkdir build && cd build
#   cmake ..
#   cmake --build . --target deps     # create venv + install requirements.txt
#   cmake --build . --target check    # syntax-check the whole package
#   cmake --build . --target run      # start the robot
#   cmake --install . --prefix /opt   # copy a deployable copy to /opt/anna_robot
# -----------------------------------------------------------------------------

find_package(Python3 COMPONENTS Interpreter REQUIRED)
find_program(CMAKE_SELF_EXE cmake)
if(NOT CMAKE_SELF_EXE)
    message(WARNING "cmake was not found on PATH - dlib (a face_recognition "
                     "dependency) will fail to build without it.")
endif()

set(PROJECT_ROOT ${CMAKE_CURRENT_SOURCE_DIR})
set(VENV_DIR ${PROJECT_ROOT}/.venv)
if(WIN32)
    set(VENV_PYTHON ${VENV_DIR}/Scripts/python.exe)
else()
    set(VENV_PYTHON ${VENV_DIR}/bin/python3)
endif()

# Create (or reuse) a virtual environment so the system Python is never touched.
add_custom_target(venv
    COMMAND ${Python3_EXECUTABLE} -m venv ${VENV_DIR}
    COMMENT "Creating virtual environment in ${VENV_DIR}"
)

# Install all Python dependencies from requirements.txt into that venv.
add_custom_target(deps
    DEPENDS venv
    COMMAND ${VENV_PYTHON} -m pip install --upgrade pip
    COMMAND ${VENV_PYTHON} -m pip install -r ${PROJECT_ROOT}/requirements.txt
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Installing Python dependencies from requirements.txt (builds dlib via CMake - can take a while on a Raspberry Pi)"
)

# Byte-compile / syntax-check the whole package - a cheap smoke test that
# catches typos and import errors without needing the Pi hardware attached.
add_custom_target(check
    COMMAND ${Python3_EXECUTABLE} -m compileall -q ${PROJECT_ROOT}/anna_robot
    COMMENT "Syntax-checking the anna_robot package"
)

# Run the robot. Extra CLI flags can be passed with -DARGS="--no-debug-window".
add_custom_target(run
    COMMAND ${VENV_PYTHON} -m anna_robot.main ${ARGS}
    WORKING_DIRECTORY ${PROJECT_ROOT}
    DEPENDS check
    COMMENT "Starting the healthcare robot"
    USES_TERMINAL
)

# `cmake --install .` copies the package plus models/known_faces folders and
# the run script to CMAKE_INSTALL_PREFIX/share/anna_robot for deployment.
install(DIRECTORY anna_robot DESTINATION share/anna_robot)
install(DIRECTORY models DESTINATION share/anna_robot)
install(DIRECTORY known_faces DESTINATION share/anna_robot)
install(FILES requirements.txt run.sh README.md DESTINATION share/anna_robot)

# -----------------------------------------------------------------------------
# Dashboards (receptionist and clinician; a patient dashboard can slot in
# next to them). These run on a regular PC at the reception desk / nurse
# station, not the Raspberry Pi, so they get their own venv and their own
# requirements file (requirements-dashboard.txt) rather than sharing the
# robot's.
#
# One-command bring-up for dashboard 1:
#   mkdir build && cd build
#   cmake ..
#   cmake --build . --target receptionist
#
# That single command creates the dashboard venv, installs its deps,
# creates/seeds the schema (SQLite by default - no server needed), and
# starts the dashboard on http://localhost:8001. Set DB_ENGINE=postgres in
# .env and run 'cmake --build . --target db-up' first if you want Postgres
# instead.
# -----------------------------------------------------------------------------

set(DASHBOARD_VENV_DIR ${PROJECT_ROOT}/.venv-dashboard)
if(WIN32)
    set(DASHBOARD_VENV_PYTHON ${DASHBOARD_VENV_DIR}/Scripts/python.exe)
else()
    set(DASHBOARD_VENV_PYTHON ${DASHBOARD_VENV_DIR}/bin/python3)
endif()

find_program(DOCKER_EXE docker)
if(NOT DOCKER_EXE)
    message(WARNING "docker was not found on PATH - the 'db-up' target will "
                     "skip starting Postgres automatically. Point the "
                     "POSTGRES_* env vars (see .env.example) at an existing "
                     "Postgres instance instead.")
endif()

add_custom_target(dashboard-venv
    COMMAND ${Python3_EXECUTABLE} -m venv ${DASHBOARD_VENV_DIR}
    COMMENT "Creating dashboard virtual environment in ${DASHBOARD_VENV_DIR}"
)

add_custom_target(dashboard-deps
    DEPENDS dashboard-venv
    COMMAND ${DASHBOARD_VENV_PYTHON} -m pip install --upgrade pip
    COMMAND ${DASHBOARD_VENV_PYTHON} -m pip install -r ${PROJECT_ROOT}/requirements-dashboard.txt
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Installing dashboard dependencies (no C++ build toolchain required)"
)

# Postgres is optional: the dashboard defaults to SQLite (DB_ENGINE=sqlite
# in .env.example), which needs no server at all. Only run 'db-up' if
# you've set DB_ENGINE=postgres.
if(DOCKER_EXE)
    add_custom_target(db-up
        COMMAND ${DOCKER_EXE} compose up -d postgres
        WORKING_DIRECTORY ${PROJECT_ROOT}
        COMMENT "Starting Postgres via Docker"
    )
    add_custom_target(db-down
        COMMAND ${DOCKER_EXE} compose down
        WORKING_DIRECTORY ${PROJECT_ROOT}
        COMMENT "Stopping the Postgres container"
    )
else()
    add_custom_target(db-up
        COMMAND ${CMAKE_COMMAND} -E echo "docker not found - skipping automatic Postgres startup. Make sure Postgres is running and reachable using the POSTGRES_* values in .env before continuing."
        COMMENT "Postgres startup skipped (no docker)"
    )
endif()

add_custom_target(init-db
    DEPENDS dashboard-deps
    COMMAND ${DASHBOARD_VENV_PYTHON} -m dashboards.init_db
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Creating tables and seeding beds"
)

add_custom_target(receptionist
    DEPENDS init-db
    COMMAND ${DASHBOARD_VENV_PYTHON} -m uvicorn dashboards.receptionist.main:app --host 0.0.0.0 --port 8001
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Starting the receptionist dashboard on http://localhost:8001"
    USES_TERMINAL
)

add_custom_target(clinician
    DEPENDS init-db
    COMMAND ${DASHBOARD_VENV_PYTHON} -m uvicorn dashboards.clinician.main:app --host 0.0.0.0 --port 8002
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Starting the clinician dashboard on http://localhost:8002"
    USES_TERMINAL
)

add_custom_target(patient
    DEPENDS init-db
    COMMAND ${DASHBOARD_VENV_PYTHON} -m uvicorn dashboards.patient.main:app --host 0.0.0.0 --port 8003
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Starting the patient dashboard on http://localhost:8003"
    USES_TERMINAL
)

add_custom_target(vision
    DEPENDS dashboard-deps
    COMMAND ${DASHBOARD_VENV_PYTHON} -m uvicorn dashboards.vision.main:app --host 0.0.0.0 --port 8004
    WORKING_DIRECTORY ${PROJECT_ROOT}
    COMMENT "Starting the read-only robot vision dashboard on http://localhost:8004"
    USES_TERMINAL
)
