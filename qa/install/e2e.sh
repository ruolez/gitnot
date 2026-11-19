#!/usr/bin/env bash
#
# End-to-end test of install.sh on Ubuntu 24.04: a privileged container with its own
# Docker daemon runs the real installer in domain mode behind the real shared proxy
# (../shared-proxy), then drives git over HTTPS and SSH, raw files, the CLI, backup,
# restore, update and remove. certbot is replaced by a self-signed certificate.
# Nothing on this machine is touched. Takes ~10 minutes (images build inside).
#
#   bash qa/install/e2e.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PROXY="$(cd "$ROOT/../shared-proxy" && pwd)" || { echo "needs ../shared-proxy"; exit 1; }
NAME=mygit-install-e2e

docker rm -f "$NAME" >/dev/null 2>&1 || true
docker volume create mygit-install-e2e-docker >/dev/null
[ "${KEEP:-0}" = 1 ] || trap 'docker rm -f "$NAME" >/dev/null 2>&1 || true' EXIT

docker run -d --name "$NAME" --privileged \
    -v "$ROOT:/src:ro" -v "$PROXY:/proxy:ro" -v mygit-install-e2e-docker:/var/lib/docker \
    ubuntu:24.04 sleep infinity >/dev/null

# The test script is written to a file and run from it, not fed on stdin: a command
# inside that reads stdin (docker exec, ssh ...) would otherwise eat the rest of it.
docker exec -i "$NAME" sh -c 'cat > /tmp/e2e-test.sh' <<'CONTAINER'
set -uo pipefail
exec </dev/null
export DEBIAN_FRONTEND=noninteractive
PASS=0; FAIL=0
check() {
  local desc="$1"; shift
  local out
  if out="$("$@" 2>&1)"; then PASS=$((PASS+1)); echo "  ok    $desc"; else FAIL=$((FAIL+1)); echo "  FAIL  $desc"; echo "$out" | tail -8 | sed 's/^/        /'; fi
}
section() { echo; echo "== $*"; }

section "test machine"
apt-get update -qq >/dev/null
apt-get install -y -qq docker.io docker-compose-v2 git curl openssl iproute2 python3 openssh-client ca-certificates >/dev/null 2>&1
(dockerd >/var/log/dockerd.log 2>&1 &)
for _ in $(seq 1 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
check "docker daemon runs" docker info
# The image cache is kept between runs (volume); containers and data of a previous run are not.
docker ps -aq | xargs -r docker rm -f >/dev/null 2>&1
docker volume ls -q | xargs -r docker volume rm >/dev/null 2>&1
docker network prune -f >/dev/null 2>&1
# Those old containers start with dockerd and create their bind-mount folders first.
rm -rf /opt/mygit /opt/mygit-backups

# No systemd in a container: handle the calls the installers make.
cat > /usr/local/bin/systemctl <<'EOF'
#!/bin/sh
cmd="$1"; for unit; do :; done
[ "$unit" = "nginx" ] || exit 0
running() { [ -f /run/nginx.pid ] && kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; }
case "$cmd" in
  is-active) running ;;
  start)     running || nginx ;;
  reload)    nginx -s reload ;;
  restart)   if running; then nginx -s stop; sleep 1; fi; nginx ;;
  stop)      if running; then nginx -s stop; fi ;;
  *)         exit 0 ;;
esac
EOF
chmod +x /usr/local/bin/systemctl
# certbot stand-in: a self-signed certificate where Let's Encrypt would put one.
cat > /usr/local/bin/certbot <<'EOF'
#!/bin/sh
d=""; while [ $# -gt 0 ]; do [ "$1" = "-d" ] && d="$2"; shift; done
mkdir -p "/etc/letsencrypt/live/$d"
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$d" -addext "subjectAltName=DNS:$d" \
  -keyout "/etc/letsencrypt/live/$d/privkey.pem" -out "/etc/letsencrypt/live/$d/fullchain.pem" 2>/dev/null
EOF
chmod +x /usr/local/bin/certbot
echo "127.0.0.1 git.test" >> /etc/hosts

# The installer clones a git URL: serve the working tree (with uncommitted changes) as one.
git config --global user.email qa@test; git config --global user.name qa; git config --global init.defaultBranch main
cp -r /src /tmp/source && cd /tmp/source && rm -rf qa/.scratch && git add -A >/dev/null && git commit -qm "e2e snapshot" >/dev/null 2>&1; cd /
git clone -q --bare /tmp/source /srv/mygit.git

section "install (domain mode behind the shared proxy)"
export MYGIT_YES=1 MYGIT_DOMAIN=git.test MYGIT_EMAIL= MYGIT_ADMIN=boss REPO_URL=/srv/mygit.git
export SHARED_PROXY_URL=file:///proxy/install.sh
bash /tmp/source/install.sh install > /tmp/install.log 2>&1; rc=$?
tail -12 /tmp/install.log
check "installer exits 0" [ "$rc" -eq 0 ]
ENVF=/opt/mygit/.env
check "proxy mode recorded" grep -q '^PROXY_MODE=1' $ENVF
check "public URL is https" grep -q '^PUBLIC_URL=https://git.test' $ENVF
check "web port bound to loopback only" sh -c "ss -ltnH 'sport = :5564' | grep -q '127.0.0.1:5564'"
check "SSH port published" sh -c "ss -ltnH 'sport = :2222' | grep -q ."
check "host vhost passes nginx -t" nginx -t
echo "  (host nginx server names: $(nginx -T 2>/dev/null | sed -n 's/^[[:space:]]*server_name[[:space:]]*\(.*\);/\1/p' | sort -u | paste -sd' ' -))"
H() { curl -fsS --cacert /etc/letsencrypt/live/git.test/fullchain.pem "$@"; }
check "https health through host nginx" H https://git.test/api/health
check "http redirects to https" sh -c "curl -s -o /dev/null -w '%{http_code}' http://git.test/ | grep -q 301"

section "accounts and tokens over https"
PW="$(grep '^ADMIN_INITIAL_PASSWORD=' $ENVF | cut -d= -f2)"
J=/tmp/cj
check "admin signs in" H -c $J -H 'X-Requested-With: mygit' -H 'Content-Type: application/json' \
  -d "{\"username\":\"boss\",\"password\":\"$PW\"}" https://git.test/api/auth/login
check "session cookie is Secure" grep -q 'TRUE.*mygit_session' $J
TOK="$(H -b $J -H 'X-Requested-With: mygit' -H 'Content-Type: application/json' -d '{"name":"e2e","access":"write"}' \
  https://git.test/api/user/tokens | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')"
check "token minted" [ -n "$TOK" ]
check "repo created" H -b $J -H 'X-Requested-With: mygit' -H 'Content-Type: application/json' -d '{"name":"app"}' https://git.test/api/repos

section "git over https through the proxy"
export GIT_SSL_CAINFO=/etc/letsencrypt/live/git.test/fullchain.pem GIT_TERMINAL_PROMPT=0
W=/tmp/work; mkdir -p $W/src && cd $W/src && git init -q
printf '#!/usr/bin/env bash\necho "hello from mygit $1"\n' > install.sh
head -c 80000000 /dev/urandom > big.bin
git add -A && git commit -qm "first"
check "push 80 MB over https" git push -q "https://boss:$TOK@git.test/boss/app.git" main
cd $W
check "anonymous clone over https" git clone -q https://git.test/boss/app.git clone1
check "clone is complete" cmp src/big.bin clone1/big.bin
check "curl | bash through the proxy" bash -c 'bash <(curl -fsSL --cacert $GIT_SSL_CAINFO https://git.test/raw/boss/app/main/install.sh) e2e | grep -q "hello from mygit e2e"'
check "protocol v2 negotiated" sh -c "GIT_TRACE_PACKET=1 git -c protocol.version=2 ls-remote https://git.test/boss/app.git 2>&1 | grep -q 'version 2'"

section "git over ssh"
ssh-keygen -q -t ed25519 -N '' -f $W/key
python3 - "$W/key.pub" <<'PY' > /tmp/keyjson
import json, sys; print(json.dumps({"key": open(sys.argv[1]).read(), "title": "e2e"}))
PY
check "ssh key added" H -b $J -H 'X-Requested-With: mygit' -H 'Content-Type: application/json' -d @/tmp/keyjson https://git.test/api/user/keys
export GIT_SSH_COMMAND="ssh -i $W/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$W/kh"
cd $W/src && echo more >> install.sh && git commit -qam second
check "push over ssh" git push -q ssh://git@git.test:2222/boss/app.git main
check "ssh clone URL from the API names the domain" sh -c "curl -fsS --cacert $GIT_SSL_CAINFO https://git.test/api/repos/boss/app | grep -q 'ssh://git@git.test:2222/boss/app.git'"
cd $W

section "releases through the proxy"
curl -fsSL --cacert $GIT_SSL_CAINFO https://git.test/cli/mygit -o $W/mygit
head -c 3000000 /dev/urandom > $W/app-1.0.0.zip
check "CLI publishes a release" env MYGIT_URL=https://git.test MYGIT_TOKEN=$TOK SSL_CERT_FILE=$GIT_SSL_CAINFO \
  python3 $W/mygit release create boss/app v1.0.0 $W/app-1.0.0.zip --notes "first"
check "latest download matches" sh -c "curl -fsSL --cacert $GIT_SSL_CAINFO https://git.test/boss/app/releases/latest/download/app-1.0.0.zip | cmp - $W/app-1.0.0.zip"

section "backup and restore"
check "backup" bash /tmp/source/install.sh backup
BK="$(ls -1dt /opt/mygit-backups/mygit-* | head -1)"
check "backup has db, repos, releases, ssh keys" sh -c "ls $BK/db.sql.gz $BK/repos.tgz $BK/releases.tgz $BK/sshkeys.tgz"
cd $W/src && echo lost >> install.sh && git commit -qam "after backup"; cd $W
check "mygit serves right after a backup: push" git -C $W/src push -q "https://boss:$TOK@git.test/boss/app.git" main
check "mygit serves right after a backup: new repo" H -b $J -H 'X-Requested-With: mygit' -H 'Content-Type: application/json' -d '{"name":"made-after-backup"}' https://git.test/api/repos
check "the new commit is there before the restore" sh -c "git ls-remote https://git.test/boss/app.git main | grep -q $(git -C $W/src rev-parse HEAD)"
check "restore refuses unattended without MYGIT_CONFIRM" sh -c "! bash /tmp/source/install.sh restore $BK < /dev/null"
check "restore" env MYGIT_CONFIRM=1 bash /tmp/source/install.sh restore "$BK"
check "pushed commit after the backup is gone" sh -c "! git ls-remote https://git.test/boss/app.git main | grep -q $(git -C $W/src rev-parse HEAD)"
check "repo made after the backup is gone" sh -c "! curl -fsS --cacert $GIT_SSL_CAINFO https://git.test/api/explore | grep -q made-after-backup"
check "release file survived" sh -c "curl -fsSL --cacert $GIT_SSL_CAINFO https://git.test/boss/app/releases/latest/download/app-1.0.0.zip | cmp - $W/app-1.0.0.zip"
check "ssh host key unchanged" git ls-remote ssh://git@git.test:2222/boss/app.git

section "update"
cd /tmp/source && echo "# e2e update marker" >> README.md && git commit -qam "e2e update" && git push -q /srv/mygit.git main; cd /
check "update" bash /tmp/source/install.sh update
check "update pulled the new commit" sh -c "git -C /opt/mygit log -1 --format=%s | grep -q 'e2e update'"
check "data kept across update" git ls-remote https://git.test/boss/app.git main
check "status" bash /tmp/source/install.sh status

section "remove (keep data) and reinstall"
check "remove (keeping data)" env MYGIT_CONFIRM=1 bash /tmp/source/install.sh remove
check "vhost removed" [ ! -e /etc/nginx/sites-enabled/mygit.conf ]
check "reinstall" bash /tmp/source/install.sh install
check "repositories survived remove + reinstall" git ls-remote https://git.test/boss/app.git main
check "old token still works after reinstall" git ls-remote "https://boss:$TOK@git.test/boss/app.git" main

echo
echo "passed: $PASS  failed: $FAIL"
[ "$FAIL" -eq 0 ]
CONTAINER
docker exec "$NAME" bash /tmp/e2e-test.sh
