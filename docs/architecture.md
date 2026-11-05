# Architecture and ownership

```mermaid
flowchart LR
    MIDI[Host MIDI] --> Processor[Plugin processor]
    Host[Host automation / restored state] --> Params[JUCE APVTS parameters]
    UI[Editor controls] --> Params
    UI --> Worker[Prompt worker]
    Worker --> Service[Loopback Python service]
    Service --> OpenAI[OpenAI Responses API]
    Service --> Apple[Optional local Apple helper]
    Worker --> Proposal[Validated and clamped proposal]
    Proposal --> Human[Producer chooses Apply]
    Human --> Params
    Params --> Snapshot[Cached atomic reads]
    Snapshot --> Engine[Fixed eight-voice engine]
    Processor --> Engine
    Engine --> Filter[Smoothed low-pass and gain]
    Filter --> Audio[Host audio]
```

## Audio thread

`processBlock` clears the existing output buffer, loads eight cached lock-free float atomics into a plain settings snapshot, updates prepared DSP, dispatches existing MIDI bytes at sample offsets, and renders fixed voices and a shared filter. MIDI bytes are inspected directly to avoid allocating JUCE SysEx messages. The callback does not access APVTS trees, strings, editor state, worker mutexes, Python, HTTP, models, or disk.

Voice storage is `std::array<SynthVoice, 8>`. Oscillator/envelope state belongs to each voice; filter and smoothing state belong to the engine. Prepare allocates the JUCE filter's storage and initializes sample-rate-dependent objects before playback. A compile-time assertion requires lock-free float atomics. Float rendering is supported; double precision is not advertised.

Saw and pulse discontinuities use PolyBLEP correction; triangle uses up to 16 odd harmonics below Nyquist. Gain reserves polyphonic/filter headroom. Filter cutoff, resonance, and output gain ramp over 20 ms; waveform and envelope parameter snapshots update per block. A shared post-mix filter is the smallest architecture needed for this milestone; a separate filter per voice is not required for the present behavior.

## Message thread and host state callbacks

The editor owns resizable JUCE parameter controls, prompt input, proposal display, and an optional prompt worker. It snapshots parameter atomics before submitting a request. A 10 Hz UI timer retrieves worker results; all proposal sanitization and parameter host gestures occur here. The audio thread never takes the worker mutex.

Proposal validation rejects unknown IDs, booleans, strings, empty objects, and nonfinite values. Finite values are clamped to native ranges and choices are snapped. All fields are validated before applying the first field. Multi-parameter host updates remain sequential independent JUCE parameters, rather than an atomic preset transaction.

APVTS state copy/replace and XML serialization belong to host state callbacks outside the render function. Version/type/required IDs/native values are checked before replacing state. UI configuration and credentials are separate from persistent DSP parameters.

## Worker and external service

The editor's worker performs request serialization and HTTP to `127.0.0.1:8765/propose`. Its mutex protects only request/result strings and the cancellable stream pointer. Closing the editor signals exit, cancels an active stream, and joins the worker on the message thread. The processor/audio thread does not own this worker.

The external Python process validates the complete snapshot and sends an OpenAI Responses request with structured output. The API key is read from its environment. It bounds input/output size and timeouts, rejects malformed/incomplete output and duplicate IDs, and clamps legitimate parameter proposals. No API key, network request, inference, or Python code runs in the plugin callback. The optional Swift helper runs Apple's available on-device model in a separate process.

AI failure falls back to a deterministic local rule proposal, clearly labeled as such. A fallback is never treated as a passing live AI test. Human review remains necessary for semantic mistakes, stale snapshots, and musical quality.

## Assistant, analysis and Match boundary

Text input includes current parameters, recent applied/undone editor turns and optional fresh descriptors. The current producer request is explicitly separated from historical context. OpenAI produces a sparse structured proposal; local rules provide a bounded state-aware coordinated baseline. Direct explicit waveform commands and common preservation directives are enforced before final validation/strength scaling. The producer reviews actual parameter values, then applies or undoes through host gestures.

Four editor-owned workers handle prompt, read-only analysis, reference matching and paired-render comparison. Workers serialize requests and return results; they do not touch live DSP. Request snapshots and comparison IDs prevent stale results from replacing newer values. Closing an active worker cancels its stream and joins outside the audio thread; the pending-response cancellation regression exercises this against a deliberately blocked fixture server while DSP continues.

The local analysis process renders current-patch/paired snapshots through DatasetRenderer, measures raw RMS/peak and held-note spectral characteristics, and returns descriptive values. It is separate from live host audio. Optional legacy inverse-model estimates are explicitly unavailable when outside their domain or missing checkpoints.

Default reference Match uses pitch/envelope measurements and bounded actual-JUCE search over seven existing timbral controls. Its technical objective uses salience-weighted log-mel power plus envelope distance. Reference and reconstruction comparison representations are RMS aligned; plugin output gain is preserved. Shared-scale spectrogram/envelope diagnostics remain internal. The old objective/experiments and current search are separately identified.

The offline seven-control CNN experiment predicts six normalized continuous targets and waveform. It uses procedural exact-label JUCE data, train-only feature statistics, mean/DSP/shuffled baselines and once-only selected-checkpoint test evaluation. At an equal actual render budget its initialized search tied DSP on all 24 cases; default Match does not load that model. PyTorch is currently an external-process dependency, never an audio-thread dependency.

No technical score is treated as listening preference. Source/renderer/config/data identities, failure observations and measured limitations are retained. See release-status.md for current acceptance, and ml/MATCH_MODEL_RESULTS.md for full experiment results.
