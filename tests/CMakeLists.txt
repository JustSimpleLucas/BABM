# Test executables and their sources, declared next to the tests themselves.
#
# Every executable links abm_core, so a test may reach any domain library. Each
# one also compiles TestSupport.cpp, which holds the shared fixtures.

function(abm_add_test_executable target_name)
    add_executable(${target_name} ${ARGN} TestSupport.cpp)
    target_link_libraries(${target_name} PRIVATE abm_core)
    # Tests that read repository fixtures resolve them from here rather than the
    # working directory, which CTest sets to the build tree.
    target_compile_definitions(${target_name} PRIVATE ABM_PROJECT_ROOT="${ABM_PROJECT_ROOT}")
    abm_apply_project_warnings(${target_name})
    abm_apply_project_sanitizers(${target_name})
    add_test(NAME ${target_name} COMMAND ${target_name})
endfunction()

abm_add_test_executable(abm_model_tests
    BuyAndHoldStrategyTests.cpp
    ChartistStrategyTests.cpp
    CoreModelTestMain.cpp
    LimitOrderBookTests.cpp
    NoiseTraderStrategyTests.cpp
    PortfolioOptimizerTests.cpp
    ProspectTheoryTests.cpp
    RandomMarketRiskTests.cpp
    SimulationComponentTests.cpp
    SimulationIntegrationTests.cpp
)

abm_add_test_executable(abm_config_parsing_tests
    ConfigKeyRegistryTests.cpp
    ConfigParsingTestMain.cpp
    ConfigParsingTests.cpp
)

abm_add_test_executable(abm_archive_workflow_tests
    ArchiveWorkflowTestMain.cpp
    ArchiveWorkflowTests.cpp
)

abm_add_test_executable(abm_config_validation_tests
    ConfigValidationTestMain.cpp
    ConfigValidationTests.cpp
)

abm_add_test_executable(abm_run_artifact_writer_tests
    RunArtifactWriterTestMain.cpp
    RunArtifactWriterTests.cpp
)
