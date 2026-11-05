#!/bin/bash
set -eu
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
if [ ! -x ml/.venv/bin/python ] || [ ! -f ml/runs/pitch_velocity/cnn/best.pt ] || [ ! -x build/DatasetRenderer ]; then
    echo "Missing ML environment, trained checkpoint or DatasetRenderer. See ml/README.md." >&2
    exit 1
fi
export PYTHONDONTWRITEBYTECODE=1
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export VECLIB_MAXIMUM_THREADS="${VECLIB_MAXIMUM_THREADS:-1}"
exec ml/.venv/bin/python -u ml/workbench.py "$@"
