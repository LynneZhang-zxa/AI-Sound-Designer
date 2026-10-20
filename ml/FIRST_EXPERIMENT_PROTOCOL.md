# Frozen first experiment protocol

Frozen before either CNN fit or any test prediction on 2026-10-20.

- Exactly 3000 examples with seed 20261020; 2400 train, 300 validation, 300 test.
- Preserve approved restricted cutoff/attack/release ranges and fixed pitch, saw waveform, velocity, MIDI timings and all other parameters from `experiment_config.json`.
- Input: only waveform-derived `[1,64,747]` log-mel features, standardized with per-mel mean/std fitted on training features only. Preserve absolute level; no per-recording normalization. No IDs, filenames, parameter values, manifests, split codes, or DSP proxies enter the CNN.
- The sole network is Conv(1→16,3,stride2,pad1), ReLU, Conv(16→32,3,stride2,pad1), ReLU, adaptive average pool(4,16), flatten, linear(2048→64), ReLU, linear(64→3), sigmoid. 136131 parameters.
- Normalized MSE; Adam learning rate 0.001, batch 32, at most 30 epochs; minimum validation MSE checkpoint; early stopping after 5 consecutive epochs without a new minimum. No hyperparameter search, augmentation, dropout, alternate architectures or retry based on accuracy.
- CPU, four intra-op threads, one inter-op thread, deterministic algorithms. Torch 2.6.0. Seed 20261020 for initialization and batch order.
- Baseline 1: mean of the three training normalized targets, subsequently converted to physical units.
- Baseline 2: RMS-envelope 10–90% rise, 90–10% fall, and fixed-sustain-window spectral centroid; three independent 1-D interpolation calibrations fitted only on training proxy/physical-target pairs. Duplicate proxy values are averaged and endpoint extrapolation is constant. This avoids intentionally underfitting the nonlinear cutoff relationship with an arbitrary straight line. No validation/test labels fit this baseline.
- One shuffled-label control: permute entire training target vectors once with seed 20261021. Use identical network initialization and batch-order seed; keep validation/test labels correct. The control uses the same optimization, checkpoint-selection, and early-stopping rules. It is a sanity check, not a candidate model.
- Training and baseline fitting cannot open test arrays. After both conditions finish, evaluate each selected checkpoint once on all 300 test examples, and evaluate both baselines on those same examples. An exclusive evaluation marker prevents repeated test-inference runs.
- Persist raw predictions immediately; then compute normalized MSE and physical-unit MAE/RMSE (cutoff Hz; attack/release ms). Export per-example physical values in Hz/seconds with explicit units.
- Measure batch-one CPU forward latency on a validation example with 30 warmups and 200 timed repetitions; report mean, median, p95, minimum. This excludes feature extraction/I/O and is an offline timing, not a real-time claim.
- Report validation histories, selected epochs, unfavorable outcomes, baseline comparisons, and shuffled-label degradation without changing the experiment after observing the test set. No ONNX, plugin inference, new parameters, pitch/velocity variation, or further experiment follows without user review.
