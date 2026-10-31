#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null 2>&1 || { echo "Install Python 3.12 or newer." >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Project Alpha requires Python 3.12 or newer." >&2; exit 1; }
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.lock
fi
.venv/bin/python -m alpha_app.bootstrap
exec .venv/bin/python -m uvicorn alpha_app.main:app --host 127.0.0.1 --port 8000
