include_guard(GLOBAL)

option(ABM_WARNINGS_AS_ERRORS "Treat project compiler warnings as errors." OFF)
option(ABM_ENABLE_SANITIZERS
       "Enable AddressSanitizer and UndefinedBehaviorSanitizer for supported compilers." OFF)

function(abm_apply_project_warnings target_name)
    if(MSVC)
        target_compile_options(${target_name} PRIVATE /W4)
        if(ABM_WARNINGS_AS_ERRORS)
            target_compile_options(${target_name} PRIVATE /WX)
        endif()
    else()
        target_compile_options(${target_name} PRIVATE -Wall -Wextra -Wpedantic)
        if(ABM_WARNINGS_AS_ERRORS)
            target_compile_options(${target_name} PRIVATE -Werror)
        endif()
    endif()
endfunction()

function(abm_apply_project_sanitizers target_name)
    if(ABM_ENABLE_SANITIZERS AND NOT MSVC)
        target_compile_options(${target_name} PRIVATE -fsanitize=address,undefined
                                                      -fno-omit-frame-pointer)
        target_link_options(${target_name} PRIVATE -fsanitize=address,undefined)
    endif()
endfunction()
