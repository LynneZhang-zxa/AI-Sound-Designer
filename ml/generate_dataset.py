"""Specify the experiment in Python before asking C++ to render anything."""
import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from parameters import normalize

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    sources = sorted(list((ROOT / "plugin/Source").rglob("*.h")) +
                     list((ROOT / "plugin/Source").rglob("*.cpp")))
    experiment = sorted((ROOT / "ml").glob("*.py")) + [ROOT / "ml/render_dataset.cpp", ROOT / "CMakeLists.txt"]
    return {"git_commit": git("rev-parse", "HEAD"),
            "git_worktree_status": git("status", "--porcelain"),
            "plugin_source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in sources},
            "experiment_source_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in experiment}}


def make_manifest(config, spec, source_info):
    config, spec = copy.deepcopy(config), copy.deepcopy(spec)
    count = config["examples"]
    if count not in (100, 3000):
        raise ValueError("Only the approved 100-example smoke and 3000-example experiment are supported")
    if sum(config["split_counts"].values()) != count or config["target_order"] != ["cutoff", "attack", "release"]:
        raise ValueError("Invalid split counts or target order")
    rng = np.random.Generator(np.random.PCG64(config["seed"]))
    vectors = {}
    for name in config["target_order"]:
        low, high = config["sampling"][name]
        exported = spec["parameters"][name]
        if not 0 < exported["minimum"] <= low < high <= exported["maximum"]:
            raise ValueError(f"Sampling bounds outside exported plugin range: {name}")
        # Stratify each log axis, then independently permute; no renderer randomness.
        quantiles = (np.arange(count) + rng.random(count)) / count
        rng.shuffle(quantiles)
        vectors[name] = np.exp(np.log(low) + quantiles * np.log(high / low))
    split_order = rng.permutation(count)
    assignments = {}
    cursor = 0
    for split, size in config["split_counts"].items():
        for index in split_order[cursor:cursor + size]:
            assignments[int(index)] = split
        cursor += size
    examples = []
    for index in range(count):
        targets = {name: float(vectors[name][index]) for name in config["target_order"]}
        examples.append({"id": f"{'smoke' if count == 100 else 'sample'}_{index:04d}", "split": assignments[index],
                         "requested_parameters": dict(config["fixed_parameters"], **targets),
                         "requested_targets": targets,
                         "requested_normalized_targets": {k: normalize(v, k, spec) for k, v in targets.items()}})
    return {"metadata": {"schema_version": 1, "config": config, "parameter_specification": spec,
                         "provenance": source_info, "numpy_version": np.__version__,
                         "sampling_algorithm": "PCG64 stratified log-uniform, independent axis permutations"},
            "examples": examples}


def merge_receipts(manifest, receipts):
    """Python retains exact requested specifications; C++ returns only readbacks."""
    result = copy.deepcopy(manifest)
    received = receipts["examples"]
    if len(received) != len(result["examples"]):
        raise ValueError("Missing renderer receipts")
    for row, receipt in zip(result["examples"], received):
        if row["id"] != receipt["id"] or row["split"] != receipt["split"]:
            raise ValueError("Renderer changed order, identity or split")
        if set(receipt) & (set(row) - {"id", "split"}):
            raise ValueError("Renderer attempted to replace a requested specification")
        row.update(receipt)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = make_manifest(json.loads(args.config.read_text()), json.loads(args.spec.read_text()), provenance())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n")
    print(f"Wrote deterministic manifest: {len(manifest['examples'])} examples, seed {manifest['metadata']['config']['seed']}")


if __name__ == "__main__":
    main()
