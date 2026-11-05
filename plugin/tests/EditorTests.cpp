#include "PluginEditor.h"
#include <iostream>
#include <cstdlib>

static void require(bool condition,const char* message) {
    if (!condition) { std::cerr<<message<<"\n";std::exit(1); }
}
class Driver final : private juce::Timer {
public:
    Driver(AISoundDesignerProcessor& p,AISoundDesignerEditor& e,bool testAnalysis,bool testExtended=false,bool testLive=false,bool testComparison=false):processor(p),editor(e),analysis(testAnalysis),extended(testExtended),live(testLive),comparison(testComparison) {
        for(int i=0;i<editor.getNumChildComponents();++i) {
            auto* c=editor.getChildComponent(i);
            if(auto* button=dynamic_cast<juce::TextButton*>(c)) {
                if(button->getButtonText()=="Propose changes") propose=button;
                if(button->getButtonText()=="Apply proposal") apply=button;
                if(button->getButtonText()=="Undo change") undo=button;
                if(button->getButtonText()=="Analyze sound") analyze=button;
            }
            if (live) if(auto* toggle=dynamic_cast<juce::ToggleButton*>(c))
                if(toggle->getButtonText()=="Live AI service") toggle->setToggleState(true,juce::dontSendNotification);
            if(auto* text=dynamic_cast<juce::TextEditor*>(c))
                if(text->getName()!="referenceGate") text->setText(extended ? "sine, cutoff 800 Hz, attack 50 ms, decay 200 ms, sustain 60%, release 1.2 s, gain 40%, resonance 0.8 Q" : "darker and shorter");
            if(auto* combo=dynamic_cast<juce::ComboBox*>(c))
                if(combo->getNumItems()==3) combo->setSelectedId(extended ? 2 : 3,juce::dontSendNotification);
        }
        require(propose && apply && undo && analyze,"Editor controls missing");
        saveStage("before"); propose->onClick();startTimer(25);
    }
    bool done() const { return completed; }
private:
    void timerCallback() override {
        require(++ticks<((live || stage==3)?2400:400),"Editor workflow timed out");
        if(stage==0 && apply->isEnabled()) {
            if (comparison) {
                bool measured=false;
                for(int i=0;i<editor.getNumChildComponents();++i)
                    if(auto* label=dynamic_cast<juce::Label*>(editor.getChildComponent(i)))
                        if(label->getText().contains("MIDI 48 render: centroid")) measured=true;
                if (!measured) return;
                require(std::abs(processor.parameters.getRawParameterValue("cutoff")->load()-2000)<.01,"Comparison modified live sound before Apply");
            }
            if (live) {
                bool received=false;
                for(int i=0;i<editor.getNumChildComponents();++i)
                    if(auto* label=dynamic_cast<juce::Label*>(editor.getChildComponent(i)))
                        if(label->getText().contains("AI service response received.")) received=true;
                require(received,"Live editor test used offline fallback");
            }
            saveStage("proposal"); apply->onClick();saveStage("applied");require(undo->isEnabled(),"Undo unavailable after apply");
            require(processor.parameters.getRawParameterValue("cutoff")->load()<1200,"Editor strength not applied");
            if (extended) {
                require(static_cast<int>(processor.parameters.getRawParameterValue("waveform")->load())==0,"UI dropped waveform");
                require(std::abs(processor.parameters.getRawParameterValue("gain")->load()-.4)<.001,"UI dropped gain");
                require(std::abs(processor.parameters.getRawParameterValue("decay")->load()-.2)<.001,"UI dropped decay");
                require(std::abs(processor.parameters.getRawParameterValue("sustain")->load()-.6)<.001,"UI dropped sustain");
                require(std::abs(processor.parameters.getRawParameterValue("release")->load()-1.2)<.001,"UI dropped release");
            }
            juce::File file=juce::File(AISD_EDITOR_PREVIEW);
            file.deleteFile(); auto stream=file.createOutputStream(); juce::PNGImageFormat png;
            require(stream && png.writeImageToStream(editor.createComponentSnapshot(editor.getLocalBounds()),*stream),"Could not save editor preview");
            undo->onClick();saveStage("undo");require(std::abs(processor.parameters.getRawParameterValue("cutoff")->load()-2000)<.01,"Editor undo failed");
            propose->onClick();auto* parameter=processor.parameters.getParameter("cutoff");
            parameter->setValueNotifyingHost(parameter->convertTo0to1(2400));stage=1;
        } else if(stage==1 && propose->isEnabled()) {
            require(!apply->isEnabled(),"Stale proposal remained applicable");
            require(std::abs(processor.parameters.getRawParameterValue("cutoff")->load()-2400)<.01,"Stale proposal modified sound");
            if(analysis) {
                for(const auto& item:std::initializer_list<std::pair<const char*,float>>{{"waveform",0},{"gain",.799734354f},{"resonance",1.2f}}) {
                    auto* parameter=processor.parameters.getParameter(item.first);parameter->setValueNotifyingHost(parameter->convertTo0to1(item.second));
                }
                analysisBefore=parameterSnapshot(processor.parameters);analyze->onClick();
                require(!analyze->isEnabled() && analyze->getButtonText()=="Analyzing...","Analyze has no immediate busy feedback");stage=2;
            }
            else finish();
        } else if(stage==2 && analyze->isEnabled()) {
            bool found=false;
            for(int i=0;i<editor.getNumChildComponents();++i)
                if(auto* label=dynamic_cast<juce::Label*>(editor.getChildComponent(i)))
                    if(label->getText().contains("Measured")) found=true;
            require(found,"Editor analysis did not display audio measurements");
            bool prominent=false;
            for(int i=0;i<editor.getNumChildComponents();++i)
                if(auto* label=dynamic_cast<juce::Label*>(editor.getChildComponent(i)))
                    if(label->getText().startsWith("Analysis ready:"))prominent=true;
            require(prominent && analyze->getButtonText()=="Analyze sound","Analysis completion feedback missing");
            require(snapshotMatches(analysisBefore,processor.parameters),"Analysis changed user settings");
            require(!apply->isEnabled(),"Measurement unexpectedly generated a proposal");
            std::cout<<"ANALYZE PASS: measurements ready, parameters unchanged, Apply disabled\n";
            const auto* reference=std::getenv("AISD_TEST_REFERENCE");
            if (!reference) { finish();return; }
            editor.beginReferenceMatch(juce::File(reference),1.4);
            require(!apply->isEnabled(),"Apply enabled while match pending");stage=3;ticks=0;
        } else if(stage==3 && !editor.referencePending) {
            require(apply->isEnabled(),"Match completed without an applicable proposal");
            require(snapshotMatches(analysisBefore,processor.parameters),"Match changed sound before Apply");
            apply->onClick();require(!snapshotMatches(analysisBefore,processor.parameters),"Match Apply did not change parameters");
            require(undo->isEnabled(),"Match Undo disabled");undo->onClick();
            require(snapshotMatches(analysisBefore,processor.parameters),"Match Undo failed to restore parameters");
            std::cout<<"MATCH PASS: proposal ready, Apply enabled, Apply changed parameters, Undo restored all parameters\n";finish();
        }
    }
    void saveStage(const char* stage) {
        auto base=juce::File(AISD_EDITOR_PREVIEW).getParentDirectory().getChildFile("demo-"+juce::String(stage));
        auto image=base.withFileExtension("png");image.deleteFile();auto stream=image.createOutputStream();juce::PNGImageFormat png;
        require(stream && png.writeImageToStream(editor.createComponentSnapshot(editor.getLocalBounds()),*stream),"Demo frame failed");
        require(base.withFileExtension("json").replaceWithText(juce::JSON::toString(parameterSnapshot(processor.parameters))),"Demo state failed");
    }
    void finish() { stopTimer();std::cout<<"EDITOR PASS: strength, apply, undo, stale snapshot"<<(analysis?", live audio measurements":"")<<(live?", actual OpenAI provider (no fallback)":"")<<(comparison?", actual before/after render measurements":"")<<"\n";completed=true; }
    AISoundDesignerProcessor& processor;AISoundDesignerEditor& editor;
    juce::TextButton *propose=nullptr,*apply=nullptr,*undo=nullptr,*analyze=nullptr;
    juce::var analysisBefore;bool analysis=false,extended=false,live=false,comparison=false,completed=false;int stage=0,ticks=0;
};
int main(int argc,char** argv) {
    juce::ScopedJuceInitialiser_GUI gui;AISoundDesignerProcessor processor;
    for(const auto& item:std::initializer_list<std::pair<const char*,float>>{{"waveform",1},{"cutoff",2000},{"attack",.1f},{"release",.4f}}) {
        auto* parameter=processor.parameters.getParameter(item.first);
        parameter->setValueNotifyingHost(parameter->convertTo0to1(item.second));
    }
    AISoundDesignerEditor editor(processor);
    editor.setVisible(true); // Offscreen component must be visible for JUCE hit testing.
    const auto layoutBefore=parameterSnapshot(processor.parameters);
    require(editor.isResizable(),"Editor does not advertise host resizing");
    for (auto size:std::initializer_list<std::pair<int,int>>{{720,660},{960,880},{1440,1320},{1000,700}}) {
        editor.setSize(size.first,size.second);
        for (int i=0;i<editor.getNumChildComponents();++i) {
            auto* c=editor.getChildComponent(i);
            if (!c->isVisible())continue;
            require(editor.getLocalBounds().expanded(1).contains(c->getBoundsInParent()),"Scaled control clipped outside editor");
            if (c->isEnabled() && (dynamic_cast<juce::TextButton*>(c) || dynamic_cast<juce::Slider*>(c)
                || dynamic_cast<juce::TextEditor*>(c) || dynamic_cast<juce::ComboBox*>(c))) {
                auto* hit=editor.getComponentAt(c->getBoundsInParent().getCentre());
                require(hit==c || c->isParentOf(hit),"Scaled control hit testing does not match its visible location");
            }
        }
        require(snapshotMatches(layoutBefore,processor.parameters),"UI resize changed synth parameters");
    }
    editor.setSize(720,660);
    {
        juce::File file=juce::File(AISD_EDITOR_PREVIEW).getSiblingFile("plugin-resize-small.png");
        auto stream=file.createOutputStream();juce::PNGImageFormat png;
        require(stream && png.writeImageToStream(editor.createComponentSnapshot(editor.getLocalBounds()),*stream),"Resize screenshot failed");
    }
    editor.setSize(960,880);
    Driver driver(processor,editor,argc>1 && juce::String(argv[1])=="--analysis",argc>1 && (juce::String(argv[1])=="--extended" || juce::String(argv[1])=="--live"),argc>1 && juce::String(argv[1])=="--live",argc>1 && juce::String(argv[1])=="--compare");
    // Pump JUCE timers on the message thread without NSApp taking over the test process.
    for(int tick=0;tick<2400 && !driver.done();++tick) {
        juce::Timer::callPendingTimersSynchronously();juce::Thread::sleep(25);
    }
    require(driver.done(),"Editor driver did not complete");
}
