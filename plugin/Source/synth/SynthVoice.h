#pragma once
#include <juce_audio_basics/juce_audio_basics.h>
#include "../Parameters.h"

// All runtime voice state belongs to the audio thread.
class SynthVoice final
{
public:
    void prepare(double);
    void setSettings(const SynthSettings& s) { waveform=s.waveform; envelope.setParameters({s.attack,s.decay,s.sustain,s.release}); }
    void startNote(int, int, float);
    void stopNote(bool allowTailOff);
    void renderNextBlock(juce::AudioBuffer<float>&, int, int);
    bool isActive() const { return envelope.isActive(); }
    bool matches(int note, int channel) const { return noteNumber == note && midiChannel == channel; }
    bool onChannel(int channel) const { return midiChannel == channel; }

private:
    int waveform = 0;
    juce::ADSR envelope;
    double sampleRate = 44100.0;
    double phase = 0.0;
    double phaseIncrement = 0.0;
    float level = 0.0f;
    int noteNumber = -1;
    int midiChannel = 0;
};
