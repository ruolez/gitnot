#!/usr/bin/env bash
# Writes .env with fresh random secrets (never overwrites an existing one).
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then echo ".env already exists"; exit 0; fi
rand() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-40}"; }
sed -e "s/^SECRET_KEY=.*/SECRET_KEY=$(rand 50)/" \
    -e "s/^INTERNAL_TOKEN=.*/INTERNAL_TOKEN=$(rand 40)/" \
    -e "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(rand 32)/" \
    -e "s/^ADMIN_INITIAL_PASSWORD=.*/ADMIN_INITIAL_PASSWORD=${ADMIN_INITIAL_PASSWORD:-$(rand 16)}/" \
    .env.example > .env
chmod 600 .env
echo "Wrote .env (admin password: $(grep ^ADMIN_INITIAL_PASSWORD= .env | cut -d= -f2))"
