from __future__ import annotations

import argparse
from collections.abc import Sequence

from streakify.config import StreakifyConfigError, load_config
from streakify.tiktok import TikTokAutomationError, run_tiktok


def main(argv: Sequence[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(argv)
    if args.command == "tiktok":
        return _run_tiktok_command(args.config)
    parser.print_help()
    return 0


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="streakify")
    parser.add_argument("--config", default="config.txt", help="Path to config file.")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("tiktok", help="Check TikTok browser session.")
    return parser


def _run_tiktok_command(config_path: str) -> int:
    try:
        config = load_config(config_path)
        result = run_tiktok(config)
    except StreakifyConfigError as exc:
        print(f"Config error: {exc}")
        return 1
    except TikTokAutomationError as exc:
        print(f"Automation error: {exc}")
        return 1
    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Chats found: {result.chats_found}")
    print(f"Headless: {str(result.headless).lower()}")
    if result.status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
