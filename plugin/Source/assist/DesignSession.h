#pragma once
#include "PromptService.h"

// Message-thread helpers only. DSP still reads the existing atomics unchanged.
inline juce::var parameterSnapshot(juce::AudioProcessorValueTreeState& state)
{
    auto result=juce::var(new juce::DynamicObject());
    for (auto* raw:state.processor.getParameters())
        if (auto* p=dynamic_cast<juce::RangedAudioParameter*>(raw))
            result.getDynamicObject()->setProperty(p->paramID,state.getRawParameterValue(p->paramID)->load());
    return result;
}
inline bool snapshotMatches(const juce::var& snapshot, juce::AudioProcessorValueTreeState& state)
{
    if (!snapshot.getDynamicObject()) return false;
    for (const auto& item:snapshot.getDynamicObject()->getProperties()) {
        auto* value=state.getRawParameterValue(item.name.toString());
        if (!value || std::abs(static_cast<double>(item.value)-value->load())>1.e-6) return false;
    }
    return snapshot.getDynamicObject()->getProperties().size()==state.processor.getParameters().size();
}
inline juce::var scaledDesignProposal(const juce::var& raw,const juce::var& before,
                                     double strength,juce::AudioProcessorValueTreeState& state)
{
    const auto safe=clampProposal(raw,state);
    if (!safe.getDynamicObject() || !before.getDynamicObject() || !std::isfinite(strength) || strength<=0) return {};
    auto result=juce::var(new juce::DynamicObject());
    for (const auto& item:safe.getDynamicObject()->getProperties()) {
        const auto id=item.name.toString();
        if (!before.hasProperty(id)) return {};
        const double initial=before[juce::Identifier(id)],target=item.value;
        const auto& range=state.getParameter(id)->getNormalisableRange();
        double value=target;
        if (id!="waveform") {
            const bool logarithmic=id=="cutoff" || id=="attack" || id=="decay" || id=="release" || id=="resonance";
            value=logarithmic && initial>0 && target>0
                ? initial*std::exp(strength*std::log(target/initial)) : initial+strength*(target-initial);
            value=juce::jlimit(static_cast<double>(range.start),static_cast<double>(range.end),value);
        }
        if (std::abs(value-initial)>1.e-6) result.getDynamicObject()->setProperty(id,value);
    }
    return clampProposal(result,state);
}

inline juce::String describeParameterValue(const juce::String& id,double value)
{
    if (id=="waveform") return juce::StringArray{"Sine","Saw","Square","Triangle"}[juce::jlimit(0,3,static_cast<int>(value))];
    if (id=="cutoff") return juce::String(value,1)+" Hz";
    if (id=="attack" || id=="decay" || id=="release") return juce::String(value*1000.,1)+" ms";
    if (id=="gain" || id=="sustain") return juce::String(value*100.,1)+" %";
    return juce::String(value,2)+" Q";
}

// Common explicit preservation requests are enforced even if an AI proposes them.
inline juce::var preserveRequestedParameters(const juce::var& raw,const juce::String& intent)
{
    if (!raw.getDynamicObject()) return {};
    auto result=juce::var(new juce::DynamicObject());const auto text=intent.toLowerCase();
    for (const auto& item:raw.getDynamicObject()->getProperties()) {
        const auto id=item.name.toString();
        const bool protectedValue=text.contains("preserve "+id) || text.contains("keep "+id)
            || text.contains("don't change "+id) || text.contains("do not change "+id)
            || (id=="waveform" && (text.contains(juce::String::fromUTF8("保留波形")) || text.contains(juce::String::fromUTF8("保持波形"))))
            || (id=="attack" && (text.contains("preserve the transient") || text.contains(juce::String::fromUTF8("保留起音")) || text.contains(juce::String::fromUTF8("保持起音"))))
            || (id=="release" && (text.contains("keep the tail") || text.contains(juce::String::fromUTF8("保留尾音")) || text.contains(juce::String::fromUTF8("保持尾音"))))
            || (id=="waveform" && (text.contains("preserve character") || text.contains(juce::String::fromUTF8("保留性格"))))
            || ((text.contains("only cutoff") || text.contains(juce::String::fromUTF8("只调cutoff"))) && id!="cutoff");
        if (!protectedValue) result.getDynamicObject()->setProperty(item.name,item.value);
    }
    return result;
}

// Resolve only unambiguous explicit waveform selections; descriptive sound design
// remains with the AI. The completed patch still needs review and Apply.
inline juce::var completeExplicitWaveform(const juce::var& raw,const juce::String& intent)
{
    if (!raw.getDynamicObject()) return {};
    const auto text=intent.toLowerCase();
    if (text.contains("not ") || text.contains("don't") || text.contains("do not")
        || text.contains("keep waveform") || text.contains("preserve waveform")
        || text.contains(juce::String::fromUTF8("不要")) || text.contains(juce::String::fromUTF8("保持波形"))
        || text.contains(juce::String::fromUTF8("保留波形"))) return raw;
    int selected=-1,matches=0;
    const char* english[]={"sine","saw","square","triangle"};
    const char* chinese[]={"正弦","锯齿","方波","三角"};
    for (int i=0;i<4;++i) {
        const auto wave=juce::String::fromUTF8(chinese[i]);
        bool explicitChoice=text.contains(juce::String::fromUTF8("换成")+wave)
            || text.contains(juce::String::fromUTF8("改成")+wave)
            || text.contains(juce::String::fromUTF8("切换到")+wave)
            || text.contains(juce::String::fromUTF8("使用")+wave);
        const std::regex pattern(std::string(R"((?:\b(?:use|choose|switch to|change to|set waveform to)\s+|^))")+english[i]+R"((?:\s+wave)?\b)");
        explicitChoice=explicitChoice || std::regex_search(text.toStdString(),pattern);
        if (explicitChoice) {selected=i;++matches;}
    }
    if (matches!=1) return raw;
    auto result=juce::var(new juce::DynamicObject());
    for (const auto& item:raw.getDynamicObject()->getProperties()) result.getDynamicObject()->setProperty(item.name,item.value);
    result.getDynamicObject()->setProperty("waveform",selected);
    return result;
}
