#include "PluginEditor.h"

AISoundDesignerEditor::AISoundDesignerEditor(AISoundDesignerProcessor& p)
    : AudioProcessorEditor(p),owner(p),controls(p)
{
    addAndMakeVisible(useAI); addAndMakeVisible(controls); addAndMakeVisible(prompt); addAndMakeVisible(propose);
    addAndMakeVisible(apply); addAndMakeVisible(status);
    prompt.setTextToShowWhenEmpty("Try: darker, shorter, warmer",juce::Colours::grey);
    status.setText("Rule baseline. AI mode sends text + parameters via the local service.",juce::dontSendNotification);
    apply.setEnabled(false);
    propose.onClick=[this] {
        if (prompt.getText().trim().isEmpty()) return;
        auto snapshot=juce::var(new juce::DynamicObject());
        const char* ids[]={"waveform","attack","decay","sustain","release","cutoff","resonance","gain"};
        for (auto id:ids) snapshot.getDynamicObject()->setProperty(id,owner.parameters.getRawParameterValue(id)->load());
        service.submit(prompt.getText().substring(0,2000),juce::JSON::toString(snapshot),
            useAI.getToggleState() ? "http://127.0.0.1:8765/propose" : juce::String{});
        propose.setEnabled(false); apply.setEnabled(false);
        status.setText("Preparing proposal…",juce::dontSendNotification);
    };
    apply.onClick=[this] {
        if (!applyProposal(proposal,owner.parameters)) return;
        apply.setEnabled(false);
        status.setText("Applied. Listen and adjust the editable controls.",juce::dontSendNotification);
    };
    setSize(600,570); startTimerHz(10);
}
void AISoundDesignerEditor::resized()
{
    auto area=getLocalBounds().reduced(10);
    controls.setBounds(area.removeFromTop(340));
    useAI.setBounds(area.removeFromTop(28));
    prompt.setBounds(area.removeFromTop(32)); area.removeFromTop(8);
    auto buttons=area.removeFromTop(30);
    propose.setBounds(buttons.removeFromLeft(140)); apply.setBounds(buttons.removeFromLeft(160));
    status.setBounds(area);
}
void AISoundDesignerEditor::timerCallback()
{
    juce::String reply,message;
    if (!service.take(reply,message)) return;
    propose.setEnabled(true); proposal=clampProposal(juce::JSON::parse(reply),owner.parameters);
    const bool valid=validateProposal(proposal,owner.parameters);
    apply.setEnabled(valid);
    status.setText(message+"\n"+(valid ? juce::JSON::toString(proposal,true) : "No valid changes proposed."),juce::dontSendNotification);
}
