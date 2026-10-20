#include "PluginProcessor.h"
#include <juce_audio_formats/juce_audio_formats.h>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <set>

// Standalone offline process only: allocation, JSON, and file I/O stay here.
namespace {
juce::var object() { return juce::var(new juce::DynamicObject()); }
void put(juce::var& o, const juce::Identifier& key, const juce::var& value) { o.getDynamicObject()->setProperty(key,value); }
void check(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
double number(const juce::var& v) {
    check(v.isInt() || v.isInt64() || v.isDouble(),"Expected numeric value");
    const auto value=static_cast<double>(v);
    check(std::isfinite(value),"Nonfinite numeric value");
    return value;
}
int integer(const juce::var& v) {
    const auto n=number(v);
    check(n>=0 && n<=10000000 && std::floor(n)==n,"Expected bounded nonnegative integer");
    return static_cast<int>(n);
}
juce::var parse(const juce::File& file) {
    check(file.existsAsFile(),"Missing input JSON");
    juce::var result;
    check(juce::JSON::parse(file.loadFileAsString(),result).wasOk() && result.getDynamicObject()!=nullptr,"Invalid input JSON");
    return result;
}
void save(const juce::File& file, const juce::var& value) {
    check(!file.exists(),"Refusing to overwrite output");
    check(file.replaceWithText(juce::JSON::toString(value,false,20)),"Could not write output JSON");
}
juce::var specification(AISoundDesignerProcessor& processor) {
    auto result=object(), parameters=object();
    put(result,"schema_version",1); put(result,"source","JUCE APVTS / createParameters()");
    for (auto* raw:processor.getParameters()) {
        auto* p=dynamic_cast<juce::RangedAudioParameter*>(raw);
        check(p!=nullptr,"Non-ranged parameter");
        const auto range=p->getNormalisableRange();
        auto item=object();
        put(item,"minimum",range.start); put(item,"maximum",range.end);
        put(item,"skew",range.skew); put(item,"interval",range.interval);
        put(item,"symmetric_skew",range.symmetricSkew);
        put(item,"default_normalized",p->getDefaultValue());
        juce::Array<juce::var> refs;
        for (int i=0;i<=32;++i) {
            const auto normalized=static_cast<float>(i)/32.f;
            const auto native=p->convertFrom0to1(normalized);
            auto ref=object(); put(ref,"raw",native); put(ref,"normalized",p->convertTo0to1(native));
            refs.add(ref);
        }
        put(item,"reference_conversions",refs);
        put(parameters,p->paramID,item);
    }
    put(result,"parameters",parameters);
    return result;
}
bool sameJson(const juce::var& a, const juce::var& b) {
    if (a.getDynamicObject()!=nullptr && b.getDynamicObject()!=nullptr) {
        const auto& props=a.getDynamicObject()->getProperties();
        if (props.size()!=b.getDynamicObject()->getProperties().size()) return false;
        for (const auto& item:props) if (!b.hasProperty(item.name) || !sameJson(item.value,b[item.name])) return false;
        return true;
    }
    if (a.isArray() && b.isArray()) {
        if (a.size()!=b.size()) return false;
        for (int i=0;i<a.size();++i) if (!sameJson(a[i],b[i])) return false;
        return true;
    }
    if ((a.isDouble() || a.isInt() || a.isInt64()) && (b.isDouble() || b.isInt() || b.isInt64()))
        return std::abs(static_cast<double>(a)-static_cast<double>(b)) <= 1.e-12*juce::jmax(1.0,std::abs(static_cast<double>(a)));
    return a==b;
}
void render(AISoundDesignerProcessor& processor, juce::var manifest, const juce::File& output) {
    check(!output.getChildFile("render_receipts.json").exists(),"Dataset already rendered");
    const auto& embedded=manifest["metadata"]["parameter_specification"];
    check(sameJson(embedded,specification(processor)),
          "Manifest parameter specification does not match current plugin");
    const auto config=manifest["metadata"]["config"]["renderer"];
    const auto rate=number(config["sample_rate"]);
    const int block=integer(config["block_size"]);
    const auto duration=number(config["duration_seconds"]);
    check(rate>=8000 && rate<=192000 && block>=1 && block<=4096 && duration>0 && duration<=32,"Invalid render configuration");
    const int frames=static_cast<int>(std::llround(duration*rate));
    const int warmup=static_cast<int>(std::llround(number(config["warmup_seconds"])*rate));
    const int on=static_cast<int>(std::llround(number(config["note_on_seconds"])*rate));
    const int off=static_cast<int>(std::llround(number(config["note_off_seconds"])*rate));
    const int note=integer(config["midi_note"]);
    const auto velocity=number(config["velocity"]);
    check(on>=0 && off>on && off<frames && warmup>=static_cast<int>(.02*rate) && warmup<=rate && note<=127 && velocity>0 && velocity<=1,
          "Invalid MIDI or warm-up configuration");
    check(integer(config["wav_bits"])==24,"Only PCM24 output is supported");
    // Keep owning var alive: array storage belongs to this local copy.
    auto rowsVar=manifest["examples"];
    auto* rows=rowsVar.getArray();
    check(rows!=nullptr && !rows->isEmpty() && rows->size()<=3000,"Offline renderer accepts 1..3000 explicit examples only");
    check(output.getChildFile("audio").createDirectory().wasOk(),"Cannot create audio directory");
    std::set<juce::String> ids;
    juce::Array<juce::var> receipts;
    for (auto& row:*rows) {
        const auto id=row["id"].toString();
        check(id.isNotEmpty() && id.containsOnly("abcdefghijklmnopqrstuvwxyz0123456789_") && ids.insert(id).second,"Unsafe or duplicate example ID");
        check(row["split"]==juce::var("train") || row["split"]==juce::var("validation") || row["split"]==juce::var("test"),"Unknown split");
        const auto requested=row["requested_parameters"];
        check(requested.getDynamicObject()!=nullptr && requested.getDynamicObject()->getProperties().size()==processor.getParameters().size(),"Incomplete parameter vector");
        for (const auto& item:requested.getDynamicObject()->getProperties()) {
            auto* p=processor.parameters.getParameter(item.name.toString());
            check(p!=nullptr,"Unknown parameter ID");
            const auto v=number(item.value);
            const auto range=p->getNormalisableRange();
            check(v>=range.start && v<=range.end && (range.interval<=0 || std::abs(std::floor(v)-v)<1.e-12),"Parameter outside legal range");
            p->setValueNotifyingHost(p->convertTo0to1(static_cast<float>(v)));
        }
        processor.prepareToPlay(rate,block);
        juce::AudioBuffer<float> buffer(2,block), rendered(1,frames);
        juce::MidiBuffer midi; midi.ensureSize(512);
        for (int position=0;position<warmup;) {
            const int count=juce::jmin(block,warmup-position);
            buffer.setSize(2,count,false,false,true);
            processor.processBlock(buffer,midi); position+=count;
        }
        for (int position=0;position<frames;) {
            const int count=juce::jmin(block,frames-position);
            buffer.setSize(2,count,false,false,true);
            if (on>=position && on<position+count) midi.addEvent(juce::MidiMessage::noteOn(1,note,static_cast<float>(velocity)),on-position);
            if (off>=position && off<position+count) midi.addEvent(juce::MidiMessage::noteOff(1,note),off-position);
            processor.processBlock(buffer,midi);
            for (int i=0;i<count;++i) check(std::isfinite(buffer.getSample(0,i)) && std::abs(buffer.getSample(0,i))<1.f,"Nonfinite or clipped render");
            rendered.copyFrom(0,position,buffer,0,0,count); position+=count;
        }
        auto applied=object(), targets=object(), normalized=object();
        for (auto* raw:processor.getParameters()) {
            auto* p=dynamic_cast<juce::RangedAudioParameter*>(raw);
            const auto native=processor.parameters.getRawParameterValue(p->paramID)->load();
            put(applied,p->paramID,native);
            if (p->paramID=="cutoff" || p->paramID=="attack" || p->paramID=="release") {
                put(targets,p->paramID,native); put(normalized,p->paramID,p->convertTo0to1(native));
            }
        }
        const auto audioPath="audio/"+id+".wav";
        const auto file=output.getChildFile(audioPath);
        check(!file.exists(),"Audio output already exists");
        std::unique_ptr<juce::OutputStream> stream=file.createOutputStream();
        check(stream!=nullptr,"Cannot open WAV output");
        juce::WavAudioFormat format;
        auto writer=format.createWriterFor(stream,juce::AudioFormatWriterOptions().withSampleRate(rate).withNumChannels(1).withBitsPerSample(24));
        check(writer!=nullptr && writer->writeFromAudioSampleBuffer(rendered,0,frames),"Cannot write WAV");
        writer.reset(); processor.releaseResources();
        auto receipt=object();
        put(receipt,"id",id); put(receipt,"split",row["split"]);
        put(receipt,"applied_parameters",applied); put(receipt,"targets",targets); put(receipt,"normalized_targets",normalized); put(receipt,"audio",audioPath);
        put(receipt,"midi_velocity_7bit",juce::MidiMessage::noteOn(1,note,static_cast<float>(velocity)).getVelocity());
        receipts.add(receipt);
    }
    auto result=object(); put(result,"examples",receipts);
    save(output.getChildFile("render_receipts.json"),result);
    std::cout<<"Rendered "<<rows->size()<<" explicit examples; no sampling or split assignment in C++.\n";
}
}
int main(int argc,char** argv) {
    try {
        juce::ScopedJuceInitialiser_GUI initialiseJuce;
        AISoundDesignerProcessor processor;
        if (argc==3 && juce::String(argv[1])=="--export-spec") save(juce::File::getCurrentWorkingDirectory().getChildFile(argv[2]),specification(processor));
        else if (argc==4 && juce::String(argv[1])=="--render") render(processor,parse(juce::File::getCurrentWorkingDirectory().getChildFile(argv[2])),juce::File::getCurrentWorkingDirectory().getChildFile(argv[3]));
        else throw std::runtime_error("Usage: DatasetRenderer --export-spec FILE | --render MANIFEST OUTPUT_DIRECTORY");
    } catch (const std::exception& error) { std::cerr<<error.what()<<"\n"; return 1; }
}
