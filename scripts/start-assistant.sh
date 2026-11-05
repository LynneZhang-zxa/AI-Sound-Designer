#!/bin/bash
set -eu
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
export PYTHONDONTWRITEBYTECODE=1
exec python3 -u service/launcher.py "$@"
