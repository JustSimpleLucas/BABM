// CoreModelTestMain.cpp

#include "tests/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;

    abm::test::runRandomMarketRiskTests(failures);
    abm::test::runPortfolioOptimizerTests(failures);
    abm::test::runProspectTheoryTests(failures);
    abm::test::runChartistStrategyTests(failures);
    abm::test::runBuyAndHoldStrategyTests(failures);
    abm::test::runNoiseTraderStrategyTests(failures);
    abm::test::runLimitOrderBookTests(failures);
    abm::test::runSimulationComponentTests(failures);
    abm::test::runSimulationIntegrationTests(failures);

    if (failures != 0) {
        std::cerr << failures << " model test(s) failed.\n";
        return 1;
    }

    std::cout << "All core model tests passed.\n";
    return 0;
}
