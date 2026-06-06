#!/bin/sh

set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJECT_DIR"

if [ -z "${DISPLAY:-}" ] && [ -n "${PREFIX:-}" ] && [ -r "$PREFIX/var/run/tx11.display" ]; then
    DISPLAY=":$(cat "$PREFIX/var/run/tx11.display")"
    export DISPLAY
fi

python -m streakify tiktok
