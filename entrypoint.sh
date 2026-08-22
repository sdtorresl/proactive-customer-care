#!/bin/sh
# RUN_MODE=loop  -> runs in an infinite loop, executing every LOOP_INTERVAL_SECONDS (default: 60s)
# RUN_MODE=once  -> runs once and exits (recommended when using host cron
#                    or an external scheduler with `docker compose run --rm app`)
set -e

RUN_MODE="${RUN_MODE:-loop}"
LOOP_INTERVAL_SECONDS="${LOOP_INTERVAL_SECONDS:-60}"

if [ "$RUN_MODE" = "loop" ]; then
    echo "Starting in loop mode, interval=${LOOP_INTERVAL_SECONDS}s"
    while true; do
        python -m app.main || echo "Run ended with an error; it will retry on the next cycle."
        sleep "$LOOP_INTERVAL_SECONDS"
    done
else
    exec python -m app.main
fi
