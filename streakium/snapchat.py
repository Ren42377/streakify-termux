from __future__ import annotations

import time
import logging
from typing import TYPE_CHECKING

from streakium.browser import click_element
from streakium.config import AppConfig
from streakium.results import SnapchatRunResult

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


SNAPCHAT_AUTH_STABLE_SECONDS = 15
SNAPCHAT_SEARCHBOX_SECONDS = 60
SNAPCHAT_SEARCH_SECONDS = 15
SNAPCHAT_SEND_WAIT_SECONDS = 8
SNAPCHAT_SEND_ACTION_SECONDS = 5
SNAPCHAT_CAPTURE_ATTEMPTS = 5
SNAPCHAT_SECOND_SEND_TIMEOUT_SECONDS = 3
SNAPCHAT_SEND_POLL_SECONDS = 0.1
SNAPCHAT_POST_SEND_DELAY_SECONDS = 2
LOGGER = logging.getLogger(__name__)


class SnapchatAutomationError(RuntimeError):
    pass


class SnapchatClient:
    def __init__(self, driver: "WebDriver", config: AppConfig):
        self.driver = driver
        self.config = config
        self.timeout_seconds = max(1, config.browser.timeout_ms // 1000)

    def open_web(self) -> None:
        self.driver.get(self.config.snapchat.web_url)

    def ensure_web_open(self) -> None:
        if self.driver.current_url != self.config.snapchat.web_url:
            self.open_web()

    def open_login(self) -> None:
        self.open_web()

    def check_session(self) -> SnapchatRunResult:
        self.open_web()
        deadline = time.monotonic() + self.timeout_seconds
        stable_since = None
        while time.monotonic() < deadline:
            if self.driver.current_url != self.config.snapchat.web_url:
                return self._result("login_required", "Snapchat login is required.")
            if self.has_unsupported_browser_message():
                return self._result("error", "Snapchat reports that this browser mode is not supported.")
            if stable_since is None:
                stable_since = time.monotonic()
            if time.monotonic() - stable_since >= SNAPCHAT_AUTH_STABLE_SECONDS:
                return self._result("ok", "Snapchat session is active.")
            time.sleep(0.25)
        return self._result("error", "Snapchat URL did not stabilize.")

    def has_unsupported_browser_message(self) -> bool:
        try:
            text = self.driver.find_element("tag name", "body").text.casefold()
        except Exception:
            return False
        return "browser not supported" in text or "only supports" in text

    def run_streaks(self, session_result: SnapchatRunResult | None = None) -> SnapchatRunResult:
        result = session_result or self.check_session()
        if result.status != "ok":
            return result
        failed = []
        sent = 0
        for username in self.config.snapchat.usernames:
            try:
                self.send_snap(username)
                sent += 1
            except Exception as exc:
                LOGGER.exception("Snapchat target failed: %s: %s", username, exc)
                failed.append(username)
        target_count = len(self.config.snapchat.usernames)
        if failed:
            status = "partial" if sent else "error"
            message = f"Snapchat sent {sent} of {target_count} Snaps."
        else:
            status = "ok"
            message = f"Snapchat sent {sent} of {target_count} Snaps."
        return SnapchatRunResult(
            status=status,
            message=message,
            target_count=target_count,
            sent_count=sent,
            failed_count=len(failed),
            failed_usernames=tuple(failed),
        )

    def send_snap(self, username: str) -> None:
        self.ensure_web_open()
        search = self.wait_for_search()
        click_element(search)
        search.clear()
        search.send_keys(username)
        target = self.wait_for_exact_search_result(username)
        click_element(target)
        self.open_camera_for_current_target()
        send_action, send_button = self.capture_and_wait_for_send_action()
        if send_action == "send_to":
            click_element(send_button)
            send_button = self.wait_for_text_button("Send")
        self.click_send_confirmation(send_button)
        self.wait_for_send_completion(send_button)
        time.sleep(SNAPCHAT_POST_SEND_DELAY_SECONDS)

    def capture_and_wait_for_send_action(self) -> tuple[str, "WebElement"]:
        last_error = None
        for _ in range(SNAPCHAT_CAPTURE_ATTEMPTS):
            try:
                capture = self.wait_for_capture_button()
            except SnapchatAutomationError as exc:
                last_error = exc
                self.open_camera_for_current_target()
                time.sleep(1)
                continue
            click_element(capture)
            try:
                return self.wait_for_send_action_button(SNAPCHAT_SEND_ACTION_SECONDS)
            except SnapchatAutomationError as exc:
                last_error = exc
            self.dispatch_capture_events(capture)
            try:
                return self.wait_for_send_action_button(SNAPCHAT_SEND_ACTION_SECONDS)
            except SnapchatAutomationError as exc:
                last_error = exc
                time.sleep(1)
        if last_error is not None:
            raise last_error
        raise SnapchatAutomationError("Snapchat send action button was not found.")

    def dispatch_capture_events(self, capture: "WebElement") -> None:
        try:
            self.driver.execute_script(
                """
                const target = arguments[0];
                for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    const event = type.startsWith('pointer')
                        ? new PointerEvent(type, { bubbles: true, cancelable: true, pointerType: 'mouse' })
                        : new MouseEvent(type, { bubbles: true, cancelable: true, view: window });
                    target.dispatchEvent(event);
                }
                """,
                capture,
            )
        except Exception:
            return

    def click_send_confirmation(self, send: "WebElement") -> None:
        from selenium.common.exceptions import StaleElementReferenceException

        click_element(send)
        deadline = time.monotonic() + SNAPCHAT_SECOND_SEND_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            time.sleep(SNAPCHAT_SEND_POLL_SECONDS)
            second_send = None
            try:
                if not send.is_displayed():
                    return
                if send.is_enabled():
                    second_send = send
            except StaleElementReferenceException:
                return
            if second_send is None:
                second_send = self.find_text_button("Send")
            if second_send is None:
                continue
            try:
                if second_send.is_enabled():
                    click_element(second_send)
                    return
            except StaleElementReferenceException:
                continue
        raise SnapchatAutomationError("Snapchat second Send confirmation was not found.")

    def wait_for_search(self) -> "WebElement":
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        def find_search(driver: "WebDriver") -> "WebElement | None":
            return next(
                (
                    element
                    for element in driver.find_elements(
                        By.CSS_SELECTOR,
                        'input[role="searchbox"], input[placeholder*="Search"], [role="searchbox"] input',
                    )
                    if element.is_displayed()
                ),
                None,
            )

        try:
            return WebDriverWait(self.driver, max(self.timeout_seconds, SNAPCHAT_SEARCHBOX_SECONDS)).until(find_search)
        except TimeoutException:
            self.open_web()
        return WebDriverWait(self.driver, max(self.timeout_seconds, SNAPCHAT_SEARCHBOX_SECONDS)).until(
            lambda driver: next(
                (
                    element
                    for element in driver.find_elements(
                        By.CSS_SELECTOR,
                        'input[role="searchbox"], input[placeholder*="Search"], [role="searchbox"] input',
                    )
                    if element.is_displayed()
                ),
                None,
            )
        )

    def wait_for_exact_search_result(self, username: str) -> "WebElement":
        from selenium.common.exceptions import StaleElementReferenceException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait

        expected = normalize_username(username)

        def find_result(driver: "WebDriver") -> "WebElement | None":
            matches = []
            for item in driver.find_elements(By.CSS_SELECTOR, '[role="listitem"]'):
                try:
                    if not item.is_displayed() or not search_result_matches(self.element_text(item), expected):
                        continue
                    interactive = item.find_elements(By.CSS_SELECTOR, '[tabindex="0"]')
                    matches.append(interactive[0] if interactive else item)
                except StaleElementReferenceException:
                    continue
            if len(matches) > 1:
                raise SnapchatAutomationError(f"Multiple Snapchat search results matched {username}.")
            if matches:
                return matches[0]
            return self.find_search_result_by_text(expected)

        try:
            timeout = min(self.timeout_seconds, SNAPCHAT_SEARCH_SECONDS)
            return WebDriverWait(self.driver, timeout, poll_frequency=0.25).until(find_result)
        except SnapchatAutomationError:
            raise
        except Exception as exc:
            raise SnapchatAutomationError(f"Snapchat user was not found: {username}.") from exc

    def find_search_result_by_text(self, expected: str) -> "WebElement | None":
        try:
            return self.driver.execute_script(
                """
                const expected = arguments[0];
                const elements = Array.from(document.querySelectorAll('div, span, a, button, [role="button"]'));
                const matches = [];
                for (const element of elements) {
                    const rect = element.getBoundingClientRect();
                    if (rect.left >= 360 || rect.width <= 0 || rect.height <= 0) continue;
                    if (element.matches('input, textarea') || element.closest('input, textarea')) continue;
                    const text = (element.innerText || element.textContent || '').trim();
                    if (!text) continue;
                    const lines = text.split(/\\n+/).map(value => value.trim().split('·', 1)[0].replace(/^@/, '').toLowerCase());
                    if (!lines.includes(expected)) continue;
                    let clickable = element;
                    for (let i = 0; i < 5 && clickable; i++) {
                        const tag = clickable.tagName.toLowerCase();
                        if (tag === 'a' || tag === 'button' || clickable.getAttribute('role') === 'button' || clickable.getAttribute('tabindex') === '0') break;
                        clickable = clickable.parentElement;
                    }
                    matches.push({ element: clickable || element, score: text.length + rect.top });
                }
                matches.sort((a, b) => a.score - b.score);
                return matches.length ? matches[0].element : null;
                """,
                expected,
            )
        except Exception:
            return None

    def open_camera_for_current_target(self) -> None:
        from selenium.webdriver.support.ui import WebDriverWait

        def open_camera(_: "WebDriver") -> bool:
            button = self.find_chat_camera_button()
            if button is not None:
                click_element(button)
                return True
            return self.find_capture_button() is not None

        try:
            WebDriverWait(self.driver, self.timeout_seconds).until(open_camera)
        except Exception as exc:
            raise SnapchatAutomationError("Snapchat camera entry button was not found.") from exc

    def find_chat_camera_button(self) -> "WebElement | None":
        from selenium.webdriver.common.by import By

        xpath = (
            '//*[@role="textbox" and @contenteditable="true" and @placeholder="Send a chat"]'
            "/ancestor::div[button][1]/button[1]"
        )
        try:
            buttons = self.driver.find_elements(By.XPATH, xpath)
        except Exception:
            return None
        for button in buttons:
            try:
                if button.is_displayed():
                    return button
            except Exception:
                continue
        return None

    def wait_for_capture_button(self) -> "WebElement":
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            return WebDriverWait(self.driver, self.timeout_seconds).until(
                lambda _: self.find_capture_button()
            )
        except Exception as exc:
            raise SnapchatAutomationError("Snapchat capture button was not found.") from exc

    def find_capture_button(self) -> "WebElement | None":
        try:
            return self.driver.execute_script(
                """
                const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                const candidates = [];
                for (const button of buttons) {
                    const rect = button.getBoundingClientRect();
                    const style = getComputedStyle(button);
                    const text = (button.innerText || button.textContent || '').trim();
                    if (style.display === 'none' || style.visibility === 'hidden') continue;
                    if (rect.width <= 0 || rect.height <= 0) continue;
                    if (text) continue;
                    if (button.getAttribute('title')) continue;
                    if (button.querySelector('input')) continue;
                    if (rect.left < 340) continue;
                    if (rect.width < 45 || rect.height < 45 || rect.width > 120 || rect.height > 120) continue;
                    if (Math.abs(rect.width - rect.height) > 20) continue;
                    const centerX = rect.left + rect.width / 2;
                    const centerY = rect.top + rect.height / 2;
                    if (centerY < viewportHeight * 0.45) continue;
                    const topElement = document.elementFromPoint(centerX, centerY);
                    const clickable = topElement ? topElement.closest('button, [role="button"]') : button;
                    const tagBonus = clickable && clickable.tagName !== 'BUTTON' ? 2000 : 0;
                    const sizePenalty = Math.abs(rect.width - 52) * 20 + Math.abs(rect.height - 52) * 20;
                    const score = rect.top + tagBonus - Math.abs(centerX - viewportWidth / 2) * 10 - sizePenalty;
                    candidates.push({ button: clickable || button, score });
                }
                candidates.sort((a, b) => b.score - a.score);
                return candidates.length ? candidates[0].button : null;
                """
            )
        except Exception:
            return None

    def wait_for_text_button(self, text: str, timeout_seconds: int | None = None) -> "WebElement":
        from selenium.webdriver.support.ui import WebDriverWait

        expected = text.casefold()

        def find_button(driver: "WebDriver") -> "WebElement | None":
            return self.find_text_button(expected, driver)

        try:
            timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
            return WebDriverWait(self.driver, timeout).until(find_button)
        except Exception as exc:
            raise SnapchatAutomationError(f"Snapchat {text} button was not found.") from exc

    def wait_for_send_action_button(self, timeout_seconds: int | None = None) -> tuple[str, "WebElement"]:
        from selenium.webdriver.support.ui import WebDriverWait

        def find_button(_: "WebDriver") -> tuple[str, "WebElement"] | None:
            send_to = self.find_text_button("Send To")
            if send_to is not None:
                return "send_to", send_to
            send = self.find_text_button("Send")
            if send is not None:
                return "send", send
            return None

        try:
            timeout = self.timeout_seconds if timeout_seconds is None else timeout_seconds
            return WebDriverWait(self.driver, timeout, poll_frequency=0.25).until(find_button)
        except Exception as exc:
            raise SnapchatAutomationError("Snapchat send action button was not found.") from exc

    def find_text_button(self, text: str, driver: "WebDriver | None" = None) -> "WebElement | None":
        from selenium.webdriver.common.by import By

        expected = text.casefold()
        source = driver or self.driver
        for selector in ("button", '[role="button"]', "a"):
            for element in source.find_elements(By.CSS_SELECTOR, selector):
                try:
                    label = self.element_text(element).strip().casefold()
                    if element.is_displayed() and button_label_matches(label, expected):
                        return element
                except Exception:
                    continue
        return None

    def element_text(self, element: "WebElement") -> str:
        try:
            text = element.text
            if text:
                return text
        except Exception:
            pass
        try:
            return self.driver.execute_script(
                "return (arguments[0].innerText || arguments[0].textContent || arguments[0].value || '');",
                element,
            )
        except Exception:
            return ""

    def wait_for_send_completion(self, send_button: "WebElement") -> None:
        from selenium.common.exceptions import StaleElementReferenceException
        from selenium.webdriver.support.ui import WebDriverWait

        def completed(_: "WebDriver") -> bool:
            try:
                return not send_button.is_displayed()
            except StaleElementReferenceException:
                return True
            except Exception:
                return False

        try:
            WebDriverWait(self.driver, SNAPCHAT_SEND_WAIT_SECONDS).until(completed)
        except Exception as exc:
            raise SnapchatAutomationError("Snapchat did not confirm that the Snap was sent.") from exc

    def _result(self, status: str, message: str) -> SnapchatRunResult:
        return SnapchatRunResult(status=status, message=message)


def normalize_username(value: str) -> str:
    return value.strip().removeprefix("@").casefold()


def search_result_matches(text: str, expected: str) -> bool:
    for line in text.splitlines():
        value = line.strip().split("·", 1)[0]
        if normalize_username(value) == expected:
            return True
    return False


def button_label_matches(label: str, expected: str) -> bool:
    if label == expected:
        return True
    return expected == "send" and label.startswith("send ") and not label.startswith("send to")


def run_snapchat_with_driver(
    driver: "WebDriver",
    config: AppConfig,
    session_result: SnapchatRunResult | None = None,
) -> SnapchatRunResult:
    if not config.snapchat_enabled:
        return SnapchatRunResult(
            status="skipped",
            message="Snapchat is disabled in config.",
        )
    client = SnapchatClient(driver, config)
    return client.run_streaks(session_result)
