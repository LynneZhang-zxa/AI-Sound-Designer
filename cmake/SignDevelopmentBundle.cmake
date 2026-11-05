# Generated development bundles on iCloud Desktop can acquire Finder metadata.
# Remove only cosmetic/resource metadata, never quarantine/security attributes.
# Descendants matter too: clearing just the bundle root leaves invalid file attrs.
foreach(attempt RANGE 1 3)
    foreach(attribute com.apple.FinderInfo com.apple.ResourceFork)
        execute_process(COMMAND /usr/bin/xattr -dr "${attribute}" "${BUNDLE}"
            OUTPUT_QUIET ERROR_QUIET)
    endforeach()
    execute_process(COMMAND /usr/bin/codesign --force --sign - "${BUNDLE}"
        RESULT_VARIABLE sign_result OUTPUT_QUIET ERROR_VARIABLE sign_error)
    if(sign_result EQUAL 0)
        execute_process(COMMAND /usr/bin/codesign --verify --deep --strict "${BUNDLE}"
            RESULT_VARIABLE verify_result OUTPUT_QUIET ERROR_VARIABLE verify_error)
        if(verify_result EQUAL 0)
            return()
        endif()
    endif()
endforeach()
message(FATAL_ERROR "Development bundle signing/verification failed: ${BUNDLE}\n${sign_error}\n${verify_error}")
