#include "PluginEditor.h"

AISoundDesignerEditor::AISoundDesignerEditor(AISoundDesignerProcessor& processor)
    : AudioProcessorEditor(processor)
{
    setSize(420, 160);
}

void AISoundDesignerEditor::paint(juce::Graphics& graphics)
{
    graphics.fillAll(juce::Colour(0xff20242a));
    graphics.setColour(juce::Colours::white);
    graphics.drawFittedText("AI Sound Designer — v0.1\n\n8-voice sine synth\nPlay MIDI notes from your host.",
                            getLocalBounds().reduced(20), juce::Justification::centred, 5);
}
