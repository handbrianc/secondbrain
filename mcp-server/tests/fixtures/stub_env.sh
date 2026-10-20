#!/bin/sh
# Stub CLI: environment probe. For each argument (a variable name), prints
# `NAME=value` when the variable is set and `NAME=<unset>` when it is not;
# a set-but-empty variable prints `NAME=`. Used by the CLI adapter
# environment tests (names come only from the test suite).
for name in "$@"; do
    eval "case \${$name+x} in
        x) printf '%s=%s\n' \"$name\" \"\${$name}\" ;;
        *) printf '%s=<unset>\n' \"$name\" ;;
    esac"
done
exit 0
