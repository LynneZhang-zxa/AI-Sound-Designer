#pragma once
#include "SynthVoice.h"
#include <array>

// Fixed storage, no locks, and no UI access. Lifecycle calls occur with playback stopped.
class SynthEngine final
{
public:
    void prepare(double sampleRate)
    {
        for (auto& voice : voices)
            voice.prepare(sampleRate);
        nextVoice = 0;
    }

    void reset()
    {
        for (auto& voice : voices)
            voice.stopNote(false);
    }

    void render(juce::AudioBuffer<float>& buffer, const juce::MidiBuffer& midi);

private:
    void renderVoices(juce::AudioBuffer<float>& buffer, int start, int count)
    {
        for (auto& voice : voices)
            voice.renderNextBlock(buffer, start, count);
    }

    std::array<SynthVoice, 8> voices;
    std::size_t nextVoice = 0;
};
