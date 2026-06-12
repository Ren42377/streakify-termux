from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TikTokRunResult:
    status: str
    message: str
    selected_chats: int = 0
    sent_chats: int = 0


@dataclass(frozen=True)
class ChessRunResult:
    status: str
    message: str
    moves_played: int = 0


@dataclass(frozen=True)
class DuolingoRunResult:
    status: str
    message: str
    page_opened: bool = False
    moves_played: int = 0
    completed: bool = False
