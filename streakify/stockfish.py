from __future__ import annotations

import re
import shutil
import subprocess
import time


STOCKFISH_COMMAND = "stockfish"


class StockfishError(RuntimeError):
    pass


class StockfishEngine:
    def __init__(self, command: str = STOCKFISH_COMMAND):
        try:
            self.process = subprocess.Popen(
                [command],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise StockfishError(f"Stockfish could not be started: {exc}") from exc
        _write(self.process, "uci")
        _wait(self.process, "uciok", timeout=15)
        _write(self.process, "isready")
        _wait(self.process, "readyok", timeout=10)

    def best_move(
        self,
        fen: str,
        think_time: float,
        search_moves: list[str] | None = None,
    ) -> str:
        move_time_ms = max(50, int(think_time * 1000))
        _write(self.process, f"position fen {fen}")
        command = f"go movetime {move_time_ms}"
        if search_moves:
            command += f" searchmoves {' '.join(search_moves)}"
        _write(self.process, command)
        deadline = time.monotonic() + max(5.0, think_time + 5.0)
        while time.monotonic() < deadline:
            if self.process.stdout is None:
                break
            line = self.process.stdout.readline().strip()
            if not line:
                continue
            if line.startswith("bestmove "):
                return line.split()[1]
        raise StockfishError("Timed out waiting for Stockfish bestmove.")

    def legal_moves(self, fen: str) -> list[str]:
        _write(self.process, f"position fen {fen}")
        _write(self.process, "go perft 1")
        moves = []
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.stdout is None:
                break
            line = self.process.stdout.readline().strip()
            if not line:
                continue
            if line.startswith("Nodes searched:"):
                if moves:
                    return moves
                break
            move = parse_perft_move(line)
            if move is not None:
                moves.append(move)
        raise StockfishError("Stockfish did not return legal moves.")

    def close(self) -> None:
        try:
            _write(self.process, "quit")
        except Exception:
            pass
        try:
            self.process.terminate()
        except Exception:
            pass


def parse_perft_move(line: str) -> str | None:
    match = re.fullmatch(r"([a-h][1-8][a-h][1-8][qrbn]?):\s+\d+", line.strip())
    if match is None:
        return None
    return match.group(1)


def is_stockfish_available() -> bool:
    return shutil.which(STOCKFISH_COMMAND) is not None


def _write(engine: subprocess.Popen[str], command: str) -> None:
    if engine.stdin is None:
        raise StockfishError("Stockfish stdin is not available.")
    engine.stdin.write(command + "\n")
    engine.stdin.flush()


def _wait(engine: subprocess.Popen[str], token: str, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if engine.stdout is None:
            break
        line = engine.stdout.readline()
        if not line:
            continue
        if token in line:
            return True
    raise StockfishError(f"Stockfish did not send {token}.")
