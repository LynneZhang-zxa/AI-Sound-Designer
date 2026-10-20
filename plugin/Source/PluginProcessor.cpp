#include "PluginProcessor.h"
#include "PluginEditor.h"

AISoundDesignerProcessor::AISoundDesignerProcessor()
    : AudioProcessor(BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true))
{
}

void AISoundDesignerProcessor::prepareToPlay(double sampleRate, int)
{
    synth.prepare(sampleRate);
}

void AISoundDesignerProcessor::releaseResources()
{
    synth.reset();
}

bool AISoundDesignerProcessor::isBusesLayoutSupported(const BusesLayout& layout) const
{
    return layout.getMainInputChannelSet().isDisabled()
        && layout.getMainOutputChannelSet() == juce::AudioChannelSet::stereo();
}

void AISoundDesignerProcessor::processBlock(juce::AudioBuffer<float>& buffer,
                                           juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    buffer.clear();
    synth.render(buffer, midi);
    midi.clear();
}

juce::AudioProcessorEditor* AISoundDesignerProcessor::createEditor()
{
    return new AISoundDesignerEditor(*this);
}

void AISoundDesignerProcessor::getStateInformation(juce::MemoryBlock& destination)
{
    juce::XmlElement state("AISoundDesignerState");
    state.setAttribute("version", 1);
    copyXmlToBinary(state, destination);
}

void AISoundDesignerProcessor::setStateInformation(const void*, int)
{
    // No editable parameters yet; there is no runtime state to restore.
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AISoundDesignerProcessor();
}
