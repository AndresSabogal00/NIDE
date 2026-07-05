#!/usr/bin/env bash
# NIDE one-shot setup: Python venv + backend deps (builds openmc from
# source, ~5 min) and frontend npm install.
#
# Prerequisites (macOS): brew install cmake hdf5 node && python3.11 available
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=${PYTHON:-python3.11}
command -v "$PYTHON" >/dev/null || PYTHON=python3

echo "==> Creating venv (backend/.venv) with $PYTHON"
"$PYTHON" -m venv backend/.venv

echo "==> Installing backend dependencies (openmc builds from source; takes a few minutes)"
HDF5_ROOT=${HDF5_ROOT:-/opt/homebrew} CMAKE_POLICY_VERSION_MINIMUM=3.5 \
  backend/.venv/bin/pip install -r backend/requirements.txt

echo "==> Installing frontend dependencies"
npm --prefix frontend install

echo "==> Done. Next: ./run.sh (first run downloads ENDF/B-VIII.0, ~2 GB)"
