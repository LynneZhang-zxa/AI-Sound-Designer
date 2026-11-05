# Plugin-native sound design and audio analysis

The editor provides proposal review, strength, apply and one-step undo. Suggestions use actual plugin parameters. Analysis is read-only and works for all legal settings; the sound is never replaced with a fixed test preset.

## Install and use

Save and quit Logic normally before `bash scripts/install-development.sh` from the canonical repository. Reopen the plugin. For text changes, enter an intent, choose Subtle/Medium/Strong, click Propose changes, review before/after values, Apply proposal, then play MIDI. Undo change restores the previous assistant change. Local rules require no service; Live AI uses the existing external `127.0.0.1:8765/propose` service. No key belongs in the plugin.

Manual/host parameter changes invalidate ready/pending suggestions. Changing prompt/strength/service invalidates a ready proposal. Undo is disabled after later sound changes and belongs to the current editor session. It does not suspend DAW automation. All eight existing parameters can be proposed; full native JUCE ranges and parameter IDs/state format are preserved.

## Analyze sound — no fixed test settings

Start `bash scripts/start-plugin-analysis.sh` once. The service binds to `127.0.0.1:8766`. Click **Analyze sound** in the plugin. A snapshot is rendered in a separate offline JUCE process, at MIDI 48 / velocity 0.8. All eight settings are kept as requested. The held note and tail extend when necessary to accommodate long attack/decay/release (at most 18.85 seconds with current ranges). The live plugin never renders test notes through the user's speakers.

The plugin shows **measured** full-render RMS and peak dBFS, and held-note spectral centroid. The response also includes the held-note spectral energy ratio above 3 kHz. These describe an actual synthesized waveform, are not LUFS or inferred synth parameters, and are not perceptual quality scores. Gain zero returns a valid silence result, not an error. No peak normalization occurs. Measurements refer to a standard-note render of the captured snapshot, not live audio or an entire song. Later parameter changes are marked as an earlier snapshot.

**Optional ML estimates** remain scientifically distinct. The existing CNN/DSP artifacts were trained/evaluated on saw wave, cutoff 100–10000 Hz, attack 0.01–0.5 s, release 0.02–1.5 s, with fixed decay 0.1 s/sustain 0.8/Q 0.707/gain 0.8. Only in those conditions does the service additionally show estimates. Other sounds still receive real audio measurements but are labeled ML-not-validated, with no invented or relabeled prediction. Missing/invalid model artifacts do not prevent measurements. No new model was trained and no broader prediction accuracy is claimed.

The former **ML test setup** button has been removed. We do not change the user's sound to satisfy an experiment. Extending inverse-synthesis predictions across all waveforms and full ranges requires a separately designed dataset/evaluation; merely relaxing validation would not accomplish that. The previous strict-gain failure (displayed 80.0%, actual 0.799734354019165) is now accepted for measured analysis and honestly marked outside the old model's fixed condition.

## Thread ownership

- Audio thread: existing fixed-capacity DSP, atomic parameter reads; no new allocations, locks, files, network, Python or models.
- Message thread: snapshots, UI, validation, host gestures, stale-state checks and undo.
- Editor workers: cancellable HTTP/service work; no direct APVTS mutation.
- External Python process: offline renderer and audio measurements; saved-model inference only when eligible. Temporary renders are removed afterwards.

The analysis response's `actual` and `rendered_parameters` are known settings/readbacks, never estimates. Only `ml.estimates` holds predictions. Old-client top-level prediction fields are emitted only for in-domain estimates, never substituted with known values. `/diagnostics` reports the most recent numeric snapshot/status for local troubleshooting; no prompt text or credentials.

## Verification

- AU/VST3 compiled with AppleClang; callback allocations/state/MIDI/automation regressions pass.
- Editor tests exercise strength, apply, undo, stale-snapshot rejection, and a live analysis response using sine, Q 1.2 and the previously failing fractional gain. They assert all parameters remain unchanged after analysis.
- 25 Python tests pass, including actual renders of all four waveforms, near-80% gain, Q changes, zero gain, zero sustain, 20 Hz/20 kHz cutoff, max attack/decay/release, missing model, HTTP validation and nonfinite/fractional-waveform rejection. Logs: `build/full-sound-analysis-tests.log`.
- No training or held-out-test reevaluation followed this product fix. Existing experiment artifacts remain intact.
- Installed-host acceptance is separate from test-harness verification. Installation refuses to replace bundles while Logic runs. If saving/quitting Logic stalls, no force termination or in-place replacement is performed; use normal closed-host installation before claiming the new UI is active.


## Initial assistant revision

The Live AI contract now accepts a structured `{proposal,message,unsupported,provider}` response; legacy flat patches remain accepted. Up to four applied/undone turns provide follow-up context. No unapplied suggestion is recorded as an accepted change; current APVTS values remain authoritative. History is editor-local, never serialized with plugin state. Closing the editor clears conversation history. Explicit numeric local intents use native units; categorical waveform changes are discrete, positive time/filter changes scale logarithmically, and gain/sustain scale linearly. The preview uses Hz/ms/%/Q and waveform names. Host changes invalidate ready or pending results, and undo cannot overwrite later manual edits.

The offline fallback supports concrete English/Chinese combinations, pad/pluck envelope presets, waveform, volume, resonance, and explicit English parameter values with Hz/kHz/ms/s/%/Q units. It is a deterministic vocabulary, not arbitrary language understanding. Unsupported-only/ambiguous Live AI turns may explain with no edit. No actual model inference or networking is placed on the audio thread.

Reference matching now uses the separate v2 background search described in `reference-matching.md`; it returns seven existing timbral controls and preserves gain. Previous 52-render experiment results remain immutable and are not scores for the v2 objective. Use `bash scripts/start-assistant.sh` for both local workers (OpenAI optional when configured).


If the current snapshot still matches a completed Analyze request, Live AI additionally receives only six bounded numeric/boolean descriptors of that standard-note render. Stale measurements are not sent. This is not live audio listening or reference-WAV upload. Service validation rejects unknown fields/descriptor paths, nonfinite values and browser-origin requests. Common explicit keep/preserve parameter directives are filtered before any AI proposal is scaled/applied.


See [coordinated-design.md](coordinated-design.md) for state-aware multi-control tone plans and asynchronous paired-render measurements added on 2026-11-03.


## Resizable editor — 2026-11-04

Drag the bottom-right diagonal grip to resize. The editor advertises host resizing and uses proportional scaling of artwork, controls and text, not a rearranged multi-column layout. Logical content limits are 720×660 through 1440×1320 with the original 960×880 aspect ratio. Every area, including AI and Match, remains visible; scrolling is unnecessary within these supported sizes. On creation, the default size is reduced when needed to fit primary-display user space with room reserved for the host header. Host-forced other aspect ratios use centered letterboxing. Window size is UI-only and is not added to serialized synth state.

Build/install, installed signatures and auval passed. Editor regression tests cover minimum/default/maximum/nonstandard dimensions, transformed-control hit testing and no parameter mutation. The 720×660 snapshot was visually checked (`build/plugin-resize-small.png`). Logic reopened the installed editor with the grip and bottom controls visible. Computer Use's native coordinate drag returned `noWindowsAvailable`, so a physical drag in Logic was not asserted as an automated pass; the editor's resize geometry/input path is directly verified. See `build/resizable-ui-audit.json`. DSP/IDs/automation/state format remain unchanged.


## Analyze feedback — 2026-11-04

Analyze sound measures a standardized background render of the current patch at MIDI 48; it does not capture live MIDI/microphone audio or analyze the imported reference WAV. A tooltip now states this. Clicking immediately shows a disabled Analyzing button and a prominent progress message. Completion restores the button and displays RMS/peak/centroid in the main status rather than leaving an old Match error above the small bottom measurements. Ready/pending parameter proposal messages are not overwritten. Optional out-of-domain model estimates are omitted without labeling the measurements unavailable. Actual in-Logic progress/completion was verified with unchanged parameters; CTests, real editor/backend integration, installed signatures and auval passed. Evidence: build/analyze-feedback-audit.json.
