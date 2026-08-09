// ArchiveWorkflowTestMain.cpp

#include "tests/TestSupport.h"

#include <iostream>

int main() {
    int failures = 0;
    abm::test::runArchiveWorkflowTests(failures);

    if (failures != 0) {
        std::cerr << failures << " archive workflow test(s) failed.\n";
        return 1;
    }

    std::cout << "All archive workflow tests passed.\n";
    return 0;
}
