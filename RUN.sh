#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
BACKEND_ENV_FILE="$ROOT_DIR/backend/.env"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$LOG_DIR/pids"
SELECTED_MODE=""
COMPOSE_CMD=()

prompt_with_default() {
  local prompt="$1"
  local default_value="$2"
  local answer=""
  read -r -p "$prompt [$default_value]: " answer
  if [[ -z "$answer" ]]; then
    printf '%s' "$default_value"
  else
    printf '%s' "$answer"
  fi
}

normalize_mode() {
  local raw_mode="$1"
  case "$raw_mode" in
    docker|DOCKER|Docker)
      printf '%s' "docker"
      ;;
    local|LOCAL|Local|non-docker|NON-DOCKER|Non-docker|nondocker|NONDOCKER|NonDocker)
      printf '%s' "local"
      ;;
    *)
      printf '%s' ""
      ;;
  esac
}

resolve_mode() {
  local requested_mode="${1:-}"
  local default_mode="local"

  if compose_available; then
    default_mode="docker"
  fi

  if [[ -n "$requested_mode" ]]; then
    SELECTED_MODE="$(normalize_mode "$requested_mode")"
  else
    SELECTED_MODE="$(normalize_mode "$(prompt_with_default 'Choose startup mode (docker/local)' "$default_mode")")"
  fi

  if [[ -z "$SELECTED_MODE" ]]; then
    echo "Unsupported startup mode. Expected docker or local."
    exit 1
  fi
}

compose_available() {
  docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1
}

compose_accessible() {
  docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1 || return 1

  if docker info >/dev/null 2>&1; then
    return 0
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    return 0
  fi

  return 1
}

select_compose_cmd() {
  if docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker compose version >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    COMPOSE_CMD=(sudo docker compose)
  elif command -v sudo >/dev/null 2>&1 && command -v docker-compose >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    COMPOSE_CMD=(sudo docker-compose)
  else
    echo "Docker Compose is installed, but the current user cannot access Docker."
    echo "Try one of the following:"
    echo "1. Run: sudo systemctl enable --now docker"
    echo "2. Run: sudo usermod -aG docker $USER  and then log in again"
    echo "3. Rerun this script in local mode"
    return 1
  fi
}

sync_env_to_backend() {
  if [[ -f "$ENV_FILE" && -d "$ROOT_DIR/backend" ]]; then
    # Fix ownership if a prior Docker run left root-owned files
    if [[ ! -w "$ROOT_DIR/backend" ]]; then
      sudo chown "$(id -u):$(id -g)" "$ROOT_DIR/backend"
    fi
    if [[ -f "$BACKEND_ENV_FILE" ]] && [[ ! -w "$BACKEND_ENV_FILE" ]]; then
      sudo chown "$(id -u):$(id -g)" "$BACKEND_ENV_FILE"
    fi
    cp "$ENV_FILE" "$BACKEND_ENV_FILE"
  fi
}

# Read a KEY=VALUE from $ENV_FILE; fall back to $2 if missing/empty.
read_env_value() {
  local key="$1"
  local default_value="$2"
  local value=""
  if [[ -f "$ENV_FILE" ]]; then
    value="$(grep -E "^${key}=" "$ENV_FILE" | tail -n 1 | cut -d '=' -f 2-)"
    # strip surrounding quotes and whitespace
    value="${value%\"}"; value="${value#\"}"
    value="${value%\'}"; value="${value#\'}"
    value="$(echo -n "$value" | sed -E 's/^[[:space:]]+|[[:space:]]+$//g')"
  fi
  if [[ -z "$value" ]]; then
    value="$default_value"
  fi
  printf '%s' "$value"
}

print_credentials() {
  local frontend_url="$1"
  local admin_pw="$2"
  # Use ANSI bold/color if the terminal supports it
  local BOLD="" CYAN="" RESET=""
  if [[ -t 1 ]]; then
    BOLD="\033[1m"
    CYAN="\033[1;36m"
    RESET="\033[0m"
  fi
  echo ""
  echo -e "${CYAN}╔══════════════════════════════════════════════╗${RESET}"
  echo -e "${CYAN}║      CC Security Management System           ║${RESET}"
  echo -e "${CYAN}╠══════════════════════════════════════════════╣${RESET}"
  echo -e "${CYAN}║${RESET}  ${BOLD}Frontend URL :${RESET}  $frontend_url"
  echo -e "${CYAN}║${RESET}  ${BOLD}Username     :${RESET}  admin"
  echo -e "${CYAN}║${RESET}  ${BOLD}Password     :${RESET}  $admin_pw"
  echo -e "${CYAN}║${RESET}"
  echo -e "${CYAN}║${RESET}  ⚠  First login requires a password change."
  echo -e "${CYAN}║${RESET}     If admin existed before, this password"
  echo -e "${CYAN}║${RESET}     may not apply — check your .env file."
  echo -e "${CYAN}╚══════════════════════════════════════════════╝${RESET}"
  echo ""
}

ensure_local_prerequisites() {
  [[ -x "$ROOT_DIR/backend/.venv/bin/uvicorn" ]] || {
    echo "Local backend is not ready: missing $ROOT_DIR/backend/.venv/bin/uvicorn"
    exit 1
  }
  [[ -x "$ROOT_DIR/backend/.venv/bin/arq" ]] || {
    echo "Local worker is not ready: missing $ROOT_DIR/backend/.venv/bin/arq"
    exit 1
  }
  command -v npm >/dev/null 2>&1 || {
    echo "Local frontend is not ready: npm is not installed"
    exit 1
  }
  [[ -f "$ROOT_DIR/frontend/package.json" ]] || {
    echo "Local frontend is not ready: missing $ROOT_DIR/frontend/package.json"
    exit 1
  }
}

start_local_services() {
  ensure_local_prerequisites
  mkdir -p "$LOG_DIR" "$PID_DIR"
  sync_env_to_backend

  local backend_host backend_port frontend_port
  backend_host="$(read_env_value BACKEND_HOST 0.0.0.0)"
  backend_port="$(read_env_value BACKEND_PORT 8000)"
  frontend_port="$(read_env_value FRONTEND_PORT 8080)"

  echo "Starting local services."
  echo "  BACKEND_HOST=$backend_host BACKEND_PORT=$backend_port FRONTEND_PORT=$frontend_port"

  if [[ "$frontend_port" -lt 1024 ]] && [[ "$(id -u)" != "0" ]]; then
    echo "WARNING: FRONTEND_PORT=$frontend_port is a privileged port; vite will fail to bind without root."
    echo "         Set FRONTEND_PORT to something >=1024 (e.g. 8080) in .env, or run RUN.sh with sudo."
  fi

  echo "Initializing database (idempotent — safe to run on every start)"
  (
    cd "$ROOT_DIR/backend"
    ./.venv/bin/python -m app.scripts.migrate_add_logs_and_user_flag >> "$LOG_DIR/backend.log" 2>&1 || {
      echo "Migration failed; see $LOG_DIR/backend.log"
      exit 1
    }
    # Run init_db and tee output so the admin password is shown in the terminal
    ./.venv/bin/python -m app.scripts.init_db 2>&1 | tee -a "$LOG_DIR/backend.log" || {
      echo "Database initialization failed; see $LOG_DIR/backend.log"
      exit 1
    }
  )

  echo "Starting backend API in the background (http://$backend_host:$backend_port)"
  (
    cd "$ROOT_DIR/backend"
    nohup ./.venv/bin/uvicorn app.main:app --host "$backend_host" --port "$backend_port" >> "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"
  )

  echo "Starting worker in the background"
  (
    cd "$ROOT_DIR/backend"
    nohup ./.venv/bin/arq app.worker.settings.WorkerSettings > "$LOG_DIR/worker.log" 2>&1 &
    echo $! > "$PID_DIR/worker.pid"
  )

  echo "Starting frontend dev server in the background (port $frontend_port)"
  (
    cd "$ROOT_DIR/frontend"
    nohup npm run dev -- --host 0.0.0.0 --port "$frontend_port" --strictPort > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"
  )

  echo "CC Security started in local mode."
  echo "Logs:"
  echo "- Backend: $LOG_DIR/backend.log"
  echo "- Worker:  $LOG_DIR/worker.log"
  echo "- Frontend: $LOG_DIR/frontend.log"
  echo "Backend health: http://localhost:$backend_port/api/health"

  local _local_frontend_url
  if [[ "$frontend_port" == "80" ]]; then
    _local_frontend_url="http://localhost/"
  else
    _local_frontend_url="http://localhost:$frontend_port/"
  fi
  local _local_admin_pw
  _local_admin_pw="$(read_env_value ADMIN_INITIAL_PASSWORD 'Admin@123456')"
  print_credentials "$_local_frontend_url" "$_local_admin_pw"
}

stop_local_services() {
  local service_name
  local pid_file
  local pid
  local stopped=false

  for service_name in backend worker frontend; do
    pid_file="$PID_DIR/$service_name.pid"
    if [[ -f "$pid_file" ]]; then
      pid="$(cat "$pid_file")"
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        kill "$pid" >/dev/null 2>&1 || true
        echo "Stopped local $service_name service (PID $pid)."
        stopped=true
      fi
      rm -f "$pid_file"
    fi
  done

  if [[ "$stopped" == false ]]; then
    echo "No tracked local services were running."
  fi
}

show_local_logs() {
  mkdir -p "$LOG_DIR"
  touch "$LOG_DIR/backend.log" "$LOG_DIR/worker.log" "$LOG_DIR/frontend.log"
  tail -f "$LOG_DIR/backend.log" "$LOG_DIR/worker.log" "$LOG_DIR/frontend.log"
}

# Write or update KEY=VALUE in $ENV_FILE.
set_env_value() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example."
fi

# Auto-generate SECRET_KEY if missing or still at default placeholder.
_current_secret="$(read_env_value SECRET_KEY '')"
if [[ -z "$_current_secret" || "$_current_secret" == change-me* ]]; then
  _current_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(64))')"
  set_env_value SECRET_KEY "$_current_secret"
  echo "Generated SECRET_KEY automatically."
fi

# Ensure ADMIN_INITIAL_PASSWORD is set (carry forward from .env.example default).
_current_admin_pw="$(read_env_value ADMIN_INITIAL_PASSWORD '')"
if [[ -z "$_current_admin_pw" ]]; then
  set_env_value ADMIN_INITIAL_PASSWORD 'Admin@123456'
  echo "Set ADMIN_INITIAL_PASSWORD=Admin@123456 in .env."
fi
unset _current_admin_pw

# Auto-generate ENCRYPTION_KEY if missing.
_current_enc="$(read_env_value ENCRYPTION_KEY '')"
if [[ -z "$_current_enc" ]]; then
  _current_enc="$(python3 - <<'PY'
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ModuleNotFoundError:
    import secrets
    print(secrets.token_urlsafe(48))
PY
)"
  set_env_value ENCRYPTION_KEY "$_current_enc"
  echo "Generated ENCRYPTION_KEY automatically."
fi

ACTION="${1:-up}"
MODE_ARG="${2:-}"

resolve_mode "$MODE_ARG"

case "$ACTION" in
  up)
    if [[ "$SELECTED_MODE" == "docker" ]]; then
      if ! compose_available; then
        echo "Docker startup was selected, but Docker Compose is not available. Install Docker/Docker Compose or rerun RUN.sh and choose local."
        exit 1
      fi
      if ! compose_accessible; then
        echo "Docker startup was selected, but Docker is not accessible for the current user."
        exit 1
      fi
      select_compose_cmd
      sync_env_to_backend

      # Read ADMIN_INITIAL_PASSWORD from .env (defaults to Admin@123456 from .env.example).
      _admin_pw="$(read_env_value ADMIN_INITIAL_PASSWORD 'Admin@123456')"
      (cd "$ROOT_DIR" && ADMIN_INITIAL_PASSWORD="$_admin_pw" "${COMPOSE_CMD[@]}" up --build -d)

      docker_frontend_port="$(read_env_value FRONTEND_PORT 8080)"
      docker_backend_port="$(read_env_value BACKEND_PORT 8000)"
      if [[ "$docker_frontend_port" == "80" ]]; then
        _frontend_url="http://localhost/"
      else
        _frontend_url="http://localhost:$docker_frontend_port/"
      fi
      echo "CC Security started in Docker mode."
      echo "Backend health: http://localhost:$docker_backend_port/api/health"
      print_credentials "$_frontend_url" "$_admin_pw"
      unset _admin_pw _frontend_url
    else
      start_local_services
    fi
    ;;
  down)
    if [[ "$SELECTED_MODE" == "docker" ]]; then
      if ! compose_available; then
        echo "Docker shutdown was selected, but Docker Compose is not available."
        exit 1
      fi
      if ! compose_accessible; then
        echo "Docker shutdown was selected, but Docker is not accessible for the current user."
        exit 1
      fi
      select_compose_cmd
      (cd "$ROOT_DIR" && "${COMPOSE_CMD[@]}" down)
    else
      stop_local_services
    fi
    ;;
  restart)
    if [[ "$SELECTED_MODE" == "docker" ]]; then
      if ! compose_available; then
        echo "Docker restart was selected, but Docker Compose is not available."
        exit 1
      fi
      if ! compose_accessible; then
        echo "Docker restart was selected, but Docker is not accessible for the current user."
        exit 1
      fi
      select_compose_cmd
      (cd "$ROOT_DIR" && "${COMPOSE_CMD[@]}" down)
      (cd "$ROOT_DIR" && "${COMPOSE_CMD[@]}" up --build -d)
    else
      stop_local_services
      start_local_services
    fi
    ;;
  logs)
    if [[ "$SELECTED_MODE" == "docker" ]]; then
      if ! compose_available; then
        echo "Docker logs were selected, but Docker Compose is not available."
        exit 1
      fi
      if ! compose_accessible; then
        echo "Docker logs were selected, but Docker is not accessible for the current user."
        exit 1
      fi
      select_compose_cmd
      (cd "$ROOT_DIR" && "${COMPOSE_CMD[@]}" logs -f)
    else
      show_local_logs
    fi
    ;;
  *)
    echo "Usage: ./RUN.sh [up|down|restart|logs] [docker|local]"
    exit 1
    ;;
esac