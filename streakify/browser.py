from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from streakify.config import BrowserConfig
from streakify.runtime_paths import get_driver_cache_dir, get_termux_chromium_binary, get_termux_prefix

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


class BrowserAutomationError(RuntimeError):
    pass


def click_element(element: "WebElement") -> None:
    element.click()


def create_browser_driver(profile_dir: Path, config: BrowserConfig, force_headful: bool = False) -> "WebDriver":
    headless = config.headless and not force_headful
    if not headless and not os.environ.get("DISPLAY"):
        raise BrowserAutomationError(build_x11_diagnostic_message("Headful browser requires DISPLAY."))
    browser_binary = _find_browser_binary()
    driver_binary = _prepare_undetected_driver_binary()
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        import undetected_chromedriver as uc
        import undetected_chromedriver.patcher as patcher
    except ModuleNotFoundError as exc:
        raise BrowserAutomationError("undetected-chromedriver is not installed. Run sh install.sh.") from exc
    patcher.IS_POSIX = True
    patcher.Patcher.platform = "linux"
    uc.IS_POSIX = True
    options = uc.ChromeOptions()
    options.binary_location = browser_binary
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    if headless:
        options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-background-networking")
    try:
        driver = uc.Chrome(
            options=options,
            driver_executable_path=driver_binary,
            browser_executable_path=browser_binary,
            user_data_dir=str(profile_dir),
            use_subprocess=True,
            version_main=_read_chromium_major_version(browser_binary),
            headless=headless,
        )
        if not headless:
            _fit_browser_to_screen(driver)
        driver.set_page_load_timeout(max(1, config.timeout_ms // 1000))
        return driver
    except Exception as exc:
        raise BrowserAutomationError(f"Undetected browser failed to start: {exc}") from exc


def build_x11_diagnostic_message(reason: str) -> str:
    lines = [
        reason,
        "Termux:X11 diagnostics:",
        _read_display_status(),
        _read_termux_x11_status(),
        _read_display_file_status(),
        _read_tx11_service_status(),
        "Fix: start Termux:X11, then rerun Streakify, or set browser.headless=true.",
    ]
    return "\n".join(lines)


def _read_display_status() -> str:
    display = os.environ.get("DISPLAY", "").strip()
    if display:
        return f"- DISPLAY is set to {display}."
    return "- DISPLAY is not set."


def _read_termux_x11_status() -> str:
    termux_x11 = shutil.which("termux-x11")
    if termux_x11:
        return f"- termux-x11 found at {termux_x11}."
    return "- termux-x11 was not found in PATH."


def _read_display_file_status() -> str:
    prefix = get_termux_prefix()
    if prefix is None:
        return "- PREFIX is not set, so tx11 display file cannot be checked."
    display_file = prefix / "var" / "run" / "tx11.display"
    if not display_file.exists():
        return f"- tx11 display file was not found: {display_file}."
    try:
        value = display_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return f"- tx11 display file exists but could not be read: {exc}."
    if value:
        return f"- tx11 display file found: {display_file} with value :{value}."
    return f"- tx11 display file found but empty: {display_file}."


def _read_tx11_service_status() -> str:
    sv = shutil.which("sv")
    if not sv:
        return "- sv was not found, so tx11 service status cannot be checked."
    try:
        completed = subprocess.run(
            [sv, "status", "tx11"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return f"- tx11 service status could not be checked: {exc}."
    output = " ".join(
        value.strip()
        for value in (completed.stdout, completed.stderr)
        if value and value.strip()
    )
    if output:
        return f"- tx11 service status: {output}."
    return f"- tx11 service status command exited with code {completed.returncode}."


def _find_browser_binary() -> str:
    candidates = [
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        get_termux_chromium_binary(),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise BrowserAutomationError("Chromium binary was not found. Install Chromium or make chromium-browser available in PATH.")


def _fit_browser_to_screen(driver: "WebDriver") -> None:
    try:
        width, height = driver.execute_script("return [screen.availWidth || screen.width, screen.availHeight || screen.height]")
        driver.set_window_rect(0, 0, int(width), int(height))
    except Exception:
        try:
            driver.maximize_window()
        except Exception:
            return


def _find_driver_binary() -> str:
    candidates = [
        shutil.which("chromedriver"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise BrowserAutomationError("ChromeDriver binary was not found. Install ChromeDriver or make chromedriver available in PATH.")


def _prepare_undetected_driver_binary() -> str:
    source = Path(_find_driver_binary())
    target_dir = get_driver_cache_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "undetected-chromedriver"
    try:
        if not target.exists() or source.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(source, target)
        target.chmod(0o700)
    except OSError as exc:
        raise BrowserAutomationError(f"ChromeDriver copy failed: {exc}") from exc
    return str(target)


def _read_chromium_major_version(browser_binary: str) -> int | None:
    try:
        import subprocess

        completed = subprocess.run(
            [browser_binary, "--version"],
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    for value in completed.stdout.split():
        if value and value[0].isdigit():
            try:
                return int(value.split(".", 1)[0])
            except ValueError:
                return None
    return None
