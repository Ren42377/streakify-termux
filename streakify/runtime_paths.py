from __future__ import annotations

import os
from pathlib import Path


def get_streakify_home() -> Path:
    value = os.environ.get("STREAKIFY_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / ".streakify"


def get_auth_profile_dir() -> Path:
    return get_streakify_home() / ".auth" / "selenium-profile"


def get_driver_cache_dir() -> Path:
    return get_streakify_home() / ".drivers"


def get_duolingo_model_dir() -> Path:
    return Path(__file__).resolve().parent / "models" / "duolingo"


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
