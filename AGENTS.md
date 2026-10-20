# AGENTS.md

## Project

**AI Sound Designer**

A JUCE-based AU/VST3 audio plugin that combines real-time DSP, structured sound parameters, audio analysis, and eventually human-in-the-loop AI-assisted sound design.

The long-term goal is:

**text intent + audio context + human feedback → editable synthesizer/effect parameters**

This is intended to be a serious portfolio project for Audio Software, DSP, Creative Tools, Applied ML, and SWE internships.

The project must demonstrate real engineering depth and must not become a thin LLM wrapper.

---

# Core Product Philosophy

The system follows:

**AI proposes → human listens → human chooses → AI adapts**

The AI assists musicians instead of replacing creative control.

Example interaction:

A producer asks:

> Make this pluck darker and warmer while preserving the transient. Make it wider but keep it out of the vocal's way.

The system should eventually reason over structured synth/effect parameters such as:

- oscillator configuration
- filter cutoff
- resonance
- ADSR
- filter envelope
- LFO
- unison
- detune
- stereo width
- saturation
- EQ
- delay
- reverb
- modulation

The result should remain fully editable by the producer.

---

# Current Priority

Do not attempt to build the complete AI system immediately.

The current priority is:

## v0.1 — Stable JUCE Synth Plugin

Build a reliable synthesizer that:

- builds successfully
- loads inside Logic Pro
- supports AU and preferably VST3
- accepts MIDI input
- produces stable audio
- exposes parameters through JUCE
- saves/restores plugin state correctly
- follows real-time audio safety rules
- has a clean architecture that later AI systems can control

Do not introduce ML until the basic DSP engine and parameter architecture are stable.

---

# Engineering Priorities

When choosing between approaches, optimize in this order:

1. Correctness
2. Real-time safety
3. Simplicity
4. Maintainability
5. Testability
6. Performance
7. Extensibility
8. UI polish

Avoid premature abstraction.

Avoid designing systems for hypothetical requirements that do not yet exist.

Prefer the simplest architecture that supports the current milestone cleanly.

---

# Technology

Primary stack:

- C++
- JUCE
- CMake
- AU
- VST3

Later components may use:

- Python
- PyTorch
- NumPy
- librosa
- ONNX / ONNX Runtime

Python and ML code must remain separated from hard real-time DSP code unless there is a technically justified deployment architecture.

---

# Real-Time Audio Rules

Treat the audio callback as hard real-time code.

Never perform the following inside `processBlock()` or equivalent real-time audio paths:

- heap allocation
- filesystem I/O
- network calls
- HTTP/API requests
- LLM calls
- Python execution
- blocking mutex acquisition
- waiting on threads
- logging to disk
- model loading
- slow initialization
- unpredictable ML inference
- destruction of large objects
- expensive formatting/string operations

Do not use code in the audio callback whose execution time is unpredictable.

Where possible:

- allocate memory during initialization
- prepare DSP objects in `prepareToPlay()`
- use lock-free or atomic communication
- pass parameter values efficiently
- move expensive work to background threads
- keep the audio thread deterministic

When reviewing or adding code, explicitly identify thread ownership when relevant.

Important thread categories:

- audio thread
- message/UI thread
- background worker
- future ML inference thread

Never casually share mutable state across these threads.

---

# Parameter Architecture

Parameters are a core part of the project.

They will eventually serve as the interface between:

**AI / search system → synthesizer**

Therefore:

- use JUCE parameter infrastructure where appropriate
- parameters must have explicit ranges
- use sensible normalization
- keep parameter IDs stable
- avoid hard-coded magic numbers scattered throughout DSP code
- keep UI state separate from DSP state
- support plugin state serialization
- ensure automation behaves correctly

Examples of possible parameters:

- oscillator waveform
- oscillator level
- oscillator detune
- filter cutoff
- filter resonance
- attack
- decay
- sustain
- release
- filter envelope amount
- LFO rate
- LFO depth
- unison voices
- stereo width

Do not add large numbers of parameters simply to make the synth appear complex.

Every parameter should have a clear musical purpose.

---

# DSP Development Rules

Implement DSP incrementally.

Preferred order:

1. MIDI note handling
2. oscillator
3. ADSR
4. polyphony
5. filter
6. parameter smoothing
7. modulation
8. unison
9. saturation/effects

Each stage should remain usable before the next stage is added.

Always consider:

- aliasing
- clipping
- gain staging
- denormals
- parameter smoothing
- sample-rate independence
- channel configuration
- voice lifecycle
- CPU cost

Do not introduce sophisticated DSP algorithms unless their benefit can be explained.

When implementing DSP, explain non-obvious mathematical or audio concepts in comments only when the comments improve maintainability.

Avoid tutorial-style comments on obvious C++ syntax.

---

# Architecture

Prefer clear boundaries such as:

- plugin processor
- plugin editor
- synth engine
- synth voice
- synth sound
- DSP modules
- parameter management
- future analysis layer
- future AI/search layer

Do not place all DSP directly inside `PluginProcessor`.

Do not allow UI code to directly implement audio behavior.

The audio engine should be testable independently where practical.

Future AI components should control the synth through a structured parameter interface rather than directly manipulating arbitrary implementation details.

---

# Suggested Repository Structure

```text
ai-sound-designer/
├── AGENTS.md
├── README.md
├── CMakeLists.txt
├── plugin/
│   ├── Source/
│   │   ├── PluginProcessor.cpp
│   │   ├── PluginProcessor.h
│   │   ├── PluginEditor.cpp
│   │   ├── PluginEditor.h
│   │   ├── synth/
│   │   │   ├── SynthEngine.cpp
│   │   │   ├── SynthEngine.h
│   │   │   ├── SynthVoice.cpp
│   │   │   └── SynthVoice.h
│   │   └── dsp/
│   │       ├── Oscillator.cpp
│   │       ├── Oscillator.h
│   │       ├── Filter.cpp
│   │       └── Filter.h
│   └── tests/
├── ml/
│   ├── README.md
│   ├── datasets/
│   ├── models/
│   └── experiments/
├── scripts/
├── tests/
├── docs/
│   ├── architecture.md
│   └── milestones.md
└── assets/
```

This structure is a guideline, not a requirement.

Do not create empty abstractions or directories until they are useful.

---

# Testing

Add tests where they provide real value.

Prioritize testing for:

- parameter serialization
- parameter ranges
- state restoration
- deterministic DSP utilities
- audio feature extraction
- dataset generation
- future ML preprocessing

Do not force unit tests onto code where the framework makes them artificially complex and low-value.

When fixing a bug, add a regression test where practical.

---

# Code Quality

Use modern, readable C++.

Prefer:

- RAII
- clear ownership
- `std::unique_ptr` where ownership is exclusive
- `std::array` / `std::vector` where appropriate
- `const` correctness
- small focused functions
- explicit types when clarity improves

Avoid:

- unnecessary raw owning pointers
- global mutable state
- giant classes
- premature templates
- clever metaprogramming
- unexplained macros
- duplicated DSP logic

Do not refactor unrelated code while implementing a focused feature unless the refactor is necessary.

---

# How Codex Should Work

Before making substantial changes:

1. Inspect the relevant existing code.
2. Understand the current architecture.
3. Identify the smallest correct change.
4. Preserve existing behavior unless change is intentional.
5. Consider real-time audio implications.
6. Consider parameter/state compatibility.
7. Implement the change.
8. Build or test where possible.
9. Explain significant design decisions.

Do not rewrite large parts of the project simply because another architecture appears cleaner.

Prefer incremental changes.

---

# Scope Control

Every proposed feature should conceptually fall into one of:

- MVP
- Important later
- Nice-to-have
- Research exploration
- Do not build yet

Current MVP features have priority.

Examples:

### MVP
- plugin loads in Logic
- MIDI input
- polyphonic synth
- oscillator
- ADSR
- filter
- parameter controls
- state save/restore
- stable playback

### Important later
- LFO
- unison
- saturation
- delay/reverb
- preset management
- audio feature extraction

### Research exploration
- audio → synth parameter prediction
- text-conditioned parameter generation
- CLAP/audio embeddings
- preference learning
- Bayesian optimization
- inverse synthesis

### Do not build yet
- large generative audio model
- DAW-wide autonomous agent
- automatic full-song mixing
- custom foundation model
- distributed ML infrastructure

Protect the project from scope creep.

---

# AI / ML Rules

Do not add machine learning merely to make the project sound more advanced.

Whenever proposing an ML component, define:

- problem formulation
- input
- target/output
- dataset
- labels
- model
- loss
- baseline
- evaluation metric
- inference latency
- deployment architecture

Always compare ML against simpler baselines.

Possible baselines include:

- deterministic parameter mapping
- nearest-neighbor search
- random search
- grid search
- optimization algorithms

ML should outperform or meaningfully improve upon a simpler approach.

---

# Future Dataset Strategy

A likely future approach is procedural synth-data generation.

Example:

```text
sample parameter vector θ
        ↓
render synth audio
        ↓
save audio + θ
        ↓
train model:
audio → θ
```

When this begins, carefully handle:

- parameter distribution
- normalization
- train/validation/test separation
- duplicated sounds
- perceptual equivalence
- identifiability
- dataset size
- rendering consistency
- data leakage

A predicted parameter vector is not automatically good just because its numeric error is low.

Sound similarity and perceptual quality must also be evaluated.

---

# Human-in-the-Loop Direction

The long-term differentiator is human preference.

Potential interaction:

```text
generate candidate A
generate candidate B
generate candidate C

        ↓

producer listens

        ↓

producer selects B

        ↓

producer says:
"less bright and slightly shorter"

        ↓

generate next candidates
```

Possible future methods:

- structured parameter adjustment
- local search
- Bayesian optimization
- evolutionary search
- ranking models
- preference learning

Do not prematurely implement advanced preference algorithms.

First prove that the interaction itself is useful.

---

# Evaluation

Measure real results.

Useful metrics may include:

- plugin CPU usage
- audio callback time
- inference latency
- model inference time
- parameter prediction error
- spectral distance
- embedding similarity
- dataset size
- convergence rounds
- human preference rate

Never invent metrics.

Do not optimize metrics merely because they are easy to report.

Separate:

**technical evaluation**

from

**perceptual evaluation**

from

**user experience evaluation**.

---

# Career Relevance

This project should eventually demonstrate:

- C++
- JUCE
- DSP
- real-time systems
- software architecture
- audio-domain expertise
- ML
- model deployment
- product judgment
- testing
- performance optimization

When choosing between equally valid implementations, prefer the one that provides meaningful engineering learning and can be defended in a technical interview.

However, never sacrifice code quality merely to use a resume keyword.

---

# Documentation

Maintain useful documentation for major architectural decisions.

Eventually the repository should contain:

- strong README
- architecture diagram
- demo instructions
- screenshots
- audio demos
- development milestones
- technical explanation
- measured performance results

The repository should feel like an early-stage professional music-tech product, not a class assignment.

---

# Final Principle

The goal is not simply to build a synthesizer.

The goal is to build a technically credible foundation for an intelligent sound-design system while developing strong skills in:

**music production + C++ + DSP + real-time software + ML + product engineering**

When uncertain, choose the solution that best balances:

**technical credibility × learning value × demo quality × realistic scope**
