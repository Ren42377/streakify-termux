# Streakify

Streakify is a Python automation tool for maintaining streaks across platforms directly from Termux on Android.

## Current Platform Support

- **TikTok**: Opens messages, checks the session, selects chats, and sends a configured message through Chromium and Selenium.
- **Chess.com**: Opens a rated puzzle, uses Stockfish to identify the best move, selects the first legal alternative, intentionally plays that one wrong move, and stops.
- **Duolingo**: Checks login, reads the canvas board, uses Stockfish to play the logged-in side until checkmate, and clicks Continue once.

> [!NOTE]
> More platforms can be added later as separate adapters.

## How It Works

```text
Run Streakify in Termux
        |
        v
Streakify starts Chromium automatically
        |
        v
Opens the enabled platform
        |
        v
TikTok sends configured messages
Chess.com plays one legal non-best puzzle move
Duolingo plays Chess Match until checkmate
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
| Chromium and ChromeDriver | Used by Selenium automation |
| Termux X11 | Used for visible login sessions |
| Stockfish | Calculates Chess.com and Duolingo chess moves |
| python-chess | Reconstructs Duolingo positions and validates legal moves |
| python-tflite-runtime | Required Duolingo AI vision runtime for tile classification |
| Internet access | Needed for installation and automation |

> [!WARNING]
> **Do not install Termux from the Play Store.** That version is outdated and often breaks package installation. Use [F-Droid](https://f-droid.org/en/packages/com.termux/) or [Termux GitHub releases](https://github.com/termux/termux-app/releases).

## Installation

Fast setup:

```sh
git clone https://github.com/Ren42377/streakify-termux.git
cd streakify-termux
sh install.sh
```

The installer will:

1. Update Termux packages.
2. Install Python, Chromium, Termux X11, and Stockfish packages when available.
3. Install TensorFlow Lite runtime when the Termux package is available.
4. Install Python dependencies from `requirements.txt`.
5. Verify that Chromium, ChromeDriver, the Termux X11 command, and the Termux:X11 Android app are available.
6. Stop with a clear error if Stockfish is missing while Chess.com or Duolingo is enabled, or if TensorFlow Lite runtime is missing while Duolingo is enabled.

Manual setup:

```sh
pkg update
pkg install x11-repo
pkg install python
pkg install chromium
pkg install termux-x11-nightly
pkg install stockfish
pkg install python-tflite-runtime
python -m pip install -r requirements.txt
```

Verify browser tools:

```sh
chromium-browser --version
chromedriver --version
command -v termux-x11
command -v stockfish
```

If Chromium or ChromeDriver is missing, check the Chromium package installation from Termux repositories.
If `termux-x11` is missing, install `x11-repo` and `termux-x11-nightly`.
If `pm path com.termux.x11` returns nothing, install the separate Termux:X11 Android app before running Streakify.
If `stockfish` is missing, install it in Termux and make sure the `stockfish` command is available in `PATH`.
If `python-tflite-runtime` is missing, the Duolingo adapter stops with an error.

## Configuration

Edit `config.txt` before running Streakify.

Required settings:

```txt
tiktok=true
chess=true
duolingo=false
browser.headless=true
tiktok.message=🔥
tiktok.max_chats=10
chess.engine_time=0.4
```

| Setting | Value | Purpose |
| --- | --- | --- |
| `tiktok` | `true` or `false` | Enable or skip the TikTok flow |
| `chess` | `true` or `false` | Enable or skip the Chess.com flow |
| `duolingo` | `true` or `false` | Enable or skip the Duolingo Chess Match flow |
| `browser.headless` | `true` or `false` | Use headless Chromium when true |
| `tiktok.message` | Any non-empty text | Message sent to each chat. Emoji are supported if `config.txt` is saved as UTF-8 |
| `tiktok.max_chats` | Positive integer | Number of chats processed in one run |
| `chess.engine_time` | Positive number | Stockfish thinking time for Chess.com and Duolingo moves |

> [!IMPORTANT]
> If any setting is missing, misspelled, duplicated, empty, or invalid, Streakify stops before opening the browser and prints the setting that must be fixed.

> [!TIP]
> Browser and ChromeDriver paths are not configured in `config.txt`. Streakify detects them automatically from Termux.
> Stockfish is not configured in `config.txt`. Streakify uses the `stockfish` command from Termux `PATH`.
## Runtime Data

By default, runtime data is stored in:

```text
$HOME/.streakify/
```

That directory contains:

- Browser profile and login session: `$HOME/.streakify/.auth/selenium-profile`
- Driver cache: `$HOME/.streakify/.drivers`

To move all runtime data:

```sh
STREAKIFY_HOME="$HOME/.streakify-alt" sh run.sh
```

> [!CAUTION]
> Do not point `STREAKIFY_HOME` to the project folder or Android shared storage. Chromium can fail to create lock files there.
>
> Do not commit tokens, cookies, credentials, browser profiles, or session files.

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

> [!NOTE]
> Streakify runs every platform set to `true` in `config.txt`. Platforms set to `false` are skipped.

> [!WARNING]
> The Chess.com flow intentionally plays exactly one legal move that differs from Stockfish's best move. It reports success only after the board position changes and Chess.com exposes the completed puzzle state, then stops without solving the puzzle. Because this uses rated puzzles, running it can lower the account's puzzle rating.

The Duolingo flow reads the initial FEN and player color once from Duolingo's React state. Every later board update is classified by the bundled TensorFlow Lite model and matched against legal `python-chess` move sequences. Stockfish chooses moves only when the local board turn matches the logged-in player color. If visual progress stalls, Streakify refreshes the cached board geometry after 8 seconds and opens a fresh match after 45 seconds. Match retries do not have a fixed limit.

## Duolingo Vision Model

Duolingo does not expose chess pieces as DOM elements. The vision model classifies each board square from a 48x48 canvas crop into 13 labels: empty plus the 12 chess pieces.

Runtime files live in:

```text
streakify/models/duolingo/
```

Expected files:

- `duolingo_chess.tflite`
- `labels.json`
- `metadata.json`

The repository includes the trained model, labels, and metadata. On Termux, install the runtime with:

```sh
pkg install python-tflite-runtime
```

If the model or runtime is missing, the Duolingo adapter stops with an error instead of using a less reliable fallback.

When `browser.headless=false`, Streakify starts a Termux X11 server automatically if one is not already running, opens the Termux:X11 Android app, connects Chromium to it, and closes the app after all enabled flows finish. If Streakify started the server, it also stops that server. When `browser.headless=true`, Streakify may prepare the X11 server environment, but it does not open the Termux:X11 Android app unless a visible login session is needed.

Run the automated tests:

```sh
python -m unittest discover -s tests -v
```

## First Login

TikTok, Chess.com, and Duolingo may require a logged-in browser profile before automation can run.

When a platform is not logged in, Streakify starts Termux X11, opens a visible Chromium tab for that platform, and waits for you to finish login.

Login tab behavior:

- If only one platform needs login, only that login tab is opened.
- If multiple platforms need login, each login page is opened in a separate tab.

After the login is complete in the visible browser, return to Termux and press `Enter`. Streakify checks the session again, continues the enabled automation, then closes the browser and the Termux X11 session it started.

If `browser.headless=true` and login is required, Streakify opens a temporary visible login session through the Termux:X11 Android app. After you press `Enter`, it returns to headless mode for automation.

> [!NOTE]
> TikTok, Chess.com, and Duolingo share the same Selenium profile directory: `$HOME/.streakify/.auth/selenium-profile`

Chess.com is checked through `https://www.chess.com/login` first. If the shared Selenium profile is not logged in, Streakify opens the login tab before going to puzzles.

Duolingo is checked through `https://www.duolingo.com/chess-match`. Streakify waits briefly so Duolingo has time to redirect. If Duolingo redirects to `/chess-match?isLoggingIn=true`, Streakify reports login required. If `/chess-match` remains stable, Streakify treats the session as active. If Duolingo leaves the `/chess-match` endpoint for any other Duolingo page, Streakify reports an error.

## Troubleshooting

### Browser Fails to Start

Check:

```sh
chromium-browser --version
chromedriver --version
command -v termux-x11
cat config.txt
```

Make sure the browser profile is already logged in before running automation.

For visible login, make sure the Termux:X11 Android app is installed. Streakify starts the Termux X11 server and opens the app automatically, but the Android app must exist on the device.

### Login Keeps Appearing

The saved session may be expired. Remove the browser profile and log in again:

```sh
rm -rf $HOME/.streakify/.auth/selenium-profile
sh run.sh
```

### Chess.com Stockfish Error

Check:

```sh
command -v stockfish
stockfish
```

If the command is missing, install Stockfish in Termux and rerun Streakify.

If Stockfish reports no legal alternative to its best move, Streakify stops with an error before clicking the board.

### Chess.com Move Click Error

The Chess.com adapter uses Selenium native `element.click()` for every browser click. For empty target squares, it waits for Chess.com's move hint after selecting the source piece and makes that hint pointer-clickable before retrying the native click. If Chess.com does not expose a target element or another overlay blocks the click, Streakify stops with an error. JavaScript click, ActionChains, and coordinate click fallbacks are not used.

### Duolingo Board or Move Error

Duolingo renders the chess board inside a canvas, so there are no Selenium piece or square elements to click. Streakify uses Chrome DevTools Protocol mouse events only for dragging moves on that canvas. Navigation and the final Continue button still use Selenium. After the local board reaches checkmate, Streakify waits for Duolingo's `data-test="player-next"` control and clicks it once with native `element.click()`.

If Duolingo repeatedly restarts matches, verify:

```sh
command -v stockfish
python -c "import chess; print(chess.__version__)"
python -c "import tflite_runtime.interpreter; print('tflite ok')"
```

Use a stable connection and avoid resizing a visible Chromium window while a match is running. Set `browser.headless=true` after login for the most consistent canvas dimensions.

### Config Error

Streakify refuses to run when:

- A required setting is missing.
- A setting name is misspelled.
- A value is empty or invalid.
- A deprecated setting is still used.
- A setting is duplicated.

Follow the error message and update `config.txt`.

## Project Structure

```text
streakify-termux/
├── install.sh              # Installation script
├── run.sh                  # Runner script
├── config.txt              # User configuration
├── requirements.txt        # Python dependencies
├── LICENSE                 # MIT license
├── README.md               # Documentation
├── streakify/              # Python package
    ├── __init__.py
    ├── __main__.py         # CLI entry point
    ├── browser.py          # Browser setup and diagnostics
    ├── config.py           # Config parsing and validation
    ├── results.py          # Run result data class
    ├── runtime_paths.py    # Runtime path helpers
    ├── stockfish.py        # Shared Stockfish UCI process
    ├── termux_x11.py       # Termux X11 lifecycle
    ├── tiktok.py           # TikTok adapter
    ├── chess.py            # Chess.com adapter
    ├── duolingo.py         # Duolingo adapter
    ├── duolingo_vision.py  # Duolingo TFLite runtime
    └── models/duolingo/    # Duolingo model files
└── tests/                  # Automated unit tests
    ├── test_duolingo.py
    └── test_duolingo_vision.py
```

## FAQ

### Is this safe?

Streakify runs locally on your phone and does not send your data to a Streakify server. Browser sessions are stored locally in `$HOME/.streakify/`. Do not share that directory.

### Can my account be banned?

Any automation has risk. Streakify uses a real Chromium browser, but you should still use it carefully and avoid setting `tiktok.max_chats` too high. The Chess.com flow intentionally makes a wrong move in a rated puzzle, so it can lower your puzzle rating.

### Can it run automatically every day?

There is no built-in scheduler yet. You can later run `sh run.sh` through Termux-compatible scheduling tools such as `crond` or `termux-job-scheduler`.

### Does it require root?

No. Streakify runs fully inside Termux.

### Can other platforms be added?

Yes. Streakify is designed so each platform can be implemented as a separate adapter.

## License

[MIT License](LICENSE). You may use, modify, and distribute this project under the license terms.
