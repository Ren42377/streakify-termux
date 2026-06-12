from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from streakify.config import AppConfig, StreakifyConfigError, load_config
from streakify.runtime_paths import get_scheduler_state_path


SCHEDULER_POLL_SECONDS = 30
MAX_RETRY_ATTEMPTS = 3
PLATFORM_NAMES = {
    "TikTok": "tiktok",
    "Chess.com": "chess",
    "Duolingo": "duolingo",
    "Snapchat": "snapchat",
}


@dataclass(frozen=True)
class RetryPlan:
    platform_key: str
    date: str
    times: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchedulerState:
    last_run_key: str = ""
    schedule_time: str = ""
    retries: tuple[RetryPlan, ...] = ()


def main() -> int:
    project_dir = Path(__file__).resolve().parent.parent
    state_path = get_scheduler_state_path()
    print("Streakify scheduler started.", flush=True)
    while True:
        try:
            config = load_config(project_dir / "config.txt")
            now = datetime.now()
            state = read_scheduler_state(state_path)
            action = scheduler_action(config, now, state)
            if action == "run":
                key = state_key(now, config.schedule.time)
                write_scheduler_state(state_path, SchedulerState(key, config.schedule.time, clear_stale_retries(state, now).retries))
                _, failed_platforms = run_streakify(project_dir)
                state = read_scheduler_state(state_path)
                write_scheduler_state(state_path, add_retry_plans(state, now, failed_platforms))
            elif action.startswith("retry:"):
                platform_key = action.split(":", 1)[1]
                _, failed_platforms = run_streakify(project_dir, platform_key)
                state = read_scheduler_state(state_path)
                write_scheduler_state(state_path, finish_retry_attempt(state, now, platform_key, platform_key in failed_platforms))
            elif action == "mark_done":
                write_scheduler_state(state_path, SchedulerState(state_key(now, config.schedule.time), config.schedule.time))
            elif action == "reset":
                write_scheduler_state(state_path, SchedulerState(state.last_run_key, config.schedule.time))
            elif state.schedule_time != config.schedule.time:
                write_scheduler_state(state_path, SchedulerState(state.last_run_key, config.schedule.time))
        except StreakifyConfigError as exc:
            print(f"Scheduler config error: {exc}", flush=True)
        except Exception as exc:
            print(f"Scheduler error: {exc}", flush=True)
        time.sleep(SCHEDULER_POLL_SECONDS)


def should_run_now(config: AppConfig, now: datetime, last_run_key: str) -> bool:
    state = SchedulerState(last_run_key, config.schedule.time)
    return scheduler_action(config, now, state) == "run"


def scheduler_action(config: AppConfig, now: datetime, state: SchedulerState) -> str:
    if not config.schedule.enabled:
        return "none"
    current_minutes = minutes_since_midnight(now.strftime("%H:%M"))
    scheduled_minutes = minutes_since_midnight(config.schedule.time)
    schedule_changed = bool(state.schedule_time and state.schedule_time != config.schedule.time)
    if schedule_changed and current_minutes > scheduled_minutes:
        return "mark_done"
    if schedule_changed:
        return "reset"
    key = state_key(now, config.schedule.time)
    if current_minutes >= scheduled_minutes:
        if state.last_run_key == key:
            retry_platform = due_retry_platform(state, now)
            if retry_platform:
                return f"retry:{retry_platform}"
            return "none"
        return "run"
    retry_platform = due_retry_platform(state, now)
    if retry_platform:
        return f"retry:{retry_platform}"
    return "none"


def state_key(now: datetime, scheduled_time: str) -> str:
    return f"{now.date().isoformat()} {scheduled_time}"


def minutes_since_midnight(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def read_last_run_key(path: Path) -> str:
    return read_scheduler_state(path).last_run_key


def write_last_run_key(path: Path, value: str) -> None:
    scheduled_time = value.rsplit(" ", 1)[-1] if " " in value else ""
    write_scheduler_state(path, SchedulerState(value, scheduled_time))


def read_scheduler_state(path: Path) -> SchedulerState:
    try:
        raw = path.read_text(encoding="ascii").strip()
    except OSError:
        return SchedulerState()
    if not raw:
        return SchedulerState()
    try:
        data = json.loads(raw)
    except ValueError:
        scheduled_time = raw.rsplit(" ", 1)[-1] if " " in raw else ""
        return SchedulerState(raw, scheduled_time)
    retries = []
    raw_retries = data.get("retries", [])
    if isinstance(raw_retries, list):
        for item in raw_retries:
            if not isinstance(item, dict):
                continue
            times = item.get("times", [])
            if not isinstance(times, list):
                times = []
            retries.append(
                RetryPlan(
                    platform_key=str(item.get("platform_key", "")).strip(),
                    date=str(item.get("date", "")).strip(),
                    times=tuple(str(value).strip() for value in times if str(value).strip()),
                )
            )
    return SchedulerState(
        last_run_key=str(data.get("last_run_key", "")).strip(),
        schedule_time=str(data.get("schedule_time", "")).strip(),
        retries=tuple(retry for retry in retries if retry.platform_key and retry.date and retry.times),
    )


def write_scheduler_state(path: Path, state: SchedulerState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "last_run_key": state.last_run_key,
                "retries": [
                    {
                        "date": retry.date,
                        "platform_key": retry.platform_key,
                        "times": list(retry.times),
                    }
                    for retry in state.retries
                ],
                "schedule_time": state.schedule_time,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="ascii",
    )


def due_retry_platform(state: SchedulerState, now: datetime) -> str:
    today = now.date().isoformat()
    current_minutes = minutes_since_midnight(now.strftime("%H:%M"))
    for retry in state.retries:
        if retry.date != today or not retry.times:
            continue
        if minutes_since_midnight(retry.times[0]) <= current_minutes:
            return retry.platform_key
    return ""


def clear_stale_retries(state: SchedulerState, now: datetime) -> SchedulerState:
    today = now.date().isoformat()
    return SchedulerState(
        state.last_run_key,
        state.schedule_time,
        tuple(retry for retry in state.retries if retry.date == today and retry.times),
    )


def add_retry_plans(state: SchedulerState, now: datetime, failed_platforms: set[str]) -> SchedulerState:
    if not failed_platforms:
        return clear_stale_retries(state, now)
    today = now.date().isoformat()
    existing = {
        retry.platform_key: retry
        for retry in clear_stale_retries(state, now).retries
        if retry.platform_key not in failed_platforms
    }
    used_minutes = {
        minutes_since_midnight(value)
        for retry in existing.values()
        for value in retry.times
        if retry.date == today
    }
    for platform_key in sorted(failed_platforms):
        times = select_retry_times(now, used_minutes)
        if times:
            existing[platform_key] = RetryPlan(platform_key, today, times)
            used_minutes.update(minutes_since_midnight(value) for value in times)
    return SchedulerState(state.last_run_key, state.schedule_time, tuple(existing[key] for key in sorted(existing)))


def finish_retry_attempt(state: SchedulerState, now: datetime, platform_key: str, failed: bool) -> SchedulerState:
    today = now.date().isoformat()
    retries = []
    for retry in clear_stale_retries(state, now).retries:
        if retry.platform_key != platform_key:
            retries.append(retry)
            continue
        remaining = tuple(value for value in retry.times if minutes_since_midnight(value) > minutes_since_midnight(now.strftime("%H:%M")))
        if failed and remaining and retry.date == today:
            retries.append(RetryPlan(retry.platform_key, retry.date, remaining))
    return SchedulerState(state.last_run_key, state.schedule_time, tuple(retries))


def select_retry_times(now: datetime, used_minutes: set[int] | None = None) -> tuple[str, ...]:
    used = used_minutes if used_minutes is not None else set()
    start = minutes_since_midnight(now.strftime("%H:%M")) + 1
    available = [minute for minute in range(start, 24 * 60) if minute not in used]
    if not available:
        return ()
    selected = random.sample(available, min(MAX_RETRY_ATTEMPTS, len(available)))
    selected.sort()
    return tuple(format_minutes(value) for value in selected)


def format_minutes(value: int) -> str:
    return f"{value // 60:02d}:{value % 60:02d}"


def parse_failed_platforms(output: str) -> set[str]:
    failed = set()
    for line in output.splitlines():
        for platform_name, platform_key in PLATFORM_NAMES.items():
            prefix = f"{platform_name} status:"
            if not line.startswith(prefix):
                continue
            status = line[len(prefix):].strip().lower()
            if status not in {"ok", "skipped"}:
                failed.add(platform_key)
    return failed


def run_streakify(project_dir: Path, platform_key: str | None = None) -> tuple[int, set[str]]:
    if platform_key:
        print(f"Scheduler retrying Streakify platform: {platform_key}.", flush=True)
    else:
        print("Scheduler running Streakify.", flush=True)
    command = [sys.executable, "-m", "streakify"]
    if platform_key:
        command.extend(["--platform", platform_key])
    completed = subprocess.run(
        command,
        cwd=project_dir,
        capture_output=True,
        check=False,
        text=True,
    )
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", flush=True)
    print(f"Scheduler run finished with exit code {completed.returncode}.", flush=True)
    failed_platforms = parse_failed_platforms(completed.stdout)
    return completed.returncode, failed_platforms


if __name__ == "__main__":
    raise SystemExit(main())
