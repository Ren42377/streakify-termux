from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

import chess

from streakify.browser import click_element
from streakify.config import AppConfig
from streakify.duolingo_vision import (
    VISION_INPUT_SIZE,
    VisionPrediction,
    load_vision_model,
)
from streakify.results import DuolingoRunResult
from streakify.stockfish import StockfishEngine, StockfishError, is_stockfish_available

if TYPE_CHECKING:
    from selenium.webdriver.chrome.webdriver import WebDriver


class DuolingoAutomationError(RuntimeError):
    pass


class DuolingoMatchRetry(RuntimeError):
    pass


DUOLINGO_AUTH_STABLE_SECONDS = 5.0
DUOLINGO_POLL_SECONDS = 0.08
DUOLINGO_DRAG_HOLD_SECONDS = 0.01
DUOLINGO_MAX_ACTIONS = 300
DUOLINGO_VISUAL_DEPTH = 2
DUOLINGO_FUZZY_SCORE = 12
DUOLINGO_GEOMETRY_RECOVERY_SECONDS = 8.0
DUOLINGO_PROGRESS_TIMEOUT_SECONDS = 45.0
DUOLINGO_INITIAL_SYNC_SECONDS = 2.0
DUOLINGO_CONTINUE_TIMEOUT_SECONDS = 30.0


MATCH_STATE_SCRIPT = r"""
return (() => {
    const canvases = [...document.querySelectorAll('canvas')]
        .map(canvas => {
            const rect = canvas.getBoundingClientRect();
            return { canvas, rect, area: rect.width * rect.height };
        })
        .filter(item => item.rect.width >= 250 && item.rect.height >= 250)
        .sort((a, b) => b.area - a.area);
    const boardCanvas = canvases[0] && canvases[0].canvas;

    function fiberOf(element) {
        if (!element) return null;
        const key = Object.keys(element).find(value =>
            value.startsWith('__reactFiber$') ||
            value.startsWith('__reactInternalInstance$')
        );
        return key ? element[key] : null;
    }

    function findRoot(value, seen, depth) {
        if (!value || typeof value !== 'object' || depth > 8 || seen.has(value)) return null;
        seen.add(value);
        if (value.challengeState && value.challenge) return value;
        const keys = Object.keys(value);
        for (const key of keys) {
            if (!/challenge|match|board|fen|state|props|memoized|current|game|chess|guess|history|move/i.test(key)) continue;
            try {
                const found = findRoot(value[key], seen, depth + 1);
                if (found) return found;
            } catch (error) {}
        }
        return null;
    }

    let fiber = fiberOf(boardCanvas) || fiberOf(boardCanvas && boardCanvas.parentElement);
    let root = null;
    for (let index = 0; fiber && index < 90 && !root; index += 1) {
        root = findRoot(fiber.memoizedProps, new WeakSet(), 0) ||
            findRoot(fiber.memoizedState, new WeakSet(), 0) ||
            findRoot(fiber.stateNode, new WeakSet(), 0);
        fiber = fiber.return;
    }
    const challenge = root && root.challenge ? root.challenge : {};
    const match = challenge.match || {};
    const guess = root && root.challengeState && root.challengeState.guess
        ? root.challengeState.guess
        : {};
    const matchState = guess.matchState || {};
    return {
        url: location.href,
        text: document.body ? document.body.innerText.slice(0, 1500) : '',
        boardFen: typeof match.boardFen === 'string' ? match.boardFen : null,
        playerColor: typeof match.playerColor === 'string' ? match.playerColor : null,
        moveHistory: Array.isArray(guess.moveHistory) ? guess.moveHistory.map(String) : [],
        matchStatus: match.status || null,
        guessStatus: matchState.status || null,
        boardRect: null
    };
})()
"""


VISION_BOARD_SCRIPT = r"""
return (() => {
    const canvas = [...document.querySelectorAll('canvas')]
        .map(element => {
            const rect = element.getBoundingClientRect();
            return { element, rect, area: rect.width * rect.height };
        })
        .filter(item => item.rect.width >= 250 && item.rect.height >= 250)
        .sort((a, b) => b.area - a.area)[0]?.element;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();

    try {
        const context = canvas.getContext('2d', { willReadFrequently: true });
        const width = canvas.width;
        const height = canvas.height;
        const data = context.getImageData(0, 0, width, height).data;
        let minX = width;
        let minY = height;
        let maxX = -1;
        let maxY = -1;
        let count = 0;
        for (let y = 0; y < height; y += 1) {
            for (let x = 0; x < width; x += 1) {
                const index = (y * width + x) * 4;
                const red = data[index];
                const green = data[index + 1];
                const blue = data[index + 2];
                const alpha = data[index + 3];
                if (alpha < 10) continue;
                const gray = Math.max(red, green, blue) - Math.min(red, green, blue) < 16;
                const lightSquare = gray && red >= 216 && red <= 252 && green >= 216 && green <= 252 && blue >= 216 && blue <= 252;
                const darkSquare = gray && red >= 120 && red <= 220 && green >= 120 && green <= 220 && blue >= 120 && blue <= 220;
                if (!lightSquare && !darkSquare) continue;
                minX = Math.min(minX, x);
                minY = Math.min(minY, y);
                maxX = Math.max(maxX, x);
                maxY = Math.max(maxY, y);
                count += 1;
            }
        }
        const pixelWidth = maxX - minX + 1;
        const pixelHeight = maxY - minY + 1;
        if (count > 1000 && pixelWidth >= 250 && pixelHeight >= 250) {
            const boardPixels = Math.round(Math.min(pixelWidth, pixelHeight) / 8) * 8;
            const scaleX = rect.width / width;
            const scaleY = rect.height / height;
            return {
                left: rect.left + minX * scaleX,
                top: rect.top + minY * scaleY,
                width: boardPixels * scaleX,
                height: boardPixels * scaleY,
                source: 'vision-canvas',
                pixelCount: count
            };
        }
    } catch (error) {}
    return null;
})()
"""


VISION_TILES_SCRIPT = f"""
return (() => {{
    let boardRect = arguments[0];
    const orientation = arguments[1] || 'white';
    const inputSize = {VISION_INPUT_SIZE};
    const canvas = [...document.querySelectorAll('canvas')]
        .map(element => {{
            const rect = element.getBoundingClientRect();
            return {{ element, rect, area: rect.width * rect.height }};
        }})
        .filter(item => item.rect.width >= 250 && item.rect.height >= 250)
        .sort((a, b) => b.area - a.area)[0]?.element;
    if (!canvas) return null;
    const canvasRect = canvas.getBoundingClientRect();
    if (!boardRect || !boardRect.width || !boardRect.height) return null;
    const scaleX = canvas.width / canvasRect.width;
    const scaleY = canvas.height / canvasRect.height;
    const outputSize = inputSize * 8;
    const boardCanvas = document.createElement('canvas');
    boardCanvas.width = outputSize;
    boardCanvas.height = outputSize;
    const boardContext = boardCanvas.getContext('2d', {{ willReadFrequently: true }});
    const sourceLeft = (boardRect.left - canvasRect.left) * scaleX;
    const sourceTop = (boardRect.top - canvasRect.top) * scaleY;
    const sourceWidth = boardRect.width * scaleX;
    const sourceHeight = boardRect.height * scaleY;
    boardContext.drawImage(
        canvas,
        sourceLeft,
        sourceTop,
        sourceWidth,
        sourceHeight,
        0,
        0,
        outputSize,
        outputSize
    );
    const boardData = boardContext.getImageData(0, 0, outputSize, outputSize).data;
    const squares = [];
    const packed = new Uint8Array(64 * inputSize * inputSize * 3);
    let packedIndex = 0;
    for (const file of 'abcdefgh') {{
        for (let rank = 1; rank <= 8; rank += 1) {{
            const square = file + String(rank);
            squares.push(square);
            const fileIndex = file.charCodeAt(0) - 97;
            const column = orientation === 'black' ? 7 - fileIndex : fileIndex;
            const row = orientation === 'black' ? rank - 1 : 8 - rank;
            const tileLeft = column * inputSize;
            const tileTop = row * inputSize;
            for (let y = 0; y < inputSize; y += 1) {{
                for (let x = 0; x < inputSize; x += 1) {{
                    const sourceIndex = ((tileTop + y) * outputSize + tileLeft + x) * 4;
                    packed[packedIndex] = boardData[sourceIndex];
                    packed[packedIndex + 1] = boardData[sourceIndex + 1];
                    packed[packedIndex + 2] = boardData[sourceIndex + 2];
                    packedIndex += 3;
                }}
            }}
        }}
    }}
    let binary = '';
    const chunkSize = 32768;
    for (let offset = 0; offset < packed.length; offset += chunkSize) {{
        binary += String.fromCharCode(...packed.subarray(offset, offset + chunkSize));
    }}
    return {{
        squares,
        packedTiles: btoa(binary),
        width: inputSize,
        height: inputSize,
        boardRect
    }};
}})()
"""


class DuolingoClient:
    def __init__(self, driver: "WebDriver", config: AppConfig):
        self.driver = driver
        self.config = config
        self.timeout_seconds = max(1, config.browser.timeout_ms // 1000)
        self.auth_stable_seconds = DUOLINGO_AUTH_STABLE_SECONDS
        self.vision_model = load_vision_model()
        self._vision_board_rect: dict[str, float] | None = None
        self._match_orientation = "white"

    def open_login(self) -> None:
        self.open_chess_match()

    def open_chess_match(self) -> None:
        self.driver.get(self.config.duolingo.chess_match_url)

    def check_auth_session(self) -> DuolingoRunResult:
        self.open_chess_match()
        deadline = time.monotonic() + self.timeout_seconds
        expected_path = normalized_path(self.config.duolingo.chess_match_url)
        stable_since = None
        while time.monotonic() < deadline:
            current_url = self.driver.current_url
            current_path = normalized_path(current_url)
            if current_path == expected_path and has_login_query(current_url):
                return self._result("login_required", "Duolingo login is required.")
            if current_path == expected_path:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= self.auth_stable_seconds:
                    return self._result("ok", "Duolingo session is active.")
                sleep_until_next_poll(deadline)
                continue
            stable_since = None
            if is_duolingo_url(current_url):
                return self._result("error", f"Duolingo left the Chess Match endpoint: {current_url}")
            sleep_until_next_poll(deadline)
        return self._result("error", "Duolingo Chess Match endpoint was not stable.")

    def check_chess_match_ready(self) -> DuolingoRunResult:
        deadline = time.monotonic() + self.timeout_seconds
        expected_path = normalized_path(self.config.duolingo.chess_match_url)
        while time.monotonic() < deadline:
            current_url = self.driver.current_url
            current_path = normalized_path(current_url)
            if current_path == expected_path and has_login_query(current_url):
                return self._result("login_required", "Duolingo login is required.")
            if current_path == expected_path:
                return DuolingoRunResult(
                    status="ok",
                    message="Duolingo Chess Match page was opened.",
                    page_opened=True,
                )
            if is_duolingo_url(current_url):
                return self._result("error", f"Duolingo left the Chess Match endpoint: {current_url}")
            sleep_until_next_poll(deadline)
        return self._result("error", "Duolingo Chess Match endpoint was not reached.")

    def play_until_complete(self) -> DuolingoRunResult:
        if not is_stockfish_available():
            raise DuolingoAutomationError(
                "Stockfish was not found in PATH. Install stockfish in Termux and make sure the stockfish command works."
            )
        if self.vision_model is None:
            raise DuolingoAutomationError(
                "The Duolingo TFLite model or runtime is unavailable."
            )
        attempt = 1
        while True:
            if attempt > 1:
                self.restart_match()
            try:
                state = self.wait_for_match_state()
                moves_played = self.play_match(state)
                return DuolingoRunResult(
                    status="ok",
                    message="Duolingo Chess Match was completed.",
                    page_opened=True,
                    moves_played=moves_played,
                    completed=True,
                )
            except DuolingoMatchRetry:
                attempt += 1

    def restart_match(self) -> None:
        self.invalidate_board_geometry()
        separator = "&" if "?" in self.config.duolingo.chess_match_url else "?"
        url = f"{self.config.duolingo.chess_match_url}{separator}autostreak={time.time_ns()}"
        self.driver.get(url)

    def wait_for_match_state(self) -> dict[str, Any]:
        deadline = time.monotonic() + max(45, self.timeout_seconds)
        while time.monotonic() < deadline:
            self.validate_endpoint()
            state = self.read_match_state()
            if state and looks_like_fen(state.get("boardFen")):
                board_rect = self.read_vision_board_rect()
                if board_rect:
                    state["boardRect"] = board_rect
                    return state
            time.sleep(0.5)
        raise DuolingoMatchRetry("Duolingo board did not become ready.")

    def play_match(self, initial_state: dict[str, Any]) -> int:
        if is_match_completed_state(initial_state):
            return self.finish_match(0)
        board, _ = reconstruct_board(initial_state["boardFen"], initial_state.get("moveHistory") or [])
        orientation = normalize_orientation(initial_state.get("playerColor"))
        self._match_orientation = orientation
        self._vision_board_rect = initial_state["boardRect"]
        player_side = chess.WHITE if orientation == "white" else chess.BLACK
        board = self.synchronize_board(board)
        try:
            engine = StockfishEngine()
        except StockfishError as exc:
            raise DuolingoAutomationError(str(exc)) from exc
        moves_played = 0
        try:
            for _ in range(DUOLINGO_MAX_ACTIONS):
                self.validate_endpoint()
                if board.is_checkmate():
                    return self.finish_match(moves_played)
                if board.is_game_over():
                    raise DuolingoMatchRetry("Duolingo match ended without checkmate.")
                if board.turn != player_side:
                    board = self.wait_for_opponent(board, player_side)
                    continue
                try:
                    move_text = select_duolingo_move(
                        engine,
                        board,
                        self.config.chess.engine_time,
                    )
                except StockfishError as exc:
                    raise DuolingoAutomationError(str(exc)) from exc
                try:
                    move = chess.Move.from_uci(move_text)
                except ValueError as exc:
                    raise DuolingoMatchRetry("Stockfish returned an invalid Duolingo move.") from exc
                if move not in board.legal_moves:
                    raise DuolingoMatchRetry("Stockfish returned an illegal Duolingo move.")
                previous = board.copy(stack=False)
                board_rect = self.read_move_board_rect()
                self.play_move(move_text, board_rect, orientation)
                sequence = self.wait_for_visual_sequence(previous, move)
                if not sequence or sequence[0] != move:
                    raise DuolingoMatchRetry("Duolingo did not apply the expected player move.")
                board = apply_sequence(previous, sequence)
                moves_played += 1
                if board.is_checkmate():
                    return self.finish_match(moves_played)
            raise DuolingoMatchRetry("Duolingo match exceeded the action limit.")
        finally:
            engine.close()

    def wait_for_opponent(
        self,
        board: chess.Board,
        player_side: chess.Color,
    ) -> chess.Board:
        while board.turn != player_side and not board.is_game_over():
            sequence = self.wait_for_progress_sequence(
                board,
                timeout_message="Duolingo opponent move timed out.",
            )
            board = apply_sequence(board, sequence)
            if board.is_checkmate():
                return board
        return board

    def wait_for_visual_sequence(
        self,
        board: chess.Board,
        expected_first: chess.Move,
    ) -> list[chess.Move] | None:
        try:
            return self.wait_for_progress_sequence(
                board,
                expected_first=expected_first,
                timeout_message="Duolingo player move verification timed out.",
            )
        except DuolingoMatchRetry:
            return None

    def wait_for_progress_sequence(
        self,
        board: chess.Board,
        timeout_message: str,
        expected_first: chess.Move | None = None,
    ) -> list[chess.Move]:
        started_at = time.monotonic()
        geometry_recovery_done = False
        while time.monotonic() - started_at < DUOLINGO_PROGRESS_TIMEOUT_SECONDS:
            self.validate_endpoint()
            sequence = self.read_progress_sequence(board, expected_first)
            if sequence:
                return sequence
            elapsed = time.monotonic() - started_at
            if elapsed >= DUOLINGO_GEOMETRY_RECOVERY_SECONDS and not geometry_recovery_done:
                geometry_recovery_done = True
                self.recover_visual_reader()
            time.sleep(DUOLINGO_POLL_SECONDS)
        raise DuolingoMatchRetry(timeout_message)

    def synchronize_board(self, board: chess.Board) -> chess.Board:
        deadline = time.monotonic() + DUOLINGO_INITIAL_SYNC_SECONDS
        expected = piece_map_from_board(board)
        while time.monotonic() < deadline:
            sequence = self.read_progress_sequence(board)
            if sequence:
                return apply_sequence(board, sequence)
            visual_map = self.read_tflite_piece_map()
            if visual_map == expected:
                return board
            time.sleep(DUOLINGO_POLL_SECONDS)
        raise DuolingoMatchRetry("Duolingo board could not be synchronized.")

    def read_progress_sequence(
        self,
        board: chess.Board,
        expected_first: chess.Move | None = None,
    ) -> list[chess.Move] | None:
        prediction = self.read_tflite_prediction()
        if prediction is not None:
            sequence = find_visual_sequence(
                board,
                prediction.piece_map,
                max_depth=DUOLINGO_VISUAL_DEPTH,
                expected_first=expected_first,
            )
            if sequence:
                return sequence
        return None

    def recover_visual_reader(self) -> None:
        self.invalidate_board_geometry()
        if self.read_vision_board_rect(force=True) is None:
            raise DuolingoMatchRetry("Duolingo board geometry could not be refreshed.")

    def read_match_state(self) -> dict[str, Any] | None:
        try:
            state = self.driver.execute_script(MATCH_STATE_SCRIPT)
        except Exception as exc:
            raise DuolingoMatchRetry(f"Duolingo match state could not be read: {exc}") from exc
        if not isinstance(state, dict):
            return None
        page_url = str(state.get("url") or "")
        page_text = str(state.get("text") or "")
        if page_url.startswith("chrome-error://") or "HTTP ERROR" in page_text.upper():
            match = re.search(r"HTTP ERROR\s+\d+", page_text, re.IGNORECASE)
            detail = match.group(0).upper() if match else "browser error"
            raise DuolingoAutomationError(f"Duolingo page failed to load: {detail}.")
        return state

    def invalidate_board_geometry(self) -> None:
        self._vision_board_rect = None

    def read_move_board_rect(self) -> dict[str, float]:
        board_rect = self.read_vision_board_rect()
        if not isinstance(board_rect, dict):
            raise DuolingoMatchRetry("Duolingo board geometry was not available.")
        return board_rect

    def read_vision_board_rect(self, force: bool = False) -> dict[str, float] | None:
        if self._vision_board_rect is not None and not force:
            return self._vision_board_rect
        try:
            result = self.driver.execute_script(VISION_BOARD_SCRIPT)
        except Exception:
            return None
        if not isinstance(result, dict):
            return None
        if not result.get("width") or not result.get("height"):
            return None
        self._vision_board_rect = result
        return result

    def read_tflite_piece_map(self) -> dict[str, str] | None:
        prediction = self.read_tflite_prediction()
        if prediction is None:
            return None
        return prediction.piece_map

    def read_tflite_prediction(self) -> VisionPrediction | None:
        if self.vision_model is None:
            return None
        board_rect = self.read_vision_board_rect()
        if not isinstance(board_rect, dict):
            return None
        try:
            payload = self.driver.execute_script(
                VISION_TILES_SCRIPT,
                board_rect,
                self._match_orientation,
            )
            prediction = self.vision_model.predict(payload)
            return prediction
        except Exception:
            return None

    def play_move(
        self,
        move: str,
        board_rect: dict[str, float],
        orientation: str,
    ) -> None:
        source = square_center(move[:2], board_rect, orientation)
        target = square_center(move[2:4], board_rect, orientation)
        validate_drag_point(source, board_rect)
        validate_drag_point(target, board_rect)
        self.dispatch_mouse("mousePressed", source["x"], source["y"], "left", 1)
        time.sleep(DUOLINGO_DRAG_HOLD_SECONDS)
        self.dispatch_mouse("mouseMoved", target["x"], target["y"], "left", 1)
        self.dispatch_mouse("mouseReleased", target["x"], target["y"], "left", 0)

    def dispatch_mouse(
        self,
        event_type: str,
        x: float,
        y: float,
        button: str,
        buttons: int,
    ) -> None:
        try:
            self.driver.execute_cdp_cmd(
                "Input.dispatchMouseEvent",
                {
                    "type": event_type,
                    "x": x,
                    "y": y,
                    "button": button,
                    "buttons": buttons,
                    "clickCount": 1,
                },
            )
        except Exception as exc:
            raise DuolingoMatchRetry(f"Duolingo CDP mouse input failed: {exc}") from exc

    def wait_and_click_continue(self) -> bool:
        from selenium.webdriver.common.by import By

        deadline = time.monotonic() + DUOLINGO_CONTINUE_TIMEOUT_SECONDS
        xpath = (
            "//button[translate(normalize-space(.), 'CONTINUE', 'continue')='continue']"
            " | //*[@role='button' and translate(normalize-space(.), 'CONTINUE', 'continue')='continue']"
            " | //a[translate(normalize-space(.), 'CONTINUE', 'continue')='continue']"
        )
        while time.monotonic() < deadline:
            elements = []
            for by, selector in (
                (By.CSS_SELECTOR, '[data-test="player-next"]'),
                (By.CSS_SELECTOR, '[data-test="continue-button"]'),
                (By.XPATH, xpath),
            ):
                try:
                    elements.extend(self.driver.find_elements(by, selector))
                except Exception:
                    continue
            for element in elements:
                try:
                    if element.is_displayed() and element.is_enabled():
                        click_element(element)
                        return True
                except Exception:
                    continue
            time.sleep(DUOLINGO_POLL_SECONDS)
        return False

    def finish_match(self, moves_played: int) -> int:
        if not self.wait_and_click_continue():
            raise DuolingoAutomationError(
                "Duolingo match finished, but the Continue button could not be clicked."
            )
        return moves_played

    def validate_endpoint(self) -> None:
        current_url = self.driver.current_url
        expected_path = normalized_path(self.config.duolingo.chess_match_url)
        current_path = normalized_path(current_url)
        if current_path == expected_path and has_login_query(current_url):
            raise DuolingoAutomationError("Duolingo login is required.")
        if current_path != expected_path:
            raise DuolingoAutomationError(f"Duolingo left the Chess Match endpoint: {current_url}")

    def _result(self, status: str, message: str) -> DuolingoRunResult:
        return DuolingoRunResult(
            status=status,
            message=message,
        )


def reconstruct_board(fen: str, move_history: list[str]) -> tuple[chess.Board, list[str]]:
    if not looks_like_fen(fen):
        raise DuolingoMatchRetry("Duolingo returned an invalid FEN.")
    for start in range(len(move_history) + 1):
        board = chess.Board(fen)
        valid = True
        for move_text in move_history[start:]:
            try:
                move = chess.Move.from_uci(move_text)
            except ValueError:
                valid = False
                break
            if move not in board.legal_moves:
                valid = False
                break
            board.push(move)
        if valid:
            return board, move_history[:start]
    raise DuolingoMatchRetry("Duolingo move history could not be applied.")


def is_match_completed_state(state: dict[str, Any]) -> bool:
    return any(
        str(state.get(key) or "").lower() == "completed"
        for key in ("guessStatus", "matchStatus")
    )


def find_visual_sequence(
    board: chess.Board,
    target_piece_map: dict[str, str],
    max_depth: int,
    expected_first: chess.Move | None = None,
) -> list[chess.Move] | None:
    if target_piece_map == piece_map_from_board(board):
        return []
    queue = [(board.copy(stack=False), [])]
    best_sequence = None
    best_score = -999
    for depth in range(max_depth + 1):
        next_queue = []
        for candidate, sequence in queue:
            candidate_map = piece_map_from_board(candidate)
            if candidate_map == target_piece_map:
                return sequence
            if sequence:
                score, _ = visual_move_score(
                    piece_map_from_board(board),
                    candidate_map,
                    target_piece_map,
                )
                if score > best_score:
                    best_score = score
                    best_sequence = sequence
            if depth == max_depth:
                continue
            legal_moves = list(candidate.legal_moves)
            if not sequence and expected_first is not None:
                legal_moves = [move for move in legal_moves if move == expected_first]
            for move in legal_moves:
                updated = candidate.copy(stack=False)
                updated.push(move)
                next_queue.append((updated, sequence + [move]))
        queue = next_queue
    if best_sequence and best_score >= DUOLINGO_FUZZY_SCORE:
        return best_sequence
    return None


def visual_move_score(
    current_map: dict[str, str],
    candidate_map: dict[str, str],
    actual_map: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    changed = {
        square
        for square in set(current_map) | set(candidate_map)
        if current_map.get(square) != candidate_map.get(square)
    }
    if not changed:
        return -999, {}
    changed_match = 0
    changed_still_current = 0
    changed_missing = 0
    for square in changed:
        actual_piece = actual_map.get(square)
        if actual_piece == candidate_map.get(square):
            changed_match += 1
        elif actual_piece == current_map.get(square):
            changed_still_current += 1
        elif actual_piece is None and candidate_map.get(square) is not None:
            changed_missing += 1
    stable_penalty = 0
    for square in set(current_map) | set(candidate_map) | set(actual_map):
        if square in changed:
            continue
        if actual_map.get(square) != candidate_map.get(square):
            stable_penalty += 1
    score = (
        changed_match * 10
        - changed_still_current * 8
        - changed_missing * 4
        - min(stable_penalty, 8)
    )
    return score, {
        "changed": sorted(changed),
        "changed_match": changed_match,
        "changed_still_current": changed_still_current,
        "changed_missing": changed_missing,
        "stable_penalty": stable_penalty,
    }


def apply_sequence(board: chess.Board, sequence: list[chess.Move]) -> chess.Board:
    updated = board.copy(stack=False)
    for move in sequence:
        updated.push(move)
    return updated


def piece_map_from_board(board: chess.Board) -> dict[str, str]:
    return {
        chess.square_name(square): piece.symbol()
        for square, piece in board.piece_map().items()
    }


def select_duolingo_move(
    engine: StockfishEngine,
    board: chess.Board,
    think_time: float,
) -> str:
    move_text = engine.best_move(board.fen(), think_time)
    try:
        move = chess.Move.from_uci(move_text)
    except ValueError:
        return move_text
    if move.promotion is None:
        return move_text
    search_moves = [
        legal_move.uci()
        for legal_move in board.legal_moves
        if legal_move.promotion is None
    ]
    if not search_moves:
        raise DuolingoMatchRetry("No legal Duolingo move without promotion is available.")
    alternative = engine.best_move(
        board.fen(),
        think_time,
        search_moves=search_moves,
    )
    try:
        alternative_move = chess.Move.from_uci(alternative)
    except ValueError:
        return alternative
    if alternative_move.promotion is not None or alternative not in search_moves:
        raise DuolingoMatchRetry("Stockfish did not return a non-promotion Duolingo move.")
    return alternative


def square_center(
    square: str,
    board_rect: dict[str, float],
    orientation: str,
) -> dict[str, int]:
    file_index = ord(square[0]) - ord("a") + 1
    rank = int(square[1])
    cell = board_rect["width"] / 8.0
    if orientation == "black":
        x = board_rect["left"] + (8 - file_index + 0.5) * cell
        y = board_rect["top"] + (rank - 0.5) * cell
    else:
        x = board_rect["left"] + (file_index - 0.5) * cell
        y = board_rect["top"] + (8 - rank + 0.5) * cell
    return {"x": round(x), "y": round(y)}


def validate_drag_point(
    point: dict[str, int],
    board_rect: dict[str, float],
) -> None:
    left = float(board_rect["left"])
    top = float(board_rect["top"])
    width = float(board_rect["width"])
    height = float(board_rect["height"])
    if width <= 0 or height <= 0:
        raise DuolingoMatchRetry("Duolingo board geometry is invalid.")
    if not left < point["x"] < left + width or not top < point["y"] < top + height:
        raise DuolingoMatchRetry("Duolingo drag coordinates are outside the board.")


def normalize_orientation(value: Any) -> str:
    if not isinstance(value, str):
        raise DuolingoMatchRetry("Duolingo playerColor is missing.")
    orientation = value.strip().lower()
    if orientation not in {"white", "black"}:
        raise DuolingoMatchRetry(f"Duolingo playerColor is invalid: {value!r}.")
    return orientation


def looks_like_fen(value: Any) -> bool:
    return bool(re.match(r"^[pnbrqkPNBRQK1-8/]+\s+[wb]\s+", str(value or "")))


def normalized_path(url: str) -> str:
    return urlparse(url).path.rstrip("/") or "/"


def has_login_query(url: str) -> bool:
    values = parse_qs(urlparse(url).query)
    return any(value.lower() == "true" for value in values.get("isLoggingIn", ()))


def is_duolingo_url(url: str) -> bool:
    return urlparse(url).netloc.endswith("duolingo.com")


def sleep_until_next_poll(deadline: float, interval: float = 0.5) -> None:
    remaining = deadline - time.monotonic()
    if remaining > 0:
        time.sleep(min(interval, remaining))


def run_duolingo_with_driver(
    driver: "WebDriver",
    config: AppConfig,
    session_result: DuolingoRunResult | None = None,
) -> DuolingoRunResult:
    if not config.duolingo_enabled:
        return DuolingoRunResult(
            status="skipped",
            message="Duolingo is disabled in config.",
        )
    client = DuolingoClient(driver, config)
    auth_result = session_result or client.check_auth_session()
    if auth_result.status != "ok":
        return auth_result
    return client.play_until_complete()
