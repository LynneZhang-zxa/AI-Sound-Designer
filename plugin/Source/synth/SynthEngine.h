#pragma once
#include "SynthVoice.h"
#include <array>
#include <juce_dsp/juce_dsp.h>

// Fixed storage, no locks, and no UI access. Lifecycle calls occur with playback stopped.
class SynthEngine final
{
public:
    void prepare(double sampleRate)
    {
        for (auto& voice : voices)
            voice.prepare(sampleRate);
        nextVoice = 0;
        rate = sampleRate;
        filter.prepare({ sampleRate, 1, 1 });
        filter.setType(juce::dsp::StateVariableTPTFilterType::lowpass);
        cutoff.reset(sampleRate,.02); gain.reset(sampleRate,.02); resonance.reset(sampleRate,.02);
        cutoff.setCurrentAndTargetValue(juce::jmin(12000.f,static_cast<float>(sampleRate*.45))); gain.setCurrentAndTargetValue(.8f); resonance.setCurrentAndTargetValue(.707f);
    }

    void reset()
    {
        for (auto& voice : voices)
            voice.stopNote(false);
        filter.reset();
    }

    void setSettings(const SynthSettings& s) {
        for (auto& voice : voices) voice.setSettings(s);
        cutoff.setTargetValue(juce::jmin(s.cutoff, static_cast<float>(rate*.45)));
        gain.setTargetValue(s.gain); resonance.setTargetValue(s.resonance);
    }
    void render(juce::AudioBuffer<float>& buffer, const juce::MidiBuffer& midi);

private:
    void renderVoices(juce::AudioBuffer<float>& buffer, int start, int count)
    {
        for (auto& voice : voices)
            voice.renderNextBlock(buffer, start, count);
    }

    double rate=44100;
    juce::dsp::StateVariableTPTFilter<float> filter;
    juce::SmoothedValue<float> cutoff, gain, resonance;
    std::array<SynthVoice, 8> voices;
    std::size_t nextVoice = 0;
};
