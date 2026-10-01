#!/usr/bin/env bash
# Installs ReportAI on this server, with one command:
#
#   curl -fsSL https://raw.githubusercontent.com/avaazquezz/ReportAI/main/infra/install/install.sh | sudo bash
#
# It asks for a domain (optional), writes /opt/reportai with its own random secrets, starts
# everything with Docker and prints the address and the one-time code for the setup wizard.
# Running it again on an installed server keeps the existing settings and data.
#
# Options (or the environment variable in brackets):
#   --domain NAME        reportes.empresa.com — HTTPS with a free certificate. Without one, the
#                        panel is served over plain HTTP on the server's IP (private networks only).
#   --version X.Y.Z      a release (default: the latest one)            [REPORTAI_VERSION]
#   --dir PATH           where it lives (default /opt/reportai)          [REPORTAI_DIR]
#   --http-port N        (default 80)  --https-port N (default 443)
#   --yes                no questions: use the options and defaults
#   --project NAME       Docker Compose project name (default reportai)   [REPORTAI_PROJECT]
#   --source PATH        install from a checkout instead of GitHub (testing) [REPORTAI_SOURCE]
#   --no-pull            use images already on this machine (testing)
set -euo pipefail

REPO="avaazquezz/ReportAI"
DIR="${REPORTAI_DIR:-/opt/reportai}"
VERSION="${REPORTAI_VERSION:-latest}"
SOURCE="${REPORTAI_SOURCE:-}"
DOMAIN="${REPORTAI_DOMAIN:-}"
PROJECT="${REPORTAI_PROJECT:-reportai}"
HTTP_PORT=80
HTTPS_PORT=443
ASSUME_YES=false
PULL=true

say() { printf '\033[1m%s\033[0m\n' "$*"; }
fail() { printf '\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --dir) DIR="$2"; shift 2 ;;
    --http-port) HTTP_PORT="$2"; shift 2 ;;
    --https-port) HTTPS_PORT="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --project) PROJECT="$2"; shift 2 ;;
    --no-pull) PULL=false; shift ;;
    --yes|-y) ASSUME_YES=true; shift ;;
    -h|--help) sed -n '2,23p' "$0" 2>/dev/null || echo "Options: see the top of install.sh"; exit 0 ;;
    *) fail "unknown option $1 (see --help)" ;;
  esac
done

# Questions are read from the terminal: with `curl … | bash`, stdin is the script itself.
ask() {
  local prompt="$1" default="${2:-}" answer=""
  if [ "$ASSUME_YES" = true ] || [ ! -r /dev/tty ]; then echo "$default"; return; fi
  read -r -p "$prompt" answer < /dev/tty || true
  echo "${answer:-$default}"
}

random_secret() { head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }

# ── 1. Docker ──────────────────────────────────────────────────────────────────────────
if ! command -v docker > /dev/null 2>&1; then
  say "Docker is not installed."
  if [ "$(ask 'Install it now with the official script (get.docker.com)? [Y/n] ' Y)" != "n" ] && [ "$ASSUME_YES" = false ]; then
    curl -fsSL https://get.docker.com | sh
  else
    fail "install Docker (https://docs.docker.com/engine/install/) and run this again"
  fi
fi
docker compose version > /dev/null 2>&1 || fail "Docker Compose v2 is missing (the 'docker compose' plugin)"
docker info > /dev/null 2>&1 || fail "can't talk to Docker: run this as root (sudo) or as a user in the docker group"

# ── 2. Which release ───────────────────────────────────────────────────────────────────
if [ "$VERSION" = latest ]; then
  VERSION=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" | grep -m1 '"tag_name"' | sed -E 's/.*"v?([^"]+)".*/\1/') \
    || fail "couldn't find the latest release on GitHub; pass --version X.Y.Z"
fi
VERSION="${VERSION#v}"
say "Installing ReportAI $VERSION in $DIR"

# ── 3. Files ───────────────────────────────────────────────────────────────────────────
mkdir -p "$DIR"
for file in docker-compose.yml Caddyfile reportai; do
  if [ -n "$SOURCE" ]; then
    cp "$SOURCE/infra/install/$file" "$DIR/$file"
  else
    curl -fsSL "https://raw.githubusercontent.com/$REPO/v$VERSION/infra/install/$file" -o "$DIR/$file" \
      || fail "couldn't download $file of version $VERSION"
  fi
done
chmod +x "$DIR/reportai"

# ── 4. Settings: generated once, kept on every later run ───────────────────────────────
if [ -f "$DIR/.env" ]; then
  say "Keeping the existing settings in $DIR/.env"
  sed -i -E "s/^REPORTAI_VERSION=.*/REPORTAI_VERSION=$VERSION/" "$DIR/.env"
else
  if [ -z "$DOMAIN" ]; then
    DOMAIN=$(ask "Domain for the panel, e.g. reportes.empresa.com (empty = use this server's IP over HTTP): " "")
  fi
  if [ -n "$DOMAIN" ]; then
    SITE_ADDRESS="$DOMAIN"
    ORIGIN="https://$DOMAIN"
    [ "$HTTPS_PORT" != 443 ] && ORIGIN="https://$DOMAIN:$HTTPS_PORT"
    PUBLIC_BASE_URL="$ORIGIN"  # Telegram calls a webhook here
    SECURE_COOKIES=true
  else
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    SITE_ADDRESS=":80"
    ORIGIN="http://${IP:-localhost}"
    [ "$HTTP_PORT" != 80 ] && ORIGIN="$ORIGIN:$HTTP_PORT"
    PUBLIC_BASE_URL=""  # no public address: the worker polls Telegram instead
    SECURE_COOKIES=false
  fi
  umask 077
  cat > "$DIR/.env" <<EOF
# ReportAI installation settings, written by install.sh. Keep this file private: it holds the
# keys everything else is protected with. The AI provider, mail server and Telegram bot are set
# up in the panel (encrypted with ENCRYPTION_KEY), not here.
COMPOSE_PROJECT_NAME=$PROJECT
REPORTAI_VERSION=$VERSION

SITE_ADDRESS=$SITE_ADDRESS
HTTP_PORT=$HTTP_PORT
HTTPS_PORT=$HTTPS_PORT
FRONTEND_ORIGIN=$ORIGIN
PUBLIC_BASE_URL=$PUBLIC_BASE_URL
SECURE_COOKIES=$SECURE_COOKIES

POSTGRES_USER=reportai
POSTGRES_DB=reportai
POSTGRES_PASSWORD=$(random_secret)
SECRET_KEY=$(random_secret)$(random_secret)
ENCRYPTION_KEY=$(random_secret)$(random_secret)
EOF
  umask 022
fi

# ── 5. The `reportai` command ──────────────────────────────────────────────────────────
if [ -w /usr/local/bin ]; then
  ln -sf "$DIR/reportai" /usr/local/bin/reportai
fi

# ── 6. Start and wait until it answers ─────────────────────────────────────────────────
cd "$DIR"
[ "$PULL" = true ] && docker compose pull --quiet
docker compose up -d --remove-orphans
say "Waiting for ReportAI to start…"
for _ in $(seq 1 60); do
  if docker compose exec -T backend curl -fsS http://localhost:8000/health > /dev/null 2>&1; then break; fi
  sleep 3
done
docker compose exec -T backend curl -fsS http://localhost:8000/health > /dev/null 2>&1 \
  || fail "ReportAI didn't start: look at '$DIR/reportai logs'"

# ── 7. Done ────────────────────────────────────────────────────────────────────────────
ORIGIN=$(grep -E '^FRONTEND_ORIGIN=' .env | cut -d= -f2-)
echo
say "ReportAI $VERSION is running."
if CODE_OUTPUT=$(docker compose exec -T backend python -m app.cli setup-code 2>/dev/null); then
  echo "$CODE_OUTPUT"
else
  echo "Open $ORIGIN and sign in."
fi
echo
echo "Manage it with:  reportai status | logs | update | setup-code | password-link EMAIL"
echo "Keeping it updated is up to whoever maintains this server: run 'reportai update' when the panel says so."
grep -qE '^SECURE_COOKIES=false' .env && echo "Note: without a domain the panel is served over plain HTTP. Use it only on a private network or VPN."
exit 0
