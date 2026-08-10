# Each domain directory declares which target its sources belong to, so a
# new .cpp is registered next to the code it implements rather than in a
# central list. Results/ is header-only and has no sources to add.
add_subdirectory(Agent)
add_subdirectory(AgentStrategy)
add_subdirectory(Application)
add_subdirectory(BehaviouralFinance)
add_subdirectory(ControlParameters)
add_subdirectory(DataManagement)
add_subdirectory(Experiment)
add_subdirectory(Market)
add_subdirectory(Metrics)
add_subdirectory(OrderBook)
add_subdirectory(Output)
add_subdirectory(RandomGenerator)
add_subdirectory(RiskManagement)
add_subdirectory(Simulation)
add_subdirectory(Utility)
