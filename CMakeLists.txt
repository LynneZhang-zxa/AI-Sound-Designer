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
    EDITOR_WANTS_KEYBOARD_FOCUS TRUE
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
    juce::juce_dsp
    PUBLIC juce::juce_recommended_config_flags
           juce::juce_recommended_warning_flags)

include(CTest)
if(BUILD_TESTING)
    add_executable(SynthTests)
    target_sources(SynthTests PRIVATE plugin/tests/SynthTests.cpp)
    target_include_directories(SynthTests PRIVATE plugin/Source)
    target_compile_features(SynthTests PRIVATE cxx_std_17)
    target_compile_definitions(SynthTests PRIVATE JucePlugin_Name="AI Sound Designer" JUCE_WEB_BROWSER=0 JUCE_USE_CURL=0)
    target_link_libraries(SynthTests PRIVATE AISoundDesigner)
    target_include_directories(SynthTests PRIVATE "${juce_SOURCE_DIR}/modules")
    add_test(NAME SynthTests COMMAND SynthTests)
endif()

# Optional macOS 26+ on-device AI helper; never linked into the audio plugin.
find_program(AISD_SWIFTC swiftc)
if(AISD_SWIFTC)
    add_custom_command(OUTPUT "${CMAKE_BINARY_DIR}/LocalModel"
        COMMAND "${AISD_SWIFTC}" -parse-as-library -O
            -module-cache-path "${CMAKE_BINARY_DIR}/swift-cache"
            "${CMAKE_SOURCE_DIR}/service/LocalModel.swift" -o "${CMAKE_BINARY_DIR}/LocalModel"
        DEPENDS service/LocalModel.swift VERBATIM)
    add_custom_target(LocalAIModel DEPENDS "${CMAKE_BINARY_DIR}/LocalModel")
endif()

# Relinking an AU invalidates its previous development signature.
add_custom_command(TARGET AISoundDesigner_AU POST_BUILD
    COMMAND "${CMAKE_COMMAND}" "-DBUNDLE=$<TARGET_BUNDLE_DIR:AISoundDesigner_AU>"
        -P "${CMAKE_SOURCE_DIR}/cmake/SignDevelopmentBundle.cmake"
    VERBATIM)
