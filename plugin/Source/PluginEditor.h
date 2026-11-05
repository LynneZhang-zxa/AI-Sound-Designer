#pragma once
#include "PluginProcessor.h"
#include "assist/DesignSession.h"

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
    friend class Driver; // Editor workflow integration tests exercise the picker completion path.
    void beginReferenceMatch(const juce::File&, double gate);
    void timerCallback() override;
    void invalidateProposal();
    juce::AffineTransform layoutTransform() const;
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
    juce::ComboBox strength;
    juce::TextButton undo {"Undo change"}, analyze {"Analyze sound"}, matchReference {"Match reference WAV"};
    juce::TextEditor referenceGate;
    juce::Label gateLabel;
    juce::ComboBox referenceNote;
    std::unique_ptr<juce::FileChooser> referenceChooser;
    juce::Label status, review, analysisStatus;
    juce::var proposal, requestedSnapshot, undoValues, appliedSnapshot, analysisSnapshot, measuredAudio;
    juce::Array<juce::var> designHistory; // Applied/undone turns only; editor lifetime, never saved in plugin state.
    juce::String requestedPrompt;
    bool proposalPending=false, analysisPending=false, referencePending=false;
    PromptService service, analysisService, referenceService, comparisonService;
    int comparisonSerial=0;
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AISoundDesignerEditor)
};
