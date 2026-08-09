// SimulationApplication.h

#ifndef SIMULATION_APPLICATION_H
#define SIMULATION_APPLICATION_H

namespace abm {

/**
 * Runs the command-line simulation application.
 *
 * The executable entry point delegates here so command-line parsing, simulation
 * orchestration, and artifact export can evolve as ordinary project code rather
 * than remaining embedded in the root main.cpp file.
 *
 * @param argc Number of command-line arguments received by main.
 * @param argv Command-line argument vector received by main.
 * @return Process exit code.
 */
[[nodiscard]] int runSimulationApplication(int argc, char** argv);

} // namespace abm

#endif // SIMULATION_APPLICATION_H
