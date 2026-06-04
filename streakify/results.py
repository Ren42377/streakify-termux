from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TikTokRunResult:
    status: str
    message: str
    chats_found: int
    headless: bool
