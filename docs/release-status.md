# Initial development deliverable — 2026-11-04

Technical implementation, reproducible checks and demo materials are complete for the documented controlled scope. This is a development/portfolio deliverable; human preference and physical resize feel remain separately reported, not inferred from technical tests.

| Gate | Current evidence |
|---|---|
| Canonical repository | Desktop AI-Sound-Designer; main; expected GitHub origin; no commit/push |
| AU/VST3 + renderer/test build | scripts/check-release.sh exited successfully; generated-bundle strict verification passed |
| Installed binaries | Exact SHA-256 equality with canonical build; installed signatures verified |
| Apple validation | AU VALIDATION SUCCEEDED in build/release-auval.log |
| C++ processor/editor | 2/2 CTests; state/MIDI/rates/blocks/proposals/resize bounds and hit testing |
| Service/launcher/client | 15 tests; malformed/provider failure/origin boundaries; actual pending-worker cancellation in <2s while callbacks continue |
| Offline tools | 38 tests passed |
| Model-absent source setup | 38 run: 37 passed, one explicitly skipped optional legacy browser-workbench test |
| Real OpenAI | Seven cases through actual C++ transport and shared protection/apply path; no fallback counted as AI success |
| Reference matrix | Eight independent SciPy notes + one existing Logic ES1 export; five invalid inputs rejected |
| Demo | Verified 16s, one video + one audio track, 1200×1080, actual JUCE states/audio |
| Physical mouse resizing | pending user observation |
| Perceptual listening | not measured; audition page available |

## Real-provider observations and corrections

The current prompt policy separates context/history from the latest request and gives explicit 0=sine/1=saw/2=square/3=triangle IDs. This corrected an observed previous-intent carryover. Earlier raw responses, including a wrong waveform ID, are retained; the plugin explicit-waveform guard corrected that value before Apply. Explanations remain best effort and numerical preview/measurements are authoritative. One Chinese request received an English explanation; language conformity is not claimed perfect.

Acceptance also distinguished generic shorter (decay or release) from explicit tail shortening, and explanation-only questions from unsupported action requests. The harness originally over-constrained those cases and incorrectly added no-op questions to applied history; those test issues were corrected rather than hidden as product failures. Current-policy real responses for the first three cases were replayed through the same parameter pipeline without additional billing; four later cases used new live requests. This is seven observed cases, not seven new requests in the final invocation or a statistical success-rate benchmark. Default checks make no paid API calls.

| Case | Actual intent | Evidence |
|---|---|---|
| 0 | square, cutoff 6000 Hz, attack 50 ms, decay 200 ms, sustain 70%, release 800 ms, resonance 1.1 Q, gain 50% | captured actual OpenAI response, replayed without another paid call |
| 1 | 更暗、更短，保留起音，保留波形 | captured actual OpenAI response, replayed without another paid call |
| 2 | 保持尾音，声音更柔和 | captured actual OpenAI response, replayed without another paid call |
| 3 | Do not change any synth parameters. Only explain whether stereo width and reverb are supported. | new live OpenAI request |
| 4 | keep waveform, keep attack, keep release; make it darker and quieter | new live OpenAI request |
| 5 | Shorten release by half; preserve attack and preserve waveform | new live OpenAI request |
| 6 | Add reverb and stereo width; do not approximate them with other synth controls | new live OpenAI request |

## Reference matrix

Same default starting patch, supplied known MIDI pitch/gate, actual loopback Match service, original source bytes retained. Scores use the v2 technical objective; they are not human similarity ratings and are not comparable across arbitrary objective versions. The eight new sources use independent SciPy oscillators/Butterworth filtering; they are controlled synthetic fixtures, not eight new Logic exports or a broad third-party recording benchmark.

| Reference | Baseline score | Matched score |
|---|---|---|
| saw_bass | 5.012940862397874 | 0.2914111554991697 |
| square_pluck | 4.071432468038972 | 1.7401622756342436 |
| saw_pad | 5.082186584842268 | 2.2066618692598685 |
| triangle_soft | 6.697355486110898 | 0.12157198575683306 |
| sine_round | 8.9115160197891 | 0.14602927270335575 |
| bright_pluck | 3.387215207127886 | 2.6703486820883837 |
| triangle_bass | 6.892780978856912 | 0.22845512690360553 |
| square_pad | 6.009036169997593 | 1.1111784806132847 |
| Logic_ES1_existing | 5.908038973532529 | 1.3154609423877528 |

Every request retained legal parameters, preserved gain and produced waveform/spectral artifacts. Rejected: wrong extension, silence, nonfinite audio, out-of-range gate and invalid note. No preference score is invented. Higher residuals in some pluck/pad examples and the ES1 partial/tail mismatch remain known limits of the current synth/search. Listen at `ml/runs/release_acceptance/index.html`.

## Reproduce and demonstrate

- Build/install/start: README.md and docs/quick-start.md.
- Credential-free release checks: `bash scripts/check-release.sh`.
- Optional real-provider acceptance: `build/SynthTests --release-ai` (running configured service; paid requests).
- Reference matrix: `ml/.venv/bin/python scripts/release-acceptance.py` (refuses to overwrite its recorded run).
- Demo generation: `ml/.venv/bin/python scripts/prepare-demo.py`.
- Video inspection: `swift -module-cache-path build/swift-cache scripts/inspect-demo.swift assets/demo`.
- Evidence report only, no model/API calls: `ml/.venv/bin/python scripts/report-release.py`.

## Delivery boundary

The synth, editable assistant and controlled reference workflow are implemented. The CNN remains offline because equal-budget search gave 24/24 ties; full unfavorable metrics are in ml/MATCH_MODEL_RESULTS.md. No new training followed that result. Reverb/unison/stereo width/arbitrary music matching, exact external preset cloning, distribution notarization and broad host/perceptual benchmarking remain outside this initial version.

Previous actual Logic MIDI/automation/state/AI and current Analyze/Match/Apply/Undo observations are dated in docs/verification.md and docs/initial-release.md. New C++/service tests do not masquerade as fresh mouse clicks or listening approval. Native resize geometry/input checks passed; physical dragging awaits user observation because the control tool failed that action. No destructive host termination, old-workspace edits, commits or pushes were performed.

`build/release-audit.json` binds current evidence hashes. Build/log/run files are intentionally Git-ignored; source protocols, measured summaries, docs and staged demo assets are available for the owner to review and commit.
