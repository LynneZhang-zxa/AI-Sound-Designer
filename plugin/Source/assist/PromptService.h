#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include <mutex>
#include <cmath>

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
    void submit(juce::String prompt, juce::String snapshot, juce::String endpoint = {}) {
        const std::lock_guard<std::mutex> lock(mutex);
        request=std::move(prompt); current=std::move(snapshot); requestEndpoint=std::move(endpoint); pending=true; ready=false; notify();
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
        if (text.contains("darker") || text.contains("warmer")) result.getDynamicObject()->setProperty("cutoff",value("cutoff",12000)*.6f);
        if (text.contains("brighter")) result.getDynamicObject()->setProperty("cutoff",value("cutoff",12000)*1.5f);
        if (text.contains("shorter")) {
            result.getDynamicObject()->setProperty("decay",value("decay",.1f)*.6f);
            result.getDynamicObject()->setProperty("release",value("release",.15f)*.6f);
        }
        return result;
    }
private:
    void run() override {
        while (!threadShouldExit()) {
            juce::String prompt, snapshot, endpoint;
            { const std::lock_guard<std::mutex> lock(mutex);
              if (pending) { prompt=request; snapshot=current; endpoint=requestEndpoint; pending=false; } }
            if (prompt.isEmpty()) { wait(100); continue; }
            juce::String result, message;
            // Optional external AI adapter contract: POST {prompt,parameters},
            // return a JSON object containing parameter IDs and native values.
            if (endpoint.isNotEmpty()) {
                auto body=juce::var(new juce::DynamicObject());
                body.getDynamicObject()->setProperty("prompt",prompt);
                body.getDynamicObject()->setProperty("parameters",juce::JSON::parse(snapshot));
                auto stream=std::make_unique<juce::WebInputStream>(
                    juce::URL(endpoint).withPOSTData(juce::JSON::toString(body)),true);
                stream->withConnectionTimeout(45000).withNumRedirectsToFollow(0)
                    .withExtraHeaders("Content-Type: application/json\r\n");
                { const std::lock_guard<std::mutex> lock(mutex);
                  activeStream=stream.get(); if (threadShouldExit()) stream->cancel(); }
                if (stream->connect(nullptr) && stream->getStatusCode()>=200 && stream->getStatusCode()<300) {
                    juce::MemoryBlock bytes;
                    const auto count=stream->readIntoMemoryBlock(bytes,16385);
                    if (count>0 && count<=16384) result=juce::String::fromUTF8(static_cast<const char*>(bytes.getData()),static_cast<int>(count));
                }
                { const std::lock_guard<std::mutex> lock(mutex); activeStream=nullptr; }
                if (result.isEmpty()) {
                    result=juce::JSON::toString(baseline(prompt,juce::JSON::parse(snapshot)));
                    message="AI unavailable; using local rule fallback.";
                } else message="AI service response received.";
            } else {
                result=juce::JSON::toString(baseline(prompt,juce::JSON::parse(snapshot)));
                message="Local rule baseline (no AI service configured).";
            }
            { const std::lock_guard<std::mutex> lock(mutex); reply=result; status=message; ready=true; }
        }
    }
    juce::WebInputStream* activeStream=nullptr; // Lifetime protected by mutex; destructor may cancel.
    std::mutex mutex;
    juce::String request,current,requestEndpoint,reply,status;
    bool pending=false,ready=false;
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
