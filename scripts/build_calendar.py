#!/usr/bin/env python3
"""Merge calendar event sources into a single docs/events.json.

Sources:
  - events.yml                       — manually curated (학회/거시/IR/휴장일)
  - .tmp/events_clinical.json        — ClinicalTrials.gov primary completion dates
  - .tmp/events_dart.json            — recent DART disclosures (last 30 days)

Output: docs/events.json
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

VALID_CATEGORIES = {
    "macro", "conference", "holiday", "earnings",
    "ir", "clinical", "disclosure", "other",
}


def _load_yaml_events() -> list[dict]:
    path = ROOT / "events.yml"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("events") or []
    out = []
    for e in raw:
        if "date_range" in e:
            start, end = e["date_range"]
            # 다일 이벤트는 매일 펼치지 않고 단 1개로 접는다 (캘린더 도배 방지).
            # 거시(FOMC 등)는 결정/발표가 마지막 날 → 마지막 날 기준,
            # 그 외(학회 등)는 시작일 기준. `_range` 는 기간 라벨/결과 타이밍용으로 유지.
            anchor = end if e.get("category") == "macro" else start
            copy = {k: v for k, v in e.items() if k != "date_range"}
            copy["date"] = anchor
            copy["_range"] = [start, end]
            out.append(copy)
        elif "date" in e:
            out.append(dict(e))
    return out


def _load_json_events(name: str) -> list[dict]:
    path = ROOT / ".tmp" / name
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(event: dict) -> dict | None:
    if not event.get("date") or not event.get("title"):
        return None
    cat = event.get("category", "other")
    if cat not in VALID_CATEGORIES:
        cat = "other"
    out = {
        "date": event["date"],
        "category": cat,
        "title": event["title"],
        "description": event.get("description", ""),
        "impact": event.get("impact", ""),
        "related_codes": list(event.get("related_codes") or []),
        "tags": list(event.get("tags") or []),
        "source": event.get("source", ""),
        "importance": int(event.get("importance", 2)),
        **({"_range": event["_range"]} if "_range" in event else {}),
    }
    # Optional: result-tracking fields. `time` (HH:MM KST) marks when an
    # outcome becomes known; `result` is filled by the agent after the event.
    if event.get("time"):
        out["time"] = event["time"]
    if event.get("result"):
        out["result"] = event["result"]
    # Optional: per-stock watch points. {code: "이 종목에서 봐야 할 핵심"}
    if event.get("per_stock"):
        out["per_stock"] = {str(k): v for k, v in event["per_stock"].items()}
    return out


def _dedupe(events: list[dict]) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for e in events:
        key = (e["date"], e["title"])
        if key in seen:
            # Higher importance wins; merge tags / related_codes
            existing = seen[key]
            existing["tags"] = sorted(set(existing["tags"] + e["tags"]))
            existing["related_codes"] = sorted(set(existing["related_codes"] + e["related_codes"]))
            existing["importance"] = max(existing["importance"], e["importance"])
            if e.get("source") and not existing.get("source"):
                existing["source"] = e["source"]
            if e.get("description") and not existing.get("description"):
                existing["description"] = e["description"]
            if e.get("impact") and not existing.get("impact"):
                existing["impact"] = e["impact"]
            if e.get("time") and not existing.get("time"):
                existing["time"] = e["time"]
            if e.get("result") and not existing.get("result"):
                existing["result"] = e["result"]
            if e.get("per_stock"):
                existing.setdefault("per_stock", {}).update(e["per_stock"])
        else:
            seen[key] = e
    return list(seen.values())


def main() -> int:
    raw: list[dict] = []
    raw.extend(_load_yaml_events())
    raw.extend(_load_json_events("events_clinical.json"))
    raw.extend(_load_json_events("events_dart.json"))

    normalized = [e for e in (_normalize(r) for r in raw) if e]
    deduped = _dedupe(normalized)
    deduped.sort(key=lambda e: (e["date"], -e["importance"]))

    payload = {
        "generated_at": datetime.now(KST).isoformat(),
        "events": deduped,
    }
    out = ROOT / "docs" / "events.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {out.relative_to(ROOT)}: {len(deduped)} events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
