#!/bin/sh
# Stub CLI: argv echo. Prints each argument it received on its own line,
# proving the adapter passes arguments verbatim as single argv elements
# (no shell interpolation).
for arg in "$@"; do
    printf '%s\n' "$arg"
done
exit 0
