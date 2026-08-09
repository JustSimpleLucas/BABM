// RunArtifactWriterTestMain.cpp

#include "tests/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;
    abm::test::runRunArtifactWriterTests(failures);

    if (failures != 0) {
        std::cerr << failures << " run artifact writer test(s) failed.\n";
        return 1;
    }

    std::cout << "All run artifact writer tests passed.\n";
    return 0;
}
