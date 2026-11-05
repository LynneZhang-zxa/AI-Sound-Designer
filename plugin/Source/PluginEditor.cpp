#include "PluginEditor.h"
#include <cmath>

namespace
{
const juce::Colour background {0xff101317}, panel {0xff1a1f25}, line {0xff303943};
const juce::Colour ink {0xffe7ecef}, muted {0xff929fa9}, accent {0xff65e2c1};
juce::Font font(float size, bool bold = false)
{
    return juce::Font(juce::FontOptions(size, bold ? juce::Font::bold : juce::Font::plain));
}
void text(juce::Graphics& g, const juce::String& s, juce::Rectangle<int> r,
          float size, juce::Colour colour, bool bold = false)
{
    g.setColour(colour); g.setFont(font(size, bold));
    g.drawText(s, r, juce::Justification::centredLeft);
}
void section(juce::Graphics& g, juce::Rectangle<int> r, const juce::String& title,
             const juce::String& detail)
{
    g.setColour(panel); g.fillRoundedRectangle(r.toFloat(), 9.f);
    g.setColour(line); g.drawRoundedRectangle(r.toFloat().reduced(.5f), 9.f, 1.f);
    text(g, title, {r.getX()+18,r.getY()+12,r.getWidth()-36,22}, 13, ink, true);
    text(g, detail, {r.getX()+18,r.getY()+35,r.getWidth()-36,18}, 11, muted);
}
}

SynthLookAndFeel::SynthLookAndFeel()
{
    setColour(juce::Slider::textBoxTextColourId, ink);
    setColour(juce::Slider::textBoxBackgroundColourId, background);
    setColour(juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour(juce::ComboBox::backgroundColourId, background);
    setColour(juce::ComboBox::textColourId, ink);
    setColour(juce::ComboBox::outlineColourId, line);
    setColour(juce::PopupMenu::backgroundColourId, panel);
    setColour(juce::PopupMenu::textColourId, ink);
    setColour(juce::PopupMenu::highlightedBackgroundColourId, accent.darker(.6f));
    setColour(juce::TextButton::buttonColourId, juce::Colour(0xff29343d));
    setColour(juce::TextButton::textColourOffId, ink);
    setColour(juce::ToggleButton::textColourId, muted);
    setColour(juce::ToggleButton::tickColourId, accent);
    setColour(juce::TextEditor::backgroundColourId, background);
    setColour(juce::TextEditor::textColourId, ink);
    setColour(juce::TextEditor::outlineColourId, line);
    setColour(juce::TextEditor::focusedOutlineColourId, accent);
    setColour(juce::TextEditor::highlightColourId, accent.withAlpha(.3f));
}
void SynthLookAndFeel::drawRotarySlider(juce::Graphics& g, int x, int y, int w, int h,
                                       float position, float start, float end, juce::Slider&)
{
    auto r = juce::Rectangle<float>((float)x,(float)y,(float)w,(float)h).reduced(9.f);
    auto radius = juce::jmin(r.getWidth(),r.getHeight())*.5f;
    auto centre = r.getCentre();
    juce::Path track, value;
    track.addCentredArc(centre.x,centre.y,radius,radius,0,start,end,true);
    value.addCentredArc(centre.x,centre.y,radius,radius,0,start,start+position*(end-start),true);
    g.setColour(line); g.strokePath(track,juce::PathStrokeType(3.f));
    g.setColour(accent); g.strokePath(value,juce::PathStrokeType(3.f));
    g.setColour(juce::Colour(0xff252d35));
    g.fillEllipse(centre.x-radius+7,centre.y-radius+7,2*radius-14,2*radius-14);
    const float angle = start+position*(end-start);
    g.setColour(ink);
    g.drawLine(centre.x+std::sin(angle)*(radius*.4f),centre.y-std::cos(angle)*(radius*.4f),
               centre.x+std::sin(angle)*(radius*.68f),centre.y-std::cos(angle)*(radius*.68f),2.f);
}

AISoundDesignerEditor::AISoundDesignerEditor(AISoundDesignerProcessor& p)
    : AudioProcessorEditor(p), owner(p)
{
    setLookAndFeel(&theme);
    waveform.addItemList({"Sine", "Saw", "Square", "Triangle"},1);
    waveform.setTooltip("Oscillator waveform");
    addAndMakeVisible(waveform);
    waveformAttachment=std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment>(owner.parameters,"waveform",waveform);
    const char* ids[] = {"cutoff","resonance","gain","attack","decay","sustain","release"};
    const char* names[] = {"CUTOFF","RESONANCE","OUTPUT","ATTACK","DECAY","SUSTAIN","RELEASE"};
    for (size_t i=0;i<knobs.size();++i)
    {
        auto& knob=knobs[i];
        knob.setSliderStyle(juce::Slider::RotaryHorizontalVerticalDrag);
        knob.setTextBoxStyle(juce::Slider::TextBoxBelow,false,90,22);
        knob.setName(names[i]); knob.setTooltip(owner.parameters.getParameter(ids[i])->getName(64));
        attachments[i]=std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment>(owner.parameters,ids[i],knob);
        const bool time=i==3 || i==4 || i==6;
        knob.textFromValueFunction=[i,time](double v) {
            if(time) return v<1 ? juce::String(v*1000,1)+" ms" : juce::String(v,2)+" s";
            if(i==0) return v>=1000 ? juce::String(v/1000,2)+" kHz" : juce::String(v,0)+" Hz";
            if(i==2 || i==5) return juce::String(v*100,1)+" %";
            return juce::String(v,3)+" Q";
        };
        knob.valueFromTextFunction=[time,i](const juce::String& s) {
            auto v=s.getDoubleValue();
            if(time && s.containsIgnoreCase("ms")) return v/1000;
            if(i==0 && s.containsIgnoreCase("k")) return v*1000;
            if((i==2 || i==5) && s.contains("%")) return v/100;
            return v;
        };
        knob.updateText();
        addAndMakeVisible(knob);
        labels[i].setText(names[i],juce::dontSendNotification);
        labels[i].setFont(font(11,true)); labels[i].setColour(juce::Label::textColourId,muted);
        labels[i].setJustificationType(juce::Justification::centred);
        addAndMakeVisible(labels[i]);
    }
    addAndMakeVisible(useAI); addAndMakeVisible(prompt); addAndMakeVisible(propose);
    addAndMakeVisible(apply); addAndMakeVisible(status);
    for (auto* component : std::initializer_list<juce::Component*>{&strength,&undo,&analyze,&matchReference,&referenceGate,&gateLabel,&referenceNote,&review,&analysisStatus}) addAndMakeVisible(component);
    strength.addItemList({"Subtle", "Medium", "Strong"},1); strength.setSelectedId(2);
    strength.setTooltip("Change strength: subtle / medium / strong");
    review.setFont(font(12)); review.setColour(juce::Label::textColourId,ink);
    analysisStatus.setFont(font(11)); analysisStatus.setColour(juce::Label::textColourId,muted);
    analysisStatus.setText("Analyze any legal setting without changing sound. ML estimates appear only within trained conditions.",juce::dontSendNotification);
    gateLabel.setText("Gate ms",juce::dontSendNotification); gateLabel.setFont(font(11));
    gateLabel.setColour(juce::Label::textColourId,muted);
    referenceGate.setName("referenceGate"); referenceGate.setText("1400"); referenceGate.setInputRestrictions(5,"0123456789.");
    referenceGate.setTooltip("Reference MIDI note-on to note-off duration (150-3000 ms), not total WAV length.");
    referenceNote.addItem("Auto pitch",1);
    for (int note=36;note<=84;++note) referenceNote.addItem("MIDI "+juce::String(note),note-34);
    referenceNote.setSelectedId(1);
    undo.setEnabled(false);
    auto invalidate=[this] { if (!proposalPending && !referencePending) invalidateProposal(); };
    prompt.onTextChange=invalidate; strength.onChange=invalidate; useAI.onClick=invalidate;
    referenceGate.onTextChange=invalidate; referenceNote.onChange=invalidate;
    prompt.setFont(font(14)); prompt.setIndents(12,9);
    prompt.setTextToShowWhenEmpty("Try: soft sine pad, slow attack, longer tail, less resonance",muted);
    status.setFont(font(12)); status.setColour(juce::Label::textColourId,muted);
    status.setJustificationType(juce::Justification::topLeft);
    status.setText("Local rules ready. Enable Live AI to send your prompt and parameters to the service.",juce::dontSendNotification);
    apply.setEnabled(false);
    apply.setColour(juce::TextButton::buttonColourId,accent.darker(.65f));
    propose.onClick=[this] {
        if (prompt.getText().trim().isEmpty()) return;
        requestedSnapshot=parameterSnapshot(owner.parameters);
        requestedPrompt=prompt.getText().substring(0,1800);
        invalidateProposal();
        service.submit(requestedPrompt,juce::JSON::toString(requestedSnapshot),
            useAI.getToggleState() ? "http://127.0.0.1:8765/propose" : juce::String{},true,juce::JSON::toString(juce::var(designHistory)),
            measuredAudio.getDynamicObject() && snapshotMatches(analysisSnapshot,owner.parameters) ? juce::JSON::toString(measuredAudio) : juce::String{});
        proposalPending=true; propose.setEnabled(false); matchReference.setEnabled(false); apply.setEnabled(false);
        prompt.setEnabled(false); strength.setEnabled(false); useAI.setEnabled(false);
        review.setText({},juce::dontSendNotification);
        status.setText("Preparing editable parameter proposal...",juce::dontSendNotification);
    };
    apply.onClick=[this] {
        if (!snapshotMatches(requestedSnapshot,owner.parameters)) { invalidateProposal(); return; }
        auto previous=juce::var(new juce::DynamicObject());
        if (!proposal.getDynamicObject()) return;
        for (const auto& item:proposal.getDynamicObject()->getProperties())
            previous.getDynamicObject()->setProperty(item.name,owner.parameters.getRawParameterValue(item.name.toString())->load());
        if (!applyProposal(proposal,owner.parameters)) return;
        undoValues=previous; appliedSnapshot=parameterSnapshot(owner.parameters);
        auto turn=juce::var(new juce::DynamicObject());
        turn.getDynamicObject()->setProperty("intent",requestedPrompt.substring(0,400));
        turn.getDynamicObject()->setProperty("applied",proposal);
        turn.getDynamicObject()->setProperty("action","applied");
        designHistory.add(turn); if (designHistory.size()>4) designHistory.remove(0);
        apply.setEnabled(false); undo.setEnabled(true);
        status.setText("Applied to host parameters. Play MIDI in Logic to listen; Undo restores this change.",juce::dontSendNotification);
    };
    undo.onClick=[this] {
        if (!snapshotMatches(appliedSnapshot,owner.parameters)) { undo.setEnabled(false); return; }
        applyProposal(undoValues,owner.parameters);
        auto turn=juce::var(new juce::DynamicObject());turn.getDynamicObject()->setProperty("action","undo");
        turn.getDynamicObject()->setProperty("applied",undoValues);designHistory.add(turn);
        if (designHistory.size()>4) designHistory.remove(0);
        undo.setEnabled(false); invalidateProposal();
        status.setText("Restored values from before the last assistant change.",juce::dontSendNotification);
    };
    analyze.setTooltip("Render and measure the current synth patch at MIDI 48. Does not analyze an imported WAV or capture live audio; use Match reference WAV for a file.");
    analyze.onClick=[this] {
        analysisSnapshot=parameterSnapshot(owner.parameters);
        analysisService.submit("analyze",juce::JSON::toString(analysisSnapshot),"http://127.0.0.1:8766/analyze",false);
        analysisPending=true; analyze.setEnabled(false); analyze.setButtonText("Analyzing...");
        if (!proposalPending && !referencePending && !apply.isEnabled()) {
            status.setText("Analyzing current synth patch at MIDI 48 in the background. Sound is unchanged...",juce::dontSendNotification);
            status.setTooltip(status.getText());
        }
        analysisStatus.setText("Measuring a background render of your current settings; sound is unchanged...",juce::dontSendNotification);
    };
    matchReference.setTooltip("Match one dry sustained note. Gate is MIDI hold duration, not file duration. Review and apply the returned starting patch.");
    matchReference.onClick=[this] {
        const double gate=referenceGate.getText().getDoubleValue()/1000.;
        if (gate<.15 || gate>3.) {
            status.setText("Reference gate must be 150-3000 ms (MIDI note-on to note-off).",juce::dontSendNotification); return;
        }
        // Keep the picker owned by the editor; native panels can be hidden behind the AU host.
        referenceChooser=std::make_unique<juce::FileChooser>("Choose a dry single-note reference WAV",juce::File{},"*.wav",false,false,this);
        juce::Component::SafePointer<AISoundDesignerEditor> safe(this);
        referenceChooser->launchAsync(juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles,
            [safe,gate](const juce::FileChooser& chooser) {
                if (!safe || !chooser.getResult().existsAsFile()) return;
                auto& editor=*safe;
                editor.beginReferenceMatch(chooser.getResult(),gate);
            });
    };
    setResizable(true,true);
    setResizeLimits(720,660,1440,1320);
    getConstrainer()->setFixedAspectRatio(960.0/880.0);
    // Reserve room for the host header and macOS menu/Dock on laptop displays.
    float initialScale=1.f;
    if (const auto* display=juce::Desktop::getInstance().getDisplays().getPrimaryDisplay())
        initialScale=juce::jlimit(.75f,1.f,juce::jmin((display->userArea.getWidth()-40)/960.f,(display->userArea.getHeight()-140)/880.f));
    setSize(juce::roundToInt(960*initialScale),juce::roundToInt(880*initialScale));
    startTimerHz(10);
}
void AISoundDesignerEditor::beginReferenceMatch(const juce::File& file,double gate) {
    requestedSnapshot=parameterSnapshot(owner.parameters);
    requestedPrompt="Match reference WAV";
    auto options=juce::var(new juce::DynamicObject());
    options.getDynamicObject()->setProperty("settings",requestedSnapshot);
    options.getDynamicObject()->setProperty("gate_seconds",gate);
    if (referenceNote.getSelectedId()>1)
        options.getDynamicObject()->setProperty("midi_note",referenceNote.getSelectedId()+34);
    referenceService.submit(file.getFullPathName(),juce::JSON::toString(options),"http://127.0.0.1:8766/match",false);
    referencePending=true; invalidateProposal();
    propose.setEnabled(false); matchReference.setEnabled(false);
    referenceGate.setEnabled(false); referenceNote.setEnabled(false);
    prompt.setEnabled(false); strength.setEnabled(false); useAI.setEnabled(false);
    status.setText("Matching reference with bounded background synth search. Current sound is unchanged...",juce::dontSendNotification);
}

void AISoundDesignerEditor::invalidateProposal()
{
    ++comparisonSerial; proposal=juce::var{}; apply.setEnabled(false); review.setText({},juce::dontSendNotification);
}

AISoundDesignerEditor::~AISoundDesignerEditor()
{
    stopTimer(); setLookAndFeel(nullptr);
}
void AISoundDesignerEditor::paint(juce::Graphics& g)
{
    g.fillAll(background);
    g.addTransform(layoutTransform());
    text(g,"RESONANCA",{24,14,300,34},26,ink,true);
    text(g,"AI SOUND DESIGNER  /  POLYPHONIC SYNTHESIZER",{25,49,540,18},10,muted);
    text(g,"8 VOICES   /   v0.1",{782,28,160,22},11,accent,true);
    section(g,{20,86,338,250},"01   OSCILLATOR","Single oscillator / four waveforms");
    section(g,{370,86,366,250},"02   FILTER","State-variable low-pass");
    section(g,{748,86,192,250},"MASTER","Output level");
    section(g,{20,348,920,204},"03   AMPLITUDE ENVELOPE","ADSR / follows MIDI note duration");
    section(g,{20,564,920,296},"SOUND DESIGN ASSISTANT","Describe > review > apply > listen");
    drawDisplay(g,{38,155,302,116},false);
    drawDisplay(g,{38,412,310,115},true);
    text(g,"WAVEFORM PREVIEW",{44,273,280,16},9,muted);
    // A schematic response, not a measured spectrum or audio meter.
    auto r=juce::Rectangle<float>(390,153,326,49);
    g.setColour(background); g.fillRoundedRectangle(r,4);
    juce::Path curve;
    float bend=(float)owner.parameters.getParameter("cutoff")->getValue();
    for(int i=0;i<160;++i) {
        float x=(float)i/159, y=1.f/(1.f+std::exp(-(x-bend)*18.f));
        auto px=r.getX()+x*r.getWidth(),py=r.getY()+8+y*(r.getHeight()-16);
        if(i==0) curve.startNewSubPath(px,py); else curve.lineTo(px,py);
    }
    g.setColour(accent); g.strokePath(curve,juce::PathStrokeType(1.8f));
}
void AISoundDesignerEditor::drawDisplay(juce::Graphics& g, juce::Rectangle<float> r, bool envelope)
{
    g.setColour(background); g.fillRoundedRectangle(r,5);
    g.setColour(line.withAlpha(.6f));
    for(int i=1;i<8;++i) g.drawVerticalLine((int)(r.getX()+r.getWidth()*static_cast<float>(i)/8.f),r.getY(),r.getBottom());
    g.drawHorizontalLine((int)r.getCentreY(),r.getX(),r.getRight());
    auto inner=r.reduced(12); juce::Path path;
    if(envelope) {
        const float a=(float)owner.parameters.getParameter("attack")->getValue();
        const float d=(float)owner.parameters.getParameter("decay")->getValue();
        const float s=owner.parameters.getRawParameterValue("sustain")->load();
        const float release=(float)owner.parameters.getParameter("release")->getValue();
        const float ax=.05f+.25f*a,dx=ax+.05f+.2f*d,rx=.95f-.25f*release;
        path.startNewSubPath(inner.getX(),inner.getBottom());
        path.lineTo(inner.getX()+ax*inner.getWidth(),inner.getY());
        path.lineTo(inner.getX()+dx*inner.getWidth(),inner.getBottom()-s*inner.getHeight());
        path.lineTo(inner.getX()+rx*inner.getWidth(),inner.getBottom()-s*inner.getHeight());
        path.lineTo(inner.getRight(),inner.getBottom());
    } else {
        const int wave=(int)owner.parameters.getRawParameterValue("waveform")->load();
        for(int i=0;i<300;++i) {
            const float phase=2.f*(float)i/299, t=phase-std::floor(phase);
            const float v=wave==0 ? std::sin(juce::MathConstants<float>::twoPi*phase)
                         : wave==1 ? 2*t-1 : wave==2 ? (t<.5f?1.f:-1.f) : 1-4*std::abs(t-.5f);
            const float x=inner.getX()+inner.getWidth()*(float)i/299,y=inner.getCentreY()-v*inner.getHeight()*.4f;
            if(i==0) path.startNewSubPath(x,y); else path.lineTo(x,y);
        }
    }
    g.setColour(accent); g.strokePath(path,juce::PathStrokeType(2.f));
}
juce::AffineTransform AISoundDesignerEditor::layoutTransform() const
{
    const float scale=juce::jmin(getWidth()/960.f,getHeight()/880.f);
    return juce::AffineTransform::scale(scale).translated((getWidth()-960*scale)*.5f,(getHeight()-880*scale)*.5f);
}
void AISoundDesignerEditor::resized()
{
    waveform.setBounds(38,297,302,26);
    const juce::Rectangle<int> positions[]={{397,209,145,112},{565,209,145,112},{774,159,140,155},
        {365,414,130,116},{507,414,130,116},{649,414,130,116},{791,414,130,116}};
    for(size_t i=0;i<knobs.size();++i) {
        auto r=positions[i]; labels[i].setBounds(r.removeFromTop(18)); knobs[i].setBounds(r);
    }
    useAI.setBounds(765,577,155,28); strength.setBounds(605,577,150,28);
    prompt.setBounds(38,622,555,37);
    propose.setBounds(605,622,150,37); apply.setBounds(767,622,155,37);
    review.setBounds(38,668,705,60); undo.setBounds(767,679,155,34);
    status.setBounds(38,729,884,44);
    matchReference.setBounds(38,779,185,32);gateLabel.setBounds(235,779,55,32);referenceGate.setBounds(290,779,75,32);
    referenceNote.setBounds(377,779,160,32);analyze.setBounds(767,779,155,32);
    analysisStatus.setBounds(38,817,884,38);
    // Share one transform between painting and controls, so hit testing follows
    // the same coordinates as the scaled artwork. Leave the JUCE resize grip alone.
    const auto transform=layoutTransform();
    for (auto* c:std::initializer_list<juce::Component*>{&waveform,&prompt,&useAI,&propose,&apply,&strength,&undo,&analyze,&matchReference,&referenceGate,&gateLabel,&referenceNote,&status,&review,&analysisStatus})
        c->setTransform(transform);
    for (auto& c:knobs)c.setTransform(transform);
    for (auto& c:labels)c.setTransform(transform);
}
void AISoundDesignerEditor::timerCallback()
{
    repaint(); // Message-thread-only schematic previews follow host automation.
    if (apply.isEnabled() && !snapshotMatches(requestedSnapshot,owner.parameters)) {
        invalidateProposal(); status.setText("Parameters changed; generate a fresh proposal.",juce::dontSendNotification);
    }
    if (undo.isEnabled() && !snapshotMatches(appliedSnapshot,owner.parameters)) undo.setEnabled(false);
    juce::String reply,message;
    if (service.take(reply,message)) {
        proposalPending=false; propose.setEnabled(true); matchReference.setEnabled(true); prompt.setEnabled(true); strength.setEnabled(true); useAI.setEnabled(true);
        if (!snapshotMatches(requestedSnapshot,owner.parameters)) {
            invalidateProposal(); status.setText("Sound changed while waiting. Generate a fresh proposal.",juce::dontSendNotification);
        } else {
            const double factor=strength.getSelectedId()==1 ? .5 : strength.getSelectedId()==3 ? 2.5 : 1.;
            const auto response=juce::JSON::parse(reply);
            const auto raw=response.hasProperty("proposal") ? response["proposal"] : response;
            auto explanation=response.getProperty("message",juce::var{}).toString();
            if (auto* unsupported=response["unsupported"].getArray())
                for (const auto& item:*unsupported) explanation+=" [Unsupported: "+item.toString()+"]";
            const auto completed=completeExplicitWaveform(raw,requestedPrompt);
            if (completed.hasProperty("waveform") && (!raw.hasProperty("waveform") || static_cast<int>(completed["waveform"])!=static_cast<int>(raw["waveform"])))
                explanation="Explicit waveform selection resolved as "+describeParameterValue("waveform",completed["waveform"])+"; review the parameter preview.";
            proposal=scaledDesignProposal(preserveRequestedParameters(completed,requestedPrompt),requestedSnapshot,factor,owner.parameters);
            const bool valid=validateProposal(proposal,owner.parameters); apply.setEnabled(valid);
            juce::String summary;
            if (valid) for (const auto& item:proposal.getDynamicObject()->getProperties()) {
                const auto id=item.name.toString();
                summary+=id+": "+describeParameterValue(id,requestedSnapshot[juce::Identifier(id)])+" -> "+
                    describeParameterValue(id,item.value)+"  ";
            }
            review.setText(summary,juce::dontSendNotification);
            status.setText(message+" "+explanation+(valid ? " Review, then apply." : " No parameter changes."),juce::dontSendNotification);
            status.setTooltip(status.getText());review.setTooltip(summary);
            if (valid) {
                auto after=juce::JSON::parse(juce::JSON::toString(requestedSnapshot));
                for (const auto& item:proposal.getDynamicObject()->getProperties()) after.getDynamicObject()->setProperty(item.name,item.value);
                auto pair=juce::var(new juce::DynamicObject());
                pair.getDynamicObject()->setProperty("before",requestedSnapshot);
                pair.getDynamicObject()->setProperty("after",after);
                pair.getDynamicObject()->setProperty("request_id",++comparisonSerial);
                comparisonService.submit("compare",juce::JSON::toString(pair),"http://127.0.0.1:8766/compare",false);
                analysisStatus.setText("Comparing before/after background renders at MIDI 48; current sound unchanged. Not a perceptual rating.",juce::dontSendNotification);
            }
        }
    }
    if (comparisonService.take(reply,message)) {
        const auto result=juce::JSON::parse(reply);
        if (apply.isEnabled() && snapshotMatches(requestedSnapshot,owner.parameters)) {
            if (result.hasProperty("request_id") && static_cast<int>(result["request_id"])==comparisonSerial) {
                const auto a=result["before"],b=result["after"];
                auto metric=[&](const char* id,const char* unit) {
                    if (a[id].isVoid() || b[id].isVoid()) return juce::String("n/a");
                    return juce::String(static_cast<double>(a[id]),1)+" -> "+juce::String(static_cast<double>(b[id]),1)+unit;
                };
                juce::String note=". Raw levels; not a quality score.";
                if (!a["rms_dbfs"].isVoid() && !b["rms_dbfs"].isVoid()
                    && std::abs(static_cast<double>(b["rms_dbfs"])-static_cast<double>(a["rms_dbfs"]))>1.5)
                    note+=" Level also changes: compare at matched listening volume.";
                if (static_cast<int>(requestedSnapshot["waveform"])==0 && (!proposal.hasProperty("waveform") || static_cast<int>(proposal["waveform"])==0))
                    note+=" Sine has little harmonic brightness to remove.";
                analysisStatus.setText("MIDI 48 render: centroid "+metric("spectral_centroid_hz"," Hz")+
                    " | RMS "+metric("rms_dbfs"," dBFS")+note,juce::dontSendNotification);
            } else if (!result.hasProperty("request_id"))
                analysisStatus.setText("Before/after render comparison unavailable; start the current analysis service. Parameter preview remains available.",juce::dontSendNotification);
            analysisStatus.setTooltip(analysisStatus.getText());
        }
    }
    if (referenceService.take(reply,message)) {
        referencePending=false;propose.setEnabled(true);matchReference.setEnabled(true);
        referenceGate.setEnabled(true);referenceNote.setEnabled(true);prompt.setEnabled(true);strength.setEnabled(true);useAI.setEnabled(true);
        const auto result=juce::JSON::parse(reply);
        const auto raw=result.getProperty("proposal",juce::var{});
        bool allowed=raw.getDynamicObject()!=nullptr && raw.getDynamicObject()->getProperties().size()>0;
        if (allowed) for (const auto& item:raw.getDynamicObject()->getProperties()) {
            const auto id=item.name.toString();
            if (id!="waveform" && id!="cutoff" && id!="attack" && id!="release" && id!="decay" && id!="sustain" && id!="resonance") allowed=false;
        }
        if (!snapshotMatches(requestedSnapshot,owner.parameters)) {
            invalidateProposal();status.setText("Sound changed during matching. Match again to preserve the current patch.",juce::dontSendNotification);
        } else if (allowed && validateProposal(clampProposal(raw,owner.parameters),owner.parameters)) {
            proposal=clampProposal(raw,owner.parameters);apply.setEnabled(true);
            juce::String summary;
            for (const auto& item:proposal.getDynamicObject()->getProperties()) {
                const auto id=item.name.toString();
                summary+=id+": "+describeParameterValue(id,requestedSnapshot[juce::Identifier(id)])+" -> "+describeParameterValue(id,item.value)+"  ";
            }
            review.setTooltip(summary);
            review.setText(summary,juce::dontSendNotification);
            status.setText("Search score "+juce::String(static_cast<double>(result["baseline"]["score"]),3)+" -> "+
                juce::String(static_cast<double>(result["matched"]["score"]),3)+" | audition at MIDI "+result["midi_note"].toString()+
                ". Review, Apply, play MIDI; Undo available. Starting patch, not an exact clone.",juce::dontSendNotification);
        } else {
            invalidateProposal();const auto error=result.getProperty("error",juce::var{}).toString();
            status.setText(error.isNotEmpty()?error:"Reference matcher unavailable. Start scripts/start-plugin-analysis.sh.",juce::dontSendNotification);
        }
        status.setTooltip(status.getText());
    }
    if (analysisService.take(reply,message)) {
        analysisPending=false; analyze.setEnabled(true); analyze.setButtonText("Analyze sound");
        const auto result=juce::JSON::parse(reply);
        juce::String summary;
        const auto audio=result.getProperty("audio_summary",juce::var{});
        const auto ml=result.getProperty("ml",juce::var{});
        if (audio.getDynamicObject()) {
            measuredAudio=juce::var(new juce::DynamicObject());
            for (const auto* id:{"rms_dbfs","peak_dbfs","spectral_centroid_hz","high_frequency_energy_ratio","silent","duration_seconds"})
                measuredAudio.getDynamicObject()->setProperty(id,audio[id]);
            if (static_cast<bool>(audio["silent"])) summary="Measured: silence (output is zero).";
            else {
                auto number=[&audio](const char* id) {
                    const auto value=audio[id];
                    return (value.isDouble() || value.isInt()) && std::isfinite(static_cast<double>(value))
                        ? juce::String(static_cast<double>(value),1) : juce::String("n/a");
                };
                summary="Measured RMS "+number("rms_dbfs")+" dBFS | Peak "+number("peak_dbfs")+
                    " dBFS | Centroid "+number("spectral_centroid_hz")+" Hz";
            }
            if (ml["status"].toString()=="within_training_conditions") {
                const auto estimates=ml["estimates"];
                summary+="\nML/DSP estimates: cutoff "+juce::String(static_cast<double>(estimates["cutoff"]),1)+
                    " Hz, attack "+juce::String(static_cast<double>(estimates["attack"])*1000.,1)+
                    " ms, release "+juce::String(static_cast<double>(estimates["release"])*1000.,1)+" ms";
            } else summary+="\nCurrent synth render at MIDI 48; no live audio captured. Optional ML estimates omitted.";
            if (!snapshotMatches(analysisSnapshot,owner.parameters)) summary+=" [earlier snapshot]";
        }
        const auto error=result.getProperty("error",juce::var{}).toString().substring(0,500);
        analysisStatus.setText(summary.isNotEmpty() ? summary : (error.isNotEmpty() ? error :
            "Analysis service unavailable. Run scripts/start-plugin-analysis.sh."),juce::dontSendNotification);
        analysisStatus.setTooltip(analysisStatus.getText());
        if (!proposalPending && !referencePending && !apply.isEnabled()) {
            status.setText(summary.isNotEmpty() ? "Analysis ready: "+summary.upToFirstOccurrenceOf("\n",false,false)+". To copy a sound, choose Match reference WAV, then Apply proposal."
                : analysisStatus.getText(),juce::dontSendNotification);
            status.setTooltip(analysisStatus.getText());
        }
    }
}
