from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streakify.runtime_paths import debug_runtime_paths as _debug_runtime_paths
from streakify.runtime_paths import get_auth_profile_dir


class StreakifyConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool
    timeout_ms: int
    profile_dir: Path


@dataclass(frozen=True)
class TikTokConfig:
    login_url: str
    messages_url: str
    login_wait_seconds: int
    message: str
    max_chats: int
    chat_open_delay_ms: int
    send_delay_ms: int


@dataclass(frozen=True)
class AppConfig:
    tiktok_enabled: bool
    browser: BrowserConfig
    tiktok: TikTokConfig


BROWSER_TIMEOUT_MS = 30000
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"
TIKTOK_MESSAGES_URL = "https://www.tiktok.com/messages"
TIKTOK_LOGIN_WAIT_SECONDS = 300
TIKTOK_CHAT_OPEN_DELAY_MS = 1500
TIKTOK_SEND_DELAY_MS = 1000

REQUIRED_KEYS = {
    "tiktok",
    "browser.headless",
    "tiktok.message",
    "tiktok.max_chats",
}

DEPRECATED_KEYS = {
    "browser.profile_dir": "browser.profile_dir is no longer supported. Use STREAKIFY_HOME to change runtime data location.",
    "browser.binary_path": "browser.binary_path is no longer supported. Chromium is detected automatically.",
    "browser.driver_path": "browser.driver_path is no longer supported. ChromeDriver is detected automatically.",
    "browser.timeout_ms": "browser.timeout_ms is no longer configurable.",
    "tiktok.login_url": "tiktok.login_url is no longer configurable.",
    "tiktok.messages_url": "tiktok.messages_url is no longer configurable.",
    "tiktok.login_wait_seconds": "tiktok.login_wait_seconds is no longer configurable.",
    "tiktok.message_template": "tiktok.message_template is no longer supported. Use tiktok.message.",
    "tiktok.chat_open_delay_ms": "tiktok.chat_open_delay_ms is no longer configurable.",
    "tiktok.send_delay_ms": "tiktok.send_delay_ms is no longer configurable.",
}

EXPECTED_CONFIG = """Expected config.txt:
tiktok=true
browser.headless=false
tiktok.message=Keep the streak alive.
tiktok.max_chats=1"""


def load_config(path: str | Path = "config.txt") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        _raise_config_error(f"Config file was not found: {config_path}.")
    values = _read_config_file(config_path)
    _validate_required_keys(values)
    return AppConfig(
        tiktok_enabled=_read_bool(values, "tiktok"),
        browser=BrowserConfig(
            headless=_read_bool(values, "browser.headless"),
            timeout_ms=BROWSER_TIMEOUT_MS,
            profile_dir=get_auth_profile_dir(),
        ),
        tiktok=TikTokConfig(
            login_url=TIKTOK_LOGIN_URL,
            messages_url=TIKTOK_MESSAGES_URL,
            login_wait_seconds=TIKTOK_LOGIN_WAIT_SECONDS,
            message=_read_required_text(values, "tiktok.message"),
            max_chats=_read_positive_int(values, "tiktok.max_chats"),
            chat_open_delay_ms=TIKTOK_CHAT_OPEN_DELAY_MS,
            send_delay_ms=TIKTOK_SEND_DELAY_MS,
        ),
    )


def debug_auth_profile_dir() -> str:
    return str(get_auth_profile_dir())


def debug_runtime_paths() -> dict[str, str]:
    return _debug_runtime_paths()


def debug_tiktok_settings(config: AppConfig) -> dict[str, int | bool]:
    return {
        "enabled": config.tiktok_enabled,
        "message_length": len(config.tiktok.message),
        "max_chats": config.tiktok.max_chats,
    }


def _read_config_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _raise_config_error(f"Config file could not be read: {path}.", exc)
    except UnicodeError as exc:
        _raise_config_error(f"Config file must use UTF-8 encoding: {path}.", exc)
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            _raise_config_error(f"Invalid config line {line_number}: expected key=value.")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in DEPRECATED_KEYS:
            _raise_config_error(f"{DEPRECATED_KEYS[key]} Line: {line_number}.")
        if key not in REQUIRED_KEYS:
            _raise_config_error(f"Unknown config key on line {line_number}: {key}.")
        if key in values:
            _raise_config_error(f"Duplicate config key on line {line_number}: {key}.")
        values[key] = value.strip()
    return values


def _validate_required_keys(values: dict[str, str]) -> None:
    missing_keys = sorted(REQUIRED_KEYS.difference(values))
    if missing_keys:
        _raise_config_error(f"Missing required config setting: {', '.join(missing_keys)}.")


def _read_bool(values: dict[str, str], key: str) -> bool:
    value = values[key].strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    _raise_config_error(f"Invalid boolean value for {key}: {values[key]}.")


def _read_positive_int(values: dict[str, str], key: str) -> int:
    try:
        value = int(values[key])
    except ValueError as exc:
        _raise_config_error(f"Invalid integer value for {key}: {values[key]}.", exc)
    if value <= 0:
        _raise_config_error(f"Config value must be positive for {key}.")
    return value


def _read_required_text(values: dict[str, str], key: str) -> str:
    value = values[key].strip()
    if not value:
        _raise_config_error(f"Config value is required for {key}.")
    return value


def _raise_config_error(message: str, cause: Exception | None = None) -> None:
    error = StreakifyConfigError(f"{message}\n\n{EXPECTED_CONFIG}")
    if cause is None:
        raise error
    raise error from cause
