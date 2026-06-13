from __future__ import annotations

import logging
import argparse
from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Callable

from streakium.browser import BrowserAutomationError, create_browser_driver
from streakium.chess import ChessAutomationError, ChessClient, run_chess_with_driver
from streakium.config import AppConfig, StreakiumConfigError, load_config
from streakium.duolingo import DuolingoAutomationError, DuolingoClient, run_duolingo_with_driver
from streakium.notifications import notify
from streakium.snapchat import SnapchatAutomationError, SnapchatClient, run_snapchat_with_driver
from streakium.snapchat_camera import (
    SnapchatCameraError,
    is_ffmpeg_available,
    prepare_snapchat_camera,
)
from streakium.stockfish import is_stockfish_available
from streakium.termux_x11 import TermuxX11Error, TermuxX11Session, stop_termux_x11_server
from streakium.tiktok import TikTokAutomationError, TikTokClient, run_tiktok_with_driver

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver


@dataclass(frozen=True)
class PlatformAdapter:
    key: str
    name: str
    enabled: Callable[[AppConfig], bool]
    create_client: Callable[["WebDriver", AppConfig], Any]
    check_login: Callable[[Any], Any]
    open_login: Callable[[Any], None]
    run: Callable[["WebDriver", AppConfig, Any | None], Any]
    dependency_available: Callable[[], bool] | None = None
    dependency_error: str = ""


PLATFORMS = (
    PlatformAdapter(
        key="tiktok",
        name="TikTok",
        enabled=lambda config: config.tiktok_enabled,
        create_client=TikTokClient,
        check_login=lambda client: client.check_session(),
        open_login=lambda client: client.open_login(),
        run=run_tiktok_with_driver,
    ),
    PlatformAdapter(
        key="chess",
        name="Chess.com",
        enabled=lambda config: config.chess_enabled,
        create_client=ChessClient,
        check_login=lambda client: client.check_auth_session(),
        open_login=lambda client: client.open_login(),
        run=run_chess_with_driver,
        dependency_available=is_stockfish_available,
        dependency_error="Stockfish was not found in PATH. Install stockfish in Termux and make sure the stockfish command works.",
    ),
    PlatformAdapter(
        key="duolingo",
        name="Duolingo",
        enabled=lambda config: config.duolingo_enabled,
        create_client=DuolingoClient,
        check_login=lambda client: client.check_auth_session(),
        open_login=lambda client: client.open_login(),
        run=run_duolingo_with_driver,
        dependency_available=is_stockfish_available,
        dependency_error="Stockfish was not found in PATH. Install stockfish in Termux and make sure the stockfish command works.",
    ),
    PlatformAdapter(
        key="snapchat",
        name="Snapchat",
        enabled=lambda config: config.snapchat_enabled,
        create_client=SnapchatClient,
        check_login=lambda client: client.check_session(),
        open_login=lambda client: client.open_login(),
        run=run_snapchat_with_driver,
        dependency_available=is_ffmpeg_available,
        dependency_error="FFmpeg was not found in PATH. Install ffmpeg in Termux.",
    ),
)

_TERMUX_X11_USED = False


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    args = _parse_args(argv)
    return _run_configured_platforms(args.platforms)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="streakium")
    parser.add_argument(
        "--platform",
        action="append",
        choices=tuple(platform.key for platform in PLATFORMS),
        dest="platforms",
    )
    return parser.parse_args(argv)


def _run_configured_platforms(platform_keys: Sequence[str] | None = None) -> int:
    notify("Streakium", "Run started.")
    try:
        config = load_config()
    except StreakiumConfigError as exc:
        print(f"Config error: {exc}")
        return _finish(1, "Config error.")
    platforms = _enabled_platforms(config)
    if platform_keys:
        platforms = _filter_platforms(platforms, platform_keys)
    if not platforms:
        print("Status: skipped")
        print("Message: All platforms are disabled in config.")
        return _finish(0, "All platforms are disabled.")
    for platform in platforms:
        if platform.dependency_available is not None and not platform.dependency_available():
            print(f"Automation error: {platform.dependency_error}")
            return _finish(1, platform.dependency_error)
    if config.snapchat_enabled:
        try:
            fake_video_path = prepare_snapchat_camera(
                config.snapchat.camera_folder,
                config.snapchat.camera_mode,
            )
        except SnapchatCameraError as exc:
            print(f"Automation error: {exc}")
            return _finish(1, str(exc))
        config = replace(
            config,
            browser=replace(config.browser, fake_video_path=fake_video_path),
        )
    try:
        results, exit_code = _run_platforms_with_login(config, platforms)
        if exit_code is not None:
            return _finish(exit_code, "Login is required.")
    except (
        BrowserAutomationError,
        TermuxX11Error,
        TikTokAutomationError,
        ChessAutomationError,
        DuolingoAutomationError,
        SnapchatAutomationError,
    ) as exc:
        print(f"Automation error: {exc}")
        return _finish(1, str(exc))
    return _finish(_print_all_results(results), _summarize_results(results))


def _finish(exit_code: int, message: str) -> int:
    status = "finished" if exit_code == 0 else "failed"
    if exit_code != 0 and _TERMUX_X11_USED:
        stop_termux_x11_server()
    notify("Streakium", f"Run {status}: {message}")
    return exit_code


def _summarize_results(results) -> str:
    parts = []
    for name, result in results:
        parts.append(f"{name} {result.status}")
    return ", ".join(parts) if parts else "No result."


def _enabled_platforms(config: AppConfig) -> list[PlatformAdapter]:
    return [platform for platform in PLATFORMS if platform.enabled(config)]


def _filter_platforms(platforms: Sequence[PlatformAdapter], platform_keys: Sequence[str]) -> list[PlatformAdapter]:
    requested = set(platform_keys)
    return [platform for platform in platforms if platform.key in requested]


def _run_platforms_with_login(
    config: AppConfig,
    platforms: Sequence[PlatformAdapter],
) -> tuple[list[tuple[str, Any]], int | None]:
    driver = None
    handles: dict[str, str] = {}
    session = nullcontext() if config.browser.headless else _termux_x11_session()
    with session:
        try:
            driver = create_browser_driver(config.browser.profile_dir, config.browser)
            login_required, session_results = _check_login_requirements(driver, config, handles, platforms)
            if login_required:
                if config.browser.headless:
                    _quit_driver_safely(driver)
                    driver = None
                    remaining = _run_interactive_login(config, login_required)
                    if remaining:
                        _print_login_required(remaining, still_required=True)
                        return [], 2
                    driver = create_browser_driver(config.browser.profile_dir, config.browser)
                    handles = {}
                    login_required, session_results = _check_login_requirements(driver, config, handles, platforms)
                    if login_required:
                        _print_login_required(login_required, still_required=True)
                        return [], 2
                else:
                    _open_login_tabs(driver, config, handles, login_required)
                    _prompt_for_login(login_required)
                    remaining, checked_results = _check_login_requirements(driver, config, handles, login_required)
                    session_results.update(checked_results)
                    if remaining:
                        _print_login_required(remaining, still_required=True)
                        return [], 2
            results = _run_enabled_platforms(driver, config, handles, platforms, session_results)
            return results, None
        finally:
            _quit_driver_safely(driver)


def _run_interactive_login(config: AppConfig, platforms: Sequence[PlatformAdapter]) -> list[PlatformAdapter]:
    driver = None
    visible_browser = replace(config.browser, headless=False)
    handles: dict[str, str] = {}
    with _termux_x11_session():
        try:
            driver = create_browser_driver(config.browser.profile_dir, visible_browser)
            _open_login_tabs(driver, config, handles, platforms)
            _prompt_for_login(platforms)
            remaining, _ = _check_login_requirements(driver, config, handles, platforms)
            return remaining
        finally:
            _quit_driver_safely(driver)


def _termux_x11_session() -> TermuxX11Session:
    global _TERMUX_X11_USED
    _TERMUX_X11_USED = True
    return TermuxX11Session()


def _quit_driver_safely(driver: "WebDriver | None") -> None:
    if driver is None:
        return
    try:
        for handle in list(driver.window_handles):
            try:
                driver.switch_to.window(handle)
                driver.close()
            except Exception:
                continue
    except Exception:
        pass
    try:
        driver.quit()
    except Exception:
        pass


def _check_login_requirements(
    driver: "WebDriver",
    config: AppConfig,
    handles: dict[str, str],
    platforms: Sequence[PlatformAdapter],
) -> tuple[list[PlatformAdapter], dict[str, Any]]:
    required = []
    results = {}
    for platform in platforms:
        _switch_platform_tab(driver, handles, platform.key)
        client = platform.create_client(driver, config)
        result = platform.check_login(client)
        results[platform.key] = result
        if result.status == "login_required":
            required.append(platform)
    return required, results


def _open_login_tabs(
    driver: "WebDriver",
    config: AppConfig,
    handles: dict[str, str],
    platforms: Sequence[PlatformAdapter],
) -> None:
    for platform in platforms:
        _switch_platform_tab(driver, handles, platform.key)
        client = platform.create_client(driver, config)
        platform.open_login(client)


def _prompt_for_login(platforms: Sequence[PlatformAdapter]) -> None:
    names = _format_platform_names(platforms)
    print("Status: login_required")
    print(f"Message: Login is required for: {names}.")
    print("A visible browser tab has been opened for each platform that needs login.")
    try:
        input("Complete the login in the browser, then press Enter here to continue.")
    except EOFError as exc:
        raise BrowserAutomationError("The login prompt could not read input. Run Streakium from an interactive Termux shell.") from exc


def _print_login_required(platforms: Sequence[PlatformAdapter], still_required: bool = False) -> None:
    names = _format_platform_names(platforms)
    print("Status: login_required")
    if still_required:
        print(f"Message: Login is still required for: {names}.")
        return
    print(f"Message: Login is required for: {names}.")


def _format_platform_names(platforms: Sequence[PlatformAdapter]) -> str:
    return ", ".join(platform.name for platform in platforms)


def _switch_platform_tab(driver: "WebDriver", handles: dict[str, str], platform: str) -> None:
    available_handles = set(driver.window_handles)
    handle = handles.get(platform)
    if handle in available_handles:
        driver.switch_to.window(handle)
        return
    if not handles:
        handles[platform] = driver.current_window_handle
        return
    driver.switch_to.new_window("tab")
    handles[platform] = driver.current_window_handle


def _run_enabled_platforms(
    driver: "WebDriver",
    config: AppConfig,
    handles: dict[str, str],
    platforms: Sequence[PlatformAdapter],
    session_results: dict[str, Any],
):
    results = []
    for platform in platforms:
        _switch_platform_tab(driver, handles, platform.key)
        results.append((platform.name, platform.run(driver, config, session_results.get(platform.key))))
    return results


def _print_all_results(results) -> int:
    exit_code = 0
    for name, result in results:
        print(f"{name} status: {result.status}")
        print(f"{name} message: {result.message}")
        if hasattr(result, "selected_chats"):
            print(f"{name} selected chats: {result.selected_chats}")
            print(f"{name} sent chats: {result.sent_chats}")
        if hasattr(result, "moves_played"):
            print(f"{name} moves played: {result.moves_played}")
        if hasattr(result, "page_opened"):
            print(f"{name} page opened: {result.page_opened}")
        if hasattr(result, "completed"):
            print(f"{name} completed: {result.completed}")
        if hasattr(result, "target_count"):
            print(f"{name} targets: {result.target_count}")
            print(f"{name} sent: {result.sent_count}")
            print(f"{name} failed: {result.failed_count}")
            if result.failed_usernames:
                print(f"{name} failed usernames: {', '.join(result.failed_usernames)}")
        if result.status not in {"ok", "skipped"}:
            exit_code = 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
