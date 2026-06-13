from __future__ import annotations

import os
from pathlib import Path


def get_streakium_home() -> Path:
    value = os.environ.get("STREAKIUM_HOME", "").strip()
    if value:
        return Path(value).expanduser()
    return Path.home() / ".streakium"


def get_auth_profile_dir() -> Path:
    return get_streakium_home() / ".auth" / "selenium-profile"


def get_driver_cache_dir() -> Path:
    return get_streakium_home() / ".drivers"


def get_media_cache_dir() -> Path:
    return get_streakium_home() / "media"


def get_scheduler_state_path() -> Path:
    return get_streakium_home() / "scheduler-state.txt"


def get_snapchat_camera_folder() -> Path:
    return Path(__file__).resolve().parent.parent / "assets"


def get_snapchat_camera_source() -> Path:
    return get_snapchat_camera_folder() / "snapchat-camera.jpg"


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
