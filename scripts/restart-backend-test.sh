#!/usr/bin/env bash
set -Eeuo pipefail

# Restart backend-test on Debian/Ubuntu-like systems.
# - Kills processes on the target port and matching backend patterns
# - Starts via gunicorn (preferred), else waitress-serve, else python app.py
# - Supports optional venv activation and basic health check
#
# Usage:
#   ./scripts/restart-backend-test.sh                # defaults
#   PORT=8080 MODE=dev ./scripts/restart-backend-test.sh
#   VENV_DIR=/opt/projects/venv PORT=5000 MODE=gunicorn WORKERS=2 THREADS=2 ./scripts/restart-backend-test.sh
#
# Env vars:
#   PORT        (default 5001)
#   HOST        (default 0.0.0.0)
#   MODE        auto|gunicorn|waitress|dev (default auto)
#   WORKERS     (gunicorn workers, default 2)
#   THREADS     (gunicorn threads, default 1)
#   TIMEOUT     (gunicorn timeout, default 60)
#   VENV_DIR    (optional path to Python venv to activate)
#   PYTHON_BIN  (optional explicit python binary path)

PORT=${PORT:-5001}
HOST=${HOST:-0.0.0.0}
MODE=${MODE:-auto}
WORKERS=${WORKERS:-2}
THREADS=${THREADS:-1}
TIMEOUT=${TIMEOUT:-60}
VENV_DIR=${VENV_DIR:-}
PYTHON_BIN=${PYTHON_BIN:-}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$REPO_ROOT/backend-test"
LOG_DIR="$REPO_ROOT/logs"
LOG_FILE="$LOG_DIR/backend-test.log"

info() { echo -e "\e[36m[INFO]\e[0m $*"; }
warn() { echo -e "\e[33m[WARN]\e[0m $*"; }
err()  { echo -e "\e[31m[ERR ]\e[0m  $*"; }

if [[ ! -d "$BACKEND_DIR" ]]; then
  err "Backend-test directory not found: $BACKEND_DIR"
  exit 1
fi
mkdir -p "$LOG_DIR"

activate_venv() {
  if [[ -n "$VENV_DIR" && -f "$VENV_DIR/bin/activate" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_DIR/bin/activate"
    info "Activated venv: $VENV_DIR"
  elif [[ -f "$REPO_ROOT/venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "$REPO_ROOT/venv/bin/activate"
    info "Activated venv: $REPO_ROOT/venv"
  fi
}

resolve_python() {
  if [[ -n "$PYTHON_BIN" ]]; then
    command -v "$PYTHON_BIN" >/dev/null 2>&1 || { err "PYTHON_BIN not executable: $PYTHON_BIN"; exit 1; }
    echo "$PYTHON_BIN"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then echo python3; return; fi
  if command -v python >/dev/null 2>&1; then echo python; return; fi
  err "python not found in PATH"
  exit 1
}

kill_by_port() {
  local port="$1"
  local pids=()
  if command -v ss >/dev/null 2>&1; then
    # ss output parsing to get pids
    while read -r line; do
      pid=$(echo "$line" | sed -n 's/.*pid=\([0-9]\+\),.*/\1/p')
      if [[ -n "$pid" ]]; then pids+=("$pid"); fi
    done < <(ss -lptn "sport = :$port" 2>/dev/null | tail -n +2)
  fi
  if [[ ${#pids[@]} -eq 0 ]] && command -v lsof >/dev/null 2>&1; then
    mapfile -t pids < <(lsof -ti ":$port" 2>/dev/null || true)
  fi
  if [[ ${#pids[@]} -gt 0 ]]; then
    for pid in "${pids[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
        info "Killed PID $pid on port $port"
      fi
    done
  fi
}

kill_by_cmdpatterns() {
  # Match likely backend-test processes
  local patterns=(
    'backend-test/app.py'
    'backend-test/wsgi.py'
    'gunicorn.*backend-test.wsgi:application'
    'waitress-serve.*backend-test.wsgi:application'
  )
  while read -r pid cmd; do
    for pat in "${patterns[@]}"; do
      if [[ "$cmd" =~ $pat ]]; then
        kill -9 "$pid" 2>/dev/null || true
        info "Killed PID $pid ('$pat' match)"
        break
      fi
    done
  done < <(ps -eo pid=,args=)
}

start_backend() {
  cd "$BACKEND_DIR"
  if [[ "$MODE" == "gunicorn" ]] || { [[ "$MODE" == "auto" ]] && command -v gunicorn >/dev/null 2>&1; }; then
    info "Starting via gunicorn on $HOST:$PORT (w=$WORKERS t=$THREADS timeout=$TIMEOUT)"
    nohup gunicorn \
      --bind "$HOST:$PORT" \
      --workers "$WORKERS" \
      --threads "$THREADS" \
      --timeout "$TIMEOUT" \
      wsgi:application >> "$LOG_FILE" 2>&1 &
  elif [[ "$MODE" == "waitress" ]] || { [[ "$MODE" == "auto" ]] && command -v waitress-serve >/dev/null 2>&1; }; then
    info "Starting via waitress-serve on $HOST:$PORT"
    nohup waitress-serve --listen="$HOST:$PORT" wsgi:application >> "$LOG_FILE" 2>&1 &
  else
    local pybin
    pybin=$(resolve_python)
    info "Starting via $pybin app.py (dev) on $HOST:$PORT"
    HOST="$HOST" PORT="$PORT" nohup "$pybin" app.py >> "$LOG_FILE" 2>&1 &
  fi
}

health_check() {
  local url="http://127.0.0.1:$PORT/healthz"
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 5 "$url" >/dev/null; then
      echo OK
      return 0
    else
      echo FAIL
      return 1
    fi
  else
    echo SKIP
    return 0
  fi
}

info "Activating venv (if any)"
activate_venv

info "Stopping existing backend-test on port $PORT"
kill_by_port "$PORT" || true
kill_by_cmdpatterns || true
sleep 1

info "Starting backend-test"
start_backend
sleep 2

info "Health check"
if [[ "$(health_check)" == "OK" ]]; then
  info "Health check OK"
  info "Logs: $LOG_FILE"
else
  warn "Health check failed; check logs: $LOG_FILE"
fi
