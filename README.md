# Streakify

Streakify is a Python automation tool for maintaining streaks across platforms directly from Termux on Android.

Current platform support:

- TikTok: opens messages, checks the session, selects chats, and sends a configured message through Chromium and Selenium.

More platforms can be added later as separate adapters.

## How It Works

```text
Run Streakify in Termux
        |
        v
Streakify starts Chromium automatically
        |
        v
Opens the platform messages page
        |
        v
Selects chat -> Inserts message -> Sends
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
| Internet access | Needed for installation and automation |
| Termux:X11 | Optional, only needed for headful browser mode or manual login |

Do not install Termux from the Play Store. That version is outdated and often breaks package installation. Use [F-Droid](https://f-droid.org/en/packages/com.termux/) or [Termux GitHub releases](https://github.com/termux/termux-app/releases).

## Installation

Fast setup:

```sh
git clone https://github.com/Ren42377/streakify-termux.git
cd streakify-termux
sh install.sh
```

The installer will:

1. Update Termux packages.
2. Install Python, Chromium, and Termux:X11 packages.
3. Install Python dependencies from `requirements.txt`.
4. Verify that Chromium and ChromeDriver are available.

Manual setup:

```sh
pkg update
pkg install python x11-repo
pkg install chromium termux-x11-nightly
python -m pip install -r requirements.txt
```

Verify browser tools:

```sh
chromium-browser --version
chromedriver --version
```

If either command is missing, check the Chromium package installation from Termux repositories.

## Configuration

Edit `config.txt` before running Streakify.

Required settings:

```txt
tiktok=true
browser.headless=true
tiktok.message=🔥
tiktok.max_chats=10
```

| Setting | Value | Purpose |
| --- | --- | --- |
| `tiktok` | `true` or `false` | Enable or skip the TikTok flow |
| `browser.headless` | `true` or `false` | Use headless Chromium when true. Headful mode requires Termux:X11 |
| `tiktok.message` | Any non-empty text | Message sent to each chat. Emoji are supported if `config.txt` is saved as UTF-8 |
| `tiktok.max_chats` | Positive integer | Number of chats processed in one run |

If any setting is missing, misspelled, duplicated, empty, or invalid, Streakify stops before opening the browser and prints the setting that must be fixed.

Browser and ChromeDriver paths are not configured in `config.txt`. Streakify detects them automatically from Termux.

## Runtime Data

By default, runtime data is stored in:

```text
$HOME/.streakify/
```

That directory contains:

- Browser profile and login session: `$HOME/.streakify/auth/selenium-profile`
- Driver cache: `$HOME/.streakify/drivers`

To move all runtime data:

```sh
STREAKIFY_HOME="$HOME/.streakify-alt" sh run.sh
```

Do not point `STREAKIFY_HOME` to the project folder or Android shared storage. Chromium can fail to create lock files there.

Do not commit tokens, cookies, credentials, browser profiles, or session files.

## Usage

Run the TikTok flow:

```sh
sh run.sh
```

Or run it directly with Python:

```sh
python -m streakify tiktok
```

If `tiktok=false`, Streakify skips the TikTok flow and exits successfully.

## First Login

TikTok may require a manual login the first time.

If `browser.headless=true` and TikTok asks for login, Streakify tries to open a headful browser when `DISPLAY` is available. Start Termux:X11 first if manual login is needed.

After login completes:

1. Finish login in the browser window.
2. Return to Termux.
3. Press Enter when prompted.
4. The browser session is saved for later runs.

After the session is saved, daily runs can usually use `browser.headless=true` without Termux:X11.

## Termux:X11 Notes

Termux:X11 is only needed for:

- `browser.headless=false`
- Manual login in a visible browser window

It is not required for a normal headless run if the browser profile is already logged in.

When Termux:X11 is missing or not ready, Streakify prints diagnostics for:

- `DISPLAY`
- `termux-x11`
- `$PREFIX/var/run/tx11.display`
- `sv status tx11`

## Troubleshooting

### Browser Fails to Start

Check:

```sh
chromium-browser --version
chromedriver --version
cat config.txt
```

If using headful mode or manual login, also check:

```sh
command -v termux-x11
sv status tx11
cat $PREFIX/var/run/tx11.display
```

If you do not want to use Termux:X11, set:

```txt
browser.headless=true
```

Then make sure the browser profile is already logged in.

### Login Keeps Appearing

The saved session may be expired. Remove the browser profile and log in again:

```sh
rm -rf $HOME/.streakify/auth/selenium-profile
sh run.sh
```

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
└── streakify/              # Python package
    ├── __init__.py
    ├── __main__.py         # CLI entry point
    ├── browser.py          # Browser setup and diagnostics
    ├── config.py           # Config parsing and validation
    ├── results.py          # Run result data class
    ├── runtime_paths.py    # Runtime path helpers
    └── tiktok.py           # TikTok adapter
```

## FAQ

### Is this safe?

Streakify runs locally on your phone and does not send your data to a Streakify server. Browser sessions are stored locally in `$HOME/.streakify/`. Do not share that directory.

### Can my account be banned?

Any automation has risk. Streakify uses a real Chromium browser, but you should still use it carefully and avoid setting `tiktok.max_chats` too high.

### Can it run automatically every day?

There is no built-in scheduler yet. You can later run `sh run.sh` through Termux-compatible scheduling tools such as `crond` or `termux-job-scheduler`.

### Does it require root?

No. Streakify runs fully inside Termux.

### Can other platforms be added?

Yes. Streakify is designed so each platform can be implemented as a separate adapter.

## License

[MIT License](LICENSE). You may use, modify, and distribute this project under the license terms.
