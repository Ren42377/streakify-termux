#!/bin/sh

set -eu

export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none
export PIP_NO_INPUT=1

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CONFIG_FILE="$PROJECT_DIR/config.txt"

pkg_update() {
    pkg update -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold"
}

pkg_upgrade() {
    pkg upgrade -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold"
}

pkg_install() {
    pkg install -y \
        -o Dpkg::Options::="--force-confdef" \
        -o Dpkg::Options::="--force-confold" \
        "$@"
}

python_has_tflite_stack() {
    python -c "import numpy; import tflite_runtime.interpreter" >/dev/null 2>&1
}

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

android_package_exists() {
    package_name=$1
    if pm path "$package_name" >/dev/null 2>&1; then
        return 0
    fi
    if pm path --user 0 "$package_name" >/dev/null 2>&1; then
        return 0
    fi
    listed=$(pm list packages "$package_name" 2>/dev/null || true)
    for package_line in $listed; do
        if [ "$package_line" = "package:$package_name" ]; then
            return 0
        fi
    done
    if command -v cmd >/dev/null 2>&1 && cmd package path "$package_name" >/dev/null 2>&1; then
        return 0
    fi
    return 1
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

if config_enabled snapchat; then
    NEEDS_FFMPEG=true
else
    NEEDS_FFMPEG=false
fi

echo "Updating Termux package lists."
pkg_update

echo "Installing X11 repository."
pkg_install x11-repo

echo "Refreshing package lists after enabling X11 repository."
pkg_update

echo "Upgrading installed Termux packages."
pkg_upgrade

echo "Installing system packages."
pkg_install python chromium termux-x11-nightly termux-services

if ! command -v stockfish >/dev/null 2>&1; then
    echo "Installing Stockfish for chess automation."
    if ! pkg_install stockfish; then
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

if ! python_has_tflite_stack; then
    echo "Installing TensorFlow Lite runtime for Duolingo vision."
    if ! pkg_install python-tflite-runtime; then
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

if [ "$NEEDS_FFMPEG" = true ] && ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Installing FFmpeg for the Snapchat fake camera."
    if ! pkg_install ffmpeg; then
        echo "FFmpeg is required because Snapchat is enabled in config.txt."
        echo "Install ffmpeg in Termux or disable snapchat before running install.sh again."
        exit 1
    fi
fi

echo "Installing Python dependencies."
python -m pip install --no-input --disable-pip-version-check -r "$PROJECT_DIR/requirements.txt"

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

TERMUX_X11_ANDROID_PACKAGE=${TERMUX_X11_ANDROID_PACKAGE:-com.termux.x11}
if ! android_package_exists "$TERMUX_X11_ANDROID_PACKAGE"; then
    echo "The Termux:X11 Android app package $TERMUX_X11_ANDROID_PACKAGE was not found."
    echo "If the app is already installed, open Termux:X11 once from Android, then run install.sh again."
    echo "If your package name is different, run install with TERMUX_X11_ANDROID_PACKAGE set to that package name."
    exit 1
fi

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

if python_has_tflite_stack; then
    echo "TensorFlow Lite runtime and numpy are available."
else
    if [ "$NEEDS_TFLITE" = true ]; then
        echo "TensorFlow Lite runtime or numpy is not available, but Duolingo is enabled in config.txt."
        echo "Install python-tflite-runtime in Termux or disable duolingo before running install.sh again."
        exit 1
    fi
    echo "TensorFlow Lite runtime or numpy is not available. Duolingo AI vision is disabled."
fi

if command -v ffmpeg >/dev/null 2>&1; then
    echo "FFmpeg command:"
    command -v ffmpeg
elif [ "$NEEDS_FFMPEG" = true ]; then
    echo "ffmpeg was not found, but Snapchat is enabled in config.txt."
    exit 1
else
    echo "ffmpeg was not found. Snapchat automation will not run until ffmpeg is installed."
fi

echo "Chromium version:"
"$CHROMIUM_BINARY" --version

echo "ChromeDriver version:"
chromedriver --version

echo "Termux X11 command:"
command -v termux-x11

LEGACY_SERVICE_NAME=streakify-scheduler
LEGACY_SERVICE_DIR="$PREFIX/var/service/$LEGACY_SERVICE_NAME"
LEGACY_BOOT_SCRIPT="$HOME/.termux/boot/$LEGACY_SERVICE_NAME.sh"

echo "Removing legacy Streakify scheduler installation."
if command -v sv >/dev/null 2>&1; then
    sv down "$LEGACY_SERVICE_NAME" >/dev/null 2>&1 || true
fi
if [ -e "$LEGACY_SERVICE_DIR" ] || [ -L "$LEGACY_SERVICE_DIR" ]; then
    rm -rf "$LEGACY_SERVICE_DIR"
fi
if [ -e "$LEGACY_BOOT_SCRIPT" ] || [ -L "$LEGACY_BOOT_SCRIPT" ]; then
    rm -f "$LEGACY_BOOT_SCRIPT"
fi

echo "Installing Streakium scheduler service."
chmod +x "$PROJECT_DIR/run.sh" "$PROJECT_DIR/schedule.sh"

SERVICE_DIR="$PREFIX/var/service/streakium-scheduler"
mkdir -p "$SERVICE_DIR/log"

cat > "$SERVICE_DIR/run" <<EOF
#!/bin/sh
exec 2>&1
cd "$PROJECT_DIR"
exec sh "$PROJECT_DIR/schedule.sh"
EOF

cat > "$SERVICE_DIR/log/run" <<'EOF'
#!/bin/sh
LOG_DIR="${STREAKIUM_HOME:-$HOME/.streakium}/logs/streakium-scheduler"
mkdir -p "$LOG_DIR"
exec svlogd -tt "$LOG_DIR"
EOF

chmod +x "$SERVICE_DIR/run" "$SERVICE_DIR/log/run"

if command -v sv >/dev/null 2>&1; then
    sv up streakium-scheduler >/dev/null 2>&1 || true
fi

TERMUX_BOOT_PACKAGE=com.termux.boot
if android_package_exists "$TERMUX_BOOT_PACKAGE"; then
    echo "Installing Termux:Boot scheduler recovery."
    BOOT_DIR="$HOME/.termux/boot"
    BOOT_SCRIPT="$BOOT_DIR/streakium-scheduler.sh"
    mkdir -p "$BOOT_DIR"
    cat > "$BOOT_SCRIPT" <<'EOF'
#!/bin/sh

if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock >/dev/null 2>&1 || true
fi

if [ -f "$PREFIX/etc/profile.d/start-services.sh" ]; then
    . "$PREFIX/etc/profile.d/start-services.sh"
fi

if command -v sv >/dev/null 2>&1; then
    sv up streakium-scheduler >/dev/null 2>&1 || true
fi
EOF
    chmod +x "$BOOT_SCRIPT"
    echo "Termux:Boot recovery installed at $BOOT_SCRIPT."
    echo "Open the Termux:Boot Android app once so it can run scripts after reboot."
else
    echo "Warning: Termux:Boot was not found."
    echo "The scheduler is running now, but it will not restart automatically after a phone reboot."
    echo "Install and open Termux:Boot once, then rerun sh install.sh to enable automatic recovery."
fi

echo "Installation complete."
echo "Run ./run.sh to start all enabled flows."
echo "Run sh schedule.sh to start the scheduler manually."
echo "The scheduler service reads schedule.enabled and schedule.time from config.txt."
