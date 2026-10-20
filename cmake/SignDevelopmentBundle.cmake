# Finder may attach display metadata to a generated bundle on iCloud Desktop.
# Remove only that cosmetic attribute, never quarantine/security attributes.
execute_process(COMMAND /usr/bin/xattr -d com.apple.FinderInfo "${BUNDLE}"
    OUTPUT_QUIET ERROR_QUIET)
execute_process(COMMAND /usr/bin/codesign --force --sign - "${BUNDLE}"
    RESULT_VARIABLE sign_result)
if(NOT sign_result EQUAL 0)
    message(FATAL_ERROR "Could not sign development plugin bundle: ${BUNDLE}")
endif()
execute_process(COMMAND /usr/bin/codesign --verify --deep --strict "${BUNDLE}"
    RESULT_VARIABLE verify_result)
if(NOT verify_result EQUAL 0)
    message(FATAL_ERROR "Development plugin signature failed verification: ${BUNDLE}")
endif()
