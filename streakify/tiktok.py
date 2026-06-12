from __future__ import annotations

import time
from typing import TYPE_CHECKING

from streakify.browser import click_element
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


class TikTokClient:
    def __init__(self, driver: "WebDriver", config: AppConfig):
        self.driver = driver
        self.config = config
        self.timeout_seconds = max(1, config.browser.timeout_ms // 1000)

    def open_messages(self) -> None:
        if self.config.tiktok.messages_url not in self.driver.current_url:
            self.driver.get(self.config.tiktok.messages_url)
        self.wait_for_page()

    def open_login(self) -> None:
        self.driver.get(self.config.tiktok.login_url)
        self.wait_for_page()

    def wait_for_page(self) -> None:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        WebDriverWait(self.driver, self.timeout_seconds).until(
            lambda driver: driver.find_elements(By.TAG_NAME, "body")
        )

    def is_logged_in(self) -> bool:
        return self.config.tiktok.messages_url in self.driver.current_url

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
        self.driver.get(self.config.tiktok.messages_url)
        self.wait_for_page()
        deadline = time.monotonic() + self.timeout_seconds
        login_prompt_deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if not self.is_logged_in():
                if time.monotonic() >= login_prompt_deadline:
                    return self._result("login_required", "TikTok login is required.")
                time.sleep(0.5)
                continue
            chats = self.find_chat_items()
            if chats:
                return self._result("ok", "TikTok session is active.")
            time.sleep(1)
        if not self.is_logged_in():
            return self._result("login_required", "TikTok login is required.")
        return self._result("no_chats", "No visible TikTok chats were found.")

    def send_message_to_chat(self, chat: "WebElement") -> None:
        from selenium.webdriver.common.keys import Keys

        click_element(chat)
        time.sleep(self.config.tiktok.chat_open_delay_ms / 1000)
        composer = self.find_composer()
        click_element(composer)
        composer.send_keys(Keys.CONTROL, "a")
        composer.send_keys(Keys.BACKSPACE)
        self.driver.execute_cdp_cmd("Input.insertText", {"text": self.config.tiktok.message})
        composer.send_keys(Keys.ENTER)
        time.sleep(self.config.tiktok.send_delay_ms / 1000)

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
                self.send_message_to_chat(target_chat)
                sent += 1
            except Exception as exc:
                raise TikTokAutomationError(f"Message action failed: {exc}") from exc
        if selected == 0:
            raise TikTokAutomationError("No visible TikTok chats were available for messaging.")
        return TikTokRunResult(
            status="ok",
            message="TikTok message flow completed.",
            selected_chats=selected,
            sent_chats=sent,
        )

    def _result(self, status: str, message: str) -> TikTokRunResult:
        return TikTokRunResult(
            status=status,
            message=message,
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


def run_tiktok_with_driver(
    driver: "WebDriver",
    config: AppConfig,
    session_result: TikTokRunResult | None = None,
) -> TikTokRunResult:
    if not config.tiktok_enabled:
        return TikTokRunResult(
            status="skipped",
            message="TikTok is disabled in config.",
        )
    client = TikTokClient(driver, config)
    result = session_result or client.check_session()
    if result.status != "ok":
        return result
    return client.run_messages(result)
