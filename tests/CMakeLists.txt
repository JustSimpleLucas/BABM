# The test tree mirrors the source split: C++ suites under cpp/ next to the
# engine they exercise, Python suites under python/ for the analysis package.
# Only the C++ side is built here; pytest collects python/ via pyproject.toml.
add_subdirectory(cpp)
