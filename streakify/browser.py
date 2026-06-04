from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from streakify.config import BrowserConfig

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver


class BrowserAutomationError(RuntimeError):
    pass


def create_browser_driver(profile_dir: Path, config: BrowserConfig, force_headful: bool = False) -> "WebDriver":
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
