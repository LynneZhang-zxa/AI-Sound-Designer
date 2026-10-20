# AI Sound Designer — v0.1

First milestone: build an AU instrument, pass Apple's AU validation, and load/play it in Logic Pro. VST3 is built alongside AU for other hosts.

## Architecture

- `CMakeLists.txt`: pinned JUCE 8.0.12 dependency via FetchContent, plugin identity, and AU/VST3 targets. No Projucer step. First configure requires internet access and Git. JUCE is downloaded inside the ignored build directory.
- `plugin/Source/PluginProcessor.*`: stereo output, no audio inputs, host MIDI input, lifecycle, editor creation, and a versioned state marker.
- `plugin/Source/PluginEditor.*`: fixed-size informational editor on the message thread. No timers or shared DSP state.
- `plugin/Source/synth/SynthEngine.*`: eight fixed voices, sample-position MIDI dispatch, free-voice selection, and round-robin stealing when full.
- `plugin/Source/synth/SynthVoice.*`: sine oscillator, velocity gain, and fixed ADSR. All voices produce the same signal in both output channels.

Voice storage exists before playback. The audio path reads existing MIDI bytes and uses stack/local arithmetic and preallocated voices, with no allocations, I/O, logging, locks, or message-thread access. Prepare/release calls require host playback to be stopped. No custom workers exist.

There are no editable parameters or presets yet. State writes a version marker; loading state intentionally has no audible effect because there is nothing editable to restore. MIDI note-on/off (including zero-velocity note-on), channels, all-notes-off, and all-sound-off are supported. Sustain pedal, pitch bend, modulation, MPE, and double-precision processing are not implemented. Forced voice stealing can click; improving that is a later DSP task. This is an audible host-loading scaffold, not a finished synth.

Keep the bundle ID and four-character manufacturer/plugin codes stable after host projects start using the plugin. Current identity: `com.aisounddesigner.synth`, manufacturer `Aisd`, plugin `Asd1`; AU type `aumu`.

## Build on macOS

Requirements: full Xcode with its command-line tools selected, Git, and CMake 3.22 or newer on PATH. Open Xcode once to finish its setup and accept its license if prompted. Install CMake from https://cmake.org/download/ (the macOS app includes a command-line setup option), or use `brew install cmake` if you already use Homebrew.

Check prerequisites:

```sh
xcode-select -p
xcrun clang++ --version
cmake --version
git --version
```

Run from the repository root:

```sh
cmake -S . -B build -G Xcode -DCMAKE_OSX_ARCHITECTURES=arm64
cmake --build build --config Release --target AISoundDesigner_AU AISoundDesigner_VST3 --parallel 4
```

On an Intel Mac, use `-DCMAKE_OSX_ARCHITECTURES=x86_64`. For both native and Rosetta hosts, configure with `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"` instead. Build for the architecture used by your Logic process. When changing generators, use a separate build directory.

Expected bundles:

```text
build/AISoundDesigner_artefacts/Release/AU/AI Sound Designer.component
build/AISoundDesigner_artefacts/Release/VST3/AI Sound Designer.vst3
```

Builds do not automatically install plugins. Quit Logic before installing or replacing the AU. These commands install into your user's plugin folders; repeat after each rebuild:

```sh
mkdir -p "$HOME/Library/Audio/Plug-Ins/Components" "$HOME/Library/Audio/Plug-Ins/VST3"
ditto "build/AISoundDesigner_artefacts/Release/AU/AI Sound Designer.component" "$HOME/Library/Audio/Plug-Ins/Components/AI Sound Designer.component"
ditto "build/AISoundDesigner_artefacts/Release/VST3/AI Sound Designer.vst3" "$HOME/Library/Audio/Plug-Ins/VST3/AI Sound Designer.vst3"
```

These instructions are for local development. Distribution signing/notarization is outside this milestone.

## Validate and load in Logic

1. After installing, list registered AUs and validate this instrument:

   ```sh
   auval -a
   auval -v aumu Asd1 Aisd
   ```

   Look for AI Sound Designer in the list and `AU VALIDATION SUCCEEDED` from validation. If the AU is not listed, restart the Mac and retry before changing anything else.

2. Open Logic Pro → Settings → Plug-in Manager. Find **AI Sound Designer** under manufacturer **AI Sound Designer**. Confirm validation passed and Use is enabled. If listed but unavailable or previously failed, select it and choose **Reset & Rescan Selection**; inspect the validation output if it still fails.
3. Create a **Software Instrument** track. In its **Instrument** slot choose **AU Instruments → AI Sound Designer → AI Sound Designer → Stereo**. Logic uses the AU build; the VST3 build is for VST3 hosts.
4. Confirm the editor opens. Play MIDI notes or open Musical Typing with Command-K. Confirm quiet sine tones, chords, and a short release after note-off.
5. Stop playback, close/reopen the editor, save/reopen the Logic project, and verify it still loads and plays. Try 44.1 and 48 kHz projects and repeated transport start/stop. Check silence after notes release.

The milestone is complete only after AU validation and this Logic loading/playback check pass.

References: [JUCE CMake API](https://github.com/juce-framework/JUCE/blob/8.0.12/docs/CMake%20API.md), [Apple Plug-in Manager guide](https://support.apple.com/en-au/guide/logicpro/lgcp9e26ef17/mac), [Apple missing-plugin troubleshooting](https://support.apple.com/en-ca/122179).

## Verification status

Scaffold source reviewed and whitespace checked. Configure was attempted in the initial environment but stopped at `cmake: command not found`. Neither compilation, AU validation, nor loading in Logic has been verified yet.
