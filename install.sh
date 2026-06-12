#!/bin/sh

set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG_FILE="$PROJECT_DIR/config.txt"

config_enabled() {
    key=$1
    [ -f "$CONFIG_FILE" ] || return 1
    value=$(awk -F= -v key="$key" '
        /^[[:space:]]*(#|$)/ { next }
        {
            name = $1
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", name)
            if (name == key) {
                value = $0
                sub(/^[^=]*=/, "", value)
                gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
                print tolower(value)
                exit
            }
        }
    ' "$CONFIG_FILE")
    [ "$value" = "true" ]
}

if [ -z "${PREFIX:-}" ] || [ ! -d "$PREFIX" ]; then
    echo "This installer must run inside Termux."
    exit 1
fi

if ! command -v pkg >/dev/null 2>&1; then
    echo "Termux package manager was not found."
    exit 1
fi

if config_enabled chess || config_enabled duolingo; then
    NEEDS_STOCKFISH=true
else
    NEEDS_STOCKFISH=false
fi

if config_enabled duolingo; then
    NEEDS_TFLITE=true
else
    NEEDS_TFLITE=false
fi

echo "Updating Termux packages."
pkg update -y

echo "Installing system packages."
pkg install -y x11-repo
pkg install -y python
pkg install -y chromium
pkg install -y termux-x11-nightly
if ! command -v stockfish >/dev/null 2>&1; then
    echo "Installing Stockfish for chess automation."
    if ! pkg install -y stockfish; then
        echo "Stockfish could not be installed automatically."
        if [ "$NEEDS_STOCKFISH" = true ]; then
            echo "Stockfish is required because Chess.com or Duolingo is enabled in config.txt."
            echo "Install stockfish in Termux or disable chess and duolingo before running install.sh again."
            exit 1
        else
            echo "Install it manually in Termux before enabling the Chess.com or Duolingo flow."
        fi
    fi
fi
if ! python -c "import tflite_runtime.interpreter" >/dev/null 2>&1; then
    echo "Installing TensorFlow Lite runtime for Duolingo vision."
    if ! pkg install -y python-tflite-runtime; then
        echo "python-tflite-runtime could not be installed automatically."
        if [ "$NEEDS_TFLITE" = true ]; then
            echo "python-tflite-runtime is required because Duolingo is enabled in config.txt."
            echo "Install python-tflite-runtime in Termux or disable duolingo before running install.sh again."
            exit 1
        else
            echo "Duolingo AI vision will stay disabled until python-tflite-runtime is installed."
        fi
    fi
fi

echo "Installing Python dependencies."
python -m pip install -r "$PROJECT_DIR/requirements.txt"

CHROMIUM_BINARY=$(command -v chromium-browser 2>/dev/null || true)
if [ -z "$CHROMIUM_BINARY" ]; then
    CHROMIUM_BINARY=$(command -v chromium 2>/dev/null || true)
fi
if [ -z "$CHROMIUM_BINARY" ] && [ -x "$PREFIX/lib/chromium/chrome" ]; then
    CHROMIUM_BINARY="$PREFIX/lib/chromium/chrome"
fi
if [ -z "$CHROMIUM_BINARY" ]; then
    echo "Chromium was not found."
    exit 1
fi

if ! command -v chromedriver >/dev/null 2>&1; then
    echo "chromedriver was not found."
    exit 1
fi

if ! command -v termux-x11 >/dev/null 2>&1; then
    echo "termux-x11 was not found."
    exit 1
fi

if ! command -v pm >/dev/null 2>&1; then
    echo "Android package manager was not found."
    echo "Install the Termux:X11 Android app and verify that the pm command works."
    exit 1
fi

TERMUX_X11_PACKAGE=$(pm path com.termux.x11 2>/dev/null || true)
case "$TERMUX_X11_PACKAGE" in
    package:*)
        ;;
    *)
        echo "The Termux:X11 Android app package com.termux.x11 was not found."
        echo "Install the Termux:X11 Android app, then run install.sh again."
        exit 1
        ;;
esac

if ! command -v stockfish >/dev/null 2>&1; then
    if [ "$NEEDS_STOCKFISH" = true ]; then
        echo "stockfish was not found, but Chess.com or Duolingo is enabled in config.txt."
        echo "Install stockfish in Termux or disable chess and duolingo before running install.sh again."
        exit 1
    fi
    echo "stockfish was not found. Chess.com and Duolingo automation will not run until stockfish is installed."
else
    echo "Stockfish command:"
    command -v stockfish
fi

if python -c "import tflite_runtime.interpreter" >/dev/null 2>&1; then
    echo "TensorFlow Lite runtime is available."
else
    if [ "$NEEDS_TFLITE" = true ]; then
        echo "TensorFlow Lite runtime is not available, but Duolingo is enabled in config.txt."
        echo "Install python-tflite-runtime in Termux or disable duolingo before running install.sh again."
        exit 1
    fi
    echo "TensorFlow Lite runtime is not available. Duolingo AI vision is disabled."
fi

echo "Chromium version:"
"$CHROMIUM_BINARY" --version

echo "ChromeDriver version:"
chromedriver --version

echo "Termux X11 command:"
command -v termux-x11

echo "Installation complete."
echo "Run ./run.sh to start all enabled flows."
