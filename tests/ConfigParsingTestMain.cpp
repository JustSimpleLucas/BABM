// ConfigParsingTestMain.cpp

#include "tests/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;
    abm::test::runConfigParsingTests(failures);

    if (failures != 0) {
        std::cerr << failures << " config parsing test(s) failed.\n";
        return 1;
    }

    std::cout << "All config parsing tests passed.\n";
    return 0;
}
