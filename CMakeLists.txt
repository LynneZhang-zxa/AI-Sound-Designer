cmake_minimum_required(VERSION 3.22)
project(AISoundDesigner VERSION 0.1.0 LANGUAGES C CXX)

if(NOT APPLE)
    message(FATAL_ERROR "This milestone currently targets macOS AU and VST3 only.")
endif()

include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG 8.0.12
    GIT_SHALLOW TRUE)
FetchContent_MakeAvailable(JUCE)

juce_add_plugin(AISoundDesigner
    COMPANY_NAME "AI Sound Designer"
    BUNDLE_ID "com.aisounddesigner.synth"
    PLUGIN_MANUFACTURER_CODE Aisd
    PLUGIN_CODE Asd1
    PRODUCT_NAME "AI Sound Designer"
    IS_SYNTH TRUE
    NEEDS_MIDI_INPUT TRUE
    NEEDS_MIDI_OUTPUT FALSE
    IS_MIDI_EFFECT FALSE
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE
    COPY_PLUGIN_AFTER_BUILD FALSE
    FORMATS AU VST3
    AU_MAIN_TYPE kAudioUnitType_MusicDevice
    VST3_CATEGORIES Instrument Synth)

target_sources(AISoundDesigner PRIVATE
    plugin/Source/PluginProcessor.cpp
    plugin/Source/PluginEditor.cpp
    plugin/Source/synth/SynthVoice.cpp
    plugin/Source/synth/SynthEngine.cpp)
target_compile_features(AISoundDesigner PRIVATE cxx_std_17)
target_compile_definitions(AISoundDesigner PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)
target_link_libraries(AISoundDesigner PRIVATE
    juce::juce_audio_processors
    PUBLIC juce::juce_recommended_config_flags
           juce::juce_recommended_warning_flags)
