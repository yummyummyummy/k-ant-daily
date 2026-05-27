#!/usr/bin/env python3
"""Fetch recent DART (한국 전자공시) disclosures for held stocks.

Requires DART_API_KEY env var (free at opendart.fss.or.kr).
Per stock, requires `dart_corp_code` (8-digit) in stocks.yml.
You can look up corp_code at https://opendart.fss.or.kr/disclosureinfo/company/main.do

Output: .tmp/events_dart.json — recent (last 30 days) disclosures.
Many are retrospective announcements; calendar build script keeps the
forward-looking ones (주주총회 일정, 배당락, IR day 등) as events and
exposes the rest as a "최근 공시" feed under each holding card.

Schema (per disclosure):
    {
      "date": "2026-05-26",            # rcept_dt formatted
      "category": "disclosure",
      "title": "알테오젠 단일판매·공급계약체결",
      "description": "report_nm 그대로",
      "related_codes": ["196170"],
      "tags": ["dart", "clinical"],    # keyword-classified
      "source": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=...",
      "importance": 2
    }
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://opendart.fss.or.kr/api/list.json"
LOOKBACK_DAYS = 30

KEYWORD_TAGS: list[tuple[str, list[str]]] = [
    ("임상", ["bio", "clinical"]),
    ("기술이전", ["bio", "license"]),
    ("라이선스", ["bio", "license"]),
    ("주주총회", ["governance"]),
    ("배당", ["dividend"]),
    ("유상증자", ["equity"]),
    ("무상증자", ["equity"]),
    ("자사주", ["buyback"]),
    ("단일판매", ["contract"]),
    ("공급계약", ["contract"]),
]


def _classify(report_name: str) -> list[str]:
    tags: list[str] = ["dart"]
    for kw, more in KEYWORD_TAGS:
        if kw in report_name:
            tags.extend(more)
    return tags


def _fetch_list(api_key: str, corp_code: str, start: str, end: str) -> list[dict]:
    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": start,
        "end_de": end,
        "page_count": 100,
    }
    r = requests.get(API, params=params, timeout=15)
    r.raise_for_status()
    body = r.json()
    status = body.get("status")
    if status == "013":  # 조회된 데이타가 없습니다
        return []
    if status != "000":
        raise RuntimeError(f"DART error {status}: {body.get('message', '')}")
    return body.get("list") or []


def main() -> int:
    api_key = os.environ.get("DART_API_KEY")
    if not api_key:
        print("[warn] DART_API_KEY not set — emitting empty events_dart.json", file=sys.stderr)
        events: list[dict] = []
    else:
        with open(ROOT / "stocks.yml", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        end = datetime.now()
        start = end - timedelta(days=LOOKBACK_DAYS)
        bgn_de, end_de = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

        events = []
        for stock in config.get("stocks", []):
            corp_code = stock.get("dart_corp_code")
            if not corp_code:
                continue
            code, name = stock["code"], stock["name"]
            try:
                items = _fetch_list(api_key, corp_code, bgn_de, end_de)
            except Exception as e:
                print(f"[warn] DART fetch failed for {name}: {e}", file=sys.stderr)
                continue
            for it in items:
                rcept_dt = it.get("rcept_dt", "")
                if len(rcept_dt) != 8:
                    continue
                d = f"{rcept_dt[:4]}-{rcept_dt[4:6]}-{rcept_dt[6:8]}"
                report = it.get("report_nm", "").strip()
                rcept_no = it.get("rcept_no", "")
                events.append({
                    "date": d,
                    "category": "disclosure",
                    "title": f"{name} {report}",
                    "description": report,
                    "related_codes": [code],
                    "tags": _classify(report),
                    "source": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
                    "importance": 2,
                })
            print(f"· {name}: {len(items)} disclosures", file=sys.stderr)

    events.sort(key=lambda e: e["date"], reverse=True)
    out = ROOT / ".tmp" / "events_dart.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Wrote {out.relative_to(ROOT)}: {len(events)} DART disclosures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
