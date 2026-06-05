from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TikTokRunResult:
    status: str
    message: str
    chats_found: int
    headless: bool
    selected_chats: int = 0
    sent_chats: int = 0
    dry_run: bool = True
