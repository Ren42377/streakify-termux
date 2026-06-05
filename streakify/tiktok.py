from __future__ import annotations

import os
import sys
import time
from typing import TYPE_CHECKING

from streakify.browser import BrowserAutomationError, click_element, create_browser_driver
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

COMPOSER_SELECTORS = (
    '[contenteditable="true"]',
    'div[role="textbox"]',
    'textarea',
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

    def find_composer(self) -> "WebElement":
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        for selector in COMPOSER_SELECTORS:
            try:
                element = WebDriverWait(self.driver, self.timeout_seconds).until(
                    lambda driver: next(
                        (
                            item
                            for item in driver.find_elements(By.CSS_SELECTOR, selector)
                            if item.is_displayed()
                        ),
                        None,
                    )
                )
                if element:
                    return element
            except Exception:
                continue
        raise TikTokAutomationError("Message input was not found.")

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

    def send_message_to_chat(self, chat: "WebElement") -> bool:
        from selenium.webdriver.common.keys import Keys

        click_element(chat)
        time.sleep(self.config.tiktok.chat_open_delay_ms / 1000)
        composer = self.find_composer()
        click_element(composer)
        composer.send_keys(Keys.CONTROL, "a")
        composer.send_keys(Keys.BACKSPACE)
        composer.send_keys(self.config.tiktok.message_template)
        if self.config.tiktok.dry_run:
            return False
        composer.send_keys(Keys.ENTER)
        time.sleep(self.config.tiktok.send_delay_ms / 1000)
        return True

    def run_messages(self, session_result: TikTokRunResult | None = None) -> TikTokRunResult:
        if session_result is None:
            session_result = self.check_session()
        if session_result.status != "ok":
            return session_result
        selected = 0
        sent = 0
        seen_chat_ids: set[str] = set()
        for _ in range(self.config.tiktok.max_chats):
            chats = self.find_chat_items()
            if not chats:
                break
            target_chat = self._select_chat(chats, seen_chat_ids)
            if target_chat is None:
                break
            selected += 1
            try:
                if self.send_message_to_chat(target_chat):
                    sent += 1
            except Exception as exc:
                raise TikTokAutomationError(f"Message action failed: {exc}") from exc
        if selected == 0:
            raise TikTokAutomationError("No visible TikTok chats were available for messaging.")
        return TikTokRunResult(
            status="ok",
            message="TikTok message flow completed.",
            chats_found=session_result.chats_found,
            selected_chats=selected,
            sent_chats=sent,
            dry_run=self.config.tiktok.dry_run,
            headless=self.headless,
        )

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
            dry_run=self.config.tiktok.dry_run,
            headless=self.headless,
        )

    def _select_chat(self, chats: list["WebElement"], seen_chat_ids: set[str]) -> "WebElement | None":
        for chat in chats:
            chat_id = self._read_chat_id(chat)
            if chat_id and chat_id not in seen_chat_ids:
                seen_chat_ids.add(chat_id)
                return chat
        return None

    def _read_chat_id(self, chat: "WebElement") -> str:
        try:
            chat_id = chat.get_attribute("href")
            if chat_id:
                return chat_id
            text = chat.text.strip()
            if text:
                return text.split("\n", 1)[0]
        except Exception:
            return ""
        return ""


def run_tiktok(config: AppConfig) -> TikTokRunResult:
    driver = _create_tiktok_driver(config)
    headless = config.browser.headless
    try:
        client = TikTokClient(driver, config, headless=headless)
        result = client.check_session()
        if result.status != "login_required":
            if result.status != "ok":
                return result
            return client.run_messages(result)
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
        login_result = client.wait_for_manual_login()
        if login_result.status != "ok":
            return login_result
        return client.run_messages(login_result)
    finally:
        driver.quit()


def _is_closed_window_error(error: Exception) -> bool:
    message = str(error).lower()
    return "no such window" in message or "disconnected" in message
