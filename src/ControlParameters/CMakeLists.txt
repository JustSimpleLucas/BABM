# Sources in this directory belong to the abm_config target.
target_sources(abm_config
    PRIVATE
        AssetUniverse.cpp
        ConfigDiagnostics.cpp
        ConfigKeyRegistry.cpp
        SimulationConfigBehaviouralSettings.cpp
        SimulationConfigIO.cpp
        SimulationConfigOutputSettings.cpp
        SimulationConfigParsing.cpp
        SimulationConfigSettingAppliers.cpp
        SimulationConfigSimulationSettings.cpp
        SimulationConfigStrategySettings.cpp
        SimulationConfigValidation.cpp
)
