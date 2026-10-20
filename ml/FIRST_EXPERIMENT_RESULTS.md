# First offline parameter-prediction experiment — measured results

One fixed CNN and one shuffled-label control. No tuning or additional run followed test evaluation.

## Held-out test (300 examples)

| Method | Cutoff MAE (Hz) | Cutoff RMSE (Hz) | Attack MAE (ms) | Attack RMSE (ms) | Release MAE (ms) | Release RMSE (ms) | Normalized MSE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| training_mean | 1618.80709697 | 2450.50087316 | 93.6889439335 | 130.730833263 | 308.316980207 | 446.691292896 | 0.0183109663329 |
| dsp | 0.0499017062773 | 0.805611991622 | 1.27482413547 | 1.85373363567 | 9.5522193866 | 18.4034018501 | 7.23425088086e-06 |
| cnn | 26.9730635579 | 51.9371684048 | 2.84110231325 | 6.14159361084 | 6.65715401992 | 10.9908567534 | 8.9885738527e-06 |
| shuffled | 1525.64646545 | 2322.06774011 | 93.1203884818 | 137.424023189 | 303.496859167 | 441.008524234 | 0.0169796904857 |

Full floating-point metrics are retained in `runs/first_experiment/results.json`; predictions are in `test_predictions.csv` and `test_predictions.npz`. CSV physical cutoff values are Hz and attack/release values are seconds; the table converts envelope errors to ms.

## Baseline comparison

- cutoff: **DSP baseline has lower test MAE** (CNN 26.9730635579, DSP 0.0499017062773, in the table’s units).
- attack: **DSP baseline has lower test MAE** (CNN 2.84110231325, DSP 1.27482413547, in the table’s units).
- release: **CNN has lower test MAE** (CNN 6.65715401992, DSP 9.5522193866, in the table’s units).
- Overall normalized MSE: **DSP baseline is lower**.

The DSP predictor uses three audio-derived scalar measurements and training-only calibration tables. It is not an uncalibrated closed-form estimator. A fixed pitch and waveform make spectral centroid particularly informative; this result cannot establish generalization to other pitches, velocities, waveforms or real recordings.

## Shuffled-label leakage sanity check

Shuffled/control test normalized MSE divided by real-CNN MSE: **1889.03053632×**.
Training target vectors alone were permuted with seed 20261021. Validation and test labels remained correct. The initial weights and batch-order seed match the main experiment. This is a pipeline sanity check, not proof of the absence of every possible leakage mechanism.

## Training and validation selection

| Condition | Epochs completed | Selected epoch | Best validation normalized MSE | Training seconds |
| --- | ---: | ---: | ---: | ---: |
| cnn | 29 | 24 | 8.92447616328e-06 | 122.134707708 |
| shuffled | 6 | 1 | 0.016156646808 | 25.304010125 |

Both checkpoints were selected solely by validation MSE. Exactly one inference pass per selected checkpoint was made on the untouched test split. No checkpoint selection used test results.

## Offline inference latency

| Condition | Mean (ms) | Median (ms) | p95 (ms) | Minimum (ms) |
| --- | ---: | ---: | ---: | ---: |
| cnn | 0.5501583 | 0.536083 | 0.6487896 | 0.4775 |
| shuffled | 0.536430415 | 0.5286875 | 0.6003503 | 0.469666 |

CPU, four Torch threads, batch size one, 30 warmups, 200 measurements on a validation example. Forward pass only: excludes WAV I/O, log-mel extraction and preprocessing. No real-time deployment claim.

## Data and leakage audit

- 3000 unique rendered audio/target vectors; 2400/300/300 split; finite, unclipped, four-second 48 kHz mono audio.
- Waveform-only log-mel inputs `[B,1,64,747]`; targets `[B,3]`. Model `forward(x)` accepts no labels, IDs, paths or metadata.
- Tests change labels, manifest contents and filenames and verify identical model inputs and forward outputs.
- Three cached train/validation inputs were recomputed directly from WAV bytes and matched exactly.
- Preprocessing statistics were independently recomputed from all 2400 training feature tensors only and matched exactly.
- DSP windows depend only on the waveform and fixed note timing; true attack/release values are not used to select measurement windows.
- Training-only means and DSP tables were frozen before CNN fitting. Neither training condition loaded the test split.
- Plugin runtime sources were not modified; no model, Python, inference or networking was added to the plugin callback.

## Provenance

Base Git commit: `a39d6947b1eafbb49b139bc38e524a773f153257`; working-tree status and source fingerprints are preserved in `runs/first_experiment/run.json`.
Dataset manifest SHA-256: `07c2d7d942adfeb3a7facec73ba98292969819cd079c92a221f7856b6b414d64`.
Preprocessing SHA-256: `d6dae3b5790df24762d758e43d21ddc1584a060492d18f10618b0e32eba006fa`.
PyTorch 2.6.0; Python 3.12.9; CPU architecture arm64.

## Interpretation and stop point

These measured results apply only to the approved controlled single-pitch, single-waveform experiment. Parameter estimation error is technical evidence; no perceptual preference or audio-similarity outcome is inferred. The next decision belongs to the user; no follow-up model or harder dataset has been started.
