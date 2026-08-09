include_guard(GLOBAL)

if(NOT DEFINED ABM_PROJECT_ROOT)
    get_filename_component(ABM_PROJECT_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." ABSOLUTE)
endif()

set(ABM_APPLICATION_SOURCES
    "${ABM_PROJECT_ROOT}/src/Application/CliOptions.cpp"
    "${ABM_PROJECT_ROOT}/src/Application/ConsoleReporter.cpp"
    "${ABM_PROJECT_ROOT}/src/Application/PythonAnalysisRunner.cpp"
    "${ABM_PROJECT_ROOT}/src/Application/SimulationApplication.cpp"
)

set(ABM_AGENT_SOURCES
    "${ABM_PROJECT_ROOT}/src/Agent/Agent.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/AssetAllocationLine.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/BuyAndHoldStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/BreakoutChartistStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/ChartistStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/ChartistStrategyFactory.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/FundamentalistStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/MeanReversionChartistStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/MeanVarianceUtility.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/MomentumChartistStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/NoiseTraderStrategy.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/OrderSizing.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/PortfolioOptimizer.cpp"
    "${ABM_PROJECT_ROOT}/src/AgentStrategy/RelativeStrengthIndexChartistStrategy.cpp"
)

set(ABM_ANALYSIS_SOURCES
    "${ABM_PROJECT_ROOT}/src/Analysis/AllocativeEfficiency.cpp"
    "${ABM_PROJECT_ROOT}/src/Analysis/StylisedFactMetrics.cpp"
)

set(ABM_BEHAVIOURAL_FINANCE_SOURCES
    "${ABM_PROJECT_ROOT}/src/BehaviouralFinance/ProspectPreferenceSampler.cpp"
    "${ABM_PROJECT_ROOT}/src/BehaviouralFinance/ProspectTheory.cpp"
)

set(ABM_CONFIG_SOURCES
    "${ABM_PROJECT_ROOT}/src/ControlParameters/AssetUniverse.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigIO.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigBehaviouralSettings.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigOutputSettings.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigParsing.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigSettingAppliers.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigSimulationSettings.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigStrategySettings.cpp"
    "${ABM_PROJECT_ROOT}/src/ControlParameters/SimulationConfigValidation.cpp"
)

set(ABM_DATA_MANAGEMENT_SOURCES
    "${ABM_PROJECT_ROOT}/src/DataManagement/ExperimentDataWorkflow.cpp"
    "${ABM_PROJECT_ROOT}/src/DataManagement/RunArchiveSchema.cpp"
)

set(ABM_EXPERIMENT_SOURCES
    "${ABM_PROJECT_ROOT}/src/Experiment/ExperimentRunManager.cpp"
)

set(ABM_MARKET_SOURCES
    "${ABM_PROJECT_ROOT}/src/Market/CovarianceEstimator.cpp"
    "${ABM_PROJECT_ROOT}/src/Market/Market.cpp"
    "${ABM_PROJECT_ROOT}/src/OrderBook/LimitOrderBook.cpp"
    "${ABM_PROJECT_ROOT}/src/RiskManagement/ShortSaleRiskControls.cpp"
)

set(ABM_OUTPUT_SOURCES
    "${ABM_PROJECT_ROOT}/src/Output/AgentSnapshotCsvWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/AssetTimeseriesCsvWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/ExperimentManifestWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/OutputSerialization.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/RunArtifactWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/RunMetadataWriters.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/RunSummaryCsvWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/StepTimeseriesCsvWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/StylisedFactCsvWriter.cpp"
    "${ABM_PROJECT_ROOT}/src/Output/TradeLedgerCsvWriter.cpp"
)

set(ABM_SIMULATION_SOURCES
    "${ABM_PROJECT_ROOT}/src/Simulation/AgentActivationScheduler.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/DiagnosticsRecorder.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/MarketClearingEngine.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/MarketProcess.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/OrderCollector.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/PopulationFactory.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/RiskControlService.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/SimulationClock.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/SimulationEngine.cpp"
    "${ABM_PROJECT_ROOT}/src/Simulation/SocialInfluenceModel.cpp"
)

set(ABM_UTILITY_SOURCES
    "${ABM_PROJECT_ROOT}/src/RandomGenerator/RandomGenerator.cpp"
    "${ABM_PROJECT_ROOT}/src/Utility/CholeskyFactorization.cpp"
    "${ABM_PROJECT_ROOT}/src/Utility/ConsoleProgressBar.cpp"
    "${ABM_PROJECT_ROOT}/src/Utility/NumericValidation.cpp"
    "${ABM_PROJECT_ROOT}/src/Utility/OrderPricing.cpp"
    "${ABM_PROJECT_ROOT}/src/Utility/ProcessMemoryUsage.cpp"
)

set(ABM_MODEL_TEST_SOURCES
    "${ABM_PROJECT_ROOT}/tests/BuyAndHoldStrategyTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/ChartistStrategyTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/CoreModelTestMain.cpp"
    "${ABM_PROJECT_ROOT}/tests/LimitOrderBookTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/NoiseTraderStrategyTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/PortfolioOptimizerTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/ProspectTheoryTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/RandomMarketRiskTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/SimulationComponentTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/SimulationIntegrationTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/TestSupport.cpp"
)

set(ABM_CONFIG_PARSING_TEST_SOURCES
    "${ABM_PROJECT_ROOT}/tests/ConfigParsingTestMain.cpp"
    "${ABM_PROJECT_ROOT}/tests/ConfigParsingTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/TestSupport.cpp"
)

set(ABM_ARCHIVE_WORKFLOW_TEST_SOURCES
    "${ABM_PROJECT_ROOT}/tests/ArchiveWorkflowTestMain.cpp"
    "${ABM_PROJECT_ROOT}/tests/ArchiveWorkflowTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/TestSupport.cpp"
)

set(ABM_CONFIG_VALIDATION_TEST_SOURCES
    "${ABM_PROJECT_ROOT}/tests/ConfigValidationTestMain.cpp"
    "${ABM_PROJECT_ROOT}/tests/ConfigValidationTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/TestSupport.cpp"
)

set(ABM_RUN_ARTIFACT_TEST_SOURCES
    "${ABM_PROJECT_ROOT}/tests/RunArtifactWriterTestMain.cpp"
    "${ABM_PROJECT_ROOT}/tests/RunArtifactWriterTests.cpp"
    "${ABM_PROJECT_ROOT}/tests/TestSupport.cpp"
)
