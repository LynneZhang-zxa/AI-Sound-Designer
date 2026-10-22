#pragma once
#include "PluginProcessor.h"
#include "assist/PromptService.h"

// All controls, visualisations and proposal handling belong to the message thread.
class SynthLookAndFeel final : public juce::LookAndFeel_V4
{
public:
    SynthLookAndFeel();
    void drawRotarySlider(juce::Graphics&, int, int, int, int, float, float, float, juce::Slider&) override;
};

class AISoundDesignerEditor final : public juce::AudioProcessorEditor, private juce::Timer
{
public:
    explicit AISoundDesignerEditor(AISoundDesignerProcessor&);
    ~AISoundDesignerEditor() override;
    void paint(juce::Graphics&) override;
    void resized() override;
private:
    void timerCallback() override;
    void drawDisplay(juce::Graphics&, juce::Rectangle<float>, bool envelope);
    AISoundDesignerProcessor& owner;
    SynthLookAndFeel theme;
    juce::ComboBox waveform;
    std::array<juce::Slider, 7> knobs;
    std::array<juce::Label, 7> labels;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> waveformAttachment;
    std::array<std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment>, 7> attachments;
    juce::TextEditor prompt;
    juce::ToggleButton useAI {"Live AI service"};
    juce::TextButton propose {"Propose changes"}, apply {"Apply proposal"};
    juce::Label status;
    juce::var proposal;
    PromptService service;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AISoundDesignerEditor)
};
