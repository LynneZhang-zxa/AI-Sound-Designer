#pragma once
#include "PluginProcessor.h"

class AISoundDesignerEditor final : public juce::AudioProcessorEditor
{
public:
    explicit AISoundDesignerEditor(AISoundDesignerProcessor&);
    void paint(juce::Graphics&) override;

private:
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(AISoundDesignerEditor)
};
