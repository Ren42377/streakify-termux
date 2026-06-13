from __future__ import annotations

import os
import signal
import shutil
import subprocess
import time

from streakium.runtime_paths import get_streakium_home


class TermuxX11Error(RuntimeError):
    pass


class TermuxX11Session:
    def __init__(
        self,
        display: str = ":0",
        startup_wait_seconds: float = 1.5,
        open_app: bool = True,
    ):
        self.display = display
        self.active_display = display
        self.startup_wait_seconds = startup_wait_seconds
        self.open_app = open_app
        self.opened_app = False
        self.process: subprocess.Popen[bytes] | None = None
        self.previous_display: str | None = None
        self.managed = False
        self.recorded_pid: int | None = None

    def __enter__(self) -> "TermuxX11Session":
        self.previous_display = os.environ.get("DISPLAY")
        self.active_display = _select_display(self.previous_display, self.display)
        os.environ["DISPLAY"] = self.active_display
        self.recorded_pid = _read_recorded_server_pid(self.active_display)
        if _is_termux_x11_running(self.active_display):
            self._open_app_if_requested()
            return self
        command = shutil.which("termux-x11")
        if command is None:
            self._restore_display()
            raise TermuxX11Error("termux-x11 was not found. Install x11-repo and termux-x11-nightly, then try again.")
        try:
            self.process = subprocess.Popen(
                [command, self.active_display, "-ac"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            self._restore_display()
            raise TermuxX11Error(f"Termux X11 could not be started: {exc}") from exc
        self.managed = True
        self.recorded_pid = self.process.pid
        _write_recorded_server_pid(self.active_display, self.process.pid)
        time.sleep(self.startup_wait_seconds)
        if self.process.poll() is not None:
            _clear_recorded_server_pid()
            self._restore_display()
            raise TermuxX11Error("Termux X11 stopped before Chromium could connect.")
        self._open_app_if_requested()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self.opened_app:
            _close_termux_x11_app()
        if self.managed:
            self._stop_server()
            _clear_recorded_server_pid()
        self._restore_display()

    def _open_app_if_requested(self) -> None:
        if not self.open_app:
            return
        try:
            _open_termux_x11_app()
        except TermuxX11Error:
            if self.managed:
                self._stop_server()
                _clear_recorded_server_pid()
            self._restore_display()
            raise
        self.opened_app = True
        time.sleep(0.5)

    def _stop_server(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def _restore_display(self) -> None:
        if self.previous_display is None:
            os.environ.pop("DISPLAY", None)
            return
        os.environ["DISPLAY"] = self.previous_display


def stop_termux_x11_server(display: str = ":0") -> None:
    pid = _read_recorded_server_pid(display)
    if pid is not None:
        _terminate_pid(pid, display)
    else:
        for found_pid in _find_termux_x11_pids(display):
            _terminate_pid(found_pid, display)
    _clear_recorded_server_pid()
    _close_termux_x11_app()


def _open_termux_x11_app() -> None:
    command = shutil.which("am")
    if command is None:
        raise TermuxX11Error("Android activity manager was not found. Open Termux X11 manually and set DISPLAY.")
    package_name = _termux_x11_package_name()
    try:
        completed = subprocess.run(
            [command, "start", "--user", "0", "-n", f"{package_name}/.MainActivity"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise TermuxX11Error("Termux X11 app did not open before the timeout.") from exc
    except OSError as exc:
        raise TermuxX11Error(f"Termux X11 app could not be opened: {exc}") from exc
    if completed.returncode != 0:
        message = (completed.stdout + completed.stderr).strip()
        if not message:
            message = "no activity manager output"
        raise TermuxX11Error(f"Termux X11 app could not be opened: {message}")


def _select_display(previous_display: str | None, default_display: str) -> str:
    if previous_display and previous_display.startswith(":"):
        return previous_display
    return default_display


def _is_termux_x11_running(display: str) -> bool:
    try:
        completed = subprocess.run(
            ["ps", "-ef"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    for line in completed.stdout.splitlines():
        if "termux-x11" not in line:
            continue
        parts = line.split()
        if display in parts:
            return True
        if display == ":0":
            return True
    return False


def _find_termux_x11_pids(display: str) -> list[int]:
    try:
        completed = subprocess.run(
            ["ps", "-ef"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    pids = []
    for line in completed.stdout.splitlines():
        if "termux-x11" not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        if display not in parts and display != ":0":
            continue
        try:
            pids.append(int(parts[1]))
        except (IndexError, ValueError):
            continue
    return pids


def _terminate_pid(pid: int, display: str) -> None:
    if not _pid_is_termux_x11(pid, display):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        return
    for _ in range(50):
        if not _pid_is_termux_x11(pid, display):
            return
        time.sleep(0.1)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return


def _pid_file_path():
    return get_streakium_home() / "termux-x11.pid"


def _read_recorded_server_pid(display: str) -> int | None:
    path = _pid_file_path()
    try:
        raw = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if len(raw) != 2 or raw[0] != display:
        return None
    try:
        pid = int(raw[1])
    except ValueError:
        return None
    if _pid_is_termux_x11(pid, display):
        return pid
    _clear_recorded_server_pid()
    return None


def _write_recorded_server_pid(display: str, pid: int) -> None:
    path = _pid_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{display}\n{pid}\n", encoding="utf-8")
    except OSError:
        return


def _clear_recorded_server_pid() -> None:
    try:
        _pid_file_path().unlink()
    except OSError:
        return


def _pid_is_termux_x11(pid: int, display: str) -> bool:
    try:
        completed = subprocess.run(
            ["ps", "-p", str(pid), "-o", "args="],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    command = completed.stdout.strip()
    return completed.returncode == 0 and "termux-x11" in command and display in command.split()


def _close_termux_x11_app() -> None:
    command = shutil.which("am")
    if command is None:
        return
    try:
        subprocess.run(
            [command, "force-stop", _termux_x11_package_name()],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except Exception:
        return


def _termux_x11_package_name() -> str:
    return os.environ.get("TERMUX_X11_ANDROID_PACKAGE", "").strip() or "com.termux.x11"
