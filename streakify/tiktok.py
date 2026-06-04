from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING

from streakify.browser import BrowserAutomationError, create_browser_driver
from streakify.config import AppConfig
from streakify.results import TikTokRunResult

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


CHAT_SELECTORS = (
    '[data-e2e="dm-new-conversation-item"]',
    '[data-e2e="chat-list"] a',
    '[data-e2e="message-list"] a',
    '[data-e2e="chat-item"]',
    'a[href*="/messages"]',
)


class TikTokAutomationError(RuntimeError):
    pass


def _create_tiktok_driver(config: AppConfig, force_headful: bool = False) -> "WebDriver":
    try:
        return create_browser_driver(config.browser.profile_dir, config.browser, force_headful=force_headful)
    except BrowserAutomationError as exc:
        raise TikTokAutomationError(str(exc)) from exc


class TikTokClient:
    def __init__(self, driver: "WebDriver", config: AppConfig, headless: bool):
        self.driver = driver
        self.config = config
        self.headless = headless
        self.timeout_seconds = max(1, config.browser.timeout_ms // 1000)

    def open_messages(self) -> None:
        if self.config.tiktok.messages_url not in self.driver.current_url:
            self.driver.get(self.config.tiktok.messages_url)
        self.wait_for_page()

    def wait_for_page(self) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        WebDriverWait(self.driver, self.timeout_seconds).until(
            lambda driver: driver.find_elements(By.TAG_NAME, "body")
        )

    def has_login_prompt(self) -> bool:
        from selenium.webdriver.common.by import By

        selectors = (
            (By.XPATH, "//button[contains(normalize-space(), 'Log in')]"),
            (By.XPATH, "//*[normalize-space()='Log in']"),
            (By.XPATH, "//*[normalize-space()='Sign up']"),
        )
        for by, value in selectors:
            try:
                elements = self.driver.find_elements(by, value)
                if any(element.is_displayed() for element in elements):
                    return True
            except Exception:
                continue
        return False

    def find_chat_items(self) -> list["WebElement"]:
        from selenium.webdriver.common.by import By

        for selector in CHAT_SELECTORS:
            try:
                items = [
                    item
                    for item in self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if item.is_displayed()
                ]
                if items:
                    return items
            except Exception:
                continue
        return []

    def check_session(self) -> TikTokRunResult:
        self.open_messages()
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            if self.has_login_prompt():
                return self._result("login_required", "TikTok login is required.", 0)
            chats = self.find_chat_items()
            if chats:
                return self._result("ok", "TikTok session is active.", len(chats))
            time.sleep(1)
        if self.has_login_prompt():
            return self._result("login_required", "TikTok login is required.", 0)
        return self._result("no_chats", "No visible TikTok chats were found.", 0)

    def wait_for_manual_login(self) -> TikTokRunResult:
        try:
            self.driver.get(self.config.tiktok.login_url)
            self.wait_for_page()
            print("Log in to TikTok in the browser window.")
            if not sys.stdin.isatty():
                return self.wait_for_login_redirect()
            while True:
                try:
                    input("Press Enter here after login is complete.")
                except EOFError:
                    return self.wait_for_login_redirect()
                result = self.check_session()
                if result.status != "login_required":
                    return result
                print("Login is still not active.")
        except Exception as exc:
            if _is_closed_window_error(exc):
                raise TikTokAutomationError("Browser window was manually closed.") from exc
            raise

    def wait_for_login_redirect(self) -> TikTokRunResult:
        deadline = time.monotonic() + self.config.tiktok.login_wait_seconds
        while time.monotonic() < deadline:
            try:
                result = self.check_session()
                if result.status != "login_required":
                    return result
            except Exception as exc:
                if _is_closed_window_error(exc):
                    raise TikTokAutomationError("Browser window was manually closed.") from exc
                raise
            time.sleep(2)
        raise TikTokAutomationError("Login was not completed before timeout.")

    def _result(self, status: str, message: str, chats_found: int) -> TikTokRunResult:
        return TikTokRunResult(
            status=status,
            message=message,
            chats_found=chats_found,
            headless=self.headless,
        )


def run_tiktok(config: AppConfig) -> TikTokRunResult:
    driver = _create_tiktok_driver(config)
    headless = config.browser.headless
    try:
        client = TikTokClient(driver, config, headless=headless)
        result = client.check_session()
        if result.status != "login_required":
            return result
        if headless:
            if not os.environ.get("DISPLAY"):
                return TikTokRunResult(
                    status="login_required",
                    message="TikTok login is required. Start Termux:X11 for manual login or reuse an existing browser profile.",
                    chats_found=0,
                    headless=True,
                )
            driver.quit()
            driver = _create_tiktok_driver(config, force_headful=True)
            client = TikTokClient(driver, config, headless=False)
        return client.wait_for_manual_login()
    finally:
        driver.quit()


def _is_closed_window_error(error: Exception) -> bool:
    message = str(error).lower()
    return "no such window" in message or "disconnected" in message
