#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
struct SynthSettings { int waveform=0; float attack=.005f, decay=.1f, sustain=.8f, release=.15f, cutoff=12000, resonance=.707f, gain=.8f; };
inline juce::AudioProcessorValueTreeState::ParameterLayout createParameters()
{
    juce::AudioProcessorValueTreeState::ParameterLayout layout;
    layout.add(std::make_unique<juce::AudioParameterChoice>(juce::ParameterID{"waveform",1}, "Waveform", juce::StringArray{"Sine","Saw","Square","Triangle"},0));
    auto add = [&](const char* id,const char* name,float low,float high,float value,float skew=1.f) {
        layout.add(std::make_unique<juce::AudioParameterFloat>(juce::ParameterID{id,1},name,juce::NormalisableRange<float>(low,high,0.f,skew),value));
    };
    add("attack","Attack (s)",.001f,5.f,.005f,.3f); add("decay","Decay (s)",.005f,5.f,.1f,.3f);
    add("sustain","Sustain",0,1,.8f); add("release","Release (s)",.005f,8.f,.15f,.3f);
    add("cutoff","Low-pass cutoff (Hz)",20,20000,12000,.25f); add("resonance","Resonance (Q)",.5f,2.f,.707f);
    add("gain","Output gain",0,1,.8f);
    return layout;
}
