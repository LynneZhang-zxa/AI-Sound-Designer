#!/bin/bash
# Credential-free checks by default. --live explicitly permits real provider calls.
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_dir"
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target AISoundDesigner_AU AISoundDesigner_VST3 DatasetRenderer SynthTests EditorTests -j4
ctest --test-dir build --output-on-failure
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s service -v
release_spec_dir="$(mktemp -d "$repo_dir/build/release-spec.XXXXXX")"
trap 'rm -rf "$release_spec_dir"' EXIT
build/DatasetRenderer --export-spec "$release_spec_dir/parameter-spec.json"
cp "$release_spec_dir/parameter-spec.json" build/release-parameter-spec.json
export PYTHONPATH="$repo_dir/ml:$repo_dir/ml/tests"
export ML_PARAMETER_SPEC="$repo_dir/build/release-parameter-spec.json"
export ML_RENDERER="$repo_dir/build/DatasetRenderer"
export OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 OMP_NUM_THREADS=1
ml/.venv/bin/python -m unittest discover -s ml/tests -v
# iCloud/Finder can reattach cosmetic metadata even when the linker is up to date.
# Reuse the bounded development signer, which clears only Finder/resource-fork metadata.
cmake "-DBUNDLE=$repo_dir/build/AISoundDesigner_artefacts/Release/AU/AI Sound Designer.component" -P cmake/SignDevelopmentBundle.cmake
cmake "-DBUNDLE=$repo_dir/build/AISoundDesigner_artefacts/Release/VST3/AI Sound Designer.vst3" -P cmake/SignDevelopmentBundle.cmake
if [[ "${1:-}" == "--live" ]]; then
    build/SynthTests --release-ai
fi
