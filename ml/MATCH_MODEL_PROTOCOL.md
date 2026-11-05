# Seven-control Match initializer — frozen initial protocol

One new 3,000-example deterministic JUCE dataset, seed 20261103, 80/10/10 splits.
Reuse the approved restricted cutoff/attack/release ranges and prior nuisance ranges;
all four waveforms, variable pitch and velocity, held-out pitch groups. Gain is nuisance,
not a predicted/applied target. Predict cutoff/attack/decay/sustain/release/resonance in
JUCE normalized units and a four-class waveform head. Labels use actual render readbacks.
Input is waveform-only log-mel [B,1,64,747], no manifest metadata, filenames or labels.
Train-only per-mel statistics. Two stride-2 convolutions (16/32 channels), pooled to
4x16, linear 2048->64->10. Loss normalized MSE + .1 cross entropy. Adam .001, batch32,
35 epochs max, patience7, fixed seeds. Select checkpoints only by validation loss.
One real fit and one fixed shuffled-training-label sanity fit, same initialization/order.
No hyperparameter search. Evaluate each selected checkpoint once on the new test set;
report six physical-unit MAE/RMSE, normalized MSE and waveform accuracy, training mean,
and DSP cutoff/attack/release with training-mean remaining controls.

Preselect 16 balanced waveform/pitch-group test examples before fitting. Compare production
DSP search versus CNN initialization under exactly 96 actual renders each, same objective,
known pitch/gate and default starting controls. Current patch always remains a candidate;
CNN replaces a fixed coarse-grid slot rather than adding free renders. No nuisance labels
seed either search. Also use eight new independent SciPy oscillator/Butterworth references
with fixed generation seed as a transfer stress test, not evidence of arbitrary-recording
performance. Save per-example predictions/search outcomes, source/model/data/config hashes,
seeds, renderer identity, timings and all candidate receipts. Forward latency is offline only.

Deployment gate fixed before results: at least 5% mean technical-score improvement, at
least 10/16 wins with no more than 4 losses on synth references, and 5/8 transfer wins with
no more than 2 losses. Even passing is not perceptual acceptance or proof for arbitrary WAVs;
keep the existing DSP matcher as default pending that evidence. Negative results retained.
Internal shared-scale spectrogram/envelope PNG/NPZ diagnostics accompany production Match;
no new plugin visualizer or inference in the audio callback.
