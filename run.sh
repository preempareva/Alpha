#!/usr/bin/env sh
set -eu
PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
VENV_DIR="$(dirname "$PROJECT_DIR")/.venv"
PYTHON="$VENV_DIR/bin/python"
cd "$PROJECT_DIR"
if [ ! -x "$PYTHON" ]; then
  command -v python3 >/dev/null 2>&1 || { echo "Install Python 3.12 or newer." >&2; exit 1; }
  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' || { echo "Project Alpha requires Python 3.12 or newer." >&2; exit 1; }
  python3 -m venv "$VENV_DIR"
  "$PYTHON" -m pip install -r requirements.lock
fi
"$PYTHON" -m alpha_app.bootstrap
exec "$PYTHON" -m uvicorn alpha_app.main:app --host 127.0.0.1 --port 8000
