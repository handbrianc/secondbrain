#!/bin/sh
# Stub CLI: sleeper. Sleeps 60 seconds by default (for deadline tests); an
# optional argument overrides the sleep so a spent runner can be probed with
# an instant, successful call.
sleep "${1:-60}"
