#!/usr/bin/env bash
set -e

if [ "$#" -eq 0 ]; then
    set -- bash -l
fi

exec "$@"