from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from streakify.config import BrowserConfig
from streakify.runtime_paths import get_driver_cache_dir, get_termux_chromium_binary

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


class BrowserAutomationError(RuntimeError):
    pass


def click_element(element: "WebElement") -> None:
    element.click()


def create_browser_driver(profile_dir: Path, config: BrowserConfig) -> "WebDriver":
    headless = config.headless
    browser_binary = _find_browser_binary()
    driver_binary = _prepare_undetected_driver_binary()
    profile_dir.mkdir(parents=True, exist_ok=True)
    _clear_stale_profile_locks(profile_dir)
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
    options.page_load_strategy = "eager"
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    if headless:
        options.add_argument("--window-size=1280,900")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-background-networking")
    driver = None
    try:
        driver = uc.Chrome(
            options=options,
            driver_executable_path=driver_binary,
            browser_executable_path=browser_binary,
            user_data_dir=str(profile_dir),
            use_subprocess=True,
            version_main=_read_chromium_major_version(browser_binary),
        )
        if not headless:
            _fit_browser_to_screen(driver)
        driver.set_page_load_timeout(max(1, config.timeout_ms // 1000))
        return driver
    except Exception as exc:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        raise BrowserAutomationError(f"Undetected browser failed to start: {exc}") from exc


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


def _clear_stale_profile_locks(profile_dir: Path) -> None:
    if _profile_has_running_chromium(profile_dir):
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
        path = profile_dir / name
        try:
            if path.exists() or path.is_symlink():
                path.unlink()
        except OSError:
            continue


def _profile_has_running_chromium(profile_dir: Path) -> bool:
    try:
        completed = subprocess.run(
            ["ps", "-ef"],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except Exception:
        return True
    profile = str(profile_dir)
    for line in completed.stdout.splitlines():
        lowered = line.lower()
        if profile in line and ("chromium" in lowered or "chrome" in lowered):
            return True
    return False


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
