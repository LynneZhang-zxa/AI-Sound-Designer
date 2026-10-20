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
    const auto frequency=juce::MidiMessage::getMidiNoteInHertz(note);
    // Suppress notes above the usable band at low host sample rates.
    if (frequency >= sampleRate*.49) { stopNote(false); return; }
    noteNumber = note;
    midiChannel = channel;
    phase = 0.0;
    phaseIncrement = frequency / sampleRate;
    // Reserve headroom for eight voices and the resonant low-pass filter.
    level = velocity * 0.05f;
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
        // PolyBLEP cancels discontinuities in saw and pulse waveforms.
        const auto blep = [dt=phaseIncrement](double t) {
            if (t < dt) { t /= dt; return t+t-t*t-1.0; }
            if (t > 1.0-dt) { t=(t-1.0)/dt; return t*t+t+t+1.0; }
            return 0.0;
        };
        double wave = std::sin(juce::MathConstants<double>::twoPi * phase);
        if (waveform == 1) wave = 2.0*phase-1.0-blep(phase);
        if (waveform == 2) wave = (phase < .5 ? 1.0 : -1.0)+blep(phase)-blep(std::fmod(phase+.5,1.0));
        // Finite odd-harmonic series stays below Nyquist.
        if (waveform == 3) {
            wave=0;
            for (int k=1; k<=31 && k*phaseIncrement < .5; k+=2)
                wave += ((k%4==1) ? 1.0 : -1.0)*std::sin(k*juce::MathConstants<double>::twoPi*phase)/(k*k);
            wave *= 8.0/(juce::MathConstants<double>::pi*juce::MathConstants<double>::pi);
        }
        const auto value = static_cast<float>(wave) * level * envelope.getNextSample();
        phase += phaseIncrement;
        if (phase >= 1.0)
            phase -= 1.0;

        for (int channel = 0; channel < buffer.getNumChannels(); ++channel)
            buffer.addSample(channel, sample, value);

        if (!envelope.isActive())
            break;
    }
}
