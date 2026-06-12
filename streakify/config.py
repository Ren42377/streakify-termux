from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    message: str
    max_chats: int
    chat_open_delay_ms: int
    send_delay_ms: int


@dataclass(frozen=True)
class ChessConfig:
    login_url: str
    puzzles_url: str
    engine_time: float
    opponent_wait_seconds: int


@dataclass(frozen=True)
class DuolingoConfig:
    chess_match_url: str


@dataclass(frozen=True)
class AppConfig:
    tiktok_enabled: bool
    chess_enabled: bool
    duolingo_enabled: bool
    browser: BrowserConfig
    tiktok: TikTokConfig
    chess: ChessConfig
    duolingo: DuolingoConfig


BROWSER_TIMEOUT_MS = 30000
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"
TIKTOK_MESSAGES_URL = "https://www.tiktok.com/messages"
TIKTOK_CHAT_OPEN_DELAY_MS = 1500
TIKTOK_SEND_DELAY_MS = 1000
CHESS_LOGIN_URL = "https://www.chess.com/login"
CHESS_PUZZLES_URL = "https://www.chess.com/puzzles/rated"
CHESS_OPPONENT_WAIT_SECONDS = 30
DUOLINGO_CHESS_MATCH_URL = "https://www.duolingo.com/chess-match"

REQUIRED_KEYS = {
    "tiktok",
    "chess",
    "duolingo",
    "browser.headless",
    "tiktok.message",
    "tiktok.max_chats",
    "chess.engine_time",
}

DEPRECATED_KEYS = {
    "browser.binary_path": "browser.binary_path is no longer supported. Chromium is detected automatically.",
    "browser.driver_path": "browser.driver_path is no longer supported. ChromeDriver is detected automatically.",
    "browser.timeout_ms": "browser.timeout_ms is no longer configurable.",
    "tiktok.login_url": "tiktok.login_url is no longer configurable.",
    "tiktok.messages_url": "tiktok.messages_url is no longer configurable.",
    "tiktok.login_wait_seconds": "tiktok.login_wait_seconds is no longer configurable.",
    "tiktok.message_template": "tiktok.message_template is no longer supported. Use tiktok.message.",
    "tiktok.chat_open_delay_ms": "tiktok.chat_open_delay_ms is no longer configurable.",
    "tiktok.send_delay_ms": "tiktok.send_delay_ms is no longer configurable.",
    "chess.login_url": "chess.login_url is no longer configurable.",
    "chess.puzzles_url": "chess.puzzles_url is no longer configurable.",
    "chess.login_wait_seconds": "chess.login_wait_seconds is no longer configurable.",
    "chess.stockfish_bin": "chess.stockfish_bin is no longer supported. Install stockfish in Termux and make sure stockfish is in PATH.",
    "chess.max_player_moves": "chess.max_player_moves is no longer supported. Chess.com stops when completion or no opponent move is detected.",
    "duolingo.login_url": "duolingo.login_url is no longer configurable.",
    "duolingo.chess_match_url": "duolingo.chess_match_url is no longer configurable.",
}

EXPECTED_CONFIG = """Expected config.txt:
tiktok=true
chess=true
duolingo=false
browser.headless=true
tiktok.message=🔥
tiktok.max_chats=10
chess.engine_time=0.4"""


def load_config(path: str | Path = "config.txt") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        _raise_config_error(f"Config file was not found: {config_path}.")
    values = _read_config_file(config_path)
    _validate_required_keys(values)
    return AppConfig(
        tiktok_enabled=_read_bool(values, "tiktok"),
        chess_enabled=_read_bool(values, "chess"),
        duolingo_enabled=_read_bool(values, "duolingo"),
        browser=BrowserConfig(
            headless=_read_bool(values, "browser.headless"),
            timeout_ms=BROWSER_TIMEOUT_MS,
            profile_dir=get_auth_profile_dir(),
        ),
        tiktok=TikTokConfig(
            login_url=TIKTOK_LOGIN_URL,
            messages_url=TIKTOK_MESSAGES_URL,
            message=_read_required_text(values, "tiktok.message"),
            max_chats=_read_positive_int(values, "tiktok.max_chats"),
            chat_open_delay_ms=TIKTOK_CHAT_OPEN_DELAY_MS,
            send_delay_ms=TIKTOK_SEND_DELAY_MS,
        ),
        chess=ChessConfig(
            login_url=CHESS_LOGIN_URL,
            puzzles_url=CHESS_PUZZLES_URL,
            engine_time=_read_positive_float(values, "chess.engine_time"),
            opponent_wait_seconds=CHESS_OPPONENT_WAIT_SECONDS,
        ),
        duolingo=DuolingoConfig(
            chess_match_url=DUOLINGO_CHESS_MATCH_URL,
        ),
    )


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


def _read_positive_float(values: dict[str, str], key: str) -> float:
    try:
        value = float(values[key])
    except ValueError as exc:
        _raise_config_error(f"Invalid number value for {key}: {values[key]}.", exc)
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
