from __future__ import annotations

import os
from pathlib import Path


def get_streakify_home() -> Path:
    value = os.environ.get("STREAKIFY_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / ".streakify"


def get_auth_profile_dir() -> Path:
    return get_streakify_home() / "auth" / "selenium-profile"


def get_driver_cache_dir() -> Path:
    return get_streakify_home() / "drivers"


def get_termux_prefix() -> Path | None:
    value = os.environ.get("PREFIX", "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def get_termux_chromium_binary() -> Path | None:
    prefix = get_termux_prefix()
    if prefix is None:
        return None
    return prefix / "lib" / "chromium" / "chrome"


def debug_runtime_paths() -> dict[str, str]:
    paths = {
        "streakify_home": get_streakify_home(),
        "auth_profile_dir": get_auth_profile_dir(),
        "driver_cache_dir": get_driver_cache_dir(),
    }
    chromium_binary = get_termux_chromium_binary()
    if chromium_binary is not None:
        paths["termux_chromium_binary"] = chromium_binary
    return {name: str(path) for name, path in paths.items()}
