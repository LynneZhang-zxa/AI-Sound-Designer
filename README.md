# Resonanca — AI Sound Designer

A macOS **C++/JUCE AU/VST3 synthesizer** with editable text-guided sound design and reference-WAV matching.

**Describe → review → Apply → listen → Undo.** Reference matching approximates one dry note using the synth's available controls. Human review stays in control.

![Actual JUCE editor proposal](assets/demo/proposal.png)

[16-second audio/video demonstration](assets/demo/resonanca-demo.mp4) · [Quick start](docs/quick-start.md) · [Architecture](docs/architecture.md) · [Release evidence and limits](docs/release-status.md)

The demonstration is assembled from actual test-editor snapshots and actual JUCE renders; it is labeled as an offline staged demonstration, not a Logic screen recording. Local rules are used in that video.

## What works

- Eight fixed-capacity voices, MIDI input, sine/saw/square/triangle, ADSR and a low-pass filter.
- Stable JUCE parameters, host automation and persistent synth state.
- Resizable proportional editor, with screen-aware initial size and a corner grip.
- Coordinated text proposals across the eight controls, strength selection, before/after review and one-step Undo. Manual/host edits invalidate stale proposals.
- Optional OpenAI structured interpretation through an external loopback Python service; clearly labeled deterministic local fallback.
- Background measurements and paired-render comparisons of the current synth patch.
- Reference WAV → bounded actual-JUCE render/search → seven editable timbral controls. Output gain is preserved. Internal spectrogram/envelope diagnostics are saved, not added to the plugin UI.

## Build and install

Validated on Apple Silicon/macOS with AppleClang, CMake 3.22+, JUCE **8.0.12**, AU and VST3. JUCE is pinned and fetched by CMake. Xcode command-line tools and network access for the first fetch are required. Intel/macOS builds are not claimed verified.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target AISoundDesigner_AU AISoundDesigner_VST3 DatasetRenderer SynthTests EditorTests -j4
ctest --test-dir build --output-on-failure
```

Save and normally quit Logic before installing:

```sh
bash scripts/install-development.sh
```

The installer refuses to replace a loaded plugin, verifies installed signatures and runs `auval`. It installs development/ad-hoc signed AU/VST3 into your user Library. It is not a notarized distribution installer. Reopen Logic and insert **AU Instruments → AI Sound Designer → AI Sound Designer → Stereo**.

## Optional analysis and AI services

Basic synthesis and local text rules need no Python service. For Analyze/Match, use **Python 3.12** (tested 3.12.9):

```sh
python3.12 -m venv ml/.venv
ml/.venv/bin/python -m pip install -r ml/training-requirements.txt
bash scripts/start-assistant.sh
```

The current external analysis process imports PyTorch even though default Match uses DSP search. No trained checkpoint or 3,000-example dataset is required for current Match/measurements; absent optional historical models are reported as unavailable. Large datasets/checkpoints are generated artifacts excluded from Git.

For Live AI, securely export `OPENAI_API_KEY` in the service terminal before starting that command. Keep that terminal open. Never paste keys into chat, source, plugin prompts or project state. `OPENAI_MODEL` optionally overrides the existing `gpt-4o-mini` default. Calls may incur provider charges. A changed AI worker can be explicitly replaced with `bash scripts/start-assistant.sh --restart-ai` in the same key-configured environment.

Services bind to `127.0.0.1`: prompt **8765**, analysis **8766**. Native-plugin requests carry structured parameters, not DAW audio. Reference audio/path is never sent to OpenAI. The Responses request uses strict structured output and `store:false`; see [official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

## Use the plugin

- **Propose changes:** try `更暖、更柔和，保留尾音` at Medium with Live AI off, or enable Live AI for broader language. Review the numbers and reasons before Apply. Undo restores the prior patch unless a newer manual/host change has occurred.
- **Analyze sound:** measures a standardized background MIDI-48 render of the current patch. It does not capture live audio or analyze the imported WAV. Progress and completed RMS/peak/centroid appear in the main status.
- **Match reference WAV:** select a dry isolated note, include its release tail, enter its known MIDI gate duration (note-on to note-off, **not file duration**) and use Auto pitch or a known note. Review, Apply and audition at the displayed pitch; Undo is available.
- **Resize:** drag the bottom-right diagonal grip. Logical size limits are 720×660 to 1440×1320; all sections scale together. UI size/conversation history are not part of saved synth parameters.

## Real-time boundary

The audio callback uses fixed eight-voice storage, cached atomic parameter reads and prepared DSP. Networking, Python, rendering subprocesses, feature extraction, file I/O and model work stay outside it. Apply uses JUCE host gestures on the message thread. Allocation checks cover exercised C++ `new` calls, not a system-wide allocator/lock proof. [Architecture and ownership](docs/architecture.md).

## ML results and engineering decision

The new controlled experiment generated **3,000 exact JUCE-labeled examples**, with train-only preprocessing, held-out test data, mean/DSP baselines and a shuffled-label control. A small PyTorch CNN predicts six continuous controls plus waveform; its test waveform accuracy was **95%**.

Under an equal **96 actual renders/reference**, CNN-seeded and DSP searches tied on all **16 synth + 8 independent** cases. The CNN is therefore **not deployed in default Match**. Parameter prediction improvement did not improve final reconstruction. Full physical-unit errors, unfavorable results and timing scope are retained in [MATCH_MODEL_RESULTS.md](ml/MATCH_MODEL_RESULTS.md), with a [frozen protocol](ml/MATCH_MODEL_PROTOCOL.md).

## Verification

```sh
bash scripts/check-release.sh
```

Default checks make no paid API calls. `bash scripts/check-release.sh --live` explicitly adds real OpenAI acceptance and requires the running key-configured service. Tests build actual processor/editor/renderer targets and exercise serialization, MIDI, DSP rates/blocks, proposal protections, resizing/input, HTTP contracts, pending-worker cancellation, features and Match boundaries.

One legacy browser-workbench test needs its historical checkpoint and explicitly skips when absent; core Match/Analyze remain testable without it. `ML_SKIP_LEGACY_MODEL_TESTS=1 bash scripts/check-release.sh` also exercises that model-absent analysis path. Old workbench tools remain optional.

Reproducible release reference checks: `ml/.venv/bin/python scripts/release-acceptance.py`. They save nine technical reference results and an audition page under `ml/runs/release_acceptance/`; the command refuses to overwrite an existing run. This is a controlled functional matrix, not a human listening score or arbitrary-recording benchmark.

## Limits

Match targets dry, stable, near-equal-tempered **single notes**, MIDI 36–84, 0.2–8-second WAVs and a known gate of 150–3000 ms. Chords, changing pitch, reverb, full songs and complex external synth topologies are outside its validated scope. Spectral/envelope distances are technical measures, not perceived similarity. Sine waves have little harmonic brightness to remove.

The synth has dual-mono output and no unison, stereo width, reverb, sustain-pedal/pitch-bend/MPE implementation. Waveform changes and voice stealing can click. Host CPU profiling, broad perceptual preference and distribution notarization are not claimed. The assistant reports unsupported requests rather than inventing effects.

No commits or pushes are performed by the assistant; repository review and Git publication remain with the project owner.
