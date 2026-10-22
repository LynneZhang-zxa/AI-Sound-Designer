# Pitch and velocity robustness — measured offline results

One fixed CNN, one shuffled-training-label control, unchanged training configuration and DSP baseline. No tuning after test evaluation.

New synthetic dataset: 3,000 four-second, 48 kHz mono examples. Same restricted cutoff/attack/release ranges and saw waveform as the first experiment. Velocity arguments vary 0.4–1.0; actual MIDI bytes are saved. No recording-level amplitude normalization.

Training/validation pitches: 48, 50, 51, 52, 54, 55, 57, 59, 60. Held-out test pitches: 49, 53, 56, 58. These are unseen pitches within the training pitch span, not extrapolation.

## Aggregate test (300 examples)

| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |
| --- | ---: | ---: | ---: | ---: |
| training_mean | 1724.10401232 / 2656.46041308 | 96.4485102282 / 132.243648898 | 273.255309555 / 397.858810544 | 0.0176230047323 |
| dsp | 1067.29349568 / 1644.03612139 | 1.68298421548 / 2.14647859866 | 7.6571649494 / 13.0721693791 | 0.00295828937881 |
| cnn | 74.6841446686 / 144.078195913 | 4.36355467575 / 7.23279917919 | 9.45181212078 / 19.6091101271 | 2.90582566707e-05 |
| shuffled | 1698.94524879 / 2688.98784254 | 96.5202934636 / 131.279902791 | 263.464637585 / 379.610026925 | 0.0169143620311 |

## held_out_pitch (150 examples)

| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |
| --- | ---: | ---: | ---: | ---: |
| training_mean | 1752.58037723 / 2655.20714543 | 99.9522232959 / 138.296788675 | 267.455678255 / 396.0231337 | 0.0179274789473 |
| dsp | 1084.7943648 / 1680.74388845 | 1.79347905875 / 2.25735807291 | 7.89454847704 / 13.0999393518 | 0.00301216492951 |
| cnn | 75.9644541931 / 147.682458825 | 4.58680624763 / 7.5337980813 | 10.2096354837 / 22.9924156092 | 2.97828587616e-05 |
| shuffled | 1722.74240667 / 2685.54394533 | 99.7396047289 / 136.82596834 | 258.370967967 / 377.870299195 | 0.0171569354677 |

## seen_pitch (150 examples)

| Method | Cutoff MAE / RMSE (Hz) | Attack MAE / RMSE (ms) | Release MAE / RMSE (ms) | Normalized MSE |
| --- | ---: | ---: | ---: | ---: |
| training_mean | 1695.6276474 / 2657.71308975 | 92.9447971605 / 125.899815685 | 279.054940856 / 399.686056585 | 0.0173185305173 |
| dsp | 1049.79262656 / 1606.4898127 | 1.57248937222 / 2.02955051173 | 7.41978142177 / 13.0443402873 | 0.00290441382811 |
| cnn | 73.403835144 / 140.381424805 | 4.14030310387 / 6.91871768489 | 8.69398875783 / 15.5042969659 | 2.83336545798e-05 |
| shuffled | 1675.14809092 / 2692.42733464 | 93.3009821984 / 125.488964222 | 268.558307203 / 381.341817888 | 0.0166717885945 |

## Interpretation

- Aggregate: cnn has lower overall normalized MSE.
  - cutoff: cnn has lower MAE.
  - attack: dsp has lower MAE.
  - release: dsp has lower MAE.
- held_out_pitch: cnn has lower overall normalized MSE.
  - cutoff: cnn has lower MAE.
  - attack: dsp has lower MAE.
  - release: dsp has lower MAE.
- seen_pitch: cnn has lower overall normalized MSE.
  - cutoff: cnn has lower MAE.
  - attack: dsp has lower MAE.
  - release: dsp has lower MAE.

Shuffled-label / real-CNN aggregate test MSE ratio: **582.084542195×**. The expected degradation is observed.
Only complete training target vectors were shuffled; validation/test targets remained correct. This sanity check does not prove every possible source of leakage is absent.

Pitch and velocity now confound the original DSP proxy. Its calibration remains three independent training-only interpolation tables; it has not been improved after inspecting the test set. A CNN advantage over this baseline does not establish superiority over all DSP methods.

Absolute scores should not be treated as a paired causal comparison to the first run: the dataset seed and test composition differ. No perceptual, arbitrary-recording, other-waveform or deployment generalization is established.

## Validation selection and training

| Condition | Selected epoch | Completed epochs | Best validation MSE | Training seconds |
| --- | ---: | ---: | ---: | ---: |
| cnn | 27 | 30 | 2.64352783779e-05 | 123.075054792 |
| shuffled | 3 | 8 | 0.0172680500895 | 34.18585975 |

The same 136,131-parameter CNN was trained once per label condition. Validation MSE alone selected checkpoints and early stopping. The test set was inferred exactly once per selected checkpoint; all subgroup metrics reuse the cached predictions.

## Actual offline forward latency

| Condition | Mean (ms) | Median (ms) | p95 (ms) | Minimum (ms) |
| --- | ---: | ---: | ---: | ---: |
| cnn | 0.51089079 | 0.505646 | 0.55689375 | 0.465083 |
| shuffled | 0.505606675 | 0.5030005 | 0.54784375 | 0.458292 |

CPU, four Torch threads, batch size one, 30 warmups and 200 timings. CNN forward only on a validation example, excluding WAV I/O, features and standardization. No real-time claim.

## Data and leakage checks

- 3000 unique audio/target vectors; split counts {'train': 2400, 'validation': 300, 'test': 300}; peak range [0.0018682479858398438, 0.043586015701293945].
- Performance isolation/readback audit: PASS; {'train/seen_pitch': 2400, 'test/held_out_pitch': 150, 'test/seen_pitch': 150, 'validation/seen_pitch': 300}.
- Smoke checks cover finite/unclipped audio, exact duration and parameter/MIDI readbacks, envelope visibility, spectral variation and log-mel distributions.
- Inputs are waveform-derived log-mel tensors `[B,1,64,747]`. Targets are separate normalized tensors `[B,3]`. Pitch, velocity, group, names and manifest data never enter model.forward(x).
- Train-only per-mel standardization independently recomputed; sampled train/validation feature caches exactly match WAV-derived recomputation.
- Mutation regression tests verify label/manifest/filename changes leave inputs and model predictions unchanged.
- Training-mean and DSP calibrations use training data only. No test data is opened during training.
- Original first-experiment outputs and plugin runtime sources were preserved. No model or Python added to audio callback.

## Reproducibility and artifacts

- Base Git commit: `d913d58b1e64c905b619046c9b4c0bde74bedf68`; working-tree state and source hashes: `ml/runs/pitch_velocity/run.json`.
- Dataset manifest SHA-256: `7549b1e44d044785e4ed59eaac9f68dd28ef935849f7ee5ae150a499e7a58021`.
- Preprocessing SHA-256: `0b6eed8037ce857a0d0f1ed2dfb52bf246fcd61713620aefb3d0f05552ea536d`.
- PyTorch 2.6.0, Python 3.12.9, CPU arm64.
- Full float metrics: `ml/runs/pitch_velocity/results.json`.
- `test_predictions.csv` and `.npz` contain all ground truth and predictions. CSV physical units are Hz/seconds; envelope errors above are ms. `test_groups.json` maps example IDs to reporting groups.
- Configuration/protocol: `pitch_velocity_config.json`, `training_config.json`, `PITCH_VELOCITY_PROTOCOL.md`.
- Run log and test evidence: `build/ml-stage2-run.log`, `build/ml-stage2-tests.log`.

Stop point: experiment complete; no tuning, additional target or plugin integration followed the held-out results.
