#!/bin/sh
# Stub CLI: background-child spawner. Spawns a sleeper in the background,
# writes its pid to the file given as $1, then sleeps — the deadline test
# uses it to prove the process-group kill takes the spawned child down too
# (the CLI spawns process pools for ingestion).
sleep 60 &
echo "$!" > "$1"
sleep 60
