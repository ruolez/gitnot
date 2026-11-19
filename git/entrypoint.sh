#!/bin/bash
# Runs fcgiwrap (git over HTTPS via git-http-backend) and sshd (git over SSH).
set -eu

: "${INTERNAL_TOKEN:?INTERNAL_TOKEN is required}"
umask 027
printf '%s' "$INTERNAL_TOKEN" > /etc/mygit/internal-token
chown root:git /etc/mygit/internal-token
chmod 640 /etc/mygit/internal-token
printf '%s' "${BACKEND_URL:-http://backend:5000}" > /etc/mygit/backend-url
chmod 644 /etc/mygit/backend-url
umask 022

chown git:git /data/repos

if [ -x /usr/local/bin/start-sshd ]; then
    /usr/local/bin/start-sshd &
fi

setpriv --reuid=git --regid=git --init-groups --reset-env \
    /usr/sbin/fcgiwrap -s tcp:0.0.0.0:9000 -c "${GIT_WORKERS:-16}" &

# Whichever exits first takes the container down so Docker restarts it.
wait -n
exit 1
