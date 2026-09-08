#!/bin/sh
# Bring up the backend against the mounted checkout and put the CLI on PATH.
set -e

# Scoped to this script, not exported into the image: see the note in the Containerfile.
# It keeps the backend's environment off the mounted repo without letting a stray `uv`
# command in cli/ re-sync the same directory and break the running server.
export UV_PROJECT_ENVIRONMENT=/venv/backend

echo "==> syncing backend dependencies"
uv sync --quiet

# The backend and the CLI are both distributions named "sessionbin", so they cannot share
# one environment. `uv tool install` gives the CLI its own, which is also how end users
# install it.
echo "==> installing the CLI from ./cli"
uv tool install --force --quiet ./cli

echo "==> applying migrations"
uv run --quiet python src/sessionbin/manage.py migrate --noinput

echo "==> serving on http://0.0.0.0:8000"
exec uv run python src/sessionbin/manage.py runserver 0.0.0.0:8000
