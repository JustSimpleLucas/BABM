// ConfigParsingTestMain.cpp

#include "tests/cpp/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;
    abm::test::runConfigParsingTests(failures);
    abm::test::runConfigKeyRegistryTests(failures);

    if (failures != 0) {
        std::cerr << failures << " config parsing test(s) failed.\n";
        return 1;
    }

    std::cout << "All config parsing tests passed.\n";
    return 0;
}
