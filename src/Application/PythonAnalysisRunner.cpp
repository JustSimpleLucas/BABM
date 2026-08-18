// PythonAnalysisRunner.cpp

#include "Application/PythonAnalysisRunner.h"

#include <filesystem>
#include <string>
#include <vector>

#ifndef __APPLE__
#include <fstream>
#endif

#include <spawn.h>
#include <sys/wait.h>

#ifdef __APPLE__
#include <crt_externs.h>
#endif

namespace abm {
namespace {

struct ProcessRequest {
    std::string executable;
    std::vector<std::string> arguments;
    std::filesystem::path pythonPath;
};

std::filesystem::path runDirectoryForAnalysis(const RuntimeConfig& runtimeConfig) {
    if (runtimeConfig.output.experimentOutputEnabled &&
        !runtimeConfig.output.runDirectoryPath.empty()) {
        return {runtimeConfig.output.runDirectoryPath};
    }

    const std::filesystem::path stepTimeseriesPath(runtimeConfig.output.simulationCsvPath);
    if (!stepTimeseriesPath.parent_path().empty()) {
        return stepTimeseriesPath.parent_path();
    }
    return std::filesystem::current_path();
}

std::filesystem::path findAnalysisPythonPath(const RuntimeConfig& runtimeConfig) {
    std::vector<std::filesystem::path> searchRoots;
    if (!runtimeConfig.sourcePath.empty()) {
        std::filesystem::path cursor =
            std::filesystem::path(runtimeConfig.sourcePath).parent_path();
        while (!cursor.empty()) {
            searchRoots.push_back(cursor);
            if (cursor == cursor.parent_path()) {
                break;
            }
            cursor = cursor.parent_path();
        }
    }
    searchRoots.push_back(std::filesystem::current_path());

    for (const std::filesystem::path& root : searchRoots) {
        const std::filesystem::path candidate = root / "analysis" / "python";
        if (std::filesystem::exists(candidate)) {
            return std::filesystem::absolute(candidate).lexically_normal();
        }
    }
    return {};
}

#ifndef __APPLE__
std::vector<std::string> readLinuxProcessEnvironment() {
    std::ifstream environmentFile("/proc/self/environ", std::ios::binary);
    std::vector<std::string> environment;
    std::string entry;
    char character = '\0';

    while (environmentFile.get(character)) {
        if (character == '\0') {
            if (!entry.empty()) {
                environment.push_back(entry);
            }
            entry.clear();
        } else {
            entry.push_back(character);
        }
    }

    if (!entry.empty()) {
        environment.push_back(entry);
    }
    return environment;
}
#endif

std::vector<std::string> currentProcessEnvironmentEntries() {
    std::vector<std::string> environment;
#ifdef __APPLE__
    for (const char* const* entry = *_NSGetEnviron(); entry != nullptr && *entry != nullptr;
         ++entry) {
        environment.emplace_back(*entry);
    }
#else
    environment = readLinuxProcessEnvironment();
#endif
    return environment;
}

std::vector<std::string>
childEnvironmentWithPythonPath(const std::filesystem::path& analysisPythonPath) {
    std::vector<std::string> environment;
    constexpr const char* kPythonPathPrefix = "PYTHONPATH=";
    bool pythonPathReplaced = false;

    for (const std::string& value : currentProcessEnvironmentEntries()) {
        if (value.rfind(kPythonPathPrefix, 0) == 0) {
            pythonPathReplaced = true;
            if (!analysisPythonPath.empty()) {
                environment.push_back(std::string(kPythonPathPrefix) + analysisPythonPath.string());
            }
        } else {
            environment.push_back(value);
        }
    }

    if (!pythonPathReplaced && !analysisPythonPath.empty()) {
        environment.push_back(std::string(kPythonPathPrefix) + analysisPythonPath.string());
    }
    return environment;
}

std::vector<char*> mutableCStringPointers(std::vector<std::string>& values) {
    std::vector<char*> pointers;
    pointers.reserve(values.size() + 1);
    for (std::string& value : values) {
        pointers.push_back(value.data());
    }
    pointers.push_back(nullptr);
    return pointers;
}

bool runProcess(const ProcessRequest& request) {
    if (request.executable.empty()) {
        return false;
    }

    std::vector<std::string> argvStorage;
    argvStorage.reserve(request.arguments.size() + 1);
    argvStorage.push_back(request.executable);
    for (const std::string& argument : request.arguments) {
        argvStorage.push_back(argument);
    }

    std::vector<std::string> environmentStorage =
        childEnvironmentWithPythonPath(request.pythonPath);
    std::vector<char*> argv = mutableCStringPointers(argvStorage);
    std::vector<char*> envp = mutableCStringPointers(environmentStorage);

    pid_t childPid = 0;
    const int spawnStatus = posix_spawnp(&childPid, request.executable.c_str(), nullptr, nullptr,
                                         argv.data(), envp.data());
    if (spawnStatus != 0) {
        return false;
    }

    int childStatus = 0;
    if (waitpid(childPid, &childStatus, 0) < 0) {
        return false;
    }
    return WIFEXITED(childStatus) && WEXITSTATUS(childStatus) == 0;
}

void appendDatabaseConnectionArguments(const RuntimeConfig& runtimeConfig,
                                       std::vector<std::string>& arguments) {
    arguments.push_back("--database-url-env");
    arguments.push_back(runtimeConfig.output.databaseUrlEnvironmentVariable);
}

ProcessRequest buildPythonProcessRequest(const RuntimeConfig& runtimeConfig,
                                         const std::vector<std::string>& arguments) {
    ProcessRequest request;
    request.executable = runtimeConfig.output.pythonAnalysisPythonPath;
    request.pythonPath = findAnalysisPythonPath(runtimeConfig);
    request.arguments = {"-m", "abm_analysis"};
    for (const std::string& argument : arguments) {
        request.arguments.push_back(argument);
    }
    return request;
}

} // namespace

PythonAnalysisRunResult
PythonAnalysisRunner::runPostRunProcessing(const RuntimeConfig& runtimeConfig) {
    PythonAnalysisRunResult result;
    if (!runtimeConfig.output.databaseOutputEnabled) {
        result.message = "Python post-processing is disabled by configuration.";
        return result;
    }

    result.attempted = true;
    const std::filesystem::path runDirectory = runDirectoryForAnalysis(runtimeConfig);

    std::vector<std::string> importArguments{"db", "import-run", runDirectory.string()};
    appendDatabaseConnectionArguments(runtimeConfig, importArguments);
    if (runtimeConfig.output.databasePruneAfterImport) {
        importArguments.push_back("--prune-source");
    }

    result.databaseImportAttempted = true;
    const ProcessRequest importRequest = buildPythonProcessRequest(runtimeConfig, importArguments);
    result.databaseImportSucceeded = runProcess(importRequest);
    if (!result.databaseImportSucceeded) {
        result.message = "PostgreSQL import failed. Staging artefacts were kept for recovery.";
        result.databaseImportMessage = result.message;
        return result;
    }

    result.databaseImportMessage = "PostgreSQL import completed.";
    result.message = "PostgreSQL import completed.";
    return result;
}

} // namespace abm
