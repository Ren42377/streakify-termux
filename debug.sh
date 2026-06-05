#!/data/data/com.termux/files/usr/bin/sh

set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DISPLAY_FILE="${PREFIX:-}/var/run/tx11.display"
DEBUG_CONFIG="${TMPDIR:-/tmp}/streakify-debug-config.txt"
X11_LOG="${TMPDIR:-/tmp}/streakify-x11.log"

cd "$PROJECT_DIR"

if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
    echo "This script must run inside Termux."
    exit 1
fi

if ! command -v termux-x11 >/dev/null 2>&1; then
    echo "termux-x11 was not found. Run sh install.sh first."
    exit 1
fi

if [ -z "${DISPLAY:-}" ]; then
    if command -v am >/dev/null 2>&1; then
        am start --user 0 -n com.termux.x11/.MainActivity >/dev/null 2>&1 || true
    fi
    if command -v sv >/dev/null 2>&1 && [ -d "$PREFIX/var/service/tx11" ]; then
        sv up tx11 >/dev/null 2>&1 || true
        sleep 2
    fi
    if [ -r "$DISPLAY_FILE" ]; then
        DISPLAY=":$(cat "$DISPLAY_FILE")"
        export DISPLAY
    fi
    if [ -z "${DISPLAY:-}" ]; then
        termux-x11 :0 >"$X11_LOG" 2>&1 &
        sleep 3
        DISPLAY=:0
        export DISPLAY
    fi
fi

if [ -z "${DISPLAY:-}" ]; then
    echo "DISPLAY is not available. Open Termux:X11 and start tx11 first."
    exit 1
fi

awk '
BEGIN { found = 0 }
/^browser.headless=/ { print "browser.headless=false"; found = 1; next }
{ print }
END { if (found == 0) print "browser.headless=false" }
' "$PROJECT_DIR/config.txt" > "$DEBUG_CONFIG"

python -m streakify --config "$DEBUG_CONFIG" tiktok
