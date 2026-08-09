// ConfigValidationTestMain.cpp

#include "tests/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;
    abm::test::runConfigValidationTests(failures);

    if (failures != 0) {
        std::cerr << failures << " config validation test(s) failed.\n";
        return 1;
    }

    std::cout << "All config validation tests passed.\n";
    return 0;
}
