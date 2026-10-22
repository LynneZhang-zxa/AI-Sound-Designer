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
            return juce::String(v,2)+" Q";
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
    prompt.setFont(font(14)); prompt.setIndents(12,9);
    prompt.setTextToShowWhenEmpty("Describe a change... darker, shorter, warmer",muted);
    status.setFont(font(12)); status.setColour(juce::Label::textColourId,muted);
    status.setJustificationType(juce::Justification::topLeft);
    status.setText("Local rules ready. Enable Live AI to send your prompt and parameters to the service.",juce::dontSendNotification);
    apply.setEnabled(false);
    apply.setColour(juce::TextButton::buttonColourId,accent.darker(.65f));
    propose.onClick=[this] {
        if (prompt.getText().trim().isEmpty()) return;
        auto snapshot=juce::var(new juce::DynamicObject());
        const char* parameterIds[]={"waveform","attack","decay","sustain","release","cutoff","resonance","gain"};
        for (auto id:parameterIds) snapshot.getDynamicObject()->setProperty(id,owner.parameters.getRawParameterValue(id)->load());
        service.submit(prompt.getText().substring(0,2000),juce::JSON::toString(snapshot),
            useAI.getToggleState() ? "http://127.0.0.1:8765/propose" : juce::String{});
        propose.setEnabled(false); apply.setEnabled(false);
        status.setText("Preparing proposal...",juce::dontSendNotification);
    };
    apply.onClick=[this] {
        if (!applyProposal(proposal,owner.parameters)) return;
        apply.setEnabled(false);
        status.setText("Applied. Listen and adjust the editable controls.",juce::dontSendNotification);
    };
    setSize(960,730); startTimerHz(10);
}
AISoundDesignerEditor::~AISoundDesignerEditor()
{
    stopTimer(); setLookAndFeel(nullptr);
}
void AISoundDesignerEditor::paint(juce::Graphics& g)
{
    g.fillAll(background);
    text(g,"RESONANCA",{24,14,300,34},26,ink,true);
    text(g,"AI SOUND DESIGNER  /  POLYPHONIC SYNTHESIZER",{25,49,540,18},10,muted);
    text(g,"8 VOICES   /   v0.1",{782,28,160,22},11,accent,true);
    section(g,{20,86,338,250},"01   OSCILLATOR","Single oscillator / four waveforms");
    section(g,{370,86,366,250},"02   FILTER","State-variable low-pass");
    section(g,{748,86,192,250},"MASTER","Output level");
    section(g,{20,348,920,204},"03   AMPLITUDE ENVELOPE","ADSR / follows MIDI note duration");
    section(g,{20,564,920,146},"SOUND DESIGN ASSISTANT","Describe > review > apply > listen");
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
void AISoundDesignerEditor::resized()
{
    waveform.setBounds(38,297,302,26);
    const juce::Rectangle<int> positions[]={{397,209,145,112},{565,209,145,112},{774,159,140,155},
        {365,414,130,116},{507,414,130,116},{649,414,130,116},{791,414,130,116}};
    for(size_t i=0;i<knobs.size();++i) {
        auto r=positions[i]; labels[i].setBounds(r.removeFromTop(18)); knobs[i].setBounds(r);
    }
    useAI.setBounds(765,577,155,28);
    prompt.setBounds(38,622,555,37);
    propose.setBounds(605,622,150,37); apply.setBounds(767,622,155,37);
    status.setBounds(38,671,884,32);
}
void AISoundDesignerEditor::timerCallback()
{
    repaint(); // Message-thread-only schematic previews follow host automation.
    juce::String reply,message;
    if (!service.take(reply,message)) return;
    propose.setEnabled(true); proposal=clampProposal(juce::JSON::parse(reply),owner.parameters);
    const bool valid=validateProposal(proposal,owner.parameters);
    apply.setEnabled(valid);
    status.setText(message+"  "+(valid ? juce::JSON::toString(proposal,true) : "No valid changes proposed."),juce::dontSendNotification);
    status.setTooltip(status.getText());
}
