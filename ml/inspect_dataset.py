"""Smoke acceptance checks and inspection figures, not model evaluation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d
from scipy.signal import welch
from scipy.stats import spearmanr
from features import log_mel
from generate_dataset import validate_performance_groups
from parameters import normalize, denormalize


def read_audio(path):
    rate, data = wavfile.read(path)
    if data.dtype != np.int32 or data.ndim != 1:
        raise ValueError("Expected mono PCM24 WAV (SciPy reads left-aligned int32)")
    return rate, data.astype(np.float64) / 2147483648.0


def demand(condition, message):
    if not condition:
        raise ValueError(message)


def inspect(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "rendered_manifest.json").read_text())
    initial = json.loads((directory / "manifest.json").read_text())
    meta, rows = manifest["metadata"], manifest["examples"]
    cfg = meta["config"]
    spec, render = meta["parameter_specification"], cfg["renderer"]
    rate, frames = render["sample_rate"], round(render["duration_seconds"] * render["sample_rate"])
    expected_frames = 1 + (frames - cfg["features"]["n_fft"]) // cfg["features"]["hop_length"]
    demand(len(rows) == cfg["examples"] == 100, "Expected smoke dataset only")
    demand(meta == initial["metadata"], "Renderer changed dataset metadata")
    requested_by_id = {row["id"]: row for row in initial["examples"]}
    demand(len(requested_by_id) == len(rows) == len({row["id"] for row in rows}), "Duplicate IDs")
    records, hashes, vectors, features, targets = [], set(), set(), [], []
    counts = {name: 0 for name in cfg["split_counts"]}
    on, off = round(render["note_on_seconds"] * rate), round(render["note_off_seconds"] * rate)
    performance_audit = validate_performance_groups(manifest)
    max_label_relative_error = 0.0
    for row in rows:
        original = requested_by_id[row["id"]]
        for key in original:
            demand(row[key] == original[key], f"Renderer changed requested specification: {key}")
        counts[row["split"]] += 1
        path = directory / row["audio"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        demand(digest not in hashes, "Duplicate audio (including across splits)")
        hashes.add(digest)
        vector = tuple(row["targets"][name] for name in cfg["target_order"])
        demand(vector not in vectors, "Duplicate applied target vector")
        vectors.add(vector)
        sr, audio = read_audio(path)
        demand(sr == rate and len(audio) == frames, "Audio duration/sample rate mismatch")
        demand(np.isfinite(audio).all(), "Nonfinite waveform")
        peak, rms = float(np.max(np.abs(audio))), float(np.sqrt(np.mean(audio ** 2)))
        demand(0 < peak < .999 and rms > 1e-6, "Clipped or silent waveform")
        demand(np.max(np.abs(audio[:on])) <= 2 ** -22, "Audio before specified note-on")
        demand(np.sqrt(np.mean(audio[-round(.2 * rate):] ** 2)) < 1e-5, "Release/tail truncated")
        for name, applied in row["applied_parameters"].items():
            requested = row["requested_parameters"][name]
            relative = abs(applied - requested) / max(abs(requested), 1e-12)
            max_label_relative_error = max(max_label_relative_error, relative)
            demand(np.isclose(applied, requested, rtol=3e-6, atol=1e-7), "Applied value differs from specification")
        for name in cfg["target_order"]:
            raw, norm = row["targets"][name], row["normalized_targets"][name]
            demand(raw == row["applied_parameters"][name], "Target is not actual readback")
            demand(np.isclose(normalize(raw, name, spec), norm, rtol=2e-6, atol=2e-7), "JUCE normalization mismatch")
            demand(np.isclose(denormalize(norm, name, spec), raw, rtol=5e-6, atol=2e-6), "Denormalization mismatch")
        envelope = np.sqrt(np.maximum(0, uniform_filter1d(audio ** 2, size=round(.02 * rate), mode="constant")))
        attack = row["targets"]["attack"]
        release = row["targets"]["release"]
        attack_end = min(off, on + round((attack + .08) * rate))
        attack_section = envelope[on:attack_end]
        height = float(np.max(attack_section))
        crossings = [int(np.flatnonzero(attack_section >= threshold * height)[0]) for threshold in (.1, .9)]
        rise = (crossings[1] - crossings[0]) / rate
        demand(rise > 0 and height > 1e-6, "Attack not visible")
        plateau = float(np.median(envelope[off - round(.15 * rate):off - round(.03 * rate)]))
        release_section = envelope[off:off + round((release + .1) * rate)]
        falls = [int(np.flatnonzero(release_section <= threshold * plateau)[0]) for threshold in (.9, .1)]
        fall = (falls[1] - falls[0]) / rate
        demand(fall > 0, "Release not visible")
        demand(envelope[min(frames - 1, off + round((release + .08) * rate))] < .03 * plateau,
               "Release does not finish near specified duration")
        frequencies, power = welch(audio[round(1.0 * rate):round(1.4 * rate)], fs=rate, nperseg=4096)
        centroid = float(np.sum(frequencies * power) / np.sum(power))
        feature = log_mel(audio, rate, cfg["features"])
        demand(feature.shape == (1, cfg["features"]["n_mels"], expected_frames), "Feature shape mismatch")
        demand(np.isfinite(feature).all() and float(np.std(feature)) > .1, "Degenerate features")
        features.append(feature)
        targets.append([row["normalized_targets"][name] for name in cfg["target_order"]])
        records.append({"id": row["id"], "split": row["split"], "peak": peak, "rms": rms,
                        "attack_seconds": attack, "release_seconds": release, "cutoff_hz": row["targets"]["cutoff"],
                        "rise_10_90_seconds": rise, "fall_90_10_seconds": fall, "sustain_centroid_hz": centroid})
    demand(counts == cfg["split_counts"], "Split counts mismatch")
    correlations = {"attack_vs_rise_spearman": float(spearmanr([r["attack_seconds"] for r in records], [r["rise_10_90_seconds"] for r in records]).statistic),
                    "release_vs_fall_spearman": float(spearmanr([r["release_seconds"] for r in records], [r["fall_90_10_seconds"] for r in records]).statistic),
                    "cutoff_vs_sustain_centroid_spearman": float(spearmanr([r["cutoff_hz"] for r in records], [r["sustain_centroid_hz"] for r in records]).statistic)}
    if performance_audit is None:
        demand(all(value > .8 for value in correlations.values()), "Target variation insufficiently visible in audio")
    else:
        # Pitch is now a deliberate confound for raw centroid/cutoff correlation.
        # Record it without treating fixed-pitch monotonicity as an acceptance gate.
        demand(correlations["attack_vs_rise_spearman"] > .8 and correlations["release_vs_fall_spearman"] > .8,
               "Envelope targets insufficiently visible")
        centroids=[r["sustain_centroid_hz"] for r in records]
        demand(max(centroids)/min(centroids)>1.2,"Insufficient spectral variation")
    all_features = np.stack(features)
    training = all_features[[row["split"] == "train" for row in rows]]
    stats = {"mean_per_mel": training.mean(axis=(0, 1, 3)).tolist(), "std_per_mel": training.std(axis=(0, 1, 3)).tolist(),
             "source_split": "train", "recording_peak_normalization": False}
    report = {"status": "PASS", "examples": len(rows), "split_counts": counts, "sample_rate": rate,
              "duration_seconds": frames / rate, "feature_batch_shape": list(all_features.shape),
              "feature_min": float(all_features.min()), "feature_max": float(all_features.max()),
              "feature_mean": float(all_features.mean()), "feature_std": float(all_features.std()),
              "peak_range": [min(r["peak"] for r in records), max(r["peak"] for r in records)],
              "rms_range": [min(r["rms"] for r in records), max(r["rms"] for r in records)],
              "max_requested_vs_applied_relative_error": max_label_relative_error,
              "visibility_checks": correlations, "unique_audio_hashes": len(hashes),
              "provenance": meta["provenance"], "config": cfg, "parameter_specification": spec,
              "inspection_records": records,
              "performance_audit": performance_audit,
              "interpretation": "Smoke visibility diagnostics, not model predictions or learned baseline performance."}
    np.savez_compressed(directory / "features.npz", inputs=all_features, targets=np.asarray(targets, dtype=np.float32),
                        ids=np.array([r["id"] for r in rows]), splits=np.array([r["split"] for r in rows]))
    (directory / "feature_statistics.json").write_text(json.dumps(stats, indent=2, allow_nan=False) + "\n")
    (directory / "validation.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    plot(directory, rows, records, cfg)
    return report


def plot(directory, rows, records, config):
    os.environ.setdefault("MPLCONFIGDIR", str(directory / "matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), layout="constrained")
    for axis, parameter in enumerate(("attack", "release", "cutoff")):
        order = sorted(range(len(rows)), key=lambda i: rows[i]["targets"][parameter])
        for index in (order[0], order[-1]):
            rate, audio = read_audio(directory / rows[index]["audio"])
            envelope = np.sqrt(np.maximum(0, uniform_filter1d(audio ** 2, size=round(.02 * rate), mode="constant")))
            axes[axis, 0].plot(np.arange(len(audio))[::96] / rate, envelope[::96], label=f"{parameter}={rows[index]['targets'][parameter]:.4g}")
        axes[axis, 0].set(xlabel="Seconds", ylabel="Absolute RMS amplitude", title=f"Independent examples at {parameter} extremes")
        axes[axis, 0].legend()
    for ax, raw, proxy in [(axes[0, 1], "attack_seconds", "rise_10_90_seconds"),
                           (axes[1, 1], "release_seconds", "fall_90_10_seconds"),
                           (axes[2, 1], "cutoff_hz", "sustain_centroid_hz")]:
        ax.scatter([r[raw] for r in records], [r[proxy] for r in records], s=12)
        ax.set(xscale="log", yscale="log", xlabel=raw, ylabel=proxy, title="Visibility diagnostic (not prediction accuracy)")
    fig.savefig(directory / "inspection.png", dpi=130)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    for ax, row in zip(axes, (min(rows, key=lambda r:r["targets"]["cutoff"]), max(rows, key=lambda r:r["targets"]["cutoff"]))):
        rate, audio = read_audio(directory / row["audio"])
        feature = log_mel(audio, rate, config["features"])[0]
        image = ax.imshow(feature, origin="lower", aspect="auto", extent=(0,4,0,64), vmin=-27.7, vmax=-5)
        ax.set(title=f"{row['id']}: cutoff {row['targets']['cutoff']:.1f} Hz", xlabel="Seconds", ylabel="Mel band")
    fig.colorbar(image, ax=axes, label="Natural log power (fixed absolute scale)")
    fig.savefig(directory / "spectrograms.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    result = inspect(args.directory)
    print(json.dumps({k:result[k] for k in ("status", "examples", "split_counts", "feature_batch_shape", "visibility_checks", "peak_range")}, indent=2))
