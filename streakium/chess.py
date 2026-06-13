from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from streakium.browser import click_element
from streakium.config import AppConfig
from streakium.results import ChessRunResult
from streakium.stockfish import StockfishEngine, StockfishError, is_stockfish_available

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver
    from selenium.webdriver.remote.webelement import WebElement


PIECE_TO_FEN = {
    "wp": "P",
    "wn": "N",
    "wb": "B",
    "wr": "R",
    "wq": "Q",
    "wk": "K",
    "bp": "p",
    "bn": "n",
    "bb": "b",
    "br": "r",
    "bq": "q",
    "bk": "k",
}

MODAL_SELECTOR = ", ".join(
    (
        "dialog[open].cc-modal-component-v2",
        ".cc-modal-component-v2[open]",
        "dialog[open]",
        '[data-cy="first-time-modal"]',
        ".modal-first-time-modal",
    )
)
class ChessAutomationError(RuntimeError):
    pass


class ChessClient:
    def __init__(self, driver: "WebDriver", config: AppConfig):
        self.driver = driver
        self.config = config
        self.timeout_seconds = max(1, config.browser.timeout_ms // 1000)

    def open_puzzles(self) -> None:
        self.driver.get(self.config.chess.puzzles_url)

    def open_login(self) -> None:
        self.driver.get(self.config.chess.login_url)

    def has_board(self) -> bool:
        from selenium.webdriver.common.by import By

        try:
            boards = self.driver.find_elements(By.CSS_SELECTOR, "#board-primary")
            return any(board.is_displayed() for board in boards)
        except Exception:
            return False

    def check_session(self) -> ChessRunResult:
        auth_result = self.check_auth_session()
        if auth_result.status != "ok":
            return auth_result
        return self.check_puzzle_session()

    def check_auth_session(self) -> ChessRunResult:
        self.open_login()
        deadline = time.monotonic() + self.timeout_seconds
        login_prompt_deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            current_url = self.driver.current_url.lower()
            login_page = self.is_login_url(current_url)
            if "chess.com/home" in current_url or ("chess.com" in current_url and not login_page):
                return self._result("ok", "Chess.com session is active.")
            if login_page and time.monotonic() >= login_prompt_deadline:
                return self._result("login_required", "Chess.com login is required.")
            time.sleep(0.5)
        return self._result("login_required", "Chess.com login is required.")

    def is_login_url(self, current_url: str) -> bool:
        current_url = current_url.lower()
        return "chess.com" in current_url and any(value in current_url for value in ("/login", "/register", "/signup"))

    def check_puzzle_session(self) -> ChessRunResult:
        self.open_puzzles()
        return self.check_puzzle_ready()

    def check_puzzle_ready(self) -> ChessRunResult:
        deadline = time.monotonic() + self.timeout_seconds
        while time.monotonic() < deadline:
            current_url = self.driver.current_url
            if self.is_login_url(current_url):
                return self._result("login_required", "Chess.com login is required.")
            path = chesscom_path(current_url)
            if path == "/puzzles":
                return self._result("no_board", "Chess.com daily puzzle limit was reached.")
            if path != "/puzzles/rated":
                time.sleep(0.25)
                continue
            if self.dismiss_optional_popups():
                time.sleep(0.2)
                continue
            if self.has_board():
                return self._result("ok", "Chess.com session is active.")
            time.sleep(0.25)
        current_url = self.driver.current_url
        path = chesscom_path(current_url)
        if path == "/puzzles":
            return self._result("no_board", "Chess.com daily puzzle limit was reached.")
        if path == "/puzzles/rated" and self.has_board():
            return self._result("ok", "Chess.com session is active.")
        if self.is_login_url(current_url):
            return self._result("login_required", "Chess.com login is required.")
        return self._result("no_board", "Chess.com puzzle board was not found.")

    def dismiss_optional_popups(self) -> bool:
        from selenium.webdriver.common.by import By

        try:
            modals = [modal for modal in self.driver.find_elements(By.CSS_SELECTOR, MODAL_SELECTOR) if modal.is_displayed()]
        except Exception:
            return False
        for modal in modals:
            button = self.find_popup_button(modal)
            if button is None:
                continue
            try:
                click_element(button)
                return True
            except Exception:
                continue
        return False

    def find_popup_button(self, modal: "WebElement") -> "WebElement | None":
        from selenium.webdriver.common.by import By

        try:
            monetization = modal.find_elements(By.CSS_SELECTOR, ".cc-button-monetization, a[href*='/membership']")
            if any(element.is_displayed() for element in monetization):
                return None
        except Exception:
            pass
        priority_selectors = (
            '[data-cy="modal-first-time-button"]',
            '[data-cy*="first-time"][data-cy*="button"]',
            '[data-cy*="confirm"]',
            '[data-cy*="continue"]',
            ".cc-button-primary",
            ".cc-modal-close-component",
            '[data-cy="modal-close"]',
        )
        for selector in priority_selectors:
            try:
                for button in modal.find_elements(By.CSS_SELECTOR, selector):
                    if button.is_displayed():
                        return button
            except Exception:
                continue
        try:
            buttons = [button for button in modal.find_elements(By.CSS_SELECTOR, "button, [role='button'], a") if button.is_displayed()]
        except Exception:
            return None
        primary_buttons = []
        for button in buttons:
            classes = (button.get_attribute("class") or "").lower()
            data_cy = (button.get_attribute("data-cy") or "").lower()
            if "primary" in classes or "primary" in data_cy or "first-time" in data_cy:
                primary_buttons.append(button)
        if primary_buttons:
            return primary_buttons[0]
        if len(buttons) == 1:
            return buttons[0]
        return None

    def run_puzzle(self, session_result: ChessRunResult | None = None) -> ChessRunResult:
        if session_result is None:
            session_result = self.check_session()
        if session_result.status != "ok":
            return session_result
        if not is_stockfish_available():
            raise ChessAutomationError("Stockfish was not found in PATH. Install stockfish in Termux and make sure the stockfish command works.")
        return self.play_intentional_wrong_move()

    def play_intentional_wrong_move(self) -> ChessRunResult:
        try:
            engine = StockfishEngine()
        except StockfishError as exc:
            raise ChessAutomationError(str(exc)) from exc
        try:
            self.dismiss_optional_popups()
            if self.is_puzzle_complete():
                return ChessRunResult(
                    status="stopped",
                    message="Chess.com puzzle was already complete before a wrong move could be played.",
                    moves_played=0,
                )
            state = self.wait_for_stable_position()
            if not state:
                return ChessRunResult(
                    status="stopped",
                    message="No stable Chess.com position was found.",
                    moves_played=0,
                )
            fen = state["fen"]
            try:
                best_move = engine.best_move(fen, self.config.chess.engine_time)
                legal_moves = engine.legal_moves(fen)
            except StockfishError as exc:
                raise ChessAutomationError(str(exc)) from exc
            if not best_move or best_move == "(none)":
                raise ChessAutomationError("Stockfish did not return a playable best move.")
            move = select_non_best_legal_move(best_move, legal_moves)
            self.play_move(move, state)
            result = self.wait_for_wrong_move_result()
            if result == "wrong":
                return ChessRunResult(
                    status="ok",
                    message=f"Chess.com intentional wrong move {move} was played.",
                    moves_played=1,
                )
            return ChessRunResult(
                status="stopped",
                message=f"Chess.com did not finish after move {move} within {self.config.chess.opponent_wait_seconds} seconds.",
                moves_played=1,
            )
        finally:
            engine.close()

    def wait_for_stable_position(self, timeout: int = 15) -> dict[str, Any] | None:
        last_fen = None
        stable_count = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.read_board_state()
            if state and state.get("fen"):
                fen = state["fen"]
                if fen == last_fen:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_fen = fen
                if stable_count >= 2:
                    return state
            time.sleep(0.4)
        return self.read_board_state()

    def wait_for_wrong_move_result(self) -> str:
        deadline = time.monotonic() + self.config.chess.opponent_wait_seconds
        while time.monotonic() < deadline:
            if self.is_puzzle_complete():
                return "wrong"
            time.sleep(0.2)
        return "timeout"

    def read_board_state(self) -> dict[str, Any] | None:
        try:
            raw = self.driver.execute_script(
                """
                const board = document.querySelector('#board-primary');
                if (!board) return null;
                const boardRect = board.getBoundingClientRect();
                const pieces = [...board.querySelectorAll('.piece')].map((el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        cls: String(el.className),
                        rect: {
                            left: rect.left,
                            top: rect.top,
                            width: rect.width,
                            height: rect.height
                        }
                    };
                });
                return {
                    url: location.href,
                    boardRect: {
                        left: boardRect.left,
                        top: boardRect.top,
                        width: boardRect.width,
                        height: boardRect.height
                    },
                    pieces
                };
                """
            )
        except Exception as exc:
            raise ChessAutomationError(f"Chess.com board state could not be read: {exc}") from exc
        return parse_board_state(raw)

    def play_move(self, move: str, state: dict[str, Any]) -> None:
        source = move[:2]
        target = move[2:4]
        promotion = move[4:5] if len(move) > 4 else ""
        source_element = self.find_piece_element(source)
        if source_element is None:
            raise ChessAutomationError(f"Source piece was not found for move {move}.")
        self.click_board_element(source_element, f"source square {source}")
        time.sleep(0.15)
        target_element = self.wait_for_square_click_element(target, state, timeout=1.5)
        if target_element is None:
            raise ChessAutomationError(f"Target square element was not found for move {move}.")
        self.click_board_element(target_element, f"target square {target}")
        if promotion and not self.click_promotion(promotion):
            raise ChessAutomationError(f"Promotion piece {promotion} could not be selected.")
        if not self.wait_for_move_applied(state):
            raise ChessAutomationError(f"Chess.com did not apply move {move}.")

    def wait_for_move_applied(self, previous_state: dict[str, Any], timeout: float = 3.0) -> bool:
        previous_board = previous_state.get("board")
        if not previous_board:
            return False
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current_state = self.read_board_state()
            if current_state and current_state.get("board") != previous_board:
                return True
            time.sleep(0.1)
        return False

    def click_board_element(self, element: "WebElement", description: str) -> None:
        try:
            click_element(element)
            return
        except Exception as exc:
            if not self.is_click_intercepted(exc):
                raise ChessAutomationError(f"Chess.com click failed for {description}: {exc}") from exc
        if self.dismiss_optional_popups():
            time.sleep(0.2)
            try:
                click_element(element)
                return
            except Exception as exc:
                if not self.is_click_intercepted(exc):
                    raise ChessAutomationError(f"Chess.com click failed for {description}: {exc}") from exc
        if self.disable_board_coordinate_overlay():
            time.sleep(0.05)
            try:
                click_element(element)
                return
            except Exception as exc:
                if not self.is_click_intercepted(exc):
                    raise ChessAutomationError(f"Chess.com click failed for {description}: {exc}") from exc
        if self.enable_element_pointer_events(element):
            time.sleep(0.05)
            try:
                click_element(element)
                return
            except Exception as exc:
                raise ChessAutomationError(f"Chess.com click failed for {description}: {exc}") from exc
        raise ChessAutomationError(f"Chess.com click failed for {description}: element remained intercepted.")

    def is_click_intercepted(self, error: Exception) -> bool:
        message = str(error).lower()
        return "click intercepted" in message or "other element would receive the click" in message

    def enable_element_pointer_events(self, element: "WebElement") -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const element = arguments[0];
                    if (!element || !element.isConnected) return false;
                    element.style.pointerEvents = 'auto';
                    return getComputedStyle(element).pointerEvents !== 'none';
                    """,
                    element,
                )
            )
        except Exception:
            return False

    def disable_board_coordinate_overlay(self) -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const board = document.querySelector('#board-primary');
                    if (!board) return false;
                    const overlays = board.querySelectorAll('.coordinates, .coordinates *');
                    for (const overlay of overlays) {
                        overlay.style.pointerEvents = 'none';
                    }
                    return overlays.length > 0;
                    """
                )
            )
        except Exception:
            return False

    def find_piece_element(self, square: str) -> "WebElement | None":
        from selenium.webdriver.common.by import By

        square_class = square_to_chesscom_class(square)
        selectors = (
            f"#board-primary .piece.{square_class}",
            f"#board-primary [class*='piece'][class*='{square_class}']",
        )
        for selector in selectors:
            try:
                for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed():
                        return element
            except Exception:
                continue
        return None

    def wait_for_square_click_element(self, square: str, state: dict[str, Any], timeout: float) -> "WebElement | None":
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            element = self.find_square_click_element(square, state)
            if element is not None:
                return element
            time.sleep(0.1)
        return None

    def find_square_click_element(self, square: str, state: dict[str, Any]) -> "WebElement | None":
        from selenium.webdriver.common.by import By

        square_class = square_to_chesscom_class(square)
        selectors = [f"#board-primary .piece.{square_class}"]
        if square not in state.get("board", {}):
            selectors.extend(
                [
                    f"#board-primary .hint.{square_class}",
                    f"#board-primary .move-hint.{square_class}",
                    f"#board-primary .capture-hint.{square_class}",
                    f"#board-primary [class*='hint'][class*='{square_class}']",
                    f"#board-primary [class*='legal'][class*='{square_class}']",
                    f"#board-primary [data-square='{square}']",
                    f"#board-primary [aria-label*='{square}']",
                ]
            )
        for selector in selectors:
            try:
                for element in self.driver.find_elements(By.CSS_SELECTOR, selector):
                    if element.is_displayed():
                        return element
            except Exception:
                continue
        return None

    def click_promotion(self, promotion: str) -> bool:
        from selenium.webdriver.common.by import By

        piece_name = {
            "q": "queen",
            "r": "rook",
            "b": "bishop",
            "n": "knight",
        }.get(promotion.lower())
        if piece_name is None:
            return False
        try:
            elements = self.driver.find_elements(By.CSS_SELECTOR, ".promotion-piece, .piece, button, [role='button']")
        except Exception:
            return False
        for element in elements:
            try:
                values = [
                    element.get_attribute("aria-label") or "",
                    element.get_attribute("title") or "",
                    element.get_attribute("class") or "",
                    element.text or "",
                ]
                if element.is_displayed() and piece_name in " ".join(values).lower():
                    click_element(element)
                    return True
            except Exception:
                continue
        return False

    def is_puzzle_complete(self) -> bool:
        return self._has_visible_selector(
            (
                '[data-cy*="next-puzzle"]',
                '[data-cy*="puzzle-complete"]',
                '[data-cy*="puzzle-completed"]',
                '[data-cy*="puzzle-success"]',
                '[data-cy*="new-rating"]',
                '[data-cy*="rating-change"]',
                ".puzzle-complete",
                ".puzzle-completed",
                ".puzzle-success",
                ".success",
            )
        )

    def _has_visible_selector(self, selectors: tuple[str, ...]) -> bool:
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    };
                    return arguments[0].some((selector) => [...document.querySelectorAll(selector)].some(visible));
                    """,
                    selectors,
                )
            )
        except Exception:
            return False

    def _result(self, status: str, message: str) -> ChessRunResult:
        return ChessRunResult(
            status=status,
            message=message,
        )


def parse_board_state(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    board = {}
    parsed_pieces = []
    for piece in raw.get("pieces") or []:
        cls = piece.get("cls") or ""
        piece_match = re.search(r"\b([wb][pnbrqk])\b", cls)
        square_match = re.search(r"\bsquare-([1-8])([1-8])\b", cls)
        if not piece_match or not square_match:
            continue
        code = piece_match.group(1)
        file_index = int(square_match.group(1))
        rank = int(square_match.group(2))
        square = f"{chr(ord('a') + file_index - 1)}{rank}"
        board[square] = PIECE_TO_FEN[code]
        parsed_pieces.append(
            {
                "piece": code,
                "square": square,
                "file": file_index,
                "rank": rank,
                "rect": piece.get("rect") or {},
            }
        )
    if not board:
        return None
    board_rect = raw.get("boardRect")
    orientation = detect_orientation(board_rect, parsed_pieces)
    side = side_from_orientation(orientation)
    return {
        "fen": board_to_fen(board, side),
        "side": side,
        "board": board,
        "pieces": parsed_pieces,
        "boardRect": board_rect,
        "orientation": orientation,
        "url": raw.get("url"),
    }


def side_from_orientation(orientation: str) -> str:
    if orientation == "black":
        return "b"
    return "w"


def board_to_fen(board: dict[str, str], side: str) -> str:
    rows = []
    for rank in range(8, 0, -1):
        empty = 0
        row = ""
        for file_index in range(1, 9):
            square = f"{chr(ord('a') + file_index - 1)}{rank}"
            piece = board.get(square)
            if piece:
                if empty:
                    row += str(empty)
                    empty = 0
                row += piece
            else:
                empty += 1
        if empty:
            row += str(empty)
        rows.append(row)
    return f"{'/'.join(rows)} {side} - - 0 1"


def detect_orientation(board_rect: dict[str, float] | None, pieces: list[dict[str, Any]]) -> str:
    if not board_rect or not pieces:
        return "white"
    cell = board_rect["width"] / 8.0
    white_error = 0.0
    black_error = 0.0
    used = 0
    for piece in pieces:
        rect = piece.get("rect") or {}
        if not rect.get("width") or not rect.get("height"):
            continue
        center_x = rect["left"] + rect["width"] / 2.0
        center_y = rect["top"] + rect["height"] / 2.0
        file_index = piece["file"]
        rank = piece["rank"]
        white_x = board_rect["left"] + (file_index - 0.5) * cell
        white_y = board_rect["top"] + (8 - rank + 0.5) * cell
        black_x = board_rect["left"] + (8 - file_index + 0.5) * cell
        black_y = board_rect["top"] + (rank - 0.5) * cell
        white_error += abs(center_x - white_x) + abs(center_y - white_y)
        black_error += abs(center_x - black_x) + abs(center_y - black_y)
        used += 1
    if used and black_error < white_error:
        return "black"
    return "white"


def square_to_chesscom_class(square: str) -> str:
    file_index = ord(square[0]) - ord("a") + 1
    rank = int(square[1])
    return f"square-{file_index}{rank}"


def chesscom_path(url: str) -> str:
    return urlparse(url).path.rstrip("/") or "/"


def select_non_best_legal_move(best_move: str, legal_moves: list[str]) -> str:
    for move in legal_moves:
        if move != best_move:
            return move
    raise ChessAutomationError("No legal move different from Stockfish bestmove was available.")


def run_chess_with_driver(
    driver: "WebDriver",
    config: AppConfig,
    session_result: ChessRunResult | None = None,
) -> ChessRunResult:
    if not config.chess_enabled:
        return ChessRunResult(
            status="skipped",
            message="Chess.com is disabled in config.",
        )
    client = ChessClient(driver, config)
    auth_result = session_result or client.check_auth_session()
    if auth_result.status != "ok":
        return auth_result
    puzzle_result = client.check_puzzle_session()
    if puzzle_result.status != "ok":
        return puzzle_result
    return client.run_puzzle(puzzle_result)
