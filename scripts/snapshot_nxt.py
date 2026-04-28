#!/usr/bin/env python3
"""08:45 KST snapshot of NXT pre-open data into today's summary.json.

NXT 는 08:00-20:00 연속 거래되며 가격이 계속 변동. 이전엔 클라이언트가 매 페이지
로드마다 현재 NXT 를 가져와서 baseline 에 적용 → reload 마다 그룹 배치가 달라지는
문제 (10:00 reload 와 14:00 reload 가 다른 NXT 가격으로 다른 그룹 배치를 보여줌).

이 스크립트는 평일 08:45 KST 에 launchd 가 한 번 실행해서 그 시점의 NXT 데이터를
summary.json 에 baked-in. 이후 페이지 로드는 server-rendered baked 결과를 그대로
보여줘서 일관성 유지.

각 stock 에 다음 필드 추가:
  - `nxt_pre_open: {change_pct, change, direction, captured_at}` — NXT 칩 데이터
  - `nxt_adjusted_recommendation: <rec>` — 그룹 이동이 필요한 경우만 (steps != 0)

render.py 가 nxt_adjusted_recommendation 을 우선 사용해 그룹 배치, 없으면
baseline recommendation 사용.

Usage:
  .venv/bin/python scripts/snapshot_nxt.py [YYYY-MM-DD]
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
WORKER_NXT_URL = "https://k-ant-daily-quotes.yummyummyummy.workers.dev/nxt-quotes"

# Mirror of the JS REC_ORDER + nxtSteps thresholds — keep these in sync if
# the matrix in daily-report.md ever changes (which would also need a
# render.py + template overhaul).
REC_ORDER = ["strong_sell", "sell", "hold", "buy", "strong_buy"]


def nxt_steps(pct: float) -> int:
    if pct >= 3.0:
        return 2
    if pct >= 1.5:
        return 1
    if pct <= -3.0:
        return -2
    if pct <= -1.5:
        return -1
    return 0


def fetch_nxt(codes: list[str]) -> dict:
    codes = [c for c in codes if c and c.isdigit()]
    if not codes:
        return {}
    try:
        url = f"{WORKER_NXT_URL}?codes={','.join(codes)}"
        # Some upstream layers reject the default Python-urllib UA — give it
        # a generic browser-ish UA so the worker (and downstream Naver) reply.
        req = urllib.request.Request(url, headers={"User-Agent": "snapshot_nxt/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[warn] NXT fetch failed: {e}", file=sys.stderr)
        return {}


def main(argv: list[str]) -> int:
    date = argv[1] if len(argv) > 1 else datetime.now(KST).strftime("%Y-%m-%d")
    summary_path = ROOT / "docs" / f"{date}.summary.json"
    if not summary_path.exists():
        print(f"[error] missing summary: {summary_path}", file=sys.stderr)
        return 1

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    stocks = summary.get("stocks") or []
    nxt_map = fetch_nxt([s.get("code", "") for s in stocks])

    chip_count = 0
    adjusted_count = 0
    for stock in stocks:
        entry = nxt_map.get(stock.get("code"))
        if not entry or entry.get("price") is None:
            stock.pop("nxt_pre_open", None)
            stock.pop("nxt_adjusted_recommendation", None)
            continue
        pct = entry.get("change_pct") or 0
        direction = entry.get("direction") or "flat"
        change_abs = entry.get("change") or 0
        stock["nxt_pre_open"] = {
            "change_pct": round(float(pct), 2),
            "change": change_abs,
            "direction": direction,
            "captured_at": datetime.now(KST).isoformat(),
        }
        chip_count += 1

        baseline = stock.get("recommendation")
        if baseline in REC_ORDER:
            steps = nxt_steps(float(pct))
            if steps != 0:
                idx = REC_ORDER.index(baseline)
                new_idx = max(0, min(len(REC_ORDER) - 1, idx + steps))
                if new_idx != idx:
                    stock["nxt_adjusted_recommendation"] = REC_ORDER[new_idx]
                    adjusted_count += 1
                else:
                    stock.pop("nxt_adjusted_recommendation", None)
            else:
                stock.pop("nxt_adjusted_recommendation", None)

    summary["nxt_snapshot_at"] = datetime.now(KST).isoformat()
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✓ NXT snapshot {date}: {chip_count}/{len(stocks)} stocks captured, {adjusted_count} group-adjusted")

    # Re-render the page so the baked snapshot reaches HTML immediately.
    rc = subprocess.call([
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "render.py"),
        str(summary_path),
        "--intraday",  # skip archive/accuracy regen — those don't change here
    ], cwd=str(ROOT))
    if rc != 0:
        print(f"[warn] render exited with status {rc}", file=sys.stderr)
        return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
