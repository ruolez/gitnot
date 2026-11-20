#!/usr/bin/env bash
#
# mygit: installer for Ubuntu 22.04 / 24.04 LTS
#
#   sudo bash -c "$(curl -fsSL https://raw.githubusercontent.com/ruolez/gitnot/main/install.sh)"
#
# Menu: Install · Update · Backup · Restore · SSL · Status · Remove
# Non-interactive: install.sh install|update|backup|restore <dir>|ssl|status|remove
#
# With a domain, mygit runs behind the shared host proxy (github.com/ruolez/shared-proxy),
# which owns 80/443 and terminates TLS. Without one it answers plain HTTP on a port
# (fine on a LAN; tokens then travel unencrypted). SSH for git listens on SSH_PORT.
#
# Unattended runs read: MYGIT_DOMAIN, MYGIT_EMAIL, MYGIT_ADMIN, MYGIT_HTTP_PORT,
# MYGIT_SSH_PORT, MYGIT_YES=1 (accept every default), REPO_URL, BRANCH. Destructive
# commands (restore, remove) run unattended only with MYGIT_CONFIRM=1; remove deletes
# data only with MYGIT_DELETE_DATA=1.
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/ruolez/gitnot.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/mygit}"
BACKUP_DIR="${BACKUP_DIR:-/opt/mygit-backups}"
DEFAULT_HTTP_PORT="5564"
DEFAULT_SSH_PORT="2222"
SHARED_PROXY_URL="${SHARED_PROXY_URL:-https://raw.githubusercontent.com/ruolez/shared-proxy/main/install.sh}"
PROXY_MARKER="/etc/nginx/snippets/shared-proxy-headers.conf"
PROXY_WEBROOT="/var/www/certbot"
HOST_VHOST="/etc/nginx/sites-available/mygit.conf"
HOST_VHOST_LINK="/etc/nginx/sites-enabled/mygit.conf"
VOLUMES="repos releases sshkeys"
# Secrets of an installation removed with its data kept: the database volume only
# opens with its original password, so a reinstall reuses them.
KEPT_ENV="$BACKUP_DIR/env-kept"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

require_root() { [ "$(id -u)" -eq 0 ] || fail "Run this script as root: sudo bash install.sh"; }

# Ask with a default; MYGIT_YES=1 or no terminal takes the default.
ask() {
    local prompt="$1" default="$2" answer=""
    if [ "${MYGIT_YES:-0}" = "1" ] || [ ! -t 0 ]; then echo "$default"; return; fi
    read -r -p "$prompt" answer
    echo "${answer:-$default}"
}
yes_no() { case "$(ask "$1" "$2")" in [Yy]*) return 0 ;; *) return 1 ;; esac; }
confirm() {
    [ "${MYGIT_CONFIRM:-0}" = "1" ] && return 0
    [ -t 0 ] || fail "Not a terminal: set MYGIT_CONFIRM=1 to run this unattended."
    local answer; read -r -p "$1" answer
    case "$answer" in [Yy]*) return 0 ;; *) return 1 ;; esac
}

# COMPOSE_FILE in .env holds relative paths, resolved against the current directory.
compose() { (cd "$INSTALL_DIR" && docker compose "$@"); }
get_env() { grep -E "^$1=" "$INSTALL_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- || true; }
set_env() {
    local key="$1" val="$2" file="$INSTALL_DIR/.env"
    if grep -qE "^${key}=" "$file" 2>/dev/null; then sed -i "s|^${key}=.*|${key}=${val}|" "$file"; else echo "${key}=${val}" >> "$file"; fi
}
rand() { openssl rand -hex "${1:-16}"; }
server_ip() { hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost"; }
proxy_mode() { [ "$(get_env PROXY_MODE)" = "1" ]; }
port_in_use() { ss -ltnH "sport = :$1" 2>/dev/null | grep -q .; }
valid_domain() { [[ "$1" =~ ^([a-zA-Z0-9](-*[a-zA-Z0-9])*\.)+[a-zA-Z]{2,}$ ]]; }
valid_port() { [[ "$1" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le 65535 ]; }

port_holder() {
    local c=""
    command -v docker >/dev/null 2>&1 && c="$(docker ps --filter "publish=$1" --format '{{.Names}}' 2>/dev/null | head -1 || true)"
    if [ -n "$c" ]; then echo "container $c"; else ss -ltnpH "sport = :$1" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1; fi
}

# ---------------------------------------------------------------- prerequisites
install_docker() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then ok "Docker with Compose already installed"; return; fi
    info "Installing Docker (official repository)..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    ok "Docker installed"
}

install_certbot() {
    command -v certbot >/dev/null 2>&1 && return 0
    info "Installing certbot..."
    apt-get update -qq && apt-get install -y -qq certbot
}

# ---------------------------------------------------------------- shared proxy
shared_proxy_present() { [ -f "$PROXY_MARKER" ]; }

ensure_shared_proxy() {
    shared_proxy_present && return 0
    if (port_in_use 80 || port_in_use 443) && ! systemctl is-active --quiet nginx; then
        fail "Ports 80/443 are held by $(port_holder 80) / $(port_holder 443), not by the shared proxy.
       Move that app behind the shared proxy first (EdgeBourne: its installer's 'Migrate to shared proxy'),
       then run this installer again. Nothing was changed."
    fi
    info "Installing the shared reverse proxy (host nginx)..."
    local tmp; tmp="$(mktemp)"
    curl -fsSL "$SHARED_PROXY_URL" -o "$tmp" || fail "Could not download $SHARED_PROXY_URL"
    bash "$tmp" install </dev/null || fail "Shared proxy installation failed."
    rm -f "$tmp"
    shared_proxy_present || fail "Shared proxy installation did not complete."
}

require_host_nginx() {
    systemctl is-active --quiet nginx && return 0
    if systemctl start nginx >/dev/null 2>&1; then systemctl enable nginx >/dev/null 2>&1 || true; return 0; fi
    fail "Host nginx (the shared proxy) is not running and could not be started: 80 is held by $(port_holder 80)."
}

obtain_certificate() {
    local domain="$1" email="$2"
    if [ -f "/etc/letsencrypt/live/${domain}/fullchain.pem" ]; then ok "Reusing the certificate for $domain"; return 0; fi
    install_certbot
    local email_args=(--register-unsafely-without-email)
    [ -n "$email" ] && email_args=(--email "$email" --no-eff-email)
    info "Requesting a Let's Encrypt certificate for $domain ..."
    if ! certbot certonly --webroot -w "$PROXY_WEBROOT" -d "$domain" --agree-tos --non-interactive \
            --keep-until-expiring "${email_args[@]}"; then
        warn "Certificate request failed. Usually DNS doesn't point here yet, or port 80 is blocked by a firewall."
        return 1
    fi
    ok "Certificate issued for $domain"
}

# Never leaves a vhost nginx rejects enabled: that would stop host nginx, and every app
# behind it, from restarting.
publish_host_vhost() {
    local domain="$1" port out
    port="$(get_env APP_PORT)"
    [ -f "$HOST_VHOST" ] && cp "$HOST_VHOST" "$HOST_VHOST.bak"
    sed -e "s/__DOMAIN__/${domain}/g" -e "s/__PORT__/${port}/g" "$INSTALL_DIR/nginx/host-vhost.conf.template" > "$HOST_VHOST"
    [ -f /proc/net/if_inet6 ] || sed -i '/\[::\]/d' "$HOST_VHOST"
    ln -sf "$HOST_VHOST" "$HOST_VHOST_LINK"
    if out="$(nginx -t 2>&1)"; then
        rm -f "$HOST_VHOST.bak"
        systemctl reload nginx
        # A reload takes effect a moment later; report success once the site answers.
        local _
        for _ in $(seq 1 20); do
            curl -fsk --resolve "${domain}:443:127.0.0.1" "https://${domain}/api/health" >/dev/null 2>&1 && break
            sleep 0.5
        done
        ok "https://${domain} is published through the shared proxy (upstream 127.0.0.1:${port})"
        return 0
    fi
    warn "nginx rejected the vhost: ${out}"
    if [ -f "$HOST_VHOST.bak" ]; then mv "$HOST_VHOST.bak" "$HOST_VHOST"; else rm -f "$HOST_VHOST_LINK" "$HOST_VHOST"; fi
    return 1
}

# ---------------------------------------------------------------- health / urls
health_url() { echo "http://127.0.0.1:$(get_env APP_PORT)"; }

public_url() {
    local url; url="$(get_env PUBLIC_URL)"
    [ -n "$url" ] && echo "$url" || echo "http://$(server_ip):$(get_env APP_PORT)"
}

wait_for_health() {
    info "Waiting for mygit to answer..."
    # The API, and the git path through nginx's auth check (an anonymous probe of a
    # repository that doesn't exist must be asked for credentials: 401).
    local code
    for _ in $(seq 1 90); do
        code="$(curl -s -o /dev/null -w '%{http_code}' "$(health_url)/-probe-/-probe-.git/info/refs?service=git-upload-pack" 2>/dev/null || true)"
        if curl -fs "$(health_url)/api/health" >/dev/null 2>&1 && [ "$code" = "401" ]; then ok "mygit is up"; return 0; fi
        sleep 2
    done
    warn "Health check timed out. Logs: cd $INSTALL_DIR && docker compose logs --tail 100"
    return 1
}

open_ssh_port() {
    local port; port="$(get_env SSH_PORT)"
    if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
        ufw allow "${port}/tcp" >/dev/null && ok "ufw: allowed ${port}/tcp for git over SSH"
    fi
    warn "If your hosting provider has its own firewall (e.g. IONOS Cloud Panel), open TCP ${port} there too."
}

# ---------------------------------------------------------------- backup / restore
volume() { echo "mygit_$1"; }

# Database dump + repositories, release files and SSH host keys. git and the backend
# pause for the copy so no push lands half-way through it.
backup_data() {
    if ! compose ps postgres 2>/dev/null | grep -q "Up"; then warn "Postgres is not running: skipping the backup"; return 0; fi
    local stamp dir old_umask
    stamp="$(date +%Y%m%d-%H%M%S)"; dir="$BACKUP_DIR/mygit-$stamp"
    old_umask="$(umask)"; umask 077
    mkdir -p "$dir"; chmod 700 "$BACKUP_DIR" "$dir"
    info "Backing up to $dir ..."
    # </dev/null everywhere below: run as `curl ... | bash`, this script *is* stdin, and
    # docker exec/run would swallow the rest of it.
    compose exec -T postgres pg_dump -U mygit --clean --if-exists mygit </dev/null | gzip > "$dir/db.sql.gz"
    compose stop git backend </dev/null >/dev/null 2>&1 || true
    local v
    for v in $VOLUMES; do
        docker run --rm -v "$(volume "$v")":/data:ro -v "$dir":/out alpine tar czf "/out/$v.tgz" -C /data . </dev/null \
            || warn "Could not back up the $v volume"
    done
    compose start backend git </dev/null >/dev/null 2>&1 || true
    cp "$INSTALL_DIR/.env" "$dir/env"
    wait_for_health >/dev/null || warn "mygit is slow to come back after the backup; check: install.sh status"
    ls -1dt "$BACKUP_DIR"/mygit-* 2>/dev/null | tail -n +11 | xargs -r rm -rf
    umask "$old_umask"
    ok "Backup complete: $dir ($(du -sh "$dir" | cut -f1)); the last 10 are kept"
}

do_backup() {
    [ -f "$INSTALL_DIR/docker-compose.yml" ] || fail "No installation at $INSTALL_DIR."
    backup_data
}

do_restore() {
    local dir="${1:-}"
    [ -f "$INSTALL_DIR/docker-compose.yml" ] || fail "No installation at $INSTALL_DIR."
    if [ -z "$dir" ]; then
        echo "Backups:"; ls -1dt "$BACKUP_DIR"/mygit-* 2>/dev/null | head -10 | sed 's/^/  /'
        dir="$(ask "Backup folder to restore: " "$(ls -1dt "$BACKUP_DIR"/mygit-* 2>/dev/null | head -1)")"
    fi
    [ -f "$dir/db.sql.gz" ] || fail "$dir is not a mygit backup (no db.sql.gz)."
    confirm "Replace ALL current data with $dir? [y/N] " || fail "Aborted."
    info "Stopping mygit..."
    compose stop nginx git backend >/dev/null
    compose up -d postgres >/dev/null
    for _ in $(seq 1 30); do compose exec -T postgres pg_isready -U mygit -d mygit </dev/null >/dev/null 2>&1 && break; sleep 1; done
    info "Restoring the database..."
    gunzip -c "$dir/db.sql.gz" | compose exec -T postgres psql -q -v ON_ERROR_STOP=1 -U mygit mygit >/dev/null
    local v
    for v in $VOLUMES; do
        [ -f "$dir/$v.tgz" ] || { warn "No $v.tgz in the backup: leaving that volume as it is"; continue; }
        info "Restoring $v..."
        docker run --rm -v "$(volume "$v")":/data -v "$dir":/in:ro alpine \
            sh -c 'find /data -mindepth 1 -delete && tar xzf "/in/'"$v"'.tgz" -C /data' </dev/null
    done
    # Recreated, not just started: nginx looks containers up by name once, at start.
    compose up -d --force-recreate >/dev/null
    wait_for_health || true
    ok "Restored from $dir"
}

# ---------------------------------------------------------------- install
do_install() {
    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        warn "mygit is already installed at $INSTALL_DIR."
        yes_no "Run an UPDATE instead? [Y/n] " "y" && { do_update; return; }
        fail "Aborted."
    fi
    info "Installing prerequisites..."
    apt-get update -qq
    apt-get install -y -qq git curl openssl ca-certificates iproute2
    install_docker

    local domain email admin http_port ssh_port
    domain="${MYGIT_DOMAIN-$(ask "Domain for mygit, e.g. git.example.com (empty = plain HTTP on a port): " "")}"
    if [ -n "$domain" ]; then
        valid_domain "$domain" || fail "'$domain' is not a domain name."
        email="${MYGIT_EMAIL-$(ask "Email for Let's Encrypt expiry notices (optional): " "")}"
        ensure_shared_proxy
        require_host_nginx
    fi
    admin="${MYGIT_ADMIN:-$(ask "Admin username [admin]: " "admin")}"
    [[ "$admin" =~ ^[A-Za-z0-9](-?[A-Za-z0-9])*$ ]] || fail "'$admin' can't be a username (letters, digits, single hyphens)."
    http_port="${MYGIT_HTTP_PORT:-$(ask "Web port [${DEFAULT_HTTP_PORT}]: " "$DEFAULT_HTTP_PORT")}"
    ssh_port="${MYGIT_SSH_PORT:-$(ask "SSH port for git [${DEFAULT_SSH_PORT}]: " "$DEFAULT_SSH_PORT")}"
    valid_port "$http_port" && valid_port "$ssh_port" || fail "Ports must be numbers between 1 and 65535."
    port_in_use "$http_port" && fail "Port $http_port is in use by $(port_holder "$http_port")."
    port_in_use "$ssh_port" && fail "Port $ssh_port is in use by $(port_holder "$ssh_port"). Pick another SSH port."

    info "Cloning $REPO_URL ($BRANCH)..."
    git clone --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"

    local admin_pass; admin_pass="$(rand 6)"
    if docker volume inspect "$(volume pgdata)" >/dev/null 2>&1; then
        [ -f "$KEPT_ENV" ] || fail "A mygit database volume exists from an earlier install, but its secrets ($KEPT_ENV) are gone.
       Put that file back, or delete the old data volumes (mygit_pgdata, mygit_repos, mygit_releases, mygit_sshkeys)."
        info "Reusing the data and secrets of the earlier installation..."
        (umask 077; cp "$KEPT_ENV" "$INSTALL_DIR/.env")
        admin_pass="(unchanged from the earlier installation)"
    else
    info "Writing $INSTALL_DIR/.env with fresh secrets..."
    (umask 077; cat > "$INSTALL_DIR/.env" <<EOF
SECRET_KEY=$(rand 32)
INTERNAL_TOKEN=$(rand 24)
POSTGRES_PASSWORD=$(rand 16)
ADMIN_USERNAME=${admin}
ADMIN_INITIAL_PASSWORD=${admin_pass}
APP_PORT=${http_port}
SSH_PORT=${ssh_port}
MAX_UPLOAD=2g
EOF
)
    fi
    set_env APP_PORT "$http_port"
    set_env SSH_PORT "$ssh_port"
    if [ -n "$domain" ]; then
        set_env PROXY_MODE 1
        set_env COMPOSE_FILE "docker-compose.yml:docker-compose.proxy.yml"
        set_env DOMAIN "$domain"
        set_env SSH_HOST "$domain"
        set_env LETSENCRYPT_EMAIL "$email"
        set_env PUBLIC_URL "http://127.0.0.1:${http_port}"
    else
        set_env PUBLIC_URL "http://$(server_ip):${http_port}"
        set_env SSH_HOST "$(server_ip)"
    fi

    info "Building images (a few minutes the first time)..."
    compose build
    if [ -n "$domain" ] && obtain_certificate "$domain" "$email"; then set_env PUBLIC_URL "https://${domain}"; fi
    info "Starting mygit (database migrations run at startup)..."
    compose up -d
    wait_for_health || true
    if [ -n "$domain" ] && [ -f "/etc/letsencrypt/live/${domain}/fullchain.pem" ]; then
        publish_host_vhost "$domain" || warn "mygit runs on 127.0.0.1:${http_port} but is not published; fix the vhost, then run: install.sh ssl"
    elif [ -n "$domain" ]; then
        warn "No certificate yet: mygit answers on 127.0.0.1:${http_port} only. When DNS points here, run: install.sh ssl"
    fi
    open_ssh_port

    echo
    ok "mygit installed."
    echo -e "  Web:       ${GREEN}$(public_url)${NC}"
    echo -e "  Sign in:   ${GREEN}$(get_env ADMIN_USERNAME)${NC} / ${GREEN}${admin_pass}${NC}   (change it in Settings)"
    echo -e "  SSH:       git@$(get_env SSH_HOST) on port $(get_env SSH_PORT)"
    echo -e "  Next:      Settings > Access tokens, then: git push $(public_url)/$(get_env ADMIN_USERNAME)/<repo>.git"
}

# ---------------------------------------------------------------- update
do_update() {
    [ -f "$INSTALL_DIR/docker-compose.yml" ] || fail "No installation at $INSTALL_DIR: run Install first."
    backup_data
    info "Pulling the latest code..."
    git -C "$INSTALL_DIR" remote set-url origin "$REPO_URL"
    git -C "$INSTALL_DIR" fetch --prune origin "$BRANCH"
    git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
    info "Building new images while the current ones keep serving..."
    compose build
    info "Restarting (repositories, releases, users and settings are kept)..."
    # --force-recreate: nginx resolves backend/git once at start; recreating everything
    # keeps it from talking to the addresses of containers that were just replaced.
    compose up -d --remove-orphans --force-recreate
    docker image prune -f >/dev/null 2>&1 || true
    wait_for_health || true
    if proxy_mode && [ -f "/etc/letsencrypt/live/$(get_env DOMAIN)/fullchain.pem" ]; then
        publish_host_vhost "$(get_env DOMAIN)" || warn "Host vhost left as it was."
    fi
    ok "mygit updated: $(git -C "$INSTALL_DIR" log -1 --format='%h %s')"
}

# ---------------------------------------------------------------- ssl
do_ssl() {
    [ -f "$INSTALL_DIR/docker-compose.yml" ] || fail "No installation at $INSTALL_DIR."
    local domain; domain="$(get_env DOMAIN)"
    if [ -z "$domain" ]; then
        domain="${MYGIT_DOMAIN:-$(ask "Domain for mygit: " "")}"
        valid_domain "$domain" || fail "'$domain' is not a domain name."
        ensure_shared_proxy
        set_env PROXY_MODE 1
        set_env COMPOSE_FILE "docker-compose.yml:docker-compose.proxy.yml"
        set_env DOMAIN "$domain"
        set_env SSH_HOST "$domain"
    fi
    require_host_nginx
    obtain_certificate "$domain" "$(get_env LETSENCRYPT_EMAIL)" || fail "No certificate, nothing changed."
    set_env PUBLIC_URL "https://${domain}"
    compose up -d --force-recreate
    wait_for_health || true
    publish_host_vhost "$domain" || fail "The vhost was rejected; see above."
}

# ---------------------------------------------------------------- status / remove
do_status() {
    [ -f "$INSTALL_DIR/docker-compose.yml" ] || fail "No installation at $INSTALL_DIR."
    compose ps
    echo
    echo "  URL:     $(public_url)"
    echo "  SSH:     git@$(get_env SSH_HOST) port $(get_env SSH_PORT)"
    echo "  Version: $(git -C "$INSTALL_DIR" log -1 --format='%h %s (%cr)')"
    if curl -fs "$(health_url)/api/health" >/dev/null; then ok "Healthy"; else warn "Not answering on $(health_url)"; fi
    echo "  Backups: $(ls -1d "$BACKUP_DIR"/mygit-* 2>/dev/null | wc -l) in $BACKUP_DIR"
}

do_remove() {
    [ -d "$INSTALL_DIR" ] || fail "No installation at $INSTALL_DIR."
    confirm "Stop mygit and remove its containers? [y/N] " || fail "Aborted."
    yes_no "Make a final backup first? [Y/n] " "y" && backup_data
    local wipe="${MYGIT_DELETE_DATA:-}"
    if [ -z "$wipe" ] && [ -t 0 ]; then
        yes_no "ALSO DELETE all data (repositories, releases, database)? This cannot be undone. [y/N] " "n" && wipe=1
    fi
    if [ "$wipe" = "1" ]; then
        compose down -v --rmi local 2>/dev/null || true
        rm -f "$KEPT_ENV"
    else
        mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
        (umask 077; cp "$INSTALL_DIR/.env" "$KEPT_ENV")
        compose down --rmi local 2>/dev/null || true
        info "Data volumes kept; a reinstall picks them up again (secrets saved in $KEPT_ENV)."
    fi
    rm -rf "$INSTALL_DIR"
    if [ -e "$HOST_VHOST_LINK" ] || [ -e "$HOST_VHOST" ]; then
        rm -f "$HOST_VHOST_LINK" "$HOST_VHOST"
        systemctl reload nginx >/dev/null 2>&1 || true
    fi
    ok "mygit removed. Backups stay in $BACKUP_DIR."
}

main() {
    require_root
    case "${1:-}" in
        install) do_install; exit 0 ;;
        update)  do_update;  exit 0 ;;
        backup)  do_backup;  exit 0 ;;
        restore) do_restore "${2:-}"; exit 0 ;;
        ssl)     do_ssl;     exit 0 ;;
        status)  do_status;  exit 0 ;;
        remove)  do_remove;  exit 0 ;;
        "") ;;
        *) fail "Unknown command '$1' (install|update|backup|restore <dir>|ssl|status|remove)" ;;
    esac
    echo
    echo -e "${BLUE}=== mygit installer ===${NC}"
    echo "  1) Install"
    echo "  2) Update   (backup, pull, rebuild; all data kept)"
    echo "  3) Backup"
    echo "  4) Restore"
    echo "  5) SSL      (add or repair HTTPS for a domain)"
    echo "  6) Status"
    echo "  7) Remove"
    echo
    read -r -p "Choose [1-7]: " choice
    case "$choice" in
        1) do_install ;; 2) do_update ;; 3) do_backup ;; 4) do_restore ;; 5) do_ssl ;; 6) do_status ;; 7) do_remove ;;
        *) echo "Bye." ;;
    esac
}

main "$@"
