#!/usr/bin/env bash
# One-command launcher for macOS and Linux. Serves everything on http://127.0.0.1:8000.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  echo "Creating Python environment..."
  python3 -m venv backend/.venv
  backend/.venv/bin/python -m pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend packages..."
  (cd frontend && npm install --silent)
fi
if [ ! -f frontend/dist/index.html ]; then
  echo "Building frontend..."
  (cd frontend && npm run build --silent)
fi

echo
echo "The Stranded Network is starting: http://127.0.0.1:8000"
cd backend
exec .venv/bin/python -m uvicorn app.main:app --port 8000
