#include "PluginProcessor.h"
#include "assist/PromptService.h"
#include <cstdlib>
#include <iostream>
#include <new>

static thread_local bool watching=false;
static thread_local size_t allocations=0;
void* operator new(std::size_t size) { if (watching) ++allocations; if(auto* p=std::malloc(size ? size : 1)) return p; throw std::bad_alloc(); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
static void require(bool value,const char* message) { if(!value) { std::cerr<<message<<"\n"; std::exit(1); } }
static void set(AISoundDesignerProcessor& p,const char* id,float value) {
    auto* parameter=p.parameters.getParameter(id);
    parameter->setValueNotifyingHost(parameter->convertTo0to1(value));
}
static void render(AISoundDesignerProcessor& p,juce::AudioBuffer<float>& audio,juce::MidiBuffer& midi) {
    watching=true; p.processBlock(audio,midi); watching=false;
    require(allocations==0,"Heap allocation in audio callback");
    for (int i=0;i<audio.getNumSamples();++i) {
        require(std::isfinite(audio.getSample(0,i)),"Nonfinite output");
        require(std::abs(audio.getSample(0,i))<2.f,"Unbounded output");
        require(std::abs(audio.getSample(0,i)-audio.getSample(1,i))<1.e-12f,"Stereo mismatch");
    }
}
int main(int argc, char**) {
    juce::ScopedJuceInitialiser_GUI init;
    AISoundDesignerProcessor p;
    set(p,"cutoff",2345); set(p,"release",.321f); set(p,"waveform",2);
    juce::MemoryBlock state; p.getStateInformation(state);
    AISoundDesignerProcessor restored; restored.setStateInformation(state.getData(),static_cast<int>(state.getSize()));
    require(std::abs(restored.parameters.getRawParameterValue("cutoff")->load()-2345)<.1f,"Cutoff restoration");
    require(std::abs(restored.parameters.getRawParameterValue("release")->load()-.321f)<.0001f,"Envelope restoration");
    require(static_cast<int>(restored.parameters.getRawParameterValue("waveform")->load())==2,"Waveform restoration");
    restored.setStateInformation("bad",3);
    require(static_cast<int>(restored.parameters.getRawParameterValue("waveform")->load())==2,"Malformed state changed parameters");
    require(validateProposal(juce::JSON::parse("{\"cutoff\":1000}"),p.parameters),"Valid proposal rejected");
    for (auto json:{"{\"cutoff\":-1}","{\"unknown\":1}","{\"waveform\":1.5}","{\"cutoff\":\"1000\"}","{}"})
        require(!validateProposal(juce::JSON::parse(json),p.parameters),"Invalid proposal accepted");
    auto proposal=PromptService::baseline("darker shorter warmer",juce::JSON::parse("{\"cutoff\":10000,\"release\":1,\"decay\":1}"));
    require(std::abs(static_cast<float>(proposal["cutoff"])-6000)<.01f,"Prompt mapping");
    require(validateProposal(proposal,p.parameters),"Baseline proposal invalid");
    const auto clamped=clampProposal(juce::JSON::parse(R"({"cutoff":-1,"release":999,"waveform":1.6})"),p.parameters);
    require(validateProposal(clamped,p.parameters),"Clamped proposal invalid");
    require(static_cast<int>(clamped["cutoff"])==20 && static_cast<int>(clamped["release"])==8
        && static_cast<int>(clamped["waveform"])==2,"Proposal clamp or snap failed");
    require(!applyProposal(juce::JSON::parse(R"({"gain":0.5,"unknown":1})"),p.parameters),"Unknown parameter partially applied");
    {
        PromptService service;
        service.submit("darker shorter",R"({"cutoff":10000,"release":1,"decay":1})","http://127.0.0.1:1/propose");
        juce::String reply,message;
        bool received=false;
        for(int i=0;i<500;++i) {
            if(service.take(reply,message)) { received=true; break; }
            juce::Thread::sleep(10);
        }
        require(received && message.contains("fallback"),"Unavailable service did not fall back");
        require(validateProposal(clampProposal(juce::JSON::parse(reply),p.parameters),p.parameters),"Offline fallback invalid");
    }
    for (double rate:{11025.,44100.,48000.,96000.}) for(int block:{1,64,511}) for(int wave=0;wave<4;++wave) {
        p.prepareToPlay(rate,block); set(p,"waveform",static_cast<float>(wave)); set(p,"release",.005f);
        juce::AudioBuffer<float> audio(2,block); juce::MidiBuffer midi; midi.ensureSize(4096);
        for(int note=48;note<64;++note) midi.addEvent(juce::MidiMessage::noteOn(1,note,1.f),0);
        double energy=0;
        for(int b=0;b<100;++b) {
            set(p,"cutoff",b%2 ? 20000.f : 20.f); set(p,"resonance",b%2 ? 2.f : .5f);
            render(p,audio,midi);
            for(int i=0;i<block;++i) energy+=std::abs(audio.getSample(0,i));
        }
        require(energy>0,"MIDI produced silence");
        midi.addEvent(juce::MidiMessage::allNotesOff(1),0);
        for(int b=0;b<static_cast<int>(rate/block)+1;++b) render(p,audio,midi);
        require(audio.getMagnitude(0,block)<1.e-6f,"Stuck notes after release");
        p.releaseResources();
    }
    p.prepareToPlay(48000,128); juce::AudioBuffer<float> audio(2,128); juce::MidiBuffer midi;
    midi.ensureSize(4096); midi.addEvent(juce::MidiMessage::noteOn(2,60,1.f),64);
    render(p,audio,midi);
    require(audio.getMagnitude(0,64)<1.e-12f,"MIDI note starts before sample position");
    midi.addEvent(juce::MidiMessage::allSoundOff(2),0); render(p,audio,midi);
    for(int b=0;b<100;++b) render(p,audio,midi);
    require(audio.getMagnitude(0,128)<1.e-6f,"All sound off failed");
    if (argc>1) {
        PromptService service;
        service.submit("darker and shorter, preserve attack",R"({"waveform":1,"attack":0.005,"decay":0.4,"sustain":0.8,"release":0.6,"cutoff":10000,"resonance":0.707,"gain":0.8})","http://127.0.0.1:8765/propose");
        juce::String reply,message;
        bool received=false;
        for (int i=0;i<5000;++i) {
            render(p,audio,midi); // Rendering continues while the AI service works.
            if (service.take(reply,message)) { received=true; break; }
            juce::Thread::sleep(10);
        }
        require(received,"AI service response timed out");
        require(message.contains("service response"),"Live AI test received offline fallback");
        const auto result=juce::JSON::parse(reply);
        require(applyProposal(result,p.parameters),"AI service proposal invalid");
        require(p.parameters.getRawParameterValue("cutoff")->load()<10000,"AI did not darken sound");
        require(p.parameters.getRawParameterValue("release")->load()<.6f,"AI did not shorten release");
        std::cout<<"LIVE AI PASS: "<<reply<<"\n";
    }
    std::cout<<"PASS: state, proposal validation, MIDI, 4 waveforms, 4 rates, 3 block sizes, automation, release, C++ callback allocations=0\n";
}
