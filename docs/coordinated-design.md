# Coordinated tone proposals — 2026-11-03

The assistant now proposes a small coordinated patch based on the current snapshot. Local rules remain deterministic; OpenAI is still a separate optional provider. This is not a new trained model or a perceptual optimizer.

- Brightness-only darkening adjusts cutoff and, when possible, resonance; it retains waveform, ADSR and gain.
- Warmth/softness may also change a square to triangle and soften attack. It does not change every control merely to increase the count.
- Common explicit keep-attack, keep-tail, keep-waveform/character and only-cutoff constraints are enforced before strength scaling. Explicit numeric values retain precedence within the local mapping. Arbitrary nuanced interpretation remains with Live AI and human review.
- Sine limitations are explained rather than solved by silently changing its waveform.
- After proposal validation/scaling, the editor submits complete before/after snapshots and a monotonically changing request ID to loopback `/compare`. Two actual JUCE renders use the same MIDI 48, velocity .8 and common hold/duration. Measurements are waveform-derived and use raw amplitude, with no peak normalization or inverse-model prediction.
- The preview reports spectral centroid and RMS in dBFS, not LUFS or subjective quality. It flags material RMS differences. Different waves can have different output levels even when the gain parameter is preserved.
- No APVTS changes occur during comparison. Apply/Undo remain user controls; snapshot checks and request IDs reject obsolete results. An unavailable backend leaves an explicit warning and the parameter preview usable.
- HTTP, file rendering, feature extraction and subprocess work stay in the external process/background workers. Existing plugin DSP, parameter IDs and serialized format are unchanged.

Measured development fixtures (not held-out evaluation or human preference):

| Case | Centroid Hz, before → after | RMS dBFS, before → after | Offline pair seconds |
|---|---|---|---|
| saw_darker | 423.2227458769913 → 305.21710930489036 | -47.56657679705611 → -47.60073245311944 | 0.0525422909995541 |
| square_warmer_softer | 318.9056544127962 → 135.77737230528473 | -42.79507560093659 → -47.553249014016004 | 0.04869516589678824 |
| sine_darker_control | 130.7882513595047 → 130.78807494231788 | -45.80576235528668 → -45.79024602016732 | 0.043355125002563 |

Exact requested/applied controls and metrics: `build/coordinated-tone-measurements.json`. The square→triangle case also became quieter; no preference win is inferred. The sine control hardly changed centroid. Measurements are for a standardized single note, not the live Logic phrase.

Validation: CTest 2/2, offline tools 35 tests, service/launcher contracts 13 tests. `EditorTests --compare` exercises the real external comparison endpoint and asserts live parameters remain unchanged before Apply, then tests Apply/Undo/staleness. Evidence is in `build/coordinated-design-*.log`. Installed AU/VST3 passed signature verification and auval.

Actual Logic acceptance: from Saw/cutoff 1290.7 Hz/Q .707/attack 300 ms/release 720 ms/gain 40%, `更暖、更柔和，保留尾音` proposed cutoff 709.9 Hz, Q .57 and attack 420 ms. Waveform, decay, sustain, release and gain stayed unchanged. The real background preview showed centroid 244.3→192.8 Hz and RMS -47.1→-48.0 dBFS (rounded UI values). Apply updated the three controls; Undo restored them. This is integration evidence, not a listening judgment.

The OpenAI instruction was updated for coordinated reasoning and preservation, with the same schema. Mocked provider contract tests pass; a fresh paid/live-provider interpretation test of these new instructions was not performed because the prompt service was not running. No key was requested/read from other processes. The local analysis worker was normally restarted only after verifying its canonical command and working directory. Startup refuses silent reuse of an older worker without comparison support.

Try at Medium with Live AI off: `更暖、更柔和，保留尾音`. Review parameter roles and raw before/after measurements, Apply while playing the same MIDI, and Undo. For brightness-only: `更暗，保留起音，保留尾音`. For waveform identity: add `保留波形`. Offline rules cover this bounded vocabulary; they do not promise general conversation. Live AI requires its key-configured local service.
