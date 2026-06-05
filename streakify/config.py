from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class StreakifyConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserConfig:
    headless: bool
    timeout_ms: int
    profile_dir: Path
    binary_path: str | None
    driver_path: str | None


@dataclass(frozen=True)
class TikTokConfig:
    login_url: str
    messages_url: str
    login_wait_seconds: int
    message_template: str
    max_chats: int
    dry_run: bool
    chat_open_delay_ms: int
    send_delay_ms: int


@dataclass(frozen=True)
class AppConfig:
    browser: BrowserConfig
    tiktok: TikTokConfig


DEFAULT_VALUES = {
    "browser.headless": "true",
    "browser.timeout_ms": "30000",
    "browser.profile_dir": "~/.streakify/selenium-profile",
    "browser.binary_path": "",
    "browser.driver_path": "",
    "tiktok.login_url": "https://www.tiktok.com/login",
    "tiktok.messages_url": "https://www.tiktok.com/messages",
    "tiktok.login_wait_seconds": "300",
    "tiktok.message_template": "Keep the streak alive.",
    "tiktok.max_chats": "1",
    "tiktok.dry_run": "true",
    "tiktok.chat_open_delay_ms": "1500",
    "tiktok.send_delay_ms": "1000",
}


def load_config(path: str | Path = "config.txt") -> AppConfig:
    values = dict(DEFAULT_VALUES)
    config_path = Path(path)
    if config_path.exists():
        values.update(_read_config_file(config_path))
    return AppConfig(
        browser=BrowserConfig(
            headless=_read_bool(values, "browser.headless"),
            timeout_ms=_read_positive_int(values, "browser.timeout_ms"),
            profile_dir=Path(values["browser.profile_dir"]).expanduser(),
            binary_path=_read_optional_text(values, "browser.binary_path"),
            driver_path=_read_optional_text(values, "browser.driver_path"),
        ),
        tiktok=TikTokConfig(
            login_url=_read_required_text(values, "tiktok.login_url"),
            messages_url=_read_required_text(values, "tiktok.messages_url"),
            login_wait_seconds=_read_positive_int(values, "tiktok.login_wait_seconds"),
            message_template=_read_required_text(values, "tiktok.message_template"),
            max_chats=_read_positive_int(values, "tiktok.max_chats"),
            dry_run=_read_bool(values, "tiktok.dry_run"),
            chat_open_delay_ms=_read_positive_int(values, "tiktok.chat_open_delay_ms"),
            send_delay_ms=_read_positive_int(values, "tiktok.send_delay_ms"),
        ),
    )


def _read_config_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise StreakifyConfigError(f"Invalid config line {line_number}: expected key=value.")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in DEFAULT_VALUES:
            raise StreakifyConfigError(f"Unknown config key on line {line_number}: {key}.")
        values[key] = value.strip()
    return values


def _read_bool(values: dict[str, str], key: str) -> bool:
    value = values[key].strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise StreakifyConfigError(f"Invalid boolean value for {key}: {values[key]}.")


def _read_positive_int(values: dict[str, str], key: str) -> int:
    try:
        value = int(values[key])
    except ValueError as exc:
        raise StreakifyConfigError(f"Invalid integer value for {key}: {values[key]}.") from exc
    if value <= 0:
        raise StreakifyConfigError(f"Config value must be positive for {key}.")
    return value


def _read_optional_text(values: dict[str, str], key: str) -> str | None:
    value = values[key].strip()
    return value or None


def _read_required_text(values: dict[str, str], key: str) -> str:
    value = values[key].strip()
    if not value:
        raise StreakifyConfigError(f"Config value is required for {key}.")
    return value
