#include "PluginProcessor.h"
#include "PluginEditor.h"

AISoundDesignerProcessor::AISoundDesignerProcessor()
    : AudioProcessor(BusesProperties().withOutput("Output", juce::AudioChannelSet::stereo(), true)),
      parameters(*this,nullptr,"AISoundDesignerState",createParameters())               // JUCE parameter state
{
    const char* ids[]={"waveform","attack","decay","sustain","release","cutoff","resonance","gain"};
    for (size_t i=0;i<values.size();++i) values[i]=parameters.getRawParameterValue(ids[i]);
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
    SynthSettings s;
    s.waveform=static_cast<int>(values[0]->load());
    s.attack=values[1]->load(); s.decay=values[2]->load(); s.sustain=values[3]->load(); s.release=values[4]->load();
    s.cutoff=values[5]->load(); s.resonance=values[6]->load(); s.gain=values[7]->load();
    synth.setSettings(s);
    synth.render(buffer, midi);
    midi.clear();
}

juce::AudioProcessorEditor* AISoundDesignerProcessor::createEditor()
{
    return new AISoundDesignerEditor(*this);
}

void AISoundDesignerProcessor::getStateInformation(juce::MemoryBlock& destination)
{
    auto state=parameters.copyState();
    state.setProperty("version",2,nullptr);
    if (auto xml=state.createXml()) copyXmlToBinary(*xml,destination);
}

void AISoundDesignerProcessor::setStateInformation(const void* data, int size)
{
    if (auto xml=getXmlFromBinary(data,size))
        if (xml->hasTagName(parameters.state.getType())) {
            auto state=juce::ValueTree::fromXml(*xml);
            if (static_cast<int>(state.getProperty("version",0)) != 2 || state.getNumChildren()!=8) return;
            const char* ids[]={"waveform","attack","decay","sustain","release","cutoff","resonance","gain"};
            for (auto id:ids) {
                const auto child=state.getChildWithProperty("id",id);
                const auto raw=child.getProperty("value");
                const auto value=raw.isString() ? juce::JSON::fromString(raw.toString()) : raw;
                if (!(value.isDouble() || value.isInt() || value.isInt64())) return;
                const auto native=static_cast<float>(value);
                const auto range=parameters.getParameter(id)->getNormalisableRange();
                if (!std::isfinite(native) || native<range.start || native>range.end
                    || std::abs(range.snapToLegalValue(native)-native)>1.e-6f) return;
            }
            parameters.replaceState(state);
        }
}

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new AISoundDesignerProcessor();
}
