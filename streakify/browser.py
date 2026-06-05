from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from streakify.config import BrowserConfig

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


class BrowserAutomationError(RuntimeError):
    pass


def click_element(element: "WebElement") -> None:
    element.click()


def create_browser_driver(profile_dir: Path, config: BrowserConfig, force_headful: bool = False) -> "WebDriver":
    if config.engine == "undetected":
        return _create_undetected_browser_driver(profile_dir, config, force_headful=force_headful)
    return _create_selenium_browser_driver(profile_dir, config, force_headful=force_headful)


def _create_selenium_browser_driver(profile_dir: Path, config: BrowserConfig, force_headful: bool = False) -> "WebDriver":
    browser_binary = _find_browser_binary(config)
    driver_binary = _find_driver_binary(config)
    headless = config.headless and not force_headful
    if not headless and not os.environ.get("DISPLAY"):
        raise BrowserAutomationError("Headful browser requires DISPLAY. Start Termux:X11 or enable headless mode.")
    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
    except ModuleNotFoundError as exc:
        raise BrowserAutomationError("Selenium is not installed. Run pip install -r requirements.txt.") from exc
    options = Options()
    options.binary_location = browser_binary
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,900")
    options.add_argument(f"--user-data-dir={profile_dir}")
    if config.safe_mode:
        options.add_argument("--disable-background-networking")
    service = Service(executable_path=driver_binary)
    try:
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(max(1, config.timeout_ms // 1000))
        return driver
    except Exception as exc:
        raise BrowserAutomationError(f"Browser failed to start: {exc}") from exc


def _create_undetected_browser_driver(profile_dir: Path, config: BrowserConfig, force_headful: bool = False) -> "WebDriver":
    browser_binary = _find_browser_binary(config)
    driver_binary = _prepare_undetected_driver_binary(config)
    headless = config.headless and not force_headful
    if not headless and not os.environ.get("DISPLAY"):
        raise BrowserAutomationError("Headful browser requires DISPLAY. Start Termux:X11 or enable headless mode.")
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
    options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-notifications")
    if config.safe_mode:
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
        driver.set_page_load_timeout(max(1, config.timeout_ms // 1000))
        return driver
    except Exception as exc:
        raise BrowserAutomationError(f"Undetected browser failed to start: {exc}") from exc


def _find_browser_binary(config: BrowserConfig) -> str:
    candidates = [
        config.binary_path,
        shutil.which("chromium-browser"),
        shutil.which("chromium"),
        "/data/data/com.termux/files/usr/lib/chromium/chrome",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise BrowserAutomationError("Chromium binary was not found. Set browser.binary_path in config.txt.")


def _find_driver_binary(config: BrowserConfig) -> str:
    candidates = [
        config.driver_path,
        shutil.which("chromedriver"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    raise BrowserAutomationError("ChromeDriver binary was not found. Set browser.driver_path in config.txt.")


def _prepare_undetected_driver_binary(config: BrowserConfig) -> str:
    source = Path(_find_driver_binary(config))
    target_dir = Path.home() / ".streakify" / "drivers"
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
