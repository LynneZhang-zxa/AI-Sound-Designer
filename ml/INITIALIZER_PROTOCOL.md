# Expanded-domain initializer: frozen protocol

Frozen before dataset generation, training and test inference. This is one offline training experiment, not OpenAI fine-tuning or a plugin/model deployment.

## Problem and data

Waveform-derived audio → normalized cutoff/attack/release plus four-way waveform classification. Model proposes an initializer; a bounded actual-JUCE render search refines it. Decay/sustain/resonance/gain vary as nuisance factors, not additional prediction targets. No target-derived input metadata.

3,000 new deterministic 48 kHz four-second mono PCM24 examples, 2,400/300/300 train/validation/test. Same target bounds: cutoff 100–10000 Hz, attack .01–.5 s, release .02–1.5 s. Waveforms balanced independently within each split (600/75/75 per class); independent seeded nuisance sampling: decay log-uniform .03–.25, sustain uniform .4–.95, Q uniform .5–1.2, gain uniform .5–.9. Pitches/velocities per initializer_config.json; 150 test examples at seen pitches and 150 at withheld pitches. Fixed note-on .1 s, off 1.5 s; no waveform amplitude normalization or level augmentation. Python owns all sampling and splits. C++ consumes exact requests and returns native and JUCE-normalized readbacks. Exported specification, commit/worktree/source hashes, renderer/config/protocol hashes and environment recorded.

100-example smoke first (80/10/10), then 3,000. Verify duration, silence before onset, complete tails, no clipping/nonfinite/duplicate audio, exact applied labels/MIDI, log-mel shape/distribution and positive envelope rise/fall proxies. Smoke class counts differ by at most one. Nuisance variation intentionally destroys the old fixed-pitch centroid correlation criterion; do not require it.

## Model and training

Same two-convolution trunk as previous work: Conv 1→16 stride2, ReLU, Conv16→32 stride2, ReLU, adaptive pool4×16, Linear2048→64, ReLU, Linear64→7. First three outputs sigmoid; final four raw waveform logits. Input `[B,1,64,747]`, normalized continuous output `[B,3]`, waveform logits `[B,4]`. Existing absolute-level log-mel extraction; mean/std per mel fitted only on training features, independently audited.

Loss = normalized MSE + 0.1 cross entropy; Adam .001, CPU four threads, batch32, max35 epochs, patience7; one real fit and one fixed jointly shuffled target-vector/waveform control, same initialization and batch-order seed. Validation combined loss alone chooses checkpoints/stopping. No tuning or alternate architecture. Train opens only train/validation caches. Baselines: training-mean continuous values and training-majority waveform; training-only calibrated DSP scalar predictors. No model input filenames, pitch, nuisance labels, manifests or split indicators. Mutation regression verifies outputs do not change when labels/IDs/metadata change.

## Single final evaluation

Selected checkpoint/control each inferred once on all 300 test examples; cache predictions before reporting. Report native Hz/ms MAE/RMSE, normalized MSE, waveform accuracy/macro-F1 and unseen/seen pitch groups; shuffled sanity. CPU batch-one forward timings on validation only. These are parameter-identification metrics; ambiguity remains, especially sine cutoff and envelope/nuisance interactions.

Main practical metric: equal **52 actual renders** per method (initial +4 waveforms×6 cutoffs +27 local refinements), comparing constant-default seed, audio-envelope DSP seed, and CNN/waveform seed. Search algorithm/objective identical, no model-specific tuning, nuisance settings always common defaults; ground-truth nuisance labels NEVER initialize rendering. Known pitch and MIDI gate are shared task conditions (not model inputs), so this benchmark does not test pitch detection. The metric is matching log-mel RMSE +2× envelope RMSE with explicit level alignment only for comparison; no perceptual claim. No early termination: equal budget rather than unmeasured claims of fewer renders.

Search subset: 32 test references fixed before predictions, four examples per waveform×seen/held-out pitch group. Selection uses labels solely for balanced reporting composition; actual matching receives waveform bytes plus shared known pitch/gate. Full test prediction cache reused as CNN seeds; no additional test inference or selection based on results. Report mean/median, paired win/tie/loss, and every example. 8 additional independent SciPy fixtures (4 waveforms×2 conditions, stereo 44.1 kHz, known note/gate) assess limited synthetic domain transfer using the same objective/budget. These are not real third-party synth recordings. No claim of generalizing to arbitrary external sounds, and no claim of matching the original parameter values of the independent filter.

Stop after measured results, without changing the plugin, production matcher, old datasets, existing test results or model artifacts. A negative result is retained. Additional real externally recorded references and listening evaluation remain necessary before deployment.
