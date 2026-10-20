"""Reproducible smoke-only entry point. No training and no large-data mode."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import scipy
import numpy as np
from generate_dataset import ROOT, make_manifest, provenance, merge_receipts
from inspect_dataset import inspect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--renderer", type=Path, default=ROOT / "build/DatasetRenderer")
    parser.add_argument("--output", type=Path, default=ROOT / "ml/data/smoke_v1")
    args = parser.parse_args()
    directory, renderer = args.output.resolve(), args.renderer.resolve()
    if not directory.is_relative_to(ROOT) or directory.exists():
        raise ValueError("Use a new output directory inside the canonical repository")
    directory.mkdir(parents=True)
    config = json.loads((ROOT / "ml/config.json").read_text())
    spec_path = directory / "parameter_spec.json"
    subprocess.run([str(renderer), "--export-spec", str(spec_path)], check=True)
    spec = json.loads(spec_path.read_text())
    source = provenance()
    source["renderer_sha256"] = hashlib.sha256(renderer.read_bytes()).hexdigest()
    source["python_version"] = platform.python_version()
    source["scipy_version"] = scipy.__version__
    source["numpy_version"] = np.__version__
    manifest = make_manifest(config, spec, source)
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    env = dict(os.environ, ML_PARAMETER_SPEC=str(spec_path), ML_RENDERER=str(renderer),
               PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT / "ml"), MPLCONFIGDIR=str(directory / "matplotlib-cache"))
    # Dataset specification and normalization/renderer tests precede smoke rendering.
    with (directory / "tests.log").open("w") as log:
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "ml/tests"), "-v"],
                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    with (directory / "renderer.log").open("w") as log:
        subprocess.run([str(renderer), "--render", str(path), str(directory)], stdout=log, stderr=subprocess.STDOUT, check=True)
    rendered = merge_receipts(manifest, json.loads((directory / "render_receipts.json").read_text()))
    (directory / "rendered_manifest.json").write_text(json.dumps(rendered, indent=2, sort_keys=True, allow_nan=False) + "\n")
    report = inspect(directory)
    if provenance()["plugin_source_sha256"] != source["plugin_source_sha256"]:
        raise RuntimeError("Plugin runtime source changed during smoke generation")
    print(json.dumps({k:report[k] for k in ("status", "examples", "split_counts", "feature_batch_shape", "visibility_checks", "peak_range")}, indent=2))
    print(f"STOP: smoke dataset complete at {directory}; no 3000-example generation or CNN training performed.")


if __name__ == "__main__":
    main()
