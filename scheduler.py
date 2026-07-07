"""Timed tasks: schedule coding tasks to start at a certain time or date.

Storage is a simple schedule.json in the current directory (gitignored).
`corvus scheduler` polls it and runs tasks when they come due.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timedelta

SCHEDULE_FILE = "schedule.json"


def _load() -> list[dict]:
    if not os.path.exists(SCHEDULE_FILE):
        return []
    with open(SCHEDULE_FILE) as f:
        return json.load(f)


def _save(items: list[dict]):
    with open(SCHEDULE_FILE, "w") as f:
        json.dump(items, f, indent=2)


def parse_when(at: str | None = None, in_: str | None = None) -> float:
    """Turn --at / --in arguments into a unix timestamp."""
    if in_:
        units = {"m": 60, "h": 3600, "d": 86400}
        unit = in_[-1].lower()
        if unit not in units:
            raise ValueError("Use --in like 30m, 2h, or 1d")
        try:
            return time.time() + float(in_[:-1]) * units[unit]
        except ValueError:
            raise ValueError("Use --in like 30m, 2h, or 1d") from None
    if at:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M"):
            try:
                dt = datetime.strptime(at, fmt)
            except ValueError:
                continue
            if fmt == "%H:%M":
                now = datetime.now()
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
                if dt <= now:
                    dt += timedelta(days=1)  # next occurrence of that time
            ts = dt.timestamp()
            if ts <= time.time():
                raise ValueError("That time is already in the past; pick a future time.")
            return ts
    raise ValueError(
        "Provide --at 'YYYY-MM-DD HH:MM' / 'YYYY-MM-DD' / 'HH:MM' or --in 30m/2h/1d"
    )


def add(task: str, run_at: float) -> dict:
    items = _load()
    item = {"id": uuid.uuid4().hex[:8], "task": task, "run_at": run_at, "status": "pending"}
    items.append(item)
    _save(items)
    return item


def format_items() -> list[str]:
    lines = []
    for it in _load():
        when = datetime.fromtimestamp(it["run_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"[{it['status']:>7}] #{it['id']} at {when}  {it['task']}")
    return lines


def run_loop(runner, poll_seconds: int = 30):
    """Poll the schedule and run due tasks. `runner(task_text)` does the work."""
    while True:
        items = _load()
        for it in items:
            if it["status"] == "pending" and time.time() >= it["run_at"]:
                it["status"] = "running"
                _save(items)
                try:
                    runner(it["task"])
                    it["status"] = "done"
                except Exception as err:
                    it["status"] = f"error: {err}"[:200]
                _save(items)
        time.sleep(poll_seconds)
