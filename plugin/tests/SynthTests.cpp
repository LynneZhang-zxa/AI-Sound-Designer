#include "PluginProcessor.h"
#include "assist/DesignSession.h"
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
int main(int argc, char** argv) {
    juce::ScopedJuceInitialiser_GUI init;
    AISoundDesignerProcessor p;
    {
        const auto before=parameterSnapshot(p.parameters);
        require(snapshotMatches(before,p.parameters),"Fresh snapshot mismatch");
        const auto raw=juce::JSON::parse(R"({"cutoff":1200,"release":0.06,"decay":0.01})");
        const auto target=scaledDesignProposal(raw,before,2.5,p.parameters);
        require(validateProposal(target,p.parameters),"Invalid scaled design proposal");
        require(target.hasProperty("decay"),"Design dropped supported decay parameter");
        require(static_cast<double>(target["cutoff"])<1200,"Strong intensity not stronger");
        require(!target.hasProperty("attack"),"Unchanged attack included");
        require(applyProposal(target,p.parameters),"Design apply failed");
        require(!snapshotMatches(before,p.parameters),"Stale snapshot accepted");
        require(applyProposal(before,p.parameters),"Undo snapshot restoration failed");
        require(snapshotMatches(before,p.parameters),"Undo did not restore parameters");
        require(!validateProposal(scaledDesignProposal(juce::JSON::parse(R"({"unknown":1})"),before,1.,p.parameters),p.parameters),"Unknown design key accepted");
        PromptService analysis;
        analysis.submit("analyze",juce::JSON::toString(before),"http://127.0.0.1:1/analyze",false);
        juce::String reply,status; bool ready=false;
        for(int i=0;i<200;++i) { if(analysis.take(reply,status)) { ready=true; break; } juce::Thread::sleep(10); }
        require(ready && reply.isEmpty(),"ML failure fabricated a fallback estimate");
    }

    {
        const auto before=parameterSnapshot(p.parameters);
        const auto raw=juce::JSON::parse(R"({"waveform":2,"gain":0.4,"sustain":0,"resonance":1.2,"decay":0.3})");
        const auto all=scaledDesignProposal(raw,before,.5,p.parameters);
        require(all.hasProperty("waveform") && all.hasProperty("gain") && all.hasProperty("sustain") && all.hasProperty("resonance") && all.hasProperty("decay"),"Supported assistant values dropped");
        require(static_cast<int>(all["waveform"])==2,"Waveform strength produced fractional choice");
        require(applyProposal(all,p.parameters),"Full proposal failed");
        require(applyProposal(before,p.parameters),"Full proposal undo failed");
        const auto numeric=PromptService::baseline("sine, cutoff 2 kHz, attack 50 ms, decay 200 ms, sustain 60%, release 1.2 s, gain 40%, resonance 0.8 Q",before);
        require(std::abs(static_cast<double>(numeric["cutoff"])-2000)<.01 && std::abs(static_cast<double>(numeric["attack"])-.05)<1.e-6,"Explicit units misparsed");
        require(std::abs(static_cast<double>(numeric["gain"])-.4)<1.e-6 && static_cast<int>(numeric["waveform"])==0,"Level or waveform misparsed");
        const auto preserved=PromptService::baseline("pluck but preserve attack and keep sustain",before);
        require(!preserved.hasProperty("attack") && !preserved.hasProperty("sustain"),"Preserve directive ignored");
        const auto omittedWave=juce::JSON::parse(R"({"attack":0.3,"release":1.2,"gain":0.4})");
        const auto completedWave=completeExplicitWaveform(omittedWave,juce::String::fromUTF8("换成正弦波，attack 设为 300 ms，release 设为 1.2 秒，音量降到 40%。"));
        require(completedWave.hasProperty("waveform") && static_cast<int>(completedWave["waveform"])==0,"Explicit Chinese sine request was omitted");
        require(static_cast<int>(completeExplicitWaveform(juce::JSON::parse(R"({"waveform":2})"),juce::String::fromUTF8("换成正弦波"))["waveform"])==0,"Wrong AI waveform was not corrected");
        require(!preserveRequestedParameters(juce::JSON::parse(R"({"waveform":0})"),juce::String::fromUTF8("保留波形")).hasProperty("waveform"),"Chinese waveform preservation failed");
        require(!omittedWave.hasProperty("waveform"),"Wave completion mutated response");
        require(!completeExplicitWaveform(omittedWave,"do not use sine").hasProperty("waveform"),"Negated waveform command applied");
        require(!completeExplicitWaveform(omittedWave,"use sine or choose square").hasProperty("waveform"),"Ambiguous waveform command applied");
        require(static_cast<int>(completeExplicitWaveform(omittedWave,"switch to triangle")["waveform"])==3,"English waveform command missed");
        const auto protectedAI=preserveRequestedParameters(juce::JSON::parse(R"({"attack":0.4,"gain":0.3})"),"keep attack, quieter");
        require(!protectedAI.hasProperty("attack") && protectedAI.hasProperty("gain"),"AI preserve guard failed");
        const auto chinese=PromptService::baseline(juce::String::fromUTF8("换成正弦 pad，起音慢一点，延长尾音，降低共鸣，音量小一点"),before);
        require(chinese.hasProperty("waveform") && static_cast<int>(chinese["waveform"])==0 && chinese.hasProperty("gain") && chinese.hasProperty("resonance"),"Chinese combined baseline failed");
        const auto square=juce::JSON::parse(R"({"waveform":2,"cutoff":8000,"resonance":1.2,"attack":0.01,"decay":0.2,"sustain":0.7,"release":0.5,"gain":0.4})");
        const auto tone=PromptService::baseline("darker",square);
        require(tone.hasProperty("cutoff") && tone.hasProperty("resonance"),"Darker did not coordinate filter controls");
        require(!tone.hasProperty("gain") && !tone.hasProperty("attack") && !tone.hasProperty("waveform"),"Brightness-only changed identity/timing/level");
        const auto warm=PromptService::baseline("warmer and softer",square);
        require(warm.hasProperty("waveform") && warm.hasProperty("attack") && warm.hasProperty("resonance") && warm.hasProperty("cutoff"),"Warm/soft plan missing coordinated controls");
        const auto keep=preserveRequestedParameters(warm,juce::String::fromUTF8("warmer and softer 保留波形 保留起音 保留尾音"));
        require(!keep.hasProperty("waveform") && !keep.hasProperty("attack") && !keep.hasProperty("release") && keep.hasProperty("cutoff"),"Protected controls changed in combined tone plan");
        const auto only=preserveRequestedParameters(warm,"warmer only cutoff");
        require(only.getDynamicObject()->getProperties().size()==1 && only.hasProperty("cutoff"),"Only-cutoff constraint lost");
        const auto negated=PromptService::baseline("not darker",square);
        require(!negated.hasProperty("cutoff") && !negated.hasProperty("resonance"),"Negated darkening changed filter");
        const auto invalidUnits=PromptService::baseline("cutoff 2 MHz, attack 40 Hz, gain 2 dB",before);
        require(!invalidUnits.hasProperty("cutoff") && !invalidUnits.hasProperty("attack") && !invalidUnits.hasProperty("gain"),"Invalid units silently treated as native values");
        const auto leadingDecimal=PromptService::baseline("attack .05 s, gain .4",before);
        require(std::abs(static_cast<double>(leadingDecimal["attack"])-.05)<1.e-6 && std::abs(static_cast<double>(leadingDecimal["gain"])-.4)<1.e-6,"Leading decimal values not parsed");
        const auto huge=PromptService::baseline("attack "+juce::String::repeatedString("9",1000)+" ms",before);
        require(!huge.hasProperty("attack"),"Overflowing numeric input accepted");
        require(describeParameterValue("gain",.4).contains("40.0 %"),"Gain review units wrong");
    }
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
    require(static_cast<float>(proposal["cutoff"])<10000 && proposal.hasProperty("resonance") && !proposal.hasProperty("gain"),"Coordinated tone mapping or level preservation failed");
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
    if (argc>1 && juce::String(argv[1])=="--service") {
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
        require(applyProposal(result.hasProperty("proposal") ? result["proposal"] : result,p.parameters),"AI service proposal invalid");
        require(p.parameters.getRawParameterValue("cutoff")->load()<10000,"AI did not darken sound");
        require(p.parameters.getRawParameterValue("release")->load()<.6f,"AI did not shorten release");
        std::cout<<"LIVE AI PASS: "<<reply<<"\n";
    }
    if (argc>1 && juce::String(argv[1])=="--release-ai") {
        const char* prompts[]={
            "square, cutoff 6000 Hz, attack 50 ms, decay 200 ms, sustain 70%, release 800 ms, resonance 1.1 Q, gain 50%",
            "更暗、更短，保留起音，保留波形",
            "保持尾音，声音更柔和",
            "Do not change any synth parameters. Only explain whether stereo width and reverb are supported.",
            "keep waveform, keep attack, keep release; make it darker and quieter",
            "Shorten release by half; preserve attack and preserve waveform",
            "Add reverb and stereo width; do not approximate them with other synth controls"};
        applyProposal(juce::JSON::parse(R"({"waveform":1,"cutoff":12000,"attack":0.005,"decay":0.1,"sustain":0.8,"release":0.15,"resonance":0.707,"gain":0.8})"),p.parameters);
        juce::Array<juce::var> history,records;
        juce::var captured;
        if(argc>2)captured=juce::JSON::parse(juce::File(argv[2]).loadFileAsString());
        for(int index=0;index<7;++index) {
            const auto before=parameterSnapshot(p.parameters);PromptService worker;
            const auto start=juce::Time::getMillisecondCounterHiRes();
            const bool replay=captured.isArray() && index<captured.getArray()->size();
            juce::String reply,message;bool received=false;
            if(replay){reply=juce::JSON::toString(captured[index]["response"]);received=true;}
            else {
                worker.submit(juce::String::fromUTF8(prompts[index]),juce::JSON::toString(before),"http://127.0.0.1:8765/propose",false,juce::JSON::toString(juce::var(history)));
                for(int n=0;n<5000;++n){render(p,audio,midi);if(worker.take(reply,message)){received=true;break;}juce::Thread::sleep(10);}
            }
            const auto response=juce::JSON::parse(reply);
            std::cout<<"RELEASE LIVE RECEIVED "<<index<<" "<<reply<<std::endl;
            require(received && (replay || message.contains("service response")) && response["provider"].toString()=="openai","Release acceptance did not receive actual OpenAI");
            require(snapshotMatches(before,p.parameters),"Provider modified parameters before Apply");
            const auto raw=response["proposal"];
            const auto safe=clampProposal(preserveRequestedParameters(completeExplicitWaveform(raw,juce::String::fromUTF8(prompts[index])),juce::String::fromUTF8(prompts[index])),p.parameters);
            if(index==3 || index==6) {
                require(raw.getDynamicObject() && raw.getDynamicObject()->getProperties().size()==0,"Unsupported-only request proposed edits");
                require(response["message"].toString().isNotEmpty(),"Explanation-only response empty");
                if(index==6)require(response["unsupported"].isArray() && response["unsupported"].getArray()->size()>0,"Unsupported action request not listed");
            } else {require(validateProposal(safe,p.parameters),"Release proposal invalid/empty");require(applyProposal(safe,p.parameters),"Release Apply failed");}
            const auto after=parameterSnapshot(p.parameters);
            std::cout<<"RELEASE LIVE OBSERVATION "<<index<<" "<<juce::JSON::toString(after,true)<<" response="<<reply<<std::endl;
            if(index==0) {
                for(auto v:std::initializer_list<std::pair<const char*,double>>{{"waveform",2},{"cutoff",6000},{"attack",.05},{"decay",.2},{"sustain",.7},{"release",.8},{"resonance",1.1},{"gain",.5}})
                    require(std::abs(static_cast<double>(after[juce::Identifier(v.first)])-v.second)<std::max(1.e-6,std::abs(v.second)*3.e-6),"Explicit live value mismatch");
            }
            if(index==1 || index==4) {
                require(static_cast<double>(after["cutoff"])<static_cast<double>(before["cutoff"]),"Live darkening did not lower cutoff");
                require(after["attack"]==before["attack"] && after["waveform"]==before["waveform"],"Protected live attack/waveform changed");
            }
            if(index==1)require(static_cast<double>(after["release"])<static_cast<double>(before["release"]) || static_cast<double>(after["decay"])<static_cast<double>(before["decay"]),"Live shorter changed neither decay nor release");
            if(index==5)require(static_cast<double>(after["release"])<static_cast<double>(before["release"]) && after["attack"]==before["attack"] && after["waveform"]==before["waveform"],"Explicit tail shortening or preservation failed");
            if(index==2 || index==4)require(after["release"]==before["release"],"Protected live tail changed");
            if(index==4)require(static_cast<double>(after["gain"])<static_cast<double>(before["gain"]),"Live quieter did not lower gain");
            auto row=juce::var(new juce::DynamicObject());row.getDynamicObject()->setProperty("prompt",juce::String::fromUTF8(prompts[index]));row.getDynamicObject()->setProperty("before",before);row.getDynamicObject()->setProperty("after",after);row.getDynamicObject()->setProperty("response",response);row.getDynamicObject()->setProperty("source",replay?"captured actual OpenAI response, replayed without another paid call":"new live OpenAI request");if(!replay)row.getDynamicObject()->setProperty("milliseconds",juce::Time::getMillisecondCounterHiRes()-start);records.add(row);
            auto turn=juce::var(new juce::DynamicObject());turn.getDynamicObject()->setProperty("intent",juce::String::fromUTF8(prompts[index]));turn.getDynamicObject()->setProperty("action","applied");turn.getDynamicObject()->setProperty("applied",safe);if(index!=3 && index!=6)history.add(turn);if(history.size()>4)history.remove(0);
            std::cout<<"RELEASE LIVE CASE PASS "<<index<<"\n";
        }
        require(juce::File::getCurrentWorkingDirectory().getChildFile("build/release-live-ai-results.json").replaceWithText(juce::JSON::toString(juce::var(records))),"Cannot save live acceptance results");
    }
    if (argc>2 && juce::String(argv[1])=="--cancel") {
        const auto before=parameterSnapshot(p.parameters);
        auto worker=std::make_unique<PromptService>();
        worker->submit("darker",juce::JSON::toString(before),argv[2],false);
        for(int i=0;i<50;++i){render(p,audio,midi);juce::Thread::sleep(10);}
        const auto started=juce::Time::getMillisecondCounterHiRes();worker.reset();
        const auto elapsed=juce::Time::getMillisecondCounterHiRes()-started;
        require(elapsed<2000,"Closing pending worker blocked message thread for >=2 seconds");
        require(snapshotMatches(before,p.parameters),"Cancelled request modified synth parameters");
        std::cout<<"CANCEL PASS: pending HTTP worker joined in "<<elapsed<<" ms; render continued; no state change\n";
    }
    if (argc>2 && juce::String(argv[1])=="--contract") {
        const auto before=parameterSnapshot(p.parameters);
        PromptService worker;
        worker.submit("soft sine pad, quieter",juce::JSON::toString(before),argv[2],false,
            R"([{"action":"applied","intent":"shorter","applied":{"release":0.2}}])",
            R"({"rms_dbfs":-30,"peak_dbfs":-20,"spectral_centroid_hz":500,"high_frequency_energy_ratio":0.1,"silent":false,"duration_seconds":4})");
        juce::String reply,message;bool ready=false;
        for(int i=0;i<1000;++i) {render(p,audio,midi);if(worker.take(reply,message)){ready=true;break;}juce::Thread::sleep(5);}
        const auto response=juce::JSON::parse(reply);
        require(ready && response.hasProperty("proposal") && response["message"].toString()=="Contract fixture","Structured contract missing");
        require(snapshotMatches(before,p.parameters),"Network changed audio parameters before apply");
        require(applyProposal(response["proposal"],p.parameters),"Structured contract apply failed");
        require(applyProposal(before,p.parameters) && snapshotMatches(before,p.parameters),"Structured contract undo failed");
        std::cout<<"CONTRACT PASS (mock provider, not a live OpenAI test)\n";
    }
    if (argc>2 && juce::String(argv[1])=="--reference") {
        const auto before=parameterSnapshot(p.parameters);
        auto options=juce::var(new juce::DynamicObject());
        options.getDynamicObject()->setProperty("settings",before);
        options.getDynamicObject()->setProperty("gate_seconds",.8);
        PromptService service;service.submit(juce::String(argv[2]),juce::JSON::toString(options),"http://127.0.0.1:8766/match",false);
        juce::String reply,message;bool ready=false;
        for(int i=0;i<4000;++i) { render(p,audio,midi);if(service.take(reply,message)) { ready=true;break; }juce::Thread::sleep(10); }
        const auto result=juce::JSON::parse(reply);
        if (!ready || !result.hasProperty("proposal")) std::cerr<<"Reference reply: "<<reply<<" status: "<<message<<" snapshot: "<<juce::JSON::toString(before)<<"\n";
        require(ready && result.hasProperty("proposal"),"Reference service did not return a patch");
        require(snapshotMatches(before,p.parameters),"Reference matching changed the live patch before Apply");
        require(applyProposal(result["proposal"],p.parameters),"Reference patch not valid for APVTS");
        require(applyProposal(before,p.parameters) && snapshotMatches(before,p.parameters),"Reference undo failed");
        std::cout<<"REFERENCE CLIENT PASS: "<<reply<<"\n";
    }
    if (argc>1 && juce::String(argv[1])=="--analysis") {
        PromptService service;
        service.submit("analyze",R"({"waveform":1,"attack":0.1,"decay":0.1,"sustain":0.8,"release":0.4,"cutoff":2000,"resonance":0.707,"gain":0.8})","http://127.0.0.1:8766/analyze",false);
        juce::String reply,message;bool ready=false;
        for(int i=0;i<1000;++i) {
            render(p,audio,midi);
            if(service.take(reply,message)) { ready=true; break; }
            juce::Thread::sleep(10);
        }
        const auto result=juce::JSON::parse(reply);
        require(ready && result.getDynamicObject()!=nullptr && result.hasProperty("cutoff"),"Live ML comparison failed");
        require(std::abs(static_cast<double>(result["actual"]["cutoff"])-2000)<.01,"ML service snapshot mismatch");
        std::cout<<"ML COMPARISON PASS: "<<reply<<"\n";
    }
    std::cout<<"PASS: state, proposal validation, MIDI, 4 waveforms, 4 rates, 3 block sizes, automation, release, C++ callback allocations=0\n";
}
