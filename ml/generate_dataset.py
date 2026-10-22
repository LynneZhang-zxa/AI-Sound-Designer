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
    if "performance_variation" in config:
        assign_performances(examples, config)
    return {"metadata": {"schema_version": 1, "config": config, "parameter_specification": spec,
                         "provenance": source_info, "numpy_version": np.__version__,
                         "sampling_algorithm": "PCG64 stratified log-uniform, independent axis permutations"},
            "examples": examples}


def assign_performances(examples, config):
    """Independent RNG stream; targets/splits are unchanged by performance sampling."""
    variation = config["performance_variation"]
    seen, held = variation["seen_midi_notes"], variation["held_out_midi_notes"]
    if (not seen or not held or set(seen) & set(held)
            or len(set(seen)) != len(seen) or len(set(held)) != len(held)
            or any(type(n) is not int or not 0 <= n <= 127 for n in seen + held)):
        raise ValueError("Pitch pools must be valid, unique and disjoint")
    low, high = variation["velocity_range"]
    if not 0 < low < high <= 1:
        raise ValueError("Invalid velocity range")
    rng = np.random.Generator(np.random.PCG64(config["seed"] + 1))
    tests = [r for r in examples if r["split"] == "test"]
    count = variation["test_seen_count"]
    if not 0 < count < len(tests):
        raise ValueError("Test must contain both seen and held-out pitches")
    seen_test_ids = {tests[i]["id"] for i in rng.permutation(len(tests))[:count]}
    for split in config["split_counts"]:
        rows = [r for r in examples if r["split"] == split]
        for group in ("seen_pitch", "held_out_pitch"):
            selected = [r for r in rows if ("held_out_pitch" if split == "test" and r["id"] not in seen_test_ids else "seen_pitch") == group]
            pool = seen if group == "seen_pitch" else held
            notes = np.resize(np.array(pool), len(selected))
            rng.shuffle(notes)
            for row, note in zip(selected, notes):
                row["requested_performance"] = {"midi_note": int(note), "velocity": float(rng.uniform(low, high))}
                row["evaluation_group"] = group


def validate_performance_groups(manifest):
    """Verify held-out pitch isolation and exact Python-to-JUCE MIDI readbacks."""
    config=manifest["metadata"]["config"]
    if "performance_variation" not in config:
        return None
    variation=config["performance_variation"]
    seen=set(variation["seen_midi_notes"]); held=set(variation["held_out_midi_notes"])
    counts={}
    for row in manifest["examples"]:
        group=row["evaluation_group"]; performance=row["requested_performance"]
        if group not in ("seen_pitch","held_out_pitch"):
            raise ValueError("Unknown evaluation group")
        expected=held if group=="held_out_pitch" else seen
        if performance["midi_note"] not in expected or (row["split"]!="test" and group!="seen_pitch"):
            raise ValueError("Held-out pitch leakage or invalid pitch group")
        if not variation["velocity_range"][0] <= performance["velocity"] <= variation["velocity_range"][1]:
            raise ValueError("Velocity outside configured range")
        if "midi_note" in row:
            # JUCE receives float32 and rounds its float32 product to nearest MIDI byte.
            encoded=int(np.floor(np.float32(np.float32(performance["velocity"])*127)+.5))
            if row["midi_note"]!=performance["midi_note"] or row["midi_velocity_7bit"]!=encoded:
                raise ValueError("Renderer MIDI readback mismatch")
        key=row["split"]+"/"+group
        counts[key]=counts.get(key,0)+1
    expected_counts={"train/seen_pitch":config["split_counts"]["train"],
                     "validation/seen_pitch":config["split_counts"]["validation"],
                     "test/seen_pitch":variation["test_seen_count"],
                     "test/held_out_pitch":config["split_counts"]["test"]-variation["test_seen_count"]}
    if counts!=expected_counts:
        raise ValueError("Incorrect pitch group counts")
    return {"status":"PASS","group_counts":counts,"seen_pitches":sorted(seen),"held_out_pitches":sorted(held),
            "pitch_and_velocity_excluded_from_model_input":True}


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
