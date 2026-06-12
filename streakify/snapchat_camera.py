from __future__ import annotations

import hashlib
import os
import random
import shutil
import subprocess
from pathlib import Path

from streakify.runtime_paths import get_media_cache_dir, get_snapchat_camera_folder


class SnapchatCameraError(RuntimeError):
    pass


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
CAMERA_MODES = {"random", "newest"}


def is_ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def prepare_snapchat_camera(source_path: Path | None = None, mode: str = "random") -> Path:
    source = select_snapchat_camera_image(source_path or get_snapchat_camera_folder(), mode)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SnapchatCameraError("FFmpeg was not found in PATH. Install ffmpeg in Termux.")
    digest = _file_sha256(source)
    cache_dir = get_media_cache_dir()
    video_path = cache_dir / "snapchat-camera.y4m"
    hash_path = cache_dir / "snapchat-camera.sha256"
    if video_path.is_file() and _read_hash(hash_path) == digest:
        return video_path
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary_path = cache_dir / "snapchat-camera.tmp.y4m"
    environment = os.environ.copy()
    if "codex-cli-termux/bin" in environment.get("LD_LIBRARY_PATH", ""):
        environment.pop("LD_LIBRARY_PATH", None)
    command = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(source),
        "-vf",
        "scale=480:854:force_original_aspect_ratio=increase,crop=480:854,format=yuv420p",
        "-r",
        "15",
        "-frames:v",
        "15",
        "-f",
        "yuv4mpegpipe",
        str(temporary_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            env=environment,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SnapchatCameraError(f"Snapchat camera video could not be created: {exc}") from exc
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()
        detail = message[-1] if message else "unknown FFmpeg error"
        raise SnapchatCameraError(f"Snapchat camera video could not be created: {detail}")
    try:
        temporary_path.replace(video_path)
        hash_path.write_text(f"{digest}\n", encoding="ascii")
    except OSError as exc:
        raise SnapchatCameraError(f"Snapchat camera cache could not be saved: {exc}") from exc
    return video_path


def select_snapchat_camera_image(source_path: Path, mode: str = "random") -> Path:
    if source_path.is_file():
        if _is_image(source_path):
            return source_path
        raise SnapchatCameraError(f"Snapchat camera source is not a supported image: {source_path}")
    if not source_path.is_dir():
        raise SnapchatCameraError(f"Snapchat camera folder was not found: {source_path}")
    images = sorted(path for path in source_path.iterdir() if path.is_file() and _is_image(path))
    if not images:
        raise SnapchatCameraError(f"Snapchat camera folder has no supported images: {source_path}")
    if mode == "random":
        return random.choice(images)
    if mode == "newest":
        return max(images, key=lambda path: (path.stat().st_mtime_ns, path.name))
    raise SnapchatCameraError(f"Invalid Snapchat camera mode: {mode}. Use random or newest.")


def _is_image(path: Path) -> bool:
    return path.suffix.casefold() in IMAGE_EXTENSIONS


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise SnapchatCameraError(f"Snapchat camera image could not be read: {exc}") from exc
    return digest.hexdigest()


def _read_hash(path: Path) -> str:
    try:
        return path.read_text(encoding="ascii").strip()
    except OSError:
        return ""
