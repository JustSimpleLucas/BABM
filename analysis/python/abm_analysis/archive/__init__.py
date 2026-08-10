"""Reading the C++ simulator's experiment archives.

Run-id parsing, run discovery, archive and manifest loading, benchmark
series, and compression. Everything here is concerned with getting data off
disk and into DataFrames; nothing here computes results.
"""
