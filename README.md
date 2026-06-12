# Streakify

Streakify is a Python automation tool for maintaining streaks across platforms directly from Termux on Android.

## Current Platform Support

- **TikTok**: Opens messages, checks the session, selects chats, and sends a configured message through undetected Chromium.
- **Chess.com**: Opens a rated puzzle, reads the board position from the DOM, uses Stockfish to identify the best move, selects the first legal alternative, intentionally plays that one wrong move, and stops.
- **Duolingo**: Opens Chess Match, reads the initial FEN and player color from Duolingo's React state, classifies each board square from the canvas using a bundled TensorFlow Lite vision model, uses Stockfish to play the logged-in side until checkmate, and clicks Continue once.
- **Snapchat**: Searches exact usernames on the Snapchat web dashboard, uses a project image as a Chromium fake camera, captures one Snap per target, and sends it.

> [!NOTE]
> More platforms can be added later as separate adapters.

## How It Works

```text
Run Streakify in Termux
        |
        v
Streakify starts undetected Chromium automatically
        |
        v
Opens the enabled platform
        |
        v
TikTok sends configured messages
Chess.com plays one legal non-best puzzle move
Duolingo plays Chess Match until checkmate
Snapchat sends one camera Snap per configured username
        |
        v
Done
```

## Requirements

| Requirement | Notes |
| --- | --- |
| Android phone | Enough storage for Termux, Chromium, and browser profile data |
| Termux | Use the latest build from F-Droid or official Termux sources |
| Python | Installed through Termux packages |
| Chromium and ChromeDriver | Used by undetected-chromedriver for browser automation |
| undetected-chromedriver | Anti-detection Chromium driver, installed through pip |
| Termux X11 | Used for visible login sessions |
| termux-services | Keeps the optional Streakify scheduler running in Termux |
| Termux:API | Optional. Enables Android notifications when `termux-notification` is available |
| Stockfish | Calculates Chess.com and Duolingo chess moves |
| python-chess | Reconstructs Duolingo positions and validates legal moves |
| python-tflite-runtime | Required Duolingo AI vision runtime for tile classification |
| FFmpeg | Converts the selected Snapchat camera image into Chromium's Y4M fake camera format |
| Internet access | Needed for installation and automation |

> [!WARNING]
> **Do not install Termux from the Play Store.** That version is outdated and often breaks package installation. Use [F-Droid](https://f-droid.org/en/packages/com.termux/) or [Termux GitHub releases](https://github.com/termux/termux-app/releases).

## Installation

Fast setup:

```sh
pkg update && pkg upgrade -y
pkg install -y git
git clone https://github.com/Ren42377/streakify-termux.git
cd streakify-termux
sh install.sh
```

The installer will:

1. Update Termux packages.
2. Install Python, Chromium, Termux X11, termux-services, FFmpeg, and Stockfish packages when available.
3. Install TensorFlow Lite runtime when the Termux package is available.
4. Install Python dependencies from `requirements.txt` (selenium, setuptools, undetected-chromedriver, chess).
5. Verify that Chromium, ChromeDriver, the Termux X11 command, and the Termux:X11 Android app are available.
6. Install the `streakify-scheduler` Termux service.
7. Stop with a clear error if Stockfish is missing while Chess.com or Duolingo is enabled, or if TensorFlow Lite runtime is missing while Duolingo is enabled.

Manual setup:

```sh
pkg update
pkg install x11-repo
pkg install python
pkg install chromium
pkg install termux-x11-nightly
pkg install termux-services
pkg install stockfish
pkg install python-tflite-runtime
pkg install ffmpeg
python -m pip install -r requirements.txt
```

Verify browser tools:

```sh
chromium-browser --version
chromedriver --version
command -v termux-x11
command -v sv
command -v stockfish
command -v ffmpeg
```

If Chromium or ChromeDriver is missing, check the Chromium package installation from Termux repositories.
If `termux-x11` is missing, install `x11-repo` and `termux-x11-nightly`.
If `sv` is missing, install `termux-services`.
If `termux-notification` is missing, Streakify skips notifications without failing.
If the Termux:X11 Android app is installed but the installer cannot detect it, open Termux:X11 once from Android and rerun `sh install.sh`. If your device uses a different package name, run install with `TERMUX_X11_ANDROID_PACKAGE` set to that package name.
If `stockfish` is missing, install it in Termux and make sure the `stockfish` command is available in `PATH`.
If `python-tflite-runtime` is missing, the Duolingo adapter stops with an error.
If `ffmpeg` is missing while Snapchat is enabled, the Snapchat adapter stops with an error.

## Configuration

Edit `config.txt` before running Streakify.

Required settings:

```txt
tiktok=true
chess=true
duolingo=false
snapchat=false
browser.headless=true
tiktok.message=🔥
tiktok.max_chats=10
chess.engine_time=0.4
snapchat.usernames=user_a,user_b
```

Optional Snapchat camera settings:

```txt
snapchat.camera_folder=assets
snapchat.camera_mode=random
```

Optional scheduler settings:

```txt
schedule.enabled=false
schedule.time=09:00
```

| Setting | Value | Purpose |
| --- | --- | --- |
| `tiktok` | `true` or `false` | Enable or skip the TikTok flow |
| `chess` | `true` or `false` | Enable or skip the Chess.com flow |
| `duolingo` | `true` or `false` | Enable or skip the Duolingo Chess Match flow |
| `snapchat` | `true` or `false` | Enable or skip the Snapchat Snap flow |
| `browser.headless` | `true` or `false` | Use headless Chromium when true |
| `tiktok.message` | Any non-empty text | Message sent to each chat. Emoji are supported if `config.txt` is saved as UTF-8 |
| `tiktok.max_chats` | Positive integer | Number of chats processed in one run |
| `chess.engine_time` | Positive number | Stockfish thinking time for Chess.com and Duolingo moves |
| `snapchat.usernames` | Comma-separated usernames | Exact Snapchat usernames that receive one Snap per run |
| `snapchat.camera_folder` | Folder path | Optional folder of images for the Snapchat fake camera. Defaults to `assets` |
| `snapchat.camera_mode` | `random` or `newest` | Optional image selection mode. Defaults to `random` |
| `schedule.enabled` | `true` or `false` | Optional scheduler switch. Defaults to `false` |
| `schedule.time` | `H:MM` or `HH:MM` | Optional daily run time in the phone's local Termux timezone. Defaults to `09:00` |

> [!IMPORTANT]
> If any setting is missing, misspelled, duplicated, empty, or invalid, Streakify stops before opening the browser and prints the setting that must be fixed.

## Runtime Data

By default, runtime data is stored in:

```text
$HOME/.streakify/
```

That directory contains:

- Browser profile and login session: `$HOME/.streakify/.auth/selenium-profile`
- Driver cache: `$HOME/.streakify/.drivers`
- Generated Snapchat fake camera and SHA-256 cache: `$HOME/.streakify/media`
- Scheduler state: `$HOME/.streakify/scheduler-state.txt`
- Termux X11 PID file: `$HOME/.streakify/termux-x11.pid`

To move all runtime data:

```sh
STREAKIFY_HOME="$HOME/.streakify-alt" sh run.sh
```

## Usage

Run all enabled flows:

```sh
./run.sh
```
*(Alternatively, you can use `sh run.sh`)*

You can also run Streakify directly with Python:

```sh
python -m streakify
```

Run a single platform (used internally by the scheduler for retries):

```sh
python -m streakify --platform tiktok
```

## Project Structure

```text
streakify-termux/
├── install.sh                  # Installation script
├── run.sh                      # Runner script
├── schedule.sh                 # Scheduler service runner
├── config.txt                  # User configuration
├── requirements.txt            # Python dependencies
├── LICENSE                     # MIT license
├── README.md                   # Documentation
├── assets/                     # Default Snapchat camera image folder
└── streakify/                  # Python package
    ├── __init__.py
    ├── __main__.py             # CLI entry point
    ├── browser.py              # Browser setup with undetected-chromedriver
    ├── config.py               # Config parsing and validation
    ├── notifications.py        # Termux notification helper
    ├── results.py              # Per-platform run result data classes
    ├── runtime_paths.py        # Runtime path helpers
    ├── scheduler.py            # Config-driven daily scheduler
    ├── stockfish.py            # Shared Stockfish UCI process
    ├── termux_x11.py           # Termux X11 lifecycle
    ├── tiktok.py               # TikTok adapter
    ├── chess.py                # Chess.com adapter
    ├── duolingo.py             # Duolingo adapter
    ├── duolingo_vision.py      # Duolingo TFLite vision runtime
    ├── snapchat.py             # Snapchat adapter
    ├── snapchat_camera.py      # Snapchat image-to-Y4M cache
    └── models/duolingo/        # Duolingo model files
        ├── duolingo_chess.tflite
        ├── labels.json
        └── metadata.json
```

## FAQ

### Is this safe?

Streakify runs locally on your phone and does not send your data to a Streakify server. Browser sessions are stored locally in `$HOME/.streakify/`. Do not share that directory.

### Can my account be banned?

Any automation has risk. Streakify uses undetected-chromedriver to look like a real Chromium browser, but you should still use it carefully and avoid setting `tiktok.max_chats` or the Snapchat target list too high.

### Can it run automatically every day?

Yes. Run `sh install.sh`, then set `schedule.enabled=true` and `schedule.time=HH:MM` in `config.txt`. The `streakify-scheduler` service keeps reading the config file and starts Streakify at that time.

### Does it require root?

No. Streakify runs fully inside Termux.

### Can other platforms be added?

Yes. Streakify is designed so each platform can be implemented as a separate adapter.
