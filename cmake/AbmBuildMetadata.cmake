include_guard(GLOBAL)

if(NOT DEFINED ABM_PROJECT_ROOT)
    get_filename_component(ABM_PROJECT_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
endif()

set(ABM_MODEL_VERSION "0.1.0" CACHE STRING "Research model version written to run metadata.")

execute_process(
    COMMAND git rev-parse --short HEAD
    WORKING_DIRECTORY "${ABM_PROJECT_ROOT}"
    OUTPUT_VARIABLE ABM_GIT_COMMIT
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
if(NOT ABM_GIT_COMMIT)
    set(ABM_GIT_COMMIT "unknown")
endif()

execute_process(
    COMMAND git status --porcelain
    WORKING_DIRECTORY "${ABM_PROJECT_ROOT}"
    OUTPUT_VARIABLE ABM_GIT_STATUS
    OUTPUT_STRIP_TRAILING_WHITESPACE
    ERROR_QUIET
)
if(ABM_GIT_STATUS)
    set(ABM_GIT_DIRTY 1)
else()
    set(ABM_GIT_DIRTY 0)
endif()
