#include "SynthEngine.h"

void SynthEngine::render(juce::AudioBuffer<float>& buffer, const juce::MidiBuffer& midi)
{
    int cursor = 0;
    for (const auto metadata : midi)
    {
        const int position = juce::jlimit(cursor, buffer.getNumSamples(), metadata.samplePosition);
        renderVoices(buffer, cursor, position - cursor);
        cursor = position;

        // Inspect the existing bytes directly: constructing a MidiMessage could allocate for SysEx.
        const auto* data = metadata.data;
        if (metadata.numBytes < 3)
            continue;
        const int type = data[0] & 0xf0;
        const int channel = (data[0] & 0x0f) + 1;
        const int note = data[1] & 0x7f;
        const int value = data[2] & 0x7f;
        if (type == 0x90 && value != 0)
        {
            auto selected = nextVoice;
            for (std::size_t offset = 0; offset < voices.size(); ++offset)
            {
                const auto index = (nextVoice + offset) % voices.size();
                if (!voices[index].isActive())
                {
                    selected = index;
                    break;
                }
            }
            voices[selected].startNote(note, channel, static_cast<float>(value) / 127.0f);
            nextVoice = (selected + 1) % voices.size();
        }
        else if (type == 0x80 || (type == 0x90 && value == 0))
        {
            for (auto& voice : voices)
                if (voice.matches(note, channel))
                    voice.stopNote(true);
        }
        else if (type == 0xb0 && (note == 120 || note == 123))
        {
            for (auto& voice : voices)
                if (voice.onChannel(channel))
                    voice.stopNote(note == 123);
        }
    }
    renderVoices(buffer, cursor, buffer.getNumSamples() - cursor);
}
