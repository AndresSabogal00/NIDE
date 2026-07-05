#!/usr/bin/env bash
# Start NIDE: FastAPI backend on :8000 and Vite frontend on :5173.
#
# On first run, downloads the required nuclear data:
#   - ENDF/B-VIII.0 HDF5 (~2 GB, foreground: the app needs it)
#   - decay / fission-yield sublibraries + NUBASE2020 (small, foreground)
#   - JEFF-3.3 and JENDL-5 (background; comparison views light up when done)
set -euo pipefail
cd "$(dirname "$0")"

PY=backend/.venv/bin/python

if [ ! -e backend/data/nubase/nubase_4.mas20.txt ]; then
  echo "==> Downloading decay, fission-yield and NUBASE2020 data (small)"
  "$PY" backend/scripts/download_data.py aux
fi

if ! ls backend/data/endfb80/*/cross_sections.xml >/dev/null 2>&1; then
  echo "==> Downloading ENDF/B-VIII.0 (~2 GB compressed — one-time)"
  "$PY" backend/scripts/download_data.py endfb80
fi

for lib in jeff33 jendl5; do
  if ! ls "backend/data/$lib"/*/cross_sections.xml >/dev/null 2>&1; then
    echo "==> Downloading $lib in the background (comparison unlocks when done)"
    nohup "$PY" backend/scripts/download_data.py "$lib" >"backend/data/$lib.download.log" 2>&1 &
  fi
done

trap 'kill 0' EXIT
(cd backend && .venv/bin/uvicorn app.main:app --port 8000) &
npm --prefix frontend run dev -- --open &
wait
