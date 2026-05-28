#!/usr/bin/env python3
"""Print the count of events whose result is due but not yet filled.

Cheap gate for the intraday `/check-results` launchd job — runs without any
network/LLM so off-event ticks exit immediately.

"Pending" = result-bearing event (not a holiday) whose resolve moment has
passed within the last WINDOW_HOURS and has no `result` yet. The bounded
window prevents runaway retries: stale stragglers (>WINDOW_HOURS old, e.g.
Mac was asleep) are left to the 07:30 / 23:00 daily runs.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
WINDOW_HOURS = 4


def _resolve_moment(e: dict) -> datetime | None:
    rng = e.get("_range")
    end_date = rng[1] if rng else e.get("date")
    if not end_date:
        return None
    t = e.get("time", "23:59")
    try:
        return datetime.fromisoformat(f"{end_date}T{t}:00+09:00")
    except ValueError:
        return None


def main() -> int:
    path = ROOT / "docs" / "events.json"
    if not path.exists():
        print(0)
        return 0
    try:
        events = json.loads(path.read_text(encoding="utf-8")).get("events", [])
    except Exception:
        print(0)
        return 0

    now = datetime.now(KST)
    window_start = now - timedelta(hours=WINDOW_HOURS)
    count = 0
    for e in events:
        if e.get("result") or e.get("category") == "holiday":
            continue
        m = _resolve_moment(e)
        if m and window_start <= m <= now:
            count += 1
    print(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
