#pragma once
#include "PluginProcessor.h"
#include "assist/PromptService.h"

class AISoundDesignerEditor final : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit AISoundDesignerEditor(AISoundDesignerProcessor&);
    ~AISoundDesignerEditor() override { stopTimer(); }
    void resized() override;
private:
    void timerCallback() override;
    AISoundDesignerProcessor& owner;
    juce::GenericAudioProcessorEditor controls;
    juce::TextEditor prompt;
    juce::ToggleButton useAI {"Use AI service (prompt + parameters)"};
    juce::TextButton propose {"Propose"}, apply {"Apply proposal"};
    juce::Label status;
    juce::var proposal;
    PromptService service;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AISoundDesignerEditor)
};
