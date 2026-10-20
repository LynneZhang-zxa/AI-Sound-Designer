# AI Sound Designer

An eight-voice C++/JUCE synthesizer with AU and VST3 builds, MIDI input, editable host parameters, and asynchronous AI-assisted sound design. The producer reviews proposals, listens, and chooses what to apply.

The canonical repository is `/Users/zhangxiai/Desktop/AI-Sound-Designer`.

## Implemented

- Fixed-capacity eight-voice MIDI engine with sample-position note dispatch and channel-aware note-off/all-notes-off/all-sound-off.
- Sine, PolyBLEP saw/square, and a Nyquist-limited additive triangle waveform.
- Per-voice ADSR; a shared resonant low-pass filter; 20 ms smoothing for cutoff, resonance, and output gain.
- Eight stable JUCE parameter IDs, host automation, normalized controls, and versioned state restoration.
- Separate processor, synth engine/voice, editor, background prompt worker, and external Python AI service.
- OpenAI Responses API interpreter with strict structured output. Service-side and plugin-side validation/clamping precede JUCE host notifications. Credentials never enter the plugin or its saved state.
- Deterministic local prompt rules for offline testing and service-failure fallback. Optional Apple on-device AI adapter.

## Build and test

Requirements: macOS, Xcode command-line tools, CMake 3.22+, Git, and internet for the first pinned JUCE 8.0.12 fetch.

```sh
cd /Users/zhangxiai/Desktop/AI-Sound-Designer
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --target AISoundDesigner_AU AISoundDesigner_VST3 SynthTests -j 4
ctest --test-dir build --output-on-failure
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s service -v
```

Built bundles are under `build/AISoundDesigner_artefacts/Release/AU/` and `build/AISoundDesigner_artefacts/Release/VST3/`. The default generator uses `build/SynthTests`; Xcode builds may place the test executable in a configuration subdirectory. Universal builds may be requested with `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"`; only native arm64 has been verified here.

Quit Logic before replacing an installed bundle. Install the build into the user plugin folders:

```sh
bash scripts/install-development.sh
```

Development bundles use ad-hoc signatures. The install script excludes Finder/iCloud metadata, refreshes and strictly verifies both installed signatures, and runs `auval`; generated bundles on an iCloud-synced Desktop can reacquire cosmetic metadata after a build. Distribution signing/notarization is outside this milestone. Keep bundle ID `com.aisounddesigner.synth`, manufacturer `Aisd`, and plugin code `Asd1` stable.

## OpenAI service

The Python service uses the standard library; no framework installation is required. It listens only on loopback. Set `OPENAI_API_KEY` in the service terminal environment, using a secure local entry mechanism rather than adding it to a source file, command history, or plugin project. Then run:

```sh
cd /Users/zhangxiai/Desktop/AI-Sound-Designer
python3 service/server.py --provider openai
```

`OPENAI_MODEL` optionally selects a compatible model; the configurable initial default is `gpt-4o-mini`. The service calls `https://api.openai.com/v1/responses` with a strict JSON schema and `store: false`. It sends only the producer prompt and eight parameter values, never audio. Model access, API billing, and credentials belong to the service environment. [Official Structured Outputs documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

In the plugin, enable **Use AI service (prompt + parameters)**, enter a prompt, and click **Propose**. Inspect the clamped parameter proposal and click **Apply proposal**. Changes use JUCE parameter gestures and host notifications; all controls remain editable. Disable AI mode to use the local rule baseline. Connection/provider failures automatically produce a clearly identified rule fallback. Malformed successful responses are rejected. Unsupported local-rule prompts propose no changes.

Example prompts: “darker”, “shorter”, “warmer”, “brighter”, or “darker and shorter while preserving attack”. Local rules deliberately recognize only the simple terms and do not understand general language or negation. The AI mode is intended for broader phrasing; it still requires human review.

The service request has a bounded response size, provider timeout, and no automatic paid retries. The editor can cancel its worker's network stream when closing. A proposal reflects the parameter snapshot at submission; inspect it if you edited controls while waiting.

For an optional credential-free model on a compatible Mac with Apple Intelligence enabled:

```sh
cmake --build build --target LocalAIModel
python3 service/server.py --provider apple
```

The helper requires macOS 26+ and a suitable Xcode SDK; the core plugin does not depend on it. With either live service running, `build/SynthTests --service` exercises the actual C++ worker → HTTP → model → validation → JUCE update path while rendering continues. A fallback fails this live-model test rather than being counted as AI success.

## Parameters

| Stable ID | Native range | Default |
| --- | --- | --- |
| `waveform` | 0 sine, 1 saw, 2 square, 3 triangle | 0 |
| `attack` | 0.001–5 s | 0.005 |
| `decay` | 0.005–5 s | 0.1 |
| `sustain` | 0–1 | 0.8 |
| `release` | 0.005–8 s | 0.15 |
| `cutoff` | 20–20,000 Hz | 12,000 |
| `resonance` | 0.5–2 Q | 0.707 |
| `gain` | 0–1 | 0.8 |

Time and frequency controls have skewed normalization. DSP cutoff is capped at 45% of the host sample rate. Notes at or above 49% of sample rate are suppressed. XML state version 2 contains only synth parameters; prompts, service selection, credentials, active notes, and filter history are excluded. Invalid/incomplete state is ignored. The original version-1 marker contained no editable values and remains a no-op when loaded.

## Verification and remaining host checks

See [verification notes](docs/verification.md) for evidence and the Logic checklist, and [architecture](docs/architecture.md) for thread ownership and real-time constraints.

AU/VST3 compilation, automated processor tests, service tests, Apple AU validation, and an actual local Apple-model integration test have passed. Live OpenAI inference and AI-driven parameter changes in Logic have also passed through the user-configured service. State restoration after a full Logic quit/relaunch also passed. On 2026-10-20, the user manually verified MIDI-driven audio and recorded parameter automation during playback in Logic, and confirmed state restoration and live OpenAI changes. The four core Logic acceptance checks are complete. The keyboard-focus correction has been rebuilt, installed with Logic closed, and AU-validated; a direct typing check and the extended regression checklist remain separate follow-up checks.

Known limitations: dual-mono stereo output, no sustain pedal/pitch bend/MPE, no effects beyond the low-pass filter, block-level parameter snapshots, immediate waveform changes, and round-robin voice stealing that can click. Callback allocation instrumentation observes C++ `new` calls in the tested render path; it does not replace a system-wide allocator/lock profiler. Host CPU usage and perceptual quality have not been measured.
