"""Statistical analysis of simulation output.

These modules compute the numbers — stylised-fact diagnostics, robustness
verdicts, seed convergence, stress-regime, multi-asset and agent-level
statistics. They are the single source for every figure the project reports:
``abm_analysis.exports`` writes them to CSV and ``abm_analysis.web`` renders
them, but neither computes anything of its own.
"""
