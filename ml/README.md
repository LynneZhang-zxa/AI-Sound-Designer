# Offline synth-parameter experiments

This directory is separate from the verified v0.1 plugin. It contains the approved smoke pipeline and first controlled 3,000-example offline experiment. The only prediction targets are cutoff, attack and release. There is no plugin inference integration, ONNX export, networking, or pitch/waveform/velocity variation.

## Ownership and data flow

1. `DatasetRenderer --export-spec` reads the actual JUCE APVTS parameters and exports ranges, skew, interval, defaults, and 33 C++ reference conversions per parameter.
2. Python `generate_dataset.py` owns seeded parameter sampling and split assignment. It writes an immutable, deterministic `manifest.json` before rendering. All eight requested native parameters are explicit for every example.
3. The standalone `ml/render_dataset.cpp` consumes that manifest, checks the embedded specification against the current plugin, renders the existing `AISoundDesignerProcessor`, and writes audio plus separate `render_receipts.json`. It has no sampling or split logic. It never creates the plugin editor or an AI worker.
4. Python combines receipts with the original manifest into `rendered_manifest.json`, preserving requested values and metadata without a C++ JSON reserialization round trip. Raw targets are actual APVTS readbacks; normalized targets are C++ JUCE conversions of those readbacks. Requested values remain separately recorded so float conversion differences are visible.
5. `inspect_dataset.py` checks audio, labels, visibility and features, writes cached features and diagnostic figures, and exits. `run_smoke.py` runs tests before the 100-example render and stops after inspection. `prepare_experiment.py` builds the approved 3,000-example dataset into a separate directory.

All calls to the processor occur synchronously in a standalone offline executable. File operations and JSON work surround rendering, rather than being added to `processBlock`. Existing plugin runtime sources, installed bundles, host state formats, and parameter IDs are unchanged by this experiment. The only root build change is an opt-in target.

## Reproduce

Use Python 3.12 in a separate environment. `requirements.txt` pins the smoke-stage dependencies; `training-requirements.txt` adds pinned PyTorch 2.6.0 for the separately approved training stage. The recorded run used Python 3.12.9, NumPy 1.26.4, SciPy 1.15.2, and Matplotlib 3.10.0.

From `/Users/zhangxiai/Desktop/AI-Sound-Designer`:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DAISD_BUILD_ML_RENDERER=ON
cmake --build build --target DatasetRenderer -j 4
PYTHONDONTWRITEBYTECODE=1 python ml/run_smoke.py --output ml/data/smoke_reproduction
ctest --test-dir build --output-on-failure
```

The environment's `python` must have the pinned dependencies. The runner refuses to overwrite an existing dataset. Use a new directory for another run. The smoke runner still uses the 100-example configuration. The general manifest generator now accepts only the approved 100- and 3,000-example configurations; the renderer accepts at most 3,000 explicit records.

The manifest can also be generated independently after exporting the specification:

```sh
build/DatasetRenderer --export-spec ml/data/new_spec.json
python ml/generate_dataset.py --spec ml/data/new_spec.json --output ml/data/new_manifest.json
build/DatasetRenderer --render ml/data/new_manifest.json ml/data/new_render
```

The last command produces rendering receipts, not an assembled dataset manifest. `run_smoke.py` shows the explicit Python merge and inspection steps.

## Fixed experiment configuration

`config.json` specifies seed 20261020, 100 examples, and an 80/10/10 train/validation/test split. Python uses PCG64 and stratifies each log-parameter axis, independently permuting the axes before assigning splits. The IDs and split memberships are recorded before audio exists.

| Target | Restricted sampling range | Stored physical unit |
| --- | --- | --- |
| cutoff | 100–10,000 | Hz |
| attack | 0.01–0.5 | seconds |
| release | 0.02–1.5 | seconds |

These are experiment bounds, not duplicated plugin range definitions. Full legal ranges/skews come from the C++ export, and Python checks that sampling bounds lie inside them. `parameters.py` implements that exported JUCE mapping and checks it against C++ reference conversions. Normalized outputs correspond to the full JUCE range, not min/max scaling within the restricted experiment.

Audio: 48 kHz, four seconds, mono PCM24, MIDI note 48, fixed saw waveform, velocity argument 0.8, note-on at 0.1 s, note-off at 1.5 s. Decay/sustain/resonance/gain use explicit fixed values in the configuration. The receipt records the actual encoded 7-bit MIDI velocity. Each example starts with freshly prepared DSP and 50 ms silent warm-up to settle cutoff smoothing. The left channel is saved because v0.1 produces dual-mono output. No amplitude normalization or automatic gain adjustment is performed.

Features: periodic Hann window, FFT 1024, hop 256, no centered padding; window-energy-normalized power; 64 HTK mel bands spanning 20–20,000 Hz with triangular area normalization; natural log with a fixed 1e-12 floor. Each feature tensor has shape `[1,64,747]`; the smoke cache is `[100,1,64,747]` and normalized targets are `[100,3]` in cutoff/attack/release order. The cached log-mel features retain absolute level. Optional future standardization statistics are fitted on the 80 training examples only and saved separately; they have not been applied to the cache.

## Artifacts and validation

Each dataset contains the random seed, full renderer/feature configuration, exported plugin specification, current Git commit, working-tree status, plugin and experiment source fingerprints, renderer binary SHA-256, and dependency versions. The Git hash alone is not presented as identifying uncommitted experiment code.

- `manifest.json`: original requests, requested normalized targets, splits, and provenance.
- `render_receipts.json`: actual applied parameter values, JUCE-normalized targets, audio paths, encoded velocity, IDs and unchanged splits.
- `rendered_manifest.json`: Python-owned manifest plus receipts.
- `features.npz`: inputs, normalized targets, IDs and splits.
- `feature_statistics.json`: training-only per-mel means/stds; no peak normalization.
- `validation.json`: per-example checks and dataset summary.
- `inspection.png`, `spectrograms.png`: envelope/visibility and fixed-scale spectrogram inspection.
- `tests.log`, `renderer.log`: run evidence.

Tests cover exported-reference normalization, endpoints/monotonicity/round trips, invalid values, deterministic sampling/splits, restricted bounds, the 100-example guard, amplitude preservation, explicit renderer order/splits, label readback, byte-identical rerendering, immutable input files, mismatched specifications, invalid parameter vectors, and overwrite refusal. Inspection additionally checks unique audio/target vectors across splits, duration, finite/unclipped audio, onset timing, tail completion, audible rise/fall sections, cutoff variation, and feature shape/distribution.

[Smoke results](SMOKE_RESULTS.md) record the actual completed run. Visibility correlations use known onset/offset and all smoke examples for dataset QA; they are not held-out prediction metrics or evidence that a CNN adds value. The shortest attacks approach the analysis-window resolution, and high-cutoff differences can be weak despite monotonic spectral measurements. Generalization beyond this fixed pitch/waveform is outside the experiment.

## Baselines for the first experiment

Keep the training-mean predictor on normalized targets. The deterministic DSP baseline uses: RMS-envelope 10–90% rise and 90–10% fall as attack/release proxies, and steady-state spectral centroid as a cutoff proxy. Three one-dimensional interpolation tables calibrate each scalar proxy to its corresponding physical target on training data only. Duplicate proxy positions are averaged; out-of-training-range values use endpoint predictions. Calibration is frozen before validation/test evaluation. Unlike smoke visibility inspection, DSP prediction uses only fixed windows and never reads true attack/release values to choose a measurement window.

The first full experiment is now authorized and implemented as described below. Actual measured results are recorded only after the guarded evaluation completes.


## First full experiment: fixed run and one shuffled-label control

The protocol in [FIRST_EXPERIMENT_PROTOCOL.md](FIRST_EXPERIMENT_PROTOCOL.md) was frozen before training and test inference. Dataset and training settings are in `experiment_config.json` and `training_config.json`.

```sh
# Install only into a separate environment; do not add Python to the plugin.
python -m venv ml/.venv
ml/.venv/bin/python -m pip install -r ml/training-requirements.txt
cmake --build build --target DatasetRenderer -j 4
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 ml/.venv/bin/python ml/prepare_experiment.py
PYTHONPATH=ml ML_PARAMETER_SPEC="$PWD/ml/data/smoke_v3/parameter_spec.json" ML_RENDERER="$PWD/build/DatasetRenderer" ml/.venv/bin/python -m unittest discover -s ml/tests -v
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 ml/.venv/bin/python ml/audit_experiment.py
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 ml/.venv/bin/python ml/train.py
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 ml/.venv/bin/python ml/evaluate.py
ml/.venv/bin/python ml/report_experiment.py
```

The existing dataset/run directories are never overwritten. The evaluation uses an exclusive marker to prevent repeating test inference after observing its results. To reproduce from scratch later, use the scripts' explicit new output/run path arguments and preserve that new run's audit; do not reuse the reported run directory.

- Dataset: `ml/data/experiment_3000/`, split-specific waveform-derived feature tensors, normalized targets, physical targets, and DSP proxies stored separately. IDs are sidecar files for reporting, never model inputs.
- Preprocessing: per-mel moments fitted on the 2,400 training feature tensors only. `input_path_audit.json` independently recomputes those moments and verifies selected cached inputs directly against WAV-derived features. Labels/metadata mutation tests verify that the feature tensors and model predictions are unchanged.
- CNN: 136,131 parameters; the previously proposed two-convolution architecture. `forward(x)` accepts only a float tensor `[B,1,64,747]`. Training passes only the feature half of each supervised `(x,y)` pair to that method.
- Baselines: training-mean normalized targets and training-only calibrated DSP proxies are frozen before fitting the CNN.
- Control: a fixed permutation of complete training target vectors, with the same initial weights and batch-order seed as the real CNN. Validation/test labels remain correct.
- Validation chooses checkpoints and early stopping. The training module never opens the test split. The selected main/control checkpoints each receive one final test pass, and predictions are cached before metric reporting.
- Predictions: `ml/runs/first_experiment/test_predictions.csv` and `.npz`. Physical CSV units are Hz and seconds. Reported envelope errors are converted to ms. Full floating-point metrics remain in `results.json`.
- Latency: actual CPU batch-one forward timing on a validation example, explicitly excluding feature extraction and file I/O. No real-time or deployment claim.

After this first evaluation and control, stop for user review. No hyperparameter search, harder dataset, extra model, or plugin integration is part of this run.

## Second experiment: pitch and velocity robustness

The fixed-pitch first experiment and its measured results above are preserved. The separate second experiment varies pitch and velocity with the same saw waveform, three targets, restricted ranges, CNN architecture, training settings and baseline algorithms. This work is still fully offline and does not change the installed synth or AI prompt service.

Read `PITCH_VELOCITY_PROTOCOL.md` for the frozen split and performance sampling protocol. The 300 test examples comprise 150 new examples at seen pitches and 150 at pitches absent from both training and validation. Pitch and velocity are Python-owned manifest specifications, C++ returns their actual MIDI readbacks, and neither becomes a CNN input. Only train-derived log-mel statistics are fitted. Subgroup evaluation reuses the single test prediction pass.

Reproduce once into fresh directories, from the canonical repository with the existing ML environment:

```sh
cmake --build build --target DatasetRenderer -j 4
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  ml/.venv/bin/python -u ml/run_pitch_velocity.py --name pitch_velocity_reproduction
```

The runner tests first, renders/inspects 100 varied-performance examples, then generates the 3,000-example dataset, audits preprocessing, fits both baselines, trains the CNN/control, evaluates once and writes a measured report. Existing output directories are refused. `--smoke-only` stops after inspection. Each run records seed, rendering/feature configuration, JUCE specification, Git commit/working-tree source hashes and dependencies. For standalone stages, `prepare_experiment.py` accepts `--config ml/pitch_velocity_config.json`; training/evaluation accept `--data` and `--run`. Do not rerun evaluation on a reported run; the exclusive marker deliberately prevents that.

Results: `PITCH_VELOCITY_RESULTS.md`. Audio/manifests/features: `ml/data/pitch_velocity_3000/`. Checkpoints, baseline tables, full metrics, cached per-example predictions and subgroup mappings: `ml/runs/pitch_velocity/`. No additional experiment or model integration follows the report automatically.

## Offline WAV analyzer (CNN cutoff + DSP envelope)

`analyze_wav.py` loads the existing selected CNN and frozen DSP calibration. It estimates cutoff with the CNN and attack/release with DSP, and writes an HTML report, absolute-amplitude waveform/RMS-envelope plot, JSON predictions for all three methods, input hash and artifact provenance. No training or plugin integration occurs.

Supported input is deliberately narrow: four-second, 48 kHz mono PCM24 saw-wave renders with note-on at 0.1 s and note-off at 1.5 s, matching `pitch_velocity_config.json`. There is no resampling, trimming, peak normalization or automatic pitch/waveform recognition. Silence, clipping, incorrect duration/rate/channels, early signal and truncated tails are rejected. Passing those checks does not establish that an arbitrary recording belongs to the training distribution. The model remains limited to the tested ranges/settings.

From the canonical repository:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  ml/.venv/bin/python ml/analyze_wav.py \
  ml/data/pitch_velocity_3000/audio/sample_0019.wav \
  --output ml/runs/my_wav_analysis
```

Open `ml/runs/my_wav_analysis/index.html` in a browser. Use a fresh output directory each time. JSON physical values use Hz and seconds; the visible report converts attack/release to milliseconds. `analysis_ms` is one measured offline analysis call including features, standardization, CNN and DSP; it excludes model/WAV loading and report rendering, and is not a latency benchmark or real-time claim.

The actual demo is saved in `ml/runs/wav_analysis_demo/`. The fixed hybrid was measured on all 300 validation examples only using `validate_hybrid.py`, without fitting anything or opening test tensors. Results, including all methods' MAE/RMSE, are in `HYBRID_VALIDATION_RESULTS.md`; per-example arrays are in `ml/runs/hybrid_validation/validation_predictions.npz`. These are development validation results, not an independent test claim. The CNN has slightly lower validation release error, while the fixed hybrid has lower overall normalized MSE. The policy was not changed after seeing validation results.

```sh
# Optional independent reproduction of validation measurement; use a new output.
ml/.venv/bin/python ml/validate_hybrid.py --output ml/runs/hybrid_validation_reproduction
```

No networking, model loading, PyTorch or inference was added to the JUCE audio thread. The existing prompt assistant and installed plugin are unchanged.
