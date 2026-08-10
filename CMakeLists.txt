cmake_minimum_required(VERSION 3.16)

project(BABM LANGUAGES CXX)

set(ABM_PROJECT_ROOT "${CMAKE_CURRENT_SOURCE_DIR}")
list(APPEND CMAKE_MODULE_PATH "${ABM_PROJECT_ROOT}/cmake")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(AbmCompilerOptions)
include(AbmBuildMetadata)

add_library(abm_project_includes INTERFACE)
target_include_directories(abm_project_includes
    INTERFACE
        "${ABM_PROJECT_ROOT}"
        "${ABM_PROJECT_ROOT}/src"
)

add_library(abm_build_metadata INTERFACE)
target_compile_definitions(abm_build_metadata
    INTERFACE
        ABM_MODEL_VERSION="${ABM_MODEL_VERSION}"
        ABM_GIT_COMMIT="${ABM_GIT_COMMIT}"
        ABM_GIT_DIRTY=${ABM_GIT_DIRTY}
        ABM_COMPILER_ID="${CMAKE_CXX_COMPILER_ID}"
        ABM_COMPILER_VERSION="${CMAKE_CXX_COMPILER_VERSION}"
)

#
# Domain libraries are declared here without sources; each directory under src/
# adds its own via target_sources(). The dependency edges below are therefore
# the whole architecture in one place, while the file lists stay next to the
# files. Nothing in a lower layer may link a higher one.
#
function(abm_add_domain_library target_name)
    add_library(${target_name} STATIC)
    target_compile_features(${target_name} PUBLIC cxx_std_17)
    target_link_libraries(${target_name} PUBLIC abm_project_includes)
    abm_apply_project_warnings(${target_name})
    abm_apply_project_sanitizers(${target_name})
endfunction()

abm_add_domain_library(abm_utility)

abm_add_domain_library(abm_config)
target_link_libraries(abm_config PRIVATE abm_utility)

abm_add_domain_library(abm_market)
target_link_libraries(abm_market PRIVATE abm_utility)

abm_add_domain_library(abm_behavioural_finance)
target_link_libraries(abm_behavioural_finance
    PUBLIC
        abm_config
        abm_utility
)

abm_add_domain_library(abm_agents)
target_link_libraries(abm_agents
    PUBLIC
        abm_behavioural_finance
        abm_config
        abm_market
        abm_utility
)

add_library(abm_results INTERFACE)
target_compile_features(abm_results INTERFACE cxx_std_17)
target_link_libraries(abm_results
    INTERFACE
        abm_project_includes
        abm_config
        abm_market
)

abm_add_domain_library(abm_simulation)
target_link_libraries(abm_simulation
    PUBLIC
        abm_agents
        abm_config
        abm_market
        abm_results
        abm_utility
)

abm_add_domain_library(abm_metrics)
target_link_libraries(abm_metrics PUBLIC abm_results)

abm_add_domain_library(abm_output)
target_link_libraries(abm_output
    PUBLIC
        abm_config
        abm_metrics
        abm_results
    PRIVATE
        abm_build_metadata
)

abm_add_domain_library(abm_archive)
target_link_libraries(abm_archive
    PUBLIC
        abm_config
        abm_output
)

abm_add_domain_library(abm_application)
target_link_libraries(abm_application
    PUBLIC
        abm_archive
        abm_config
        abm_metrics
        abm_output
        abm_simulation
        abm_utility
)

add_library(abm_core INTERFACE)
target_compile_features(abm_core INTERFACE cxx_std_17)
target_link_libraries(abm_core
    INTERFACE
        abm_application
        abm_archive
        abm_output
        abm_metrics
        abm_simulation
        abm_agents
        abm_behavioural_finance
        abm_market
        abm_config
        abm_results
        abm_utility
)

add_subdirectory(src)

add_executable(simulate app/simulate/main.cpp)
target_link_libraries(simulate PRIVATE abm_core)
abm_apply_project_warnings(simulate)
abm_apply_project_sanitizers(simulate)

include(CTest)
if(BUILD_TESTING)
    add_subdirectory(tests)
endif()
