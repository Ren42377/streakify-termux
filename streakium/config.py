from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from streakium.runtime_paths import get_auth_profile_dir, get_snapchat_camera_folder


class StreakiumConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool
    timeout_ms: int
    profile_dir: Path
    fake_video_path: Path | None = None


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
class SnapchatConfig:
    web_url: str
    usernames: tuple[str, ...]
    camera_folder: Path
    camera_mode: str


@dataclass(frozen=True)
class ScheduleConfig:
    enabled: bool
    time: str


@dataclass(frozen=True)
class AppConfig:
    tiktok_enabled: bool
    chess_enabled: bool
    duolingo_enabled: bool
    snapchat_enabled: bool
    browser: BrowserConfig
    tiktok: TikTokConfig
    chess: ChessConfig
    duolingo: DuolingoConfig
    snapchat: SnapchatConfig
    schedule: ScheduleConfig


BROWSER_TIMEOUT_MS = 30000
TIKTOK_LOGIN_URL = "https://www.tiktok.com/login"
TIKTOK_MESSAGES_URL = "https://www.tiktok.com/messages"
TIKTOK_CHAT_OPEN_DELAY_MS = 1500
TIKTOK_SEND_DELAY_MS = 1000
CHESS_LOGIN_URL = "https://www.chess.com/login"
CHESS_PUZZLES_URL = "https://www.chess.com/puzzles/rated"
CHESS_OPPONENT_WAIT_SECONDS = 30
DUOLINGO_CHESS_MATCH_URL = "https://www.duolingo.com/chess-match"
SNAPCHAT_WEB_URL = "https://www.snapchat.com/web"
SNAPCHAT_CAMERA_MODE = "random"
SNAPCHAT_CAMERA_MODES = {"random", "newest"}
SCHEDULE_ENABLED = False
SCHEDULE_TIME = "09:00"

REQUIRED_KEYS = {
    "tiktok",
    "chess",
    "duolingo",
    "snapchat",
    "browser.headless",
    "tiktok.message",
    "tiktok.max_chats",
    "chess.engine_time",
    "snapchat.usernames",
}

OPTIONAL_KEYS = {
    "snapchat.camera_folder",
    "snapchat.camera_mode",
    "schedule.enabled",
    "schedule.time",
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
    "snapchat.web_url": "snapchat.web_url is not configurable.",
}

EXPECTED_CONFIG = """Expected config.txt:
tiktok=true
chess=true
duolingo=false
snapchat=false
browser.headless=true
tiktok.message=🔥
tiktok.max_chats=10
chess.engine_time=0.4
snapchat.usernames=user_a,user_b
snapchat.camera_folder=assets
snapchat.camera_mode=random
schedule.enabled=false
schedule.time=09:00"""


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
        snapchat_enabled=_read_bool(values, "snapchat"),
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
        snapchat=SnapchatConfig(
            web_url=SNAPCHAT_WEB_URL,
            usernames=_read_usernames(
                values,
                "snapchat.usernames",
                required=_read_bool(values, "snapchat"),
            ),
            camera_folder=_read_optional_path(
                values,
                "snapchat.camera_folder",
                get_snapchat_camera_folder(),
                config_path.parent,
            ),
            camera_mode=_read_camera_mode(values, "snapchat.camera_mode"),
        ),
        schedule=ScheduleConfig(
            enabled=_read_optional_bool(values, "schedule.enabled", SCHEDULE_ENABLED),
            time=_read_schedule_time(values, "schedule.time"),
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
        if key not in REQUIRED_KEYS and key not in OPTIONAL_KEYS:
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
    return _parse_bool(value, key, values[key])


def _read_optional_bool(values: dict[str, str], key: str, default: bool) -> bool:
    if key not in values:
        return default
    return _parse_bool(values[key].strip().lower(), key, values[key])


def _parse_bool(value: str, key: str, original: str) -> bool:
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    _raise_config_error(f"Invalid boolean value for {key}: {original}.")


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


def _read_usernames(values: dict[str, str], key: str, required: bool) -> tuple[str, ...]:
    raw_usernames = [value.strip().removeprefix("@") for value in values[key].split(",")]
    usernames = tuple(value for value in raw_usernames if value)
    if required and not usernames:
        _raise_config_error(f"At least one username is required for {key}.")
    normalized = [value.casefold() for value in usernames]
    if len(normalized) != len(set(normalized)):
        _raise_config_error(f"Duplicate username in {key}.")
    return usernames


def _read_optional_path(values: dict[str, str], key: str, default: Path, base_dir: Path) -> Path:
    value = values.get(key, "").strip()
    if not value:
        return default
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _read_camera_mode(values: dict[str, str], key: str) -> str:
    value = values.get(key, SNAPCHAT_CAMERA_MODE).strip().casefold()
    if value in SNAPCHAT_CAMERA_MODES:
        return value
    _raise_config_error(f"Invalid Snapchat camera mode for {key}: {values[key]}. Use random or newest.")


def _read_schedule_time(values: dict[str, str], key: str) -> str:
    value = values.get(key, SCHEDULE_TIME).strip()
    parts = value.split(":", 1)
    if len(parts) != 2:
        _raise_config_error(f"Invalid schedule time for {key}: {value}. Use HH:MM.")
    hour_text, minute_text = parts
    if len(hour_text) not in {1, 2} or len(minute_text) != 2:
        _raise_config_error(f"Invalid schedule time for {key}: {value}. Use HH:MM.")
    try:
        hour = int(hour_text)
        minute = int(minute_text)
    except ValueError as exc:
        _raise_config_error(f"Invalid schedule time for {key}: {value}. Use HH:MM.", exc)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        _raise_config_error(f"Invalid schedule time for {key}: {value}. Use HH:MM.")
    return f"{hour:02d}:{minute:02d}"


def _raise_config_error(message: str, cause: Exception | None = None) -> None:
    error = StreakiumConfigError(f"{message}\n\n{EXPECTED_CONFIG}")
    if cause is None:
        raise error
    raise error from cause
