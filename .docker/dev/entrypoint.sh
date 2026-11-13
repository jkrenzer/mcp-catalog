#!/usr/bin/env bash
set -e

if ! docker info >/dev/null 2>&1; then
    printf '%s\n' \
        'Warning: Docker CLI is installed, but no working Docker engine is reachable.' \
        'Start the host Docker engine and ensure its socket is available to this container; Docker-dependent commands will fail until then.' \
        >&2
fi

if [ "$#" -eq 0 ]; then
    set -- bash -l
fi

exec "$@"