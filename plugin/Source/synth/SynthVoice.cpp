#include "SynthVoice.h"
#include <cmath>

void SynthVoice::prepare(double rate)
{
    sampleRate = rate;
    envelope.setSampleRate(rate);
    envelope.setParameters({ 0.005f, 0.1f, 0.8f, 0.15f });
    stopNote(false);
}

void SynthVoice::startNote(int note, int channel, float velocity)
{
    noteNumber = note;
    midiChannel = channel;
    phase = 0.0;
    phaseIncrement = juce::MathConstants<double>::twoPi
        * juce::MidiMessage::getMidiNoteInHertz(note) / sampleRate;
    // Eight full-velocity voices sum to at most 0.8 before host processing.
    level = velocity * 0.1f;
    envelope.reset();
    envelope.noteOn();
}

void SynthVoice::stopNote(bool allowTailOff)
{
    if (allowTailOff)
        envelope.noteOff();
    else
    {
        envelope.reset();
        noteNumber = -1;
        midiChannel = 0;
    }
}

void SynthVoice::renderNextBlock(juce::AudioBuffer<float>& buffer,
                                 int startSample, int numSamples)
{
    if (!isActive())
        return;

    for (int sample = startSample; sample < startSample + numSamples; ++sample)
    {
        const auto value = static_cast<float>(std::sin(phase))
            * level * envelope.getNextSample();
        phase += phaseIncrement;
        if (phase >= juce::MathConstants<double>::twoPi)
            phase -= juce::MathConstants<double>::twoPi;

        for (int channel = 0; channel < buffer.getNumChannels(); ++channel)
            buffer.addSample(channel, sample, value);

        if (!envelope.isActive())
            break;
    }
}
