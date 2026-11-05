# Frozen-model hybrid matching follow-up

Development validation, not a new untouched final test or perceptual result. Motivated by the completed initializer experiment. Freeze checkpoint and preprocessing; no fitting or hyperparameter search. Do not read old test audio/predictions. All work is offline; no plugin changes.

Generate 16 new independent SciPy fixtures (four per waveform), seed 20261027. Each has independently sampled pitch 48–72, velocity-like amplitude .07–.16, cutoff log-uniform 150–8000Hz, attack .015–.4s, release .04–1.1s, sustain .45–.9, decay .04–.2s; second-order Butterworth filter. Save 44.1kHz stereo four-second WAV with known onset .1s and gate 1.4s. These are synthetic transfer references, not real recordings. Actual plugin parameter identity is not defined for the independent filter.

Input: audio-only log-mel, existing frozen train preprocessing. Hybrid initializer uses CNN cutoff/waveform and waveform-only DSP envelope rise/fall estimates. Baseline uses identical DSP envelopes with constant saw/12000Hz cutoff. Both use the exact previous search: 52 actual JUCE renders, identical nuisance defaults, known pitch/gate and objective (log-mel RMSE + 2 envelope RMSE). No label-derived nuisance values initialize search. Predictions, fixtures and initializers frozen before matching. Absolute input amplitude retained; matching objective alone aligns level.

Report every paired score, mean/median, wins/ties/losses and actual search times. Check actual receipt budget, finite/unclipped output and unchanged checkpoint/plugin sources. Equal-budget technical comparison does not demonstrate perceptual superiority or arbitrary recording generalization.

Provide blind A/B listening page with reference and randomized method labels, identical listening gain applied to both candidate methods per reference. Mapping saved separately. No listening preference numbers until a human listens. Stop after results; no automatic deployment based on this small development set.
