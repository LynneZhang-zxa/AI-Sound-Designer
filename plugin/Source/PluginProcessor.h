#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include "synth/SynthEngine.h"

static_assert(std::atomic<float>::is_always_lock_free, "Audio parameters require lock-free float atomics");

class AISoundDesignerProcessor final : public juce::AudioProcessor
{
public:
    AISoundDesignerProcessor();
    void prepareToPlay(double, int) override;
    void releaseResources() override;
    void processBlock(juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    bool isBusesLayoutSupported(const BusesLayout&) const override;
    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }
    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 8.0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram(int) override {}
    const juce::String getProgramName(int) override { return {}; }
    void changeProgramName(int, const juce::String&) override {}
    void getStateInformation(juce::MemoryBlock&) override;
    void setStateInformation(const void*, int) override;

juce::AudioProcessorValueTreeState parameters;

private:
    std::array<std::atomic<float>*,8> values {};
    // Constructed before playback; runtime access is audio-thread-only.
    SynthEngine synth;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AISoundDesignerProcessor)
};
