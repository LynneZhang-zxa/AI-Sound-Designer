# Quick start and demo

1. Build/install using README; quit Logic normally before replacement.
2. Start `bash scripts/start-assistant.sh` from the canonical repository and keep the terminal open. Basic synth/local rules work without this. Analyze/Match need the external analysis worker; Live AI additionally needs its key-configured prompt worker.
3. In a separate Logic project, add a software instrument and insert AI Sound Designer. Loop the same MIDI phrase while comparing sounds.
4. Try `更暖、更柔和，保留尾音` at Medium, review the coordinated values, Apply, then Undo. `更暗，保留起音，保留尾音` should retain those explicit controls. Numeric English units are supported offline; broader intent understanding requires Live AI.
5. Analyze sound reports a standardized current-patch render at MIDI 48; it does not listen to your microphone or imported reference. It deliberately leaves sound unchanged.
6. Match a dry isolated WAV with its complete tail. Gate ms is the musician's held note time. For the saved ES1 example, use `ml/references/logic_es1/ES1Warm.wav`, gate 1400 ms and Auto pitch (expected MIDI 72). Review/Apply and play MIDI 72; Undo restores your patch.
7. Save, close and reopen the test project to verify your own host setup. Prompt history, service toggles and window dimensions are editor-local; synth parameter values are saved.

## Listen before judging

Use `ml/runs/release_acceptance/index.html` after running the reference matrix for eight distinct bass/pluck/pad/soft-note pairs. Those playback copies have held-window RMS alignment; they are not LUFS matched. Source WAVs remain unchanged. Compare harmonic color, onset and tail separately rather than judging by level alone. They are independent SciPy fixtures, not new Logic recordings. The existing real ES1 reference is separately identified in results.

`assets/demo/resonanca-demo.mp4` is a 16-second staged demonstration using genuine JUCE editor states and matching renderer audio: Before / Preview / Apply / Undo. Preview and Undo use exactly the original audio. Reproduce with `ml/.venv/bin/python scripts/prepare-demo.py`; this requires Swift/AVFoundation and current test/renderer targets. It is not a Logic screen recording or a live OpenAI demonstration.

## Troubleshooting

- **No MIDI audio:** check the instrument track, MIDI region, output routing, plugin power and gain. Propose alone does not apply anything.
- **Analyze appears inactive:** it should show Analyzing then Analysis ready in the main status. Check `http://127.0.0.1:8766/health`; it measures the current synth, not a file.
- **Match gate error:** enter note-on → note-off duration shorter than the WAV's full release-inclusive duration. A 1-second WAV cannot support a 1.4-second held note plus release.
- **ML unavailable:** optional saved research models are absent/outside trained conditions; measurements and default DSP Match remain available.
- **Service port occupied/old worker:** reuse only recognized current workers. Stop an old analysis worker normally in its own terminal before restarting. Do not launch duplicates or terminate an unrelated process.
- **Live AI fallback:** it is labeled local rules and is not proof of OpenAI success. Check 8765 health/configuration and provider access. Do not paste a key into the plugin or chat.
- **Subtle darkening on sine:** there are few upper partials to remove. Lower cutoff can mostly alter level; changing waveform also changes identity and should be reviewed.
- **Native drag automation:** UI geometry/hit tests cover supported sizes, and the installed resize grip is visible in Logic. Computer Use's native drag previously failed at the tool layer; manual physical dragging is a separate host check.
