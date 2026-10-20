# Smoke dataset results — 2026-10-20

**PASS — stopped after 100 examples.** No 3,000-example dataset or CNN training was performed.

Run directory: `ml/data/smoke_v3/` (generated and Git-ignored).
Base Git commit: `a39d6947b1eafbb49b139bc38e524a773f153257`. The manifest also records working-tree status and source/binary fingerprints, since the new experiment is uncommitted.

| Check | Actual result |
| --- | --- |
| Dataset / splits | 100 examples: 80 train, 10 validation, 10 test |
| Waveforms | All 100 mono PCM24, 48,000 Hz, 192,000 samples / 4 seconds |
| Unique audio and target vectors | 100; no duplicates across splits |
| Clipping / nonfinite audio | None detected |
| Peak absolute amplitude | 0.01326680–0.03559566 |
| Full-clip RMS amplitude | 0.00369490–0.01001002 |
| Actual cutoff values | 104.0873–9727.9502 Hz |
| Actual attack values | 0.01026140–0.48345342 seconds |
| Actual release values | 0.02064837–1.48665142 seconds |
| Applied/readback label and normalization checks | All passed |
| Maximum requested/applied relative difference | 8.26371011e-07 (float parameter conversion) |
| Onset / complete release tails | All passed |
| Feature tensor shape | `[100,1,64,747]`; targets `[100,3]` |
| Log-mel distribution | min -27.631021, max -6.466236, mean -23.846186, std 6.101006 |
| New offline tests | 8 passed; includes byte-identical repeated renders of 3 explicit examples |
| Existing plugin CTest suite | Passed; `build/ml-plugin-regression.log` |
| Plugin runtime source changes | None (`git diff --exit-code -- plugin/Source`) |

## Visibility diagnostics

Spearman correlations across the smoke dataset:

- Attack versus RMS-envelope 10–90% rise: **0.999259**.
- Release versus RMS-envelope 90–10% fall: **0.999556**.
- Cutoff versus steady-state spectral centroid: **1.000000**.

These confirm the three sampled parameters leave measurable traces under the controlled rendering setup. They are **not model accuracy, MAE/RMSE, or held-out baseline results**. The plots were visually inspected: attack/release extremes are visible, tails complete before the clip ends, and low/high-cutoff spectrograms differ on the same absolute color scale.

![Envelope and visibility inspection](data/smoke_v3/inspection.png)

![Fixed-scale log-mel inspection](data/smoke_v3/spectrograms.png)

## Artifact fingerprints

- `manifest.json` SHA-256: `b97fc09d9b17efe393ef4096019c6b4b5b6d7d388b38c51ab9b80580e918ccfe`
- `parameter_spec.json` SHA-256: `76cf61fe329adcb7ca3c417097b0f1f105547a3d4ea4896509800c901e0befda`
- `rendered_manifest.json` SHA-256: `f0e30657ddf7c33e0926b321b45ef5b302f9b280f4a3ace8c0e6b9bafd6ccdcb`
- `features.npz` SHA-256: `a09599c9be761fada9681bff7005e1a7b5c8db780d2b7dd7ad80effb8fc550ee`

Full per-example measurements, configuration, parameter specification and provenance are in `data/smoke_v3/validation.json`. Generated audio occupies 57,610,400 bytes.
