#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <mutex>
#include <cmath>
#include <regex>

// Owned by the editor. Worker owns computation/network I/O; the message thread
// snapshots parameters and applies validated results. No audio-thread access.
class PromptService final : private juce::Thread
{
public:
    PromptService() : Thread("Sound design service") { startThread(); }
    ~PromptService() override {
        signalThreadShouldExit(); notify();
        { const std::lock_guard<std::mutex> lock(mutex); if (activeStream) activeStream->cancel(); }
        stopThread(-1);
    }
    void submit(juce::String prompt, juce::String snapshot, juce::String endpoint = {}, bool allowFallback = true, juce::String context = {}, juce::String audioContext = {}) {
        const std::lock_guard<std::mutex> lock(mutex);
        request=std::move(prompt); current=std::move(snapshot); requestEndpoint=std::move(endpoint); requestFallback=allowFallback; requestContext=std::move(context); requestAudioContext=std::move(audioContext); pending=true; ready=false; notify();
    }
    bool take(juce::String& result, juce::String& message) {
        const std::lock_guard<std::mutex> lock(mutex);
        if (!ready) return false;
        result=reply; message=status; ready=false; return true;
    }
    static juce::var baseline(const juce::String& prompt, const juce::var& snapshot) {
        auto result=juce::var(new juce::DynamicObject());
        const auto text=prompt.toLowerCase();
        auto value=[&](const char* id,float fallback) { return snapshot.hasProperty(id) ? static_cast<float>(snapshot[id]) : fallback; };
        auto set=[&](const char* id,double target) { result.getDynamicObject()->setProperty(id,target); };
        auto has=[&](const char* english,const char* chinese) { return text.contains(english) || text.contains(juce::String::fromUTF8(chinese)); };
        // Conservative offline vocabulary. This runs only on the editor worker.
        if (has("pad","铺底")) { set("attack",.4);set("release",1.2);set("sustain",.8); }
        if (has("pluck","拨弦")) { set("attack",.005);set("decay",.18);set("sustain",.2);set("release",.15); }
        const bool dark=(has("darker","暗") || has("warmer","暖"))
            && !text.contains("not darker") && !text.contains("don't darken")
            && !text.contains(juce::String::fromUTF8("不要变暗"));
        const bool warm=has("warmer","暖");
        const bool soft=text.contains("softer") || text.contains("soften") || text.contains(juce::String::fromUTF8("柔和"));
        if (dark) {
            // Reduce upper partials and filter emphasis together, without changing
            // pitch, waveform identity or envelope timing for a brightness-only intent.
            set("cutoff",juce::jmin(value("cutoff",12000)*.55f,2000.f));
            if (value("resonance",.707f)>.55f) set("resonance",juce::jmax(.5f,value("resonance",.707f)*.8f));
        }
        if (warm || soft) {
            if (value("waveform",1)==2) set("waveform",3); // Square -> triangle reduces upper partials.
            set("resonance",juce::jmax(.5f,value("resonance",.707f)*.8f));
            if (soft) set("attack",juce::jmax(.015f,value("attack",.01f)*1.4f));
        }
        if (has("brighter","亮")) set("cutoff",value("cutoff",12000)*1.5);
        if (has("shorter","短")) {set("decay",value("decay",.1f)*.6);set("release",value("release",.15f)*.6);}
        if (has("longer tail","长尾") || text.contains("longer release") || text.contains(juce::String::fromUTF8("延长尾音")) || text.contains(juce::String::fromUTF8("尾音长"))) set("release",value("release",.15f)*1.8);
        if (has("slow attack","慢起音") || text.contains("softer attack") || text.contains(juce::String::fromUTF8("起音慢"))) set("attack",juce::jmax(.08f,value("attack",.01f)*2.f));
        if (has("fast attack","快起音") || text.contains("sharper attack") || text.contains(juce::String::fromUTF8("起音快"))) set("attack",value("attack",.01f)*.5);
        if (has("less resonance","降低共鸣") || text.contains("less resonant")) set("resonance",value("resonance",.707f)*.8);
        if (has("more resonance","增加共鸣") || text.contains("more resonant")) set("resonance",value("resonance",.707f)*1.2);
        if (has("quieter","小声") || text.contains("lower volume") || text.contains(juce::String::fromUTF8("音量小")) || text.contains(juce::String::fromUTF8("降低音量"))) set("gain",value("gain",.8f)*.75);
        if (has("louder","大声") || text.contains("higher volume") || text.contains(juce::String::fromUTF8("提高音量"))) set("gain",value("gain",.8f)*1.2);
        for (const auto& wave:std::initializer_list<std::pair<const char*,int>>{{"sine",0},{"saw",1},{"square",2},{"triangle",3}})
            if (text.contains(wave.first)) set("waveform",wave.second);
        const char* chineseWaves[]={"正弦","锯齿","方波","三角"};
        for (int i=0;i<4;++i) if (text.contains(juce::String::fromUTF8(chineseWaves[i]))) set("waveform",i);
        if (text.contains("not brighter") || text.contains("don't brighten") || text.contains(juce::String::fromUTF8("不要更亮"))) result.getDynamicObject()->removeProperty("cutoff");
        const auto input=text.toStdString();
        // Explicit native values override descriptive mappings; units are checked by parameter type.
        for (const auto* id:{"cutoff","attack","decay","release","sustain","resonance","gain"}) {
            const std::regex pattern(std::string("\\b")+id+R"([ ]*(?:to[ ]*|=[ ]*|:[ ]*)?((?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))[ ]*([a-z%]*)(?![a-z0-9.%]))");
            std::smatch match;
            if (std::regex_search(input,match,pattern)) {
                const double number=juce::String(match[1].str()).getDoubleValue();const auto unit=match[2].str();
                if (!std::isfinite(number)) continue;
                const bool time=juce::String(id)=="attack" || juce::String(id)=="decay" || juce::String(id)=="release";
                if (time && (unit.empty() || unit=="s" || unit=="sec" || unit=="seconds" || unit=="ms")) set(id,number*(unit=="ms"?.001:1.));
                else if (juce::String(id)=="cutoff" && (unit.empty() || unit=="hz" || unit=="khz")) set(id,number*(unit=="khz"?1000.:1.));
                else if ((juce::String(id)=="sustain" || juce::String(id)=="gain") && (unit.empty() || unit=="%")) set(id,number*(unit=="%"?.01:1.));
                else if (juce::String(id)=="resonance" && (unit.empty() || unit=="q")) set(id,number);
            }
        }
        // Preserve directives take precedence over every offline mapping.
        for (const auto* id:{"waveform","cutoff","attack","decay","sustain","release","resonance","gain"})
            if (text.contains("preserve "+juce::String(id)) || text.contains("keep "+juce::String(id)) || text.contains("don't change "+juce::String(id)))
                result.getDynamicObject()->removeProperty(id);
        if (text.contains("preserve the transient")) result.getDynamicObject()->removeProperty("attack");
        return result;
    }
private:
    void run() override {
        while (!threadShouldExit()) {
            juce::String prompt, snapshot, endpoint, context, audioContext; bool allowFallback=true;
            { const std::lock_guard<std::mutex> lock(mutex);
              if (pending) { prompt=request; snapshot=current; endpoint=requestEndpoint; allowFallback=requestFallback; context=requestContext; audioContext=requestAudioContext; pending=false; } }
            if (prompt.isEmpty()) { wait(100); continue; }
            juce::String result, message;
            // Optional external AI adapter contract: POST {prompt,parameters},
            // return a JSON object containing parameter IDs and native values.
            if (endpoint.isNotEmpty()) {
                auto body=juce::var(new juce::DynamicObject());
                body.getDynamicObject()->setProperty("prompt",prompt);
                body.getDynamicObject()->setProperty("parameters",juce::JSON::parse(snapshot));
                if (context.isNotEmpty()) body.getDynamicObject()->setProperty("history",juce::JSON::parse(context));
                if (audioContext.isNotEmpty()) body.getDynamicObject()->setProperty("audio_context",juce::JSON::parse(audioContext));
                auto stream=std::make_unique<juce::WebInputStream>(
                    juce::URL(endpoint).withPOSTData(juce::JSON::toString(body)),true);
                stream->withConnectionTimeout(45000).withNumRedirectsToFollow(0)
                    .withExtraHeaders("Content-Type: application/json\r\n");
                { const std::lock_guard<std::mutex> lock(mutex);
                  activeStream=stream.get(); if (threadShouldExit()) stream->cancel(); }
                if (stream->connect(nullptr) && ((stream->getStatusCode()>=200 && stream->getStatusCode()<300) || !allowFallback)) {
                    juce::MemoryBlock bytes;
                    const auto count=stream->readIntoMemoryBlock(bytes,16385);
                    if (count>0 && count<=16384) result=juce::String::fromUTF8(static_cast<const char*>(bytes.getData()),static_cast<int>(count));
                }
                { const std::lock_guard<std::mutex> lock(mutex); activeStream=nullptr; }
                if (result.isEmpty()) {
                    result=allowFallback ? juce::JSON::toString(baseline(prompt,juce::JSON::parse(snapshot))) : juce::String{};
                    message="AI unavailable; using local rule fallback.";
                } else message="AI service response received.";
            } else {
                result=juce::JSON::toString(baseline(prompt,juce::JSON::parse(snapshot)));
                message="Local rule baseline (no AI service configured).";
            }
            if (endpoint.isEmpty() || message.contains("fallback")) {
                const auto text=prompt.toLowerCase();
                if (text.contains("darker") || text.contains("warmer") || text.contains(juce::String::fromUTF8("暗")) || text.contains(juce::String::fromUTF8("暖")))
                {
                    const auto patch=juce::JSON::parse(result);
                    if (patch.hasProperty("cutoff")) message+=" Cutoff shapes upper partials.";
                    if (patch.hasProperty("resonance")) message+=" Resonance shapes filter emphasis.";
                    if (patch.hasProperty("waveform")) message+=" Waveform changes harmonic structure.";
                    if (patch.hasProperty("attack")) message+=" Attack shapes onset.";
                    if (!patch.hasProperty("gain")) message+=" Gain held.";
                    const auto initial=juce::JSON::parse(snapshot);
                    if (initial.hasProperty("waveform") && static_cast<int>(initial["waveform"])==0
                        && (!patch.hasProperty("waveform") || static_cast<int>(patch["waveform"])==0))
                        message+=" Sine has little harmonic brightness to remove; cutoff may mainly change level.";
                }
            }
            { const std::lock_guard<std::mutex> lock(mutex); reply=result; status=message; ready=true; }
        }
    }
    juce::WebInputStream* activeStream=nullptr; // Lifetime protected by mutex; destructor may cancel.
    std::mutex mutex;
    juce::String request,current,requestEndpoint,requestContext,requestAudioContext,reply,status;
    bool pending=false,ready=false,requestFallback=true;
};

inline bool validateProposal(const juce::var& proposal, juce::AudioProcessorValueTreeState& state)
{
    const auto* object=proposal.getDynamicObject();
    if (object==nullptr || object->getProperties().size()==0) return false;
    for (const auto& item: object->getProperties()) {
        auto* parameter=state.getParameter(item.name.toString());
        if (parameter==nullptr || !(item.value.isDouble() || item.value.isInt() || item.value.isInt64())) return false;
        const auto value=static_cast<float>(item.value);
        const auto range=parameter->getNormalisableRange();
        if (!std::isfinite(value) || value<range.start || value>range.end || std::abs(range.snapToLegalValue(value)-value)>1.e-6f) return false;
    }
    return true;
}

// Message-thread only. Reject unknown/nonfinite values, clamp continuous values,
// and snap choices before any host notification. Validation is all-or-nothing.
inline juce::var clampProposal(const juce::var& proposal, juce::AudioProcessorValueTreeState& state)
{
    const auto* object=proposal.getDynamicObject();
    if (object==nullptr || object->getProperties().size()==0) return {};
    auto result=juce::var(new juce::DynamicObject());
    for (const auto& item:object->getProperties()) {
        auto* parameter=state.getParameter(item.name.toString());
        if (parameter==nullptr || !(item.value.isDouble() || item.value.isInt() || item.value.isInt64())) return {};
        const auto value=static_cast<double>(item.value);
        if (!std::isfinite(value)) return {};
        const auto range=parameter->getNormalisableRange();
        const auto clamped=juce::jlimit(static_cast<double>(range.start),static_cast<double>(range.end),value);
        result.getDynamicObject()->setProperty(item.name,range.snapToLegalValue(static_cast<float>(clamped)));
    }
    return result;
}

// Host gestures and notifications may call host/UI code; never call from DSP.
inline bool applyProposal(const juce::var& proposal, juce::AudioProcessorValueTreeState& state)
{
    const auto safe=clampProposal(proposal,state);
    if (!validateProposal(safe,state)) return false;
    for (const auto& item:safe.getDynamicObject()->getProperties()) {
        auto* parameter=state.getParameter(item.name.toString());
        parameter->beginChangeGesture();
        parameter->setValueNotifyingHost(parameter->convertTo0to1(static_cast<float>(item.value)));
        parameter->endChangeGesture();
    }
    return true;
}
