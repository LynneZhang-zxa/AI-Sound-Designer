# Second offline experiment: pitch and velocity robustness

Protocol fixed before rendering/training/test inference. No plugin runtime changes.

- 3,000 newly synthesized examples, seed 20261022; 2,400 train, 300 validation, 300 test.
- Same restricted cutoff 100–10,000 Hz, attack 0.01–0.5 s, release 0.02–1.5 s. Same saw waveform, remaining synth settings, note timing, four-second 48 kHz PCM24 rendering, log-mel representation and JUCE normalization.
- Python owns seeded targets, splits, pitches and velocities. C++ consumes explicit specifications, returns applied parameter and MIDI readbacks, never samples.
- Train/validation pitches: MIDI 48, 50, 51, 52, 54, 55, 57, 59, 60. Test: 150 new examples from those pitches and 150 from withheld pitches 49, 53, 56, 58. Notes are balanced within each split/group, then shuffled independently from targets. No held-out pitch enters train/validation. This is interpolation within an octave, not extrapolation.
- Velocity argument sampled uniformly 0.4–1.0, independently from targets; actual 7-bit encoded velocity recorded. No peak normalization.
- Same fixed 136,131-parameter CNN, training configuration, initialization seed, optimizer and normalized MSE as first experiment. No tuning or architecture changes. One normal fit plus one fixed shuffled-training-target control; validation only selects checkpoint/early stopping. Test untouched by fitting.
- Retain training mean and the exact same training-calibrated DSP baseline, even if pitch weakens its centroid proxy. Do not improve the baseline after seeing test results.
- Train-only feature standardization. Model accepts only waveform-derived `[B,1,64,747]` input. Pitch, velocity, grouping, IDs and labels are reporting metadata, never CNN inputs.
- Before full generation: tests and a 100-example varied-performance smoke render; verify exact performance readbacks, pitch exclusion, finite/unclipped duration-correct audio, envelope visibility, cutoff variation and valid features.
- One test pass per selected checkpoint. Report aggregate plus separate seen-pitch and held-out-pitch MAE/RMSE in Hz/ms, normalized MSE, saved per-example predictions and CPU forward latency. Subgroup metrics reuse cached predictions; no additional inference.
- Existing first experiment data/results remain immutable. New outputs: `ml/data/pitch_velocity_smoke`, `ml/data/pitch_velocity_3000`, `ml/runs/pitch_velocity`. Stop after measured report. No plugin integration, ONNX, new targets, downloaded recordings or deployment claims.
