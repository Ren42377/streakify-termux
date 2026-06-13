from __future__ import annotations

import shutil
import subprocess


def notify(title: str, message: str) -> None:
    command = shutil.which("termux-notification")
    if command is None:
        return
    try:
        subprocess.run(
            [command, "--title", title, "--content", message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        return
