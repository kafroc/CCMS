#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$ROOT_DIR/.env"
BACKEND_ENV_FILE="$ROOT_DIR/backend/.env"
ENV_EXAMPLE_FILE="$ROOT_DIR/.env.example"
TOTAL_PARTS=0
CURRENT_PART=0
PACKAGE_INDEXES_REFRESHED=false
INSTALL_MODE=""

if [[ -t 1 ]]; then
  COLOR_GREEN=$'\033[32m'
  COLOR_RED=$'\033[31m'
  COLOR_YELLOW=$'\033[33m'
  COLOR_BLUE=$'\033[34m'
  COLOR_RESET=$'\033[0m'
else
  COLOR_GREEN=''
  COLOR_RED=''
  COLOR_YELLOW=''
  COLOR_BLUE=''
  COLOR_RESET=''
fi

print_color() {
  local color="$1"
  local message="$2"
  printf '%b%s%b\n' "$color" "$message" "$COLOR_RESET"
}

section() {
  CURRENT_PART=$((CURRENT_PART + 1))
  echo
  print_color "$COLOR_BLUE" "[$CURRENT_PART/$TOTAL_PARTS] $1"
}

pass() {
  print_color "$COLOR_GREEN" "[PASS] $1"
}

info() {
  print_color "$COLOR_BLUE" "[INFO] $1"
}

warn() {
  print_color "$COLOR_YELLOW" "[WARN] $1"
}

block() {
  print_color "$COLOR_RED" "[BLOCKED] $1"
  print_color "$COLOR_RED" "Resolve this issue and rerun Install_for_Linux.sh before continuing."
  exit 1
}

confirm() {
  local prompt="$1"
  local answer=""
  read -r -p "$prompt [Y/n]: " answer
  answer="${answer// /}"
  if [[ -z "$answer" ]]; then
    return 0
  fi
  [[ ! "$answer" =~ ^[Nn]$ ]]
}

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

normalize_install_mode() {
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

prompt_secret() {
  local prompt="$1"
  local current_value="${2:-}"
  local answer=""
  while true; do
    if [[ -n "$current_value" ]]; then
      read -r -s -p "$prompt [Press Enter to keep current value]: " answer
    else
      read -r -s -p "$prompt: " answer
    fi
    echo >&2
    if [[ -n "$answer" ]]; then
      printf '%s' "$answer"
      return
    fi
    if [[ -n "$current_value" ]]; then
      printf '%s' "$current_value"
      return
    fi
    warn "A value is required for this field."
  done
}

run_cmd() {
  echo "> $*"
  eval "$*"
}

version_ge() {
  local current="$1"
  local required="$2"
  [[ "$(printf '%s\n%s\n' "$required" "$current" | sort -V | head -n1)" == "$required" ]]
}

get_python_version() {
  python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'
}

get_node_version() {
  node -p "process.versions.node"
}

url_encode() {
  python3 - "$1" <<'PY'
import sys
from urllib.parse import quote

print(quote(sys.argv[1], safe=''))
PY
}

get_env_value() {
  local key="$1"
  local default_value="${2:-}"
  if [[ ! -f "$ENV_FILE" ]]; then
    printf '%s' "$default_value"
    return
  fi
  local value
  value=$(grep -E "^${key}=" "$ENV_FILE" | tail -n1 | cut -d'=' -f2- || true)
  if [[ -z "$value" ]]; then
    printf '%s' "$default_value"
  else
    printf '%s' "$value"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

env_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3].replace("\r", "").replace("\n", "")
line = f"{key}={value}"

if env_path.exists():
    lines = env_path.read_text(encoding="utf-8").splitlines()
else:
    lines = []

updated = False
normalized_lines = []
index = 0
while index < len(lines):
  current = lines[index]
  if current.startswith(f"{key}="):
    normalized_lines.append(line)
    updated = True
    index += 1
    while index < len(lines):
      trailing = lines[index]
      if not trailing or trailing.startswith("#") or "=" in trailing:
        break
      index += 1
    continue
  normalized_lines.append(current)
  index += 1

if not updated:
  normalized_lines.append(line)

env_path.write_text("\n".join(normalized_lines) + "\n", encoding="utf-8")
PY
}

sync_env_to_backend() {
  local backend_dir
  backend_dir="$(dirname "$BACKEND_ENV_FILE")"
  mkdir -p "$backend_dir" 2>/dev/null || sudo mkdir -p "$backend_dir"
  # Fix ownership if a prior Docker run left root-owned files
  if [[ ! -w "$backend_dir" ]]; then
    sudo chown "$(id -u):$(id -g)" "$backend_dir"
  fi
  if [[ -f "$BACKEND_ENV_FILE" ]] && [[ ! -w "$BACKEND_ENV_FILE" ]]; then
    sudo chown "$(id -u):$(id -g)" "$BACKEND_ENV_FILE"
  fi
  cp "$ENV_FILE" "$BACKEND_ENV_FILE"
}

compose_available() {
  docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1
}

resolve_debian_codename() {
  local os_codename=""
  local debian_version_major=""
  local lsb_codename=""

  os_codename="$(. /etc/os-release && echo "${DEBIAN_CODENAME:-${VERSION_CODENAME:-}}")"
  if [[ -n "$os_codename" && "$os_codename" != "kali-rolling" ]]; then
    printf '%s' "$os_codename"
    return 0
  fi

  if command -v lsb_release >/dev/null 2>&1; then
    lsb_codename="$(lsb_release -cs 2>/dev/null || true)"
    if [[ -n "$lsb_codename" && "$lsb_codename" != "kali-rolling" ]]; then
      printf '%s' "$lsb_codename"
      return 0
    fi
  fi

  if [[ -f /etc/debian_version ]]; then
    debian_version_major="$(cut -d'.' -f1 /etc/debian_version | tr -cd '0-9')"
    case "$debian_version_major" in
      13) printf '%s' "trixie"; return 0 ;;
      12) printf '%s' "bookworm"; return 0 ;;
      11) printf '%s' "bullseye"; return 0 ;;
      10) printf '%s' "buster"; return 0 ;;
      9) printf '%s' "stretch"; return 0 ;;
    esac
  fi

  # Kali rolling currently tracks Debian stable closely enough for Docker's Debian repo.
  printf '%s' "bookworm"
  return 0
}

install_docker_for_apt() {
  local docker_repo_id
  local docker_repo_codename
  local docker_repo_like

  docker_repo_id="$(. /etc/os-release && echo "${ID:-}")"
  docker_repo_like="$(. /etc/os-release && echo "${ID_LIKE:-}")"
  docker_repo_codename="$(. /etc/os-release && echo "${VERSION_CODENAME:-${UBUNTU_CODENAME:-${DEBIAN_CODENAME:-}}}")"

  if [[ "$docker_repo_id" == "kali" ]]; then
    docker_repo_id="debian"
    docker_repo_codename="$(resolve_debian_codename || true)"
    if [[ -n "$docker_repo_codename" ]]; then
      info "Detected Kali Linux. Docker will be installed from the Debian '$docker_repo_codename' repository."
    fi
  elif [[ "$docker_repo_id" != "ubuntu" && "$docker_repo_id" != "debian" ]]; then
    if [[ " $docker_repo_like " == *" ubuntu "* ]]; then
      docker_repo_id="ubuntu"
    elif [[ " $docker_repo_like " == *" debian "* ]]; then
      docker_repo_id="debian"
      docker_repo_codename="$(resolve_debian_codename || true)"
    fi
  fi

  if [[ -z "$docker_repo_id" || -z "$docker_repo_codename" ]]; then
    warn "Unable to determine a supported apt distribution for Docker repository setup."
    return 1
  fi

  if [[ "$docker_repo_id" != "ubuntu" && "$docker_repo_id" != "debian" ]]; then
    warn "Official Docker apt repository setup is only automated for Ubuntu and Debian. Current distribution: $docker_repo_id"
    return 1
  fi

  info "Configuring the official Docker apt repository"
  run_cmd "sudo apt-get install -y ca-certificates curl gnupg" || return 1
  run_cmd "sudo install -m 0755 -d /etc/apt/keyrings" || return 1
  run_cmd "curl -fsSL https://download.docker.com/linux/$docker_repo_id/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg" || return 1
  run_cmd "sudo chmod a+r /etc/apt/keyrings/docker.gpg" || return 1
  run_cmd "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$docker_repo_id $docker_repo_codename stable\" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null" || return 1
  PACKAGE_INDEXES_REFRESHED=false
  refresh_package_indexes_if_needed
  run_cmd "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin"
}

start_local_services() {
  local log_dir
  log_dir="$ROOT_DIR/logs"
  mkdir -p "$log_dir"
  sync_env_to_backend

  local backend_host backend_port frontend_port
  backend_host="$(get_env_value BACKEND_HOST '0.0.0.0')"
  backend_port="$(get_env_value BACKEND_PORT '8000')"
  frontend_port="$(get_env_value FRONTEND_PORT '8080')"

  info "Running database migration (idempotent)"
  run_cmd "cd '$ROOT_DIR/backend' && ./.venv/bin/python -m app.scripts.migrate_add_logs_and_user_flag >> '$log_dir/backend.log' 2>&1"

  info "Starting backend API in the background (http://$backend_host:$backend_port)"
  run_cmd "cd '$ROOT_DIR/backend' && nohup ./.venv/bin/uvicorn app.main:app --host '$backend_host' --port '$backend_port' >> '$log_dir/backend.log' 2>&1 &"
  info "Starting worker in the background"
  run_cmd "cd '$ROOT_DIR/backend' && nohup ./.venv/bin/arq app.worker.settings.WorkerSettings > '$log_dir/worker.log' 2>&1 &"
  info "Starting frontend dev server in the background (port $frontend_port)"
  run_cmd "cd '$ROOT_DIR/frontend' && nohup npm run dev -- --host 0.0.0.0 --port '$frontend_port' --strictPort > '$log_dir/frontend.log' 2>&1 &"

  pass "Local services started"
  echo "Logs:"
  echo "- Backend: $log_dir/backend.log"
  echo "- Worker: $log_dir/worker.log"
  echo "- Frontend: $log_dir/frontend.log"
  if [[ "$frontend_port" == "80" ]]; then
    echo "Frontend URL: http://localhost/"
  else
    echo "Frontend URL: http://localhost:$frontend_port/"
  fi
  echo "Backend health: http://localhost:$backend_port/api/health"
}

start_services() {
  section "Service startup"

  local start_mode=""
  start_mode="$(prompt_with_default 'Start services now? (local/skip)' 'local')"

  case "$start_mode" in
    local|LOCAL|Local)
      start_local_services
      ;;
    skip|SKIP|Skip)
      warn "Service startup skipped"
      ;;
    *)
      warn "Unknown startup mode '$start_mode'. Services were not started."
      ;;
  esac
}

ensure_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
    UPDATE_CMD="sudo apt-get update"
    BASE_INSTALL_CMD="sudo apt-get install -y"
    PYTHON_INSTALL_CMD="sudo apt-get install -y python3 python3-pip python3-venv build-essential libpq-dev"
    POSTGRES_INSTALL_CMD="sudo apt-get install -y postgresql postgresql-contrib"
    REDIS_INSTALL_CMD="sudo apt-get install -y redis-server"
    DOCKER_INSTALL_CMD="sudo apt-get install -y docker.io docker-compose-plugin"
    NODE_SETUP_CMD="curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
    NODE_INSTALL_CMD="sudo apt-get install -y nodejs"
    POSTGRES_SERVICE_NAME="postgresql"
    REDIS_SERVICE_NAME="redis-server"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
    UPDATE_CMD="sudo dnf makecache"
    BASE_INSTALL_CMD="sudo dnf install -y"
    PYTHON_INSTALL_CMD="sudo dnf install -y python3 python3-pip gcc gcc-c++ postgresql-devel"
    POSTGRES_INSTALL_CMD="sudo dnf install -y postgresql-server postgresql-contrib"
    REDIS_INSTALL_CMD="sudo dnf install -y redis"
    DOCKER_INSTALL_CMD="sudo dnf install -y docker docker-compose-plugin"
    NODE_SETUP_CMD="curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -"
    NODE_INSTALL_CMD="sudo dnf install -y nodejs"
    POSTGRES_SERVICE_NAME="postgresql"
    REDIS_SERVICE_NAME="redis"
  elif command -v yum >/dev/null 2>&1; then
    PKG_MANAGER="yum"
    UPDATE_CMD="sudo yum makecache"
    BASE_INSTALL_CMD="sudo yum install -y"
    PYTHON_INSTALL_CMD="sudo yum install -y python3 python3-pip gcc gcc-c++ postgresql-devel"
    POSTGRES_INSTALL_CMD="sudo yum install -y postgresql-server postgresql-contrib"
    REDIS_INSTALL_CMD="sudo yum install -y redis"
    DOCKER_INSTALL_CMD="sudo yum install -y docker docker-compose-plugin"
    NODE_SETUP_CMD="curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -"
    NODE_INSTALL_CMD="sudo yum install -y nodejs"
    POSTGRES_SERVICE_NAME="postgresql"
    REDIS_SERVICE_NAME="redis"
  else
    block "No supported package manager was detected. Supported managers: apt, dnf, yum."
  fi
}

refresh_package_indexes_if_needed() {
  if [[ "$PACKAGE_INDEXES_REFRESHED" == false ]]; then
    info "Refreshing package indexes before installation"
    run_cmd "$UPDATE_CMD"
    PACKAGE_INDEXES_REFRESHED=true
  fi
}

service_is_active() {
  local service_name="$1"
  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi
  systemctl is-active --quiet "$service_name"
}

resolve_service_name() {
  local preferred_name="$1"
  local pattern="$2"
  local candidate=""

  if ! command -v systemctl >/dev/null 2>&1; then
    printf '%s' "$preferred_name"
    return
  fi

  if systemctl list-unit-files "${preferred_name}.service" --no-legend 2>/dev/null | grep -q .; then
    printf '%s' "$preferred_name"
    return
  fi

  candidate=$(systemctl list-unit-files "${pattern}*.service" --no-legend 2>/dev/null | awk '{print $1}' | head -n1 | sed 's/\.service$//')
  if [[ -n "$candidate" ]]; then
    printf '%s' "$candidate"
  else
    printf '%s' "$preferred_name"
  fi
}

is_local_host() {
  local host="$1"
  # Match TCP loopback addresses AND Unix socket directory paths (start with /)
  [[ "$host" == "localhost" || "$host" == "127.0.0.1" || "$host" == "::1" || "$host" == /* ]]
}

# Check if the current Linux user can connect to local PostgreSQL via peer auth (no password)
current_user_peer_ready() {
  local sock_dir
  sock_dir="$(postgres_socket_dir 2>/dev/null || true)"
  [[ -z "$sock_dir" ]] && sock_dir="/var/run/postgresql"
  local cur_user
  cur_user="$(id -un)"
  psql -h "$sock_dir" -U "$cur_user" -d postgres -tAc 'SELECT 1' >/dev/null 2>&1
}

postgres_server_ready() {
  local host="$1"
  local port="$2"
  if command -v pg_isready >/dev/null 2>&1; then
    pg_isready -h "$host" -p "$port" >/dev/null 2>&1
  else
    return 0
  fi
}

sudo_postgres_ready() {
  command -v sudo >/dev/null 2>&1 && sudo -u postgres psql -d postgres -tAc 'SELECT 1' >/dev/null 2>&1
}

postgres_socket_dir() {
  local socket_dir
  socket_dir="$(sudo -u postgres psql -d postgres -tAc "SHOW unix_socket_directories" 2>/dev/null | head -n1 | cut -d',' -f1 | tr -d '[:space:]')"
  if [[ -z "$socket_dir" ]]; then
    socket_dir="/var/run/postgresql"
  fi
  printf '%s' "$socket_dir"
}

sql_quote_literal() {
  python3 - "$1" <<'PY'
import sys
print("'" + sys.argv[1].replace("'", "''") + "'")
PY
}

sql_quote_identifier() {
  python3 - "$1" <<'PY'
import sys
print('"' + sys.argv[1].replace('"', '""') + '"')
PY
}

configure_postgres_with_sudo_mode() {
  local pg_database="$1"
  local app_db_user
  local current_linux_user
  local socket_dir
  local role_exists
  local db_exists
  local quoted_role
  local quoted_db
  local url_user

  current_linux_user="$(id -un)"
  app_db_user="$(prompt_with_default 'Database login role for passwordless local access' "$current_linux_user")"
  pg_database="$(prompt_with_default 'Application database name' "$pg_database")"

  socket_dir="$(postgres_socket_dir)"
  quoted_role="$(sql_quote_identifier "$app_db_user")"
  quoted_db="$(sql_quote_identifier "$pg_database")"

  role_exists="$(sudo -u postgres psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname = $(sql_quote_literal "$app_db_user")" | tr -d '[:space:]')"
  if [[ "$role_exists" != "1" ]]; then
    info "Creating PostgreSQL role '$app_db_user' for local passwordless access"
    sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE ROLE $quoted_role LOGIN CREATEDB" >/dev/null
  fi

  db_exists="$(sudo -u postgres psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = $(sql_quote_literal "$pg_database")" | tr -d '[:space:]')"
  if [[ "$db_exists" == "1" ]]; then
    warn "Database '$pg_database' already exists."
    local db_action
    db_action="$(prompt_with_default "Choose database action (keep/reset/exit)" 'keep')"
    case "$db_action" in
      keep|KEEP|Keep)
        info "Keeping existing database '$pg_database'"
        ;;
      reset|RESET|Reset)
        if confirm "Drop and recreate database '$pg_database'? This will delete existing data."; then
          sudo -u postgres dropdb "$pg_database"
          sudo -u postgres createdb -O "$app_db_user" "$pg_database"
        else
          block "Database reset was cancelled."
        fi
        ;;
      exit|EXIT|Exit)
        block "Installation stopped because the target database already exists."
        ;;
      *)
        block "Unsupported database action '$db_action'. Expected keep, reset, or exit."
        ;;
    esac
  else
    info "Database '$pg_database' does not exist. It will be created now."
    sudo -u postgres createdb -O "$app_db_user" "$pg_database" >/dev/null
  fi

  sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE $quoted_db OWNER TO $quoted_role" >/dev/null
  psql -h "$socket_dir" -U "$app_db_user" -d postgres -tAc 'SELECT 1' >/dev/null 2>&1 || block "Passwordless local PostgreSQL access could not be verified for role '$app_db_user'."

  set_env_value POSTGRES_HOST "$socket_dir"
  set_env_value POSTGRES_PORT "5432"
  set_env_value POSTGRES_USER "$app_db_user"
  set_env_value POSTGRES_PASSWORD ""
  set_env_value POSTGRES_DB "$pg_database"
  url_user="$(url_encode "$app_db_user")"
  set_env_value DATABASE_URL "postgresql+asyncpg://$url_user@/$pg_database?host=$socket_dir"
  set_env_value SYNC_DATABASE_URL "postgresql+psycopg2://$url_user@/$pg_database?host=$socket_dir"
  sync_env_to_backend

  pass "Environment check for PostgreSQL passed with sudo-based local passwordless access"
}

prepare_project_env() {
  section "Project configuration"

  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
    info "Created $ENV_FILE from .env.example"
  fi

  local current_secret
  current_secret="$(get_env_value SECRET_KEY '')"
  if [[ -z "$current_secret" || "$current_secret" == change-me* ]]; then
    current_secret="$(python3 - <<'PY'
import secrets
print(secrets.token_hex(32))
PY
)"
    set_env_value SECRET_KEY "$current_secret"
    info "Generated a new SECRET_KEY automatically"
  fi

  # ENCRYPTION_KEY — required in production to encrypt AI API keys at rest.
  # Generate a Fernet key automatically when absent.
  local current_encryption_key
  current_encryption_key="$(get_env_value ENCRYPTION_KEY '')"
  if [[ -z "$current_encryption_key" ]]; then
    current_encryption_key="$(python3 - <<'PY'
try:
    from cryptography.fernet import Fernet
    print(Fernet.generate_key().decode())
except ModuleNotFoundError:
    # Fallback: strong random passphrase; security.py will KDF-derive a Fernet key.
    import secrets
    print(secrets.token_urlsafe(48))
PY
)"
    set_env_value ENCRYPTION_KEY "$current_encryption_key"
    info "Generated a new ENCRYPTION_KEY automatically"
  fi

  # ALLOWED_ORIGINS — required in production, otherwise the backend refuses
  # to start. Default to the local dev hosts; user can edit .env later.
  local current_cors
  current_cors="$(get_env_value ALLOWED_ORIGINS '')"
  if [[ -z "$current_cors" ]]; then
    set_env_value ALLOWED_ORIGINS 'http://localhost:8080,http://127.0.0.1:8080,http://localhost'
    info "Set a default ALLOWED_ORIGINS (edit .env to match your deployment domain)"
  fi

  # ADMIN_INITIAL_PASSWORD — optional. If left blank, init_db generates a
  # random 20-char password and prints it once to the console. The account
  # is always seeded with must_change_password=True.
  local current_admin_password
  current_admin_password="$(get_env_value ADMIN_INITIAL_PASSWORD '')"
  if [[ "$current_admin_password" == 'Admin@123456' ]]; then
    # Old default — wipe it so init_db will randomize.
    set_env_value ADMIN_INITIAL_PASSWORD ''
    info "Cleared legacy default ADMIN_INITIAL_PASSWORD; init_db will generate a random one"
  elif [[ -z "$current_admin_password" ]]; then
    info "ADMIN_INITIAL_PASSWORD is empty — init_db will generate a random password and print it once on startup."
  fi

  sync_env_to_backend
  pass "Environment check for project configuration passed"
}

ensure_base_tools() {
  section "Base tools"
  local missing=()
  for tool in curl git; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      missing+=("$tool")
    fi
  done

  if [[ ${#missing[@]} -eq 0 ]]; then
    pass "Environment check for base tools passed"
    return
  fi

  local install_cmd="$BASE_INSTALL_CMD ${missing[*]} ca-certificates"
  info "Missing base tools: ${missing[*]}"
  info "The following command will be executed: $install_cmd"
  if confirm "Continue with base tool installation?"; then
    refresh_package_indexes_if_needed
    run_cmd "$install_cmd"
  else
    block "Base tools are incomplete. Install ${missing[*]} manually and rerun the script."
  fi

  for tool in curl git; do
    command -v "$tool" >/dev/null 2>&1 || block "Base tool '$tool' is still missing after installation."
  done
  pass "Environment check for base tools passed"
}

ensure_python() {
  section "Python environment"

  local python_ok=false
  local pip_ok=false
  local venv_ok=false
  local python_version=""

  if command -v python3 >/dev/null 2>&1; then
    python_version="$(get_python_version)"
    if version_ge "$python_version" "3.11.0"; then
      python_ok=true
    fi
  fi

  if command -v pip3 >/dev/null 2>&1 || python3 -m pip --version >/dev/null 2>&1; then
    pip_ok=true
  fi

  if command -v python3 >/dev/null 2>&1 && python3 -m venv --help >/dev/null 2>&1; then
    venv_ok=true
  fi

  if [[ "$python_ok" == true && "$pip_ok" == true && "$venv_ok" == true ]]; then
    pass "Environment check for Python passed: python3 $python_version, pip and venv are available"
    return
  fi

  info "Python requirement: Python 3.11+, pip, and venv support"
  info "The following command will be executed: $PYTHON_INSTALL_CMD"
  if confirm "Continue with Python installation or repair?"; then
    refresh_package_indexes_if_needed
    run_cmd "$PYTHON_INSTALL_CMD"
  else
    block "Python requirements are not satisfied. Install Python 3.11+, pip, and venv support, then rerun the script."
  fi

  command -v python3 >/dev/null 2>&1 || block "python3 is still missing after installation."
  python_version="$(get_python_version)"
  version_ge "$python_version" "3.11.0" || block "python3 version is $python_version. Version 3.11 or higher is required."
  (command -v pip3 >/dev/null 2>&1 || python3 -m pip --version >/dev/null 2>&1) || block "pip is still unavailable after installation."
  python3 -m venv --help >/dev/null 2>&1 || block "venv support is still unavailable after installation."
  pass "Environment check for Python passed: python3 $python_version"
}

ensure_node() {
  section "Node.js environment"

  local node_ok=false
  local npm_ok=false
  local node_version=""

  if command -v node >/dev/null 2>&1; then
    node_version="$(get_node_version)"
    if version_ge "$node_version" "18.0.0"; then
      node_ok=true
    fi
  fi

  if command -v npm >/dev/null 2>&1; then
    npm_ok=true
  fi

  if [[ "$node_ok" == true && "$npm_ok" == true ]]; then
    pass "Environment check for Node.js passed: node $node_version and npm are available"
    return
  fi

  info "Node.js requirement: Node.js 18+ and npm"
  info "The following commands will be executed:"
  info "1. $NODE_SETUP_CMD"
  info "2. $NODE_INSTALL_CMD"
  if confirm "Continue with Node.js installation or upgrade?"; then
    run_cmd "$NODE_SETUP_CMD"
    refresh_package_indexes_if_needed
    run_cmd "$NODE_INSTALL_CMD"
  else
    block "Node.js requirements are not satisfied. Install Node.js 18+ and npm, then rerun the script."
  fi

  command -v node >/dev/null 2>&1 || block "node is still missing after installation."
  node_version="$(get_node_version)"
  version_ge "$node_version" "18.0.0" || block "node version is $node_version. Version 18 or higher is required."
  command -v npm >/dev/null 2>&1 || block "npm is still missing after installation."
  pass "Environment check for Node.js passed: node $node_version"
}

ensure_postgres() {
  section "PostgreSQL configuration"

  local postgres_service_name
  postgres_service_name="$(resolve_service_name "$POSTGRES_SERVICE_NAME" 'postgresql')"

  if ! command -v psql >/dev/null 2>&1; then
    info "PostgreSQL is not installed."
    info "The following command will be executed: $POSTGRES_INSTALL_CMD"
    if confirm "Continue with PostgreSQL installation?"; then
      refresh_package_indexes_if_needed
      run_cmd "$POSTGRES_INSTALL_CMD"
      if [[ "$PKG_MANAGER" != "apt" ]]; then
        run_cmd "sudo postgresql-setup --initdb || sudo postgresql-setup initdb || true"
      fi
    else
      block "PostgreSQL is required. Install it manually and rerun the script."
    fi
  fi

  if command -v systemctl >/dev/null 2>&1 && ! service_is_active "$postgres_service_name"; then
    info "PostgreSQL is installed but the service is not running."
    if confirm "Start PostgreSQL now with 'sudo systemctl enable --now $postgres_service_name'?"; then
      run_cmd "sudo systemctl enable --now $postgres_service_name"
    fi
  fi

  command -v psql >/dev/null 2>&1 || block "psql is still missing after installation."

  local pg_host
  local pg_port
  local pg_user
  local pg_password
  local pg_database
  local current_password
  local url_user
  local url_password

  pg_host="$(get_env_value POSTGRES_HOST 'localhost')"
  pg_port="$(get_env_value POSTGRES_PORT '5432')"
  pg_user="$(get_env_value POSTGRES_USER "$(id -un)")"
  current_password="$(get_env_value POSTGRES_PASSWORD '')"
  pg_database="$(get_env_value POSTGRES_DB 'cc_security')"

  # Priority 1: current Linux user already has peer-auth access to PostgreSQL (most common on Kali/Debian).
  if is_local_host "$pg_host" && current_user_peer_ready; then
    info "Detected that the current user '$(id -un)' can connect to local PostgreSQL via peer authentication (no password needed)."
    if confirm "Use passwordless local PostgreSQL setup mode for current user '$(id -un)'?"; then
      configure_postgres_with_sudo_mode "$pg_database"
      return
    fi
  # Priority 2: superuser access via 'sudo -u postgres'.
  elif is_local_host "$pg_host" && sudo_postgres_ready; then
    info "Detected local PostgreSQL administrative access via 'sudo -u postgres psql'."
    if confirm "Use passwordless local PostgreSQL setup mode?"; then
      configure_postgres_with_sudo_mode "$pg_database"
      return
    fi
  fi

  if [[ "$current_password" == 'your_password' ]]; then
    current_password=''
  fi

  while true; do
    pg_host="$(prompt_with_default 'PostgreSQL host' "$pg_host")"
    pg_port="$(prompt_with_default 'PostgreSQL port' "$pg_port")"
    pg_user="$(prompt_with_default 'PostgreSQL user' "$pg_user")"
    pg_password="$(prompt_secret "PostgreSQL password for user '$pg_user'" "$current_password")"
    echo
    pg_database="$(prompt_with_default 'Application database name' "$pg_database")"
    current_password="$pg_password"

    if is_local_host "$pg_host" && ! postgres_server_ready "$pg_host" "$pg_port"; then
      warn "A local PostgreSQL server is not accepting connections on $pg_host:$pg_port."
      if command -v systemctl >/dev/null 2>&1 && ! service_is_active "$postgres_service_name"; then
        if confirm "Try to start local PostgreSQL now with 'sudo systemctl enable --now $postgres_service_name'?"; then
          run_cmd "sudo systemctl enable --now $postgres_service_name"
          continue
        fi
      fi
      if confirm "Retry PostgreSQL host/port configuration?"; then
        continue
      fi
      block "PostgreSQL is not reachable on $pg_host:$pg_port."
    fi

    if PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres -tAc 'SELECT 1' >/dev/null 2>&1; then
      break
    fi

    warn "Unable to connect to PostgreSQL with the provided host, port, user, and password."
    if is_local_host "$pg_host" && command -v systemctl >/dev/null 2>&1 && ! service_is_active "$postgres_service_name"; then
      if confirm "Local PostgreSQL may be stopped. Start it now with 'sudo systemctl enable --now $postgres_service_name'?"; then
        run_cmd "sudo systemctl enable --now $postgres_service_name"
        continue
      fi
    fi
    if confirm "Retry PostgreSQL configuration?"; then
      continue
    fi
    block "PostgreSQL connection could not be established with the provided settings."
  done

  local db_exists
  db_exists="$(PGPASSWORD="$pg_password" psql -h "$pg_host" -p "$pg_port" -U "$pg_user" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$pg_database'" | tr -d '[:space:]')"
  if [[ "$db_exists" == "1" ]]; then
    warn "Database '$pg_database' already exists."
    local db_action
    db_action="$(prompt_with_default "Choose database action (keep/reset/exit)" 'keep')"
    case "$db_action" in
      keep|KEEP|Keep)
        info "Keeping existing database '$pg_database'"
        ;;
      reset|RESET|Reset)
        if confirm "Drop and recreate database '$pg_database'? This will delete existing data."; then
          PGPASSWORD="$pg_password" dropdb -h "$pg_host" -p "$pg_port" -U "$pg_user" "$pg_database"
          PGPASSWORD="$pg_password" createdb -h "$pg_host" -p "$pg_port" -U "$pg_user" "$pg_database"
        else
          block "Database reset was cancelled."
        fi
        ;;
      exit|EXIT|Exit)
        block "Installation stopped because the target database already exists."
        ;;
      *)
        block "Unsupported database action '$db_action'. Expected keep, reset, or exit."
        ;;
    esac
  else
    info "Database '$pg_database' does not exist. It will be created now."
    PGPASSWORD="$pg_password" createdb -h "$pg_host" -p "$pg_port" -U "$pg_user" "$pg_database" || block "Failed to create database '$pg_database'."
  fi

  set_env_value POSTGRES_HOST "$pg_host"
  set_env_value POSTGRES_PORT "$pg_port"
  set_env_value POSTGRES_USER "$pg_user"
  set_env_value POSTGRES_PASSWORD "$pg_password"
  set_env_value POSTGRES_DB "$pg_database"
  url_user="$(url_encode "$pg_user")"
  url_password="$(url_encode "$pg_password")"
  set_env_value DATABASE_URL "postgresql+asyncpg://$url_user:$url_password@$pg_host:$pg_port/$pg_database"
  set_env_value SYNC_DATABASE_URL "postgresql+psycopg2://$url_user:$url_password@$pg_host:$pg_port/$pg_database"
  sync_env_to_backend

  pass "Environment check for PostgreSQL passed"
}

ensure_redis() {
  section "Redis configuration"

  if ! command -v redis-cli >/dev/null 2>&1; then
    info "Redis is not installed."
    info "The following command will be executed: $REDIS_INSTALL_CMD"
    if confirm "Continue with Redis installation?"; then
      refresh_package_indexes_if_needed
      run_cmd "$REDIS_INSTALL_CMD"
    else
      block "Redis is required. Install it manually and rerun the script."
    fi
  fi

  if command -v systemctl >/dev/null 2>&1 && ! service_is_active "$REDIS_SERVICE_NAME"; then
    info "Redis is installed but the service is not running."
    if confirm "Start Redis now with 'sudo systemctl enable --now $REDIS_SERVICE_NAME'?"; then
      run_cmd "sudo systemctl enable --now $REDIS_SERVICE_NAME"
    else
      block "Redis must be running before installation can continue."
    fi
  fi

  command -v redis-cli >/dev/null 2>&1 || block "redis-cli is still missing after installation."
  redis-cli ping >/dev/null 2>&1 || block "Redis is installed but not responding to 'redis-cli ping'."

  set_env_value REDIS_URL "redis://localhost:6379"
  sync_env_to_backend
  pass "Environment check for Redis passed"
}

install_project_dependencies() {
  section "Project dependencies"

  local backend_ready=false
  local frontend_ready=false

  if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]] && "$ROOT_DIR/backend/.venv/bin/python" -m pip show fastapi >/dev/null 2>&1; then
    backend_ready=true
  fi

  if [[ -d "$ROOT_DIR/frontend/node_modules" ]]; then
    frontend_ready=true
  fi

  if [[ "$backend_ready" == false ]]; then
    info "Backend virtual environment or Python dependencies are missing."
    info "The following commands will be executed:"
    info "1. python3 -m venv '$ROOT_DIR/backend/.venv'"
    info "2. '$ROOT_DIR/backend/.venv/bin/pip' install --upgrade pip"
    info "3. '$ROOT_DIR/backend/.venv/bin/pip' install -r '$ROOT_DIR/backend/requirements.txt'"
    if confirm "Continue with backend dependency installation?"; then
      run_cmd "python3 -m venv '$ROOT_DIR/backend/.venv'"
      run_cmd "'$ROOT_DIR/backend/.venv/bin/pip' install --upgrade pip"
      run_cmd "'$ROOT_DIR/backend/.venv/bin/pip' install -r '$ROOT_DIR/backend/requirements.txt'"
    else
      block "Backend dependencies are required. Install them manually and rerun the script."
    fi
  fi

  if [[ "$frontend_ready" == false ]]; then
    info "Frontend npm dependencies are missing."
    info "The following command will be executed: cd '$ROOT_DIR/frontend' && npm install"
    if confirm "Continue with frontend dependency installation?"; then
      run_cmd "cd '$ROOT_DIR/frontend' && npm install"
    else
      block "Frontend dependencies are required. Install them manually and rerun the script."
    fi
  fi

  [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]] || block "Backend virtual environment was not created successfully."
  "$ROOT_DIR/backend/.venv/bin/python" -m pip show fastapi >/dev/null 2>&1 || block "Backend Python dependencies are still incomplete."
  [[ -d "$ROOT_DIR/frontend/node_modules" ]] || block "Frontend node_modules directory is still missing after npm install."

  pass "Environment check for project dependencies passed"
}

initialize_database() {
  section "Database initialization"
  sync_env_to_backend
  # Run the additive migration first so upgrades from older schemas
  # (pre-audit-logs / pre-must_change_password) don't break init_db.
  run_cmd "cd '$ROOT_DIR/backend' && ./.venv/bin/python -m app.scripts.migrate_add_logs_and_user_flag"
  run_cmd "cd '$ROOT_DIR/backend' && ./.venv/bin/python -m app.scripts.init_db"
  pass "Database schema and initial admin account are ready"
}

ensure_docker() {
  local required_mode="${1:-optional}"
  if [[ "$required_mode" == "required" ]]; then
    section "Docker setup"
  else
    section "Docker support (optional)"
  fi

  local docker_ok=false
  local compose_ok=false
  local daemon_ok=false
  local sudo_daemon_ok=false

  if command -v docker >/dev/null 2>&1; then
    docker_ok=true
  fi
  if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then
    compose_ok=true
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    daemon_ok=true
  fi
  if command -v sudo >/dev/null 2>&1 && command -v docker >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    sudo_daemon_ok=true
  fi

  if [[ "$docker_ok" == true && "$compose_ok" == true && ( "$daemon_ok" == true || "$sudo_daemon_ok" == true ) ]]; then
    pass "Environment check for Docker passed"
    if [[ "$daemon_ok" != true && "$sudo_daemon_ok" == true ]]; then
      warn "Docker is currently accessible via sudo only. RUN.sh will use sudo docker compose until docker group access is configured."
    fi
    return
  fi

  if [[ "$required_mode" != "required" ]]; then
    warn "Docker support is optional. Local startup will work without Docker after this installer finishes."
  fi

  if [[ "$docker_ok" == false || "$compose_ok" == false ]]; then
    info "Docker support is missing or incomplete."
    if [[ "$required_mode" == "required" ]] || confirm "Install Docker support for one-command deployment with ./RUN.sh?"; then
      if [[ "$PKG_MANAGER" == "apt" ]]; then
        if ! install_docker_for_apt; then
          if [[ "$required_mode" == "required" ]]; then
            block "Docker installation via the official apt repository failed or is unsupported on this distribution."
          fi
          warn "Docker installation via the official apt repository failed or is unsupported on this distribution. Continuing without Docker."
          return
        fi
      else
        info "The following command will be executed to install Docker support: $DOCKER_INSTALL_CMD"
        refresh_package_indexes_if_needed
        if ! run_cmd "$DOCKER_INSTALL_CMD"; then
          if [[ "$required_mode" == "required" ]]; then
            block "Docker installation failed."
          fi
          warn "Docker installation failed. Continuing without Docker."
          return
        fi
      fi
    else
      if [[ "$required_mode" == "required" ]]; then
        block "Docker installation was skipped. Docker mode cannot continue."
      fi
      warn "Docker installation skipped"
      return
    fi
  fi

  if command -v systemctl >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
    if [[ "$required_mode" == "required" ]] || confirm "Start Docker now with 'sudo systemctl enable --now docker'?"; then
      if ! run_cmd "sudo systemctl enable --now docker"; then
        if [[ "$required_mode" == "required" ]]; then
          block "Docker service could not be started automatically."
        fi
        warn "Docker service could not be started automatically. Continuing without Docker startup."
        return
      fi
    else
      if [[ "$required_mode" == "required" ]]; then
        block "Docker daemon was not started. Docker mode cannot continue."
      fi
      warn "Docker daemon was not started. You can still run the project locally without Docker."
      return
    fi
  fi

  if command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1 && ! docker info >/dev/null 2>&1; then
    warn "Docker daemon is running, but the current user does not have direct access to /var/run/docker.sock. RUN.sh will fall back to sudo docker compose."
  fi

  if docker compose version >/dev/null 2>&1 || command -v docker-compose >/dev/null 2>&1; then
    pass "Environment check for Docker passed"
  else
    if [[ "$required_mode" == "required" ]]; then
      block "Docker was installed but Docker Compose is still unavailable."
    fi
    warn "Docker was installed but Docker Compose is still unavailable. Local startup is still ready."
  fi
}

run_docker_install_flow() {
  TOTAL_PARTS=4
  section "Package manager detection"
  ensure_pkg_manager
  pass "Environment check for package manager passed: $PKG_MANAGER"
  info "Docker installation consists of $TOTAL_PARTS parts. Progress will be updated automatically."

  ensure_docker required
  prepare_project_env

  section "Docker startup guidance"
  pass "Docker mode prerequisites are ready"
  echo "Run the following command to start the system with Docker:"
  echo "cd '$ROOT_DIR' && ./RUN.sh up docker"
}

run_local_install_flow() {
  TOTAL_PARTS=10
  section "Package manager detection"
  ensure_pkg_manager
  pass "Environment check for package manager passed: $PKG_MANAGER"
  info "Local installation consists of $TOTAL_PARTS parts. Progress will be updated automatically."

  ensure_base_tools
  ensure_python
  ensure_node
  prepare_project_env
  ensure_postgres
  ensure_redis
  install_project_dependencies
  initialize_database
  start_services
}

echo "CC Security Linux installer"
echo "Project root: $ROOT_DIR"
echo "Choose Docker mode to install/check Docker only, or local mode to prepare native dependencies and start locally."

if compose_available; then
  INSTALL_MODE="$(normalize_install_mode "$(prompt_with_default 'Choose installation mode (docker/local)' 'docker')")"
else
  INSTALL_MODE="$(normalize_install_mode "$(prompt_with_default 'Choose installation mode (docker/local)' 'local')")"
fi

if [[ -z "$INSTALL_MODE" ]]; then
  block "Unsupported installation mode. Expected docker or local."
fi

case "$INSTALL_MODE" in
  docker)
    run_docker_install_flow
    ;;
  local)
    run_local_install_flow
    ;;
esac

echo
print_color "$COLOR_GREEN" "Installation completed successfully."
if [[ "$INSTALL_MODE" == "docker" ]]; then
  echo "Next step: run Docker startup via RUN.sh"
  echo "1. Docker startup: cd '$ROOT_DIR' && ./RUN.sh up docker"
else
  echo "Run one of the following commands to start the system:"
  echo "1. Local startup via RUN.sh: cd '$ROOT_DIR' && ./RUN.sh up local"
  echo "2. Local backend API: cd '$ROOT_DIR/backend' && ./.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
  echo "3. Local worker: cd '$ROOT_DIR/backend' && ./.venv/bin/arq app.worker.settings.WorkerSettings"
  echo "4. Local frontend: cd '$ROOT_DIR/frontend' && npm run dev"
  echo "5. Docker startup later: cd '$ROOT_DIR' && ./RUN.sh up docker"
fi