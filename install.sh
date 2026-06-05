#!/data/data/com.termux/files/usr/bin/sh

set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
    echo "This installer must run inside Termux."
    exit 1
fi

if ! command -v pkg >/dev/null 2>&1; then
    echo "Termux package manager was not found."
    exit 1
fi

echo "Updating Termux packages."
pkg update -y

echo "Installing system packages."
pkg install -y python x11-repo
pkg install -y chromium termux-x11-nightly

echo "Installing Python dependencies."
python -m pip install -r "$PROJECT_DIR/requirements.txt"

if ! command -v chromium-browser >/dev/null 2>&1; then
    echo "chromium-browser was not found."
    exit 1
fi

if ! command -v chromedriver >/dev/null 2>&1; then
    echo "chromedriver was not found."
    exit 1
fi

echo "Chromium version:"
chromium-browser --version

echo "ChromeDriver version:"
chromedriver --version

echo "Installation complete."
echo "Run ./run.sh to check the TikTok session."
