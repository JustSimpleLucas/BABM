# Sources in this directory belong to the abm_config target.
#
# The SimulationConfigSettingAppliers* files are one header split across several
# translation units: the appliers are declared together in
# SimulationConfigSettingAppliers.h and grouped here by the part of the config
# they populate, so no single file carries every key in the schema. Each source
# name begins with the header it implements, which is the convention the
# repository-hygiene test checks.
target_sources(abm_config
    PRIVATE
        ConfigDiagnostics.cpp
        ConfigKeyRegistry.cpp
        MarketConfigAssetUniverse.cpp
        SimulationConfigIO.cpp
        SimulationConfigParsing.cpp
        SimulationConfigSettingAppliers.cpp
        SimulationConfigSettingAppliersBehavioural.cpp
        SimulationConfigSettingAppliersOutput.cpp
        SimulationConfigSettingAppliersSimulation.cpp
        SimulationConfigSettingAppliersStrategy.cpp
        SimulationConfigValidation.cpp
)
