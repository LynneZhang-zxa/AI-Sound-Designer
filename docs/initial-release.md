# Initial assistant build — 2026-10-28

> Historical evidence log. Current consolidated delivery status: [release-status.md](release-status.md).


The repaired AU/VST3 are installed, signature-verified and auval-validated. Actual Logic Live AI preview, Apply and Undo passed. This is an initial editable sound-design assistant, not an exact preset-cloning system. No commit or push was made.

## Available workflow

- The existing eight-voice MIDI synth, eight stable parameter IDs, DSP and state format remain unchanged.
- Text can propose waveform, cutoff, resonance, gain and all ADSR controls. Review shows native units and waveform names. Apply uses JUCE host gestures; one-step Undo restores the assistant change. Later host/manual edits invalidate stale proposals and undo.
- OpenAI runs through the external local service, with strict structured output, validation/clamping, explanation and unsupported-feature reporting. Four recent applied/undone turns provide editor-local follow-up context. Current parameters remain authoritative. History is not serialized.
- Deterministic English/Chinese local rules remain available offline and are explicitly labeled. Unsupported numeric units and overflow are rejected. Unambiguous explicit waveform requests are resolved before review so a missing/wrong model waveform does not silently defeat a direct selection; negated or ambiguous requests are not completed.
- Optional fresh Analyze measurements describe a standardized offline render. No reference WAV/path is sent to OpenAI. Networking, rendering/search, Python and feature extraction stay outside the audio callback.
- Reference matcher v2 searches waveform, filter and four envelope controls with actual JUCE renders. Output gain is preserved. Choose a dry isolated note and supply MIDI gate duration. Review before Apply, then refine with text.
- Existing ML experiments remain frozen/offline. Controlled comparisons did not establish a CNN advantage over DSP, so the CNN was not deployed. No new training or ONNX integration was added.

## Verified evidence

All paths below are relative to the canonical repository.

| Check | Result | Evidence |
|---|---|---|
| Repaired AU/VST3 build | Passed | build/explicit-waveform-build.log |
| C++ synth/editor regressions | 2/2 passed | build/explicit-waveform-tests.log |
| Offline Python/ML tools | 33 passed | build/initial-release-ml-tests.log |
| Provider/HTTP/launcher/C++ transport contracts | 12 passed | build/initial-release-service-tests.log |
| Installed AU/VST3 signatures and auval | Passed | build/explicit-waveform-install.log; build/auval.log |
| Actual OpenAI worker while DSP renders | Passed, no fallback | build/initial-release-live-ai.log |
| JUCE editor live eight-parameter Apply/Undo/staleness | Passed, no fallback | build/initial-release-live-editor.log |
| Actual C++ reference request, Apply and restore | Passed | build/initial-release-reference-client.log |
| Exercised callback allocations | Zero detected; not an exhaustive host proof | SynthTests output |
| Actual Logic Chinese Live AI waveform request | Preview Square → Sine; Apply Sine; Undo Square | Host accessibility observations, then final Sine applied |
| Current installed Logic MIDI playback | Playhead advanced; Inst 1 and Stereo Out had nonzero meters, observed -29.2 then -24.2 dB without clipping indication | 2026-10-28 host accessibility observations |
| Existing Logic volume automation | Track fader moved during playback, observed +0.8 then +1.8 dB | Host accessibility observations; this is channel-volume automation, not a fresh plugin-parameter automation test |
| Save/reopen after newest repair | Save requested; project data timestamp updated; reopen not completed | Logic UI repeatedly timed out after Close Project |
| Actual Logic reference file chooser workflow | Not completed this session | File chooser connection failed; C++ service integration above passed |
| Perceptual reference match approval | Pending | No human preference win claimed |

Earlier v0.1 MIDI, plugin automation and relaunch restoration were manually verified by the user. They are separate from the narrower current host checks. Output meters establish host signal activity, not a listening-quality judgment. No forced quit or replacement of a loaded plugin was performed when Logic became unresponsive.

## Run

The current repaired plugin is already installed. Keep the existing assistant terminal open. For later sessions, from the canonical repository:

```sh
bash scripts/start-assistant.sh
```

This reuses recognized healthy local workers: analysis on 8766, OpenAI on 8765. A new OpenAI worker requires OPENAI_API_KEY exported securely in that terminal. Never put keys in chat, Git, plugin prompts or project state. If intentionally replacing an existing AI worker after configuration/code changes, use `bash scripts/start-assistant.sh --restart-ai`; the launcher checks process identity and caller key presence before normal termination. No automatic paid retries.

Only if reinstalling a future build, save and normally quit Logic first, then run `bash scripts/install-development.sh`. The installer refuses while Logic is open, verifies installed signatures and runs auval.

At Medium strength, try `换成正弦波，attack 设为 300 ms，release 设为 1.2 秒，音量降到 40%。` with Live AI enabled. Review, Apply, play MIDI and Undo. Existing controls cannot provide reverb, stereo width, unison or LFO; the service reports unsupported requests rather than claiming those effects exist.

## Reference matching limits and listening

Open `ml/runs/initial_release_listening/index.html` for common-window RMS-matched mono Reference/Previous/New comparisons of the existing Logic ES1 development recording. This is not an untouched test case or blinded preference experiment.

Under the same v2 technical objective, previous patch 1.7217783372628326 → new patch 1.4076618187798566; envelope RMSE .1478223119156854 → .038692837769691076. The measured search used 135 renders in 1.9049311670241877 seconds on this machine, outside the callback. These scores cannot be compared numerically to legacy-objective scores. Centroid moved 533.2663042508659 → 531.6522425033352 Hz versus reference 529.3164745091765 Hz; high-frequency power above 2 kHz remains greater than the reference. Brightness is not claimed solved.

Matching produces an editable starting patch within this synth's limited architecture. It does not recover arbitrary external synth parameters, handle full songs/chords/reverberant audio reliably, or guarantee perceived similarity. Remaining host gates are reopening the saved newest-repair state and completing the native reference chooser → review → Apply → Undo sequence when Logic's UI connection responds.

## Final background transport check

The current running reference service was checked again through the real C++ asynchronous client using `ml/runs/reference_match_demo/independent_reference.wav`, whose known 800 ms gate matches the harness. Pre-Apply immutability, validated apply/restore and DSP regressions passed (`build/final-reference-service-check.log`). This is separate from native file chooser acceptance. A short read-only Logic thread sample showed its main thread in the normal AppKit event loop, rather than an observed plugin shutdown wait (`build/logic-close-diagnostic.txt`). Rebuilding the CUA session still timed out; the cause of that UI connection failure is not established.

## Current environment revalidation — 2026-11-03

The canonical AU/VST3 and both C++ test targets rebuilt successfully. CTest passed 2/2; the local service contract suite passed 12 tests, with no paid API requests (`build/revalidation-2026-11-03-*.log`). Analysis service 8766 is healthy, but prompt service 8765 is unreachable. The installed AU has the same bundle/version/AU identifiers but a different Mach-O UUID and executable size from the canonical build; the user reports no intentional reinstall. Its origin is unresolved. Historical installed-host evidence above does not verify this currently installed binary. Logic is running, and this session has no desktop-control tool. No installed bundle was overwritten. Next installation requires normal host exit; preserve the existing bundles before replacement.

## Canonical installation restored — 2026-11-03

After the user confirmed normal Logic exit, the canonical AU/VST3 installed successfully. Both installed executable SHA-256 values exactly match the canonical build executables; installed signature verification and auval passed (`build/revalidation-2026-11-03-install.log`, `build/auval.log`). The replaced versions are preserved with file hashes under `build/installed-backups/20261103-144128/`. This resolves the installed-version mismatch above without attributing its unknown origin. Reopening the saved Logic test project and completing the native reference chooser/review/apply/undo remain unverified for this installation. Prompt service 8765 was unavailable at the last check; analysis service 8766 was healthy.

## Final host acceptance — 2026-11-03 (supersedes earlier pending host gates)

Computer Use became callable again. The saved canonical LogicVerification project was opened after restarting Logic, and the actual plugin UI restored Sine, cutoff 2.69 kHz, resonance .707 Q, attack 300 ms, decay 100 ms, sustain 80%, release 1.20 s and gain 40%. Editor-only conversation/Live AI toggle correctly reset rather than becoming DSP state.

The original native reference picker again produced no usable file window in this host session. Its exact underlying OS cause is not established. The chooser now uses JUCE's editor-owned file dialog (`useOSNativeDialogBox=false`, parent editor), avoiding a detached native panel. This affects file selection on the message thread only. AU/VST3 rebuilt; CTest passed 2/2; normal Save/Quit, installation, signature checks and auval passed (`build/reference-picker-{build,tests,install}.log`, `build/auval.log`).

Actual in-Logic acceptance of the repaired picker passed: selected `ml/references/logic_es1/ES1Warm.wav`, Gate 1400 ms, Auto pitch. The proposal displayed MIDI 72 and score 4.621 → 1.315 (rounded UI display, this run starts from the saved Sine patch; not directly the previous development-run result). Before Apply, all eight current controls remained unchanged. Apply produced Saw, cutoff 500 Hz, resonance 1.307 Q, attack 57.0 ms, decay 150 ms, sustain 61.4%, release 406.1 ms; gain stayed 40%. Undo restored every original displayed parameter. The test project is left open with its original Sine settings restored. This is host workflow evidence, not a claim of heard similarity or a new perceptual preference result.

The initial implementation and remaining host workflow gates are now verified. The known ES1 brightness difference and limited synth topology remain explicit product limits. Prior actual live OpenAI verification is historical; the 8765 service was unavailable at the latest health check and must run to use Live AI now. Local rules and the local reference matcher remain separate, usable paths. No new training, plugin DSP changes, parameter-ID/state-format changes, commit or push was performed.
