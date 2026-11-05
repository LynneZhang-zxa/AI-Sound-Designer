# Actual Logic ES1 reference: development comparison

Source: ES1Warm.wav bounced by Logic Pro, 48kHz 24-bit stereo, four seconds, Normalize Off. Dry ES1 patch, chorus/LFO/analog drift disabled. MIDI 60 stimulus with ES1 octave setting 4'; audio pitch detected as MIDI 72. Shared gate 1.4s; no target-derived parameter seed.

| Method | Initial distance | Final distance ↓ | Search seconds | Actual renders |
|---|---:|---:|---:|---:|
| dsp | 8.00132210615 | 4.23338319818 | 0.71600575 | 52 |
| hybrid | 4.67162915651 | 4.23338319818 | 0.61361441703 | 52 |

Distance = log-mel RMSE + 2 envelope RMSE. This single real host bounce is independent of the training renderer, but is still synthesized audio, not a musical recording. ES1 filter/envelope topology differs; exact original parameter recovery is not claimed. Both searches use the same fixed nuisance defaults and budget. Checkpoint/plugin sources unchanged. No training or deployment. Human listening preference remains unmeasured.

Blind listening: ml/runs/logic_es1_match/index.html; complete initializers, candidate receipts, parameters, source hash and provenance retained. Only one actual Logic reference completed: subsequent UI access timed out after bounce; additional timbres remain pending.


## Listening correction

The initial page boosted both candidates toward peak 0.7 while leaving the reference at its original level; its reference/candidate comparison was level-biased. The original files and numerical evaluation are preserved. `prepare_logic_listening.py` creates separate mono copies under `ml/runs/logic_es1_match/level_matched/`, matching RMS over the same 0.1–1.5s held-note interval with common clipping headroom. This is RMS level matching, not LUFS or proof of perceptual loudness equality. Regression test verifies gain-only processing, original-array preservation, matched RMS, headroom and silent-input rejection.

Both raw selected candidates are sample-identical (maximum absolute difference 0), and the old A/B WAV SHA-256 values match. No preference between these identical files can establish a method advantage. Preliminary listener feedback: candidates louder than reference, A seemed closer but brighter; retained as uncontrolled feedback.

Steady 1.0–1.4s measurements: reference centroid 529.3164745091765Hz; candidate 533.2663042508659Hz. Power fraction above 2kHz: reference 0.000033339572177390646; candidate 0.00032732250551031797. Both fractions are small; this is consistent with slightly more high-frequency energy, not a complete explanation of perceived brightness. No EQ, cutoff change, extra search, or retraining was applied. Full values and original hashes are in level_matched/audit.json.


## User-directed brightness audition

After RMS matching, listener still described candidates as roughly 10% too bright (subjective estimate). `refine_logic_brightness.py` rendered exactly five candidates with cutoff factors 1/.9/.8/.7/.6 (approximately 160/144/128/112/96Hz). All other parameters held fixed and checked against C++ readbacks; the baseline listening waveform reproduces the prior corrected candidate. Original WAV/result hashes unchanged. Same held-window RMS matching, finite/peak checks and preserved raw renders; no training or plugin changes.

Scores in order: 4.233383198180946, 4.233044805988343, 4.234573743347623, 4.237675283300447, 4.238466789057682. Centroid barely changes (533.2663→533.1967Hz). Cutoff is already below the approximately 523Hz fundamental, so further lowering mainly attenuates the signal; after level matching the timbral difference can be small. This sweep does not establish that the perceived brightness issue is solved. Do not map subjective 10% brightness directly to a 10% cutoff reduction. No preference winner selected. Listen at ml/runs/logic_es1_match/cutoff_audition/index.html; exact readbacks/metrics/levels are saved in measurements.json.
