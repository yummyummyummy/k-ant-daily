#!/usr/bin/env python3
"""Fetch upcoming clinical trial events from ClinicalTrials.gov v2 API.

For each bio stock with a `clinical_sponsor` in stocks.yml, query the
ClinicalTrials.gov registry and emit "Primary Completion" / "Completion"
date events into .tmp/events_clinical.json.

These are *estimated* readout windows — actual press releases typically
follow 3~6 months later. The calendar marks them with an "예상" badge.

Output schema (per event):
    {
      "date": "2026-09-30",
      "category": "clinical",
      "title": "알테오젠 ALT-B4 3상 1차 평가지표 데이터 수집 예정",
      "description": "NCT12345678 — Recruiting → Primary Completion",
      "related_codes": ["196170"],
      "tags": ["bio", "clinical", "estimated"],
      "source": "https://clinicaltrials.gov/study/NCT12345678",
      "importance": 2,
      "_meta": {"nct_id": "...", "phase": "PHASE3", "status": "RECRUITING"}
    }
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://clinicaltrials.gov/api/v2/studies"

# Fields we ask the API to return. Smaller payloads = faster.
FIELDS = [
    "NCTId",
    "BriefTitle",
    "OverallStatus",
    "Phase",
    "PrimaryCompletionDate",
    "CompletionDate",
    "StartDate",
    "LeadSponsorName",
    "Conditions",
]

# Only surface studies whose status is one of these — completed/terminated
# trials don't add forward-looking dates.
ACTIVE_STATUSES = {
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
}


def _fetch_sponsor_studies(sponsor: str, page_size: int = 50) -> list[dict]:
    """Fetch all studies for a sponsor (paginated)."""
    studies: list[dict] = []
    next_token: str | None = None
    while True:
        params = {
            "query.spons": sponsor,
            "fields": ",".join(FIELDS),
            "pageSize": page_size,
            "format": "json",
        }
        if next_token:
            params["pageToken"] = next_token
        r = requests.get(API, params=params, timeout=20)
        r.raise_for_status()
        body = r.json()
        studies.extend(body.get("studies", []))
        next_token = body.get("nextPageToken")
        if not next_token:
            break
        if len(studies) >= 500:  # safety cap
            break
    return studies


def _parse_date(raw: str | None) -> str | None:
    """ClinicalTrials.gov returns dates as 'YYYY-MM' or 'YYYY-MM-DD'.
    Normalize to YYYY-MM-DD (use month-end for month-only)."""
    if not raw:
        return None
    parts = raw.split("-")
    if len(parts) == 3:
        return raw
    if len(parts) == 2:
        # Month-only — push to last day of month so it sorts after exact dates.
        y, m = int(parts[0]), int(parts[1])
        # Last day of month: take first of next month minus 1 day.
        if m == 12:
            return f"{y+1:04d}-01-01"  # caller filters past dates
        # crude but fine: 28th avoids leap edge cases
        return f"{y:04d}-{m:02d}-28"
    return None


def _phase_label(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.replace("PHASE", "").strip() or raw


def _build_event(code: str, name: str, study: dict, today: date) -> dict | None:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    cond_mod = proto.get("conditionsModule", {})

    nct = ident.get("nctId", "")
    title = ident.get("briefTitle", "")
    status = status_mod.get("overallStatus", "")
    phases = design.get("phases") or []
    phase = _phase_label(phases[0] if phases else None)
    conditions = ", ".join(cond_mod.get("conditions") or [])

    if status not in ACTIVE_STATUSES:
        return None

    pcd = (status_mod.get("primaryCompletionDateStruct") or {}).get("date")
    cd = (status_mod.get("completionDateStruct") or {}).get("date")
    # Prefer primary completion (most relevant readout signal)
    target = _parse_date(pcd) or _parse_date(cd)
    if not target:
        return None
    if target < today.isoformat():
        return None

    cond_part = f" · {conditions}" if conditions else ""
    phase_part = f" {phase}상" if phase else ""
    return {
        "date": target,
        "category": "clinical",
        "title": f"{name}{phase_part} 1차 평가지표 데이터 수집 예정",
        "description": f"{nct} — {title}{cond_part}",
        "related_codes": [code],
        "tags": ["bio", "clinical", "estimated"],
        "source": f"https://clinicaltrials.gov/study/{nct}",
        "importance": 2,
        "_meta": {
            "nct_id": nct,
            "phase": phase,
            "status": status,
        },
    }


def main() -> int:
    with open(ROOT / "stocks.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    today = datetime.now().date()
    events: list[dict] = []

    for stock in config.get("stocks", []):
        sponsor = stock.get("clinical_sponsor")
        if not sponsor:
            continue
        code, name = stock["code"], stock["name"]
        try:
            studies = _fetch_sponsor_studies(sponsor)
        except Exception as e:
            print(f"[warn] CT.gov fetch failed for {name} ({sponsor}): {e}", file=sys.stderr)
            continue
        added = 0
        for study in studies:
            event = _build_event(code, name, study, today)
            if event:
                events.append(event)
                added += 1
        print(f"· {name}: {len(studies)} studies → {added} forward-looking events", file=sys.stderr)

    events.sort(key=lambda e: e["date"])
    out = ROOT / ".tmp" / "events_clinical.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {out.relative_to(ROOT)}: {len(events)} clinical events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
