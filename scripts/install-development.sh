#!/bin/bash
set -eu
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
install_bundle() {
    local format="$1" folder="$2" extension="$3"
    local source="$repo_dir/build/AISoundDesigner_artefacts/Release/$format/AI Sound Designer.$extension"
    local destination="$HOME/Library/Audio/Plug-Ins/$folder/AI Sound Designer.$extension"
    if [ ! -d "$source" ]; then
        echo "Missing build: $source" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$destination")"
    # Finder/iCloud cosmetic metadata can invalidate strict bundle verification.
    ditto --norsrc --noextattr "$source" "$destination"
    cmake "-DBUNDLE=$destination" -P "$repo_dir/cmake/SignDevelopmentBundle.cmake"
}
install_bundle AU Components component
install_bundle VST3 VST3 vst3
auval -v aumu Asd1 Aisd > "$repo_dir/build/auval.log" 2>&1
echo "Installed and signature-verified AU/VST3. AU validation passed; see build/auval.log."
