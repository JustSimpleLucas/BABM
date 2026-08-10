// PythonAnalysisRunner.cpp

#include "Application/PythonAnalysisRunner.h"

#include <algorithm>
#include <filesystem>
#include <string>
#include <system_error>
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

std::string databaseRunIdentifier(const RuntimeConfig& runtimeConfig,
                                  const std::filesystem::path& runDirectory) {
    if (!runtimeConfig.output.runId.empty()) {
        return runtimeConfig.output.runId;
    }
    if (!runDirectory.filename().empty()) {
        return runDirectory.filename().string();
    }
    return "latest";
}

std::string databaseExperimentIdentifier(const RuntimeConfig& runtimeConfig,
                                         const std::filesystem::path& experimentDirectory) {
    if (!runtimeConfig.output.experimentName.empty()) {
        return runtimeConfig.output.experimentName;
    }
    if (!experimentDirectory.filename().empty()) {
        return experimentDirectory.filename().string();
    }
    return "default_experiment";
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

ProcessRequest buildOpenReportProcessRequest(const std::filesystem::path& reportPath) {
    const std::filesystem::path absoluteReportPath =
        std::filesystem::absolute(reportPath).lexically_normal();

#ifdef __APPLE__
    return {"open", {"-a", "Safari", absoluteReportPath.string()}, {}};
#else
    return {"xdg-open", {absoluteReportPath.string()}, {}};
#endif
}

bool openReportInDefaultBrowser(const std::filesystem::path& reportPath, std::string& message) {
    const std::filesystem::path absoluteReportPath =
        std::filesystem::absolute(reportPath).lexically_normal();
    std::error_code errorCode;
    const bool reportExists = std::filesystem::exists(absoluteReportPath, errorCode);
    if (errorCode || !reportExists) {
        message = "The single-run HTML report could not be opened because it was not found: " +
                  absoluteReportPath.string();
        return false;
    }

    const ProcessRequest openRequest = buildOpenReportProcessRequest(absoluteReportPath);
    if (!runProcess(openRequest)) {
        message = "The single-run HTML report was generated, but the default browser could not be "
                  "opened.";
        return false;
    }

    message = "The single-run HTML report was opened in the default browser.";
    return true;
}

} // namespace

PythonAnalysisRunResult
PythonAnalysisRunner::generatePostRunReports(const RuntimeConfig& runtimeConfig) {
    PythonAnalysisRunResult result;
    if (!runtimeConfig.output.pythonAnalysisEnabled &&
        !runtimeConfig.output.databaseOutputEnabled) {
        result.message = "Python post-processing is disabled by configuration.";
        return result;
    }

    result.attempted = true;
    const std::filesystem::path runDirectory = runDirectoryForAnalysis(runtimeConfig);
    const std::filesystem::path runReportPath = runDirectory / "python_analysis" / "index.html";
    result.runReportPath = runReportPath.string();

    if (runtimeConfig.output.databaseOutputEnabled) {
        std::vector<std::string> importArguments{"db", "import-run", runDirectory.string()};
        appendDatabaseConnectionArguments(runtimeConfig, importArguments);
        if (runtimeConfig.output.databasePruneAfterImport) {
            importArguments.push_back("--prune-source");
        }

        result.databaseImportAttempted = true;
        const ProcessRequest importRequest =
            buildPythonProcessRequest(runtimeConfig, importArguments);
        result.databaseImportSucceeded = runProcess(importRequest);
        if (!result.databaseImportSucceeded) {
            result.message = "PostgreSQL import failed. Staging artefacts were kept for recovery.";
            result.databaseImportMessage = result.message;
            return result;
        }
        result.databaseImportMessage = "PostgreSQL import completed.";
    }

    if (!runtimeConfig.output.pythonAnalysisEnabled) {
        result.message = "PostgreSQL import completed; Python report generation is disabled.";
        return result;
    }

    result.runReportAttempted = true;
    std::vector<std::string> runArguments{
        "run",
        runtimeConfig.output.databaseOutputEnabled
            ? databaseRunIdentifier(runtimeConfig, runDirectory)
            : runDirectory.string(),
        "--output-dir",
        (runDirectory / "python_analysis").string(),
        "--source",
        runtimeConfig.output.databaseOutputEnabled ? "database" : "files",
    };
    if (runtimeConfig.output.databaseOutputEnabled) {
        appendDatabaseConnectionArguments(runtimeConfig, runArguments);
    }

    const ProcessRequest runRequest = buildPythonProcessRequest(runtimeConfig, runArguments);
    result.runReportSucceeded = runProcess(runRequest);

    if (!result.runReportSucceeded) {
        result.message =
            "Python single-run analysis failed. Check the Python environment and dependencies.";
        return result;
    }

    if (runtimeConfig.output.experimentOutputEnabled &&
        runtimeConfig.output.pythonAnalysisComparisonEnabled &&
        !runtimeConfig.output.runDirectoryPath.empty()) {
        const std::filesystem::path experimentDirectory =
            std::filesystem::path(runtimeConfig.output.runDirectoryPath).parent_path();
        const std::filesystem::path comparisonOutputDirectory =
            experimentDirectory / "comparison_reports" / "latest";
        const std::size_t maxRuns =
            std::max<std::size_t>(1, runtimeConfig.output.pythonAnalysisMaxComparisonRuns);

        result.comparisonReportAttempted = true;
        result.comparisonReportPath = (comparisonOutputDirectory / "index.html").string();
        std::vector<std::string> comparisonArguments{
            "compare",
            runtimeConfig.output.databaseOutputEnabled
                ? databaseExperimentIdentifier(runtimeConfig, experimentDirectory)
                : experimentDirectory.string(),
            "--output-dir",
            comparisonOutputDirectory.string(),
            "--max-runs",
            std::to_string(maxRuns),
            "--source",
            runtimeConfig.output.databaseOutputEnabled ? "database" : "files",
        };
        if (runtimeConfig.output.databaseOutputEnabled) {
            appendDatabaseConnectionArguments(runtimeConfig, comparisonArguments);
        }

        const ProcessRequest comparisonRequest =
            buildPythonProcessRequest(runtimeConfig, comparisonArguments);
        result.comparisonReportSucceeded = runProcess(comparisonRequest);
        if (!result.comparisonReportSucceeded) {
            result.message =
                "Python comparison analysis failed. The single-run report was generated.";
        }
    }

    result.runReportOpenAttempted = true;
    result.runReportOpenSucceeded =
        openReportInDefaultBrowser(runReportPath, result.runReportOpenMessage);

    if (result.message.empty()) {
        result.message = "Python analysis completed.";
    }
    return result;
}

} // namespace abm
