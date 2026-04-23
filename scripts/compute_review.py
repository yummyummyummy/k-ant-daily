#!/usr/bin/env python3
"""Compare morning prediction against today's actual close and produce a
`review` overlay on summary.json.

Usage:
  .venv/bin/python scripts/compute_review.py [YYYY-MM-DD]

Inputs:
  - docs/<date>.summary.json  (morning prediction — persisted by render.py)
  - .tmp/news.json            (fresh scrape at evening; quote fields now hold today's close)

Output:
  - .tmp/summary.json with a `review` block + per-stock `result` / `predicted`.
    Feeds straight into render.py for the re-render.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

WORKER_NXT_URL = "https://k-ant-daily-quotes.yummyummyummy.workers.dev/nxt-quotes"


def classify(rec: str, pct: float) -> tuple[str, str]:
    """Map (recommendation, actual change%) → (outcome, note)."""
    if rec == "strong_buy":
        if pct >= 2.0:
            return "hit", f"풀매수 · 실제 +{pct:.2f}% · 강한 상승 확인"
        if pct >= 0.0:
            return "partial", f"풀매수 · 실제 +{pct:.2f}% · 방향은 맞았으나 강도 약함"
        return "miss", f"풀매수 · 실제 {pct:+.2f}% · 방향 틀림"
    if rec == "buy":
        if pct > 0.5:
            return "hit", f"매수 · 실제 +{pct:.2f}% · 상승 적중"
        if pct >= -0.5:
            return "partial", f"매수 · 실제 {pct:+.2f}% · 사실상 보합"
        return "miss", f"매수 · 실제 {pct:.2f}% · 하락"
    if rec == "hold":
        if abs(pct) < 1.5:
            return "hit", f"관망 · 실제 {pct:+.2f}% · 보합 구간 적중"
        if abs(pct) < 3.0:
            return "partial", f"관망 · 실제 {pct:+.2f}% · 움직임은 있었음"
        return "miss", f"관망 · 실제 {pct:+.2f}% · 큰 변동 놓침"
    if rec == "sell":
        if pct < -0.5:
            return "hit", f"매도 · 실제 {pct:.2f}% · 하락 적중"
        if pct <= 0.5:
            return "partial", f"매도 · 실제 {pct:+.2f}% · 사실상 보합"
        return "miss", f"매도 · 실제 +{pct:.2f}% · 상승"
    if rec == "strong_sell":
        if pct <= -2.0:
            return "hit", f"풀매도 · 실제 {pct:.2f}% · 강한 하락 확인"
        if pct <= 0.0:
            return "partial", f"풀매도 · 실제 {pct:.2f}% · 방향은 맞았으나 강도 약함"
        return "miss", f"풀매도 · 실제 +{pct:.2f}% · 방향 틀림"
    return "n/a", "투자의견 없음"


def direction_from_pct(pct: float) -> str:
    if pct > 0.3:
        return "up"
    if pct < -0.3:
        return "down"
    return "flat"


def matrix_direction(rec: str) -> str:
    if rec in ("strong_buy", "buy"):
        return "up"
    if rec in ("strong_sell", "sell"):
        return "down"
    if rec == "hold":
        return "flat"
    return ""


def _fetch_nxt_closes(codes: list[str]) -> dict:
    """Pull 20:00 NXT closing prices from the Worker endpoint. Called from the
    20:10 review so the archived HTML reflects the full-day picture (KRX +
    NXT after-hours) rather than 15:30 KRX close. Returns {} on any failure;
    the caller falls back to the KRX close already in stock["quote"]."""
    codes = [c for c in codes if c and c.isdigit()]
    if not codes:
        return {}
    try:
        url = f"{WORKER_NXT_URL}?codes={','.join(codes)}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[warn] NXT close fetch failed: {e}", file=sys.stderr)
        return {}


def _nxt_to_quote(nxt: dict) -> dict:
    """Shape an NXT endpoint entry into the same fields _normalize_stock_quote
    in render.py expects — the KRX 'news.json' quote shape."""
    if not nxt or nxt.get("price") is None:
        return {}
    price_num = nxt["price"]
    change_num = nxt.get("change") or 0
    pct_num = nxt.get("change_pct") or 0
    direction = nxt.get("direction") or "flat"
    sign = "+" if pct_num > 0 else ""
    return {
        "price": f"{int(round(price_num)):,}",
        "change": f"{int(round(abs(change_num))):,}",
        "change_pct": f"{sign}{pct_num:.2f}%",
        "change_pct_num": pct_num,
        "direction": direction,
    }


def _parse_pct(raw) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw) if isinstance(raw, (int, float)) else float(str(raw).replace("%", "").replace("+", ""))
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    date = argv[1] if len(argv) > 1 else datetime.now(KST).strftime("%Y-%m-%d")

    prediction_path = ROOT / "docs" / f"{date}.summary.json"
    news_path = ROOT / ".tmp" / "news.json"
    out_path = ROOT / ".tmp" / "summary.json"

    if not prediction_path.exists():
        print(f"[error] missing prediction artifact: {prediction_path}", file=sys.stderr)
        return 1
    if not news_path.exists():
        print(f"[error] missing news.json: {news_path}", file=sys.stderr)
        return 1

    prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
    news = json.loads(news_path.read_text(encoding="utf-8"))
    evening_quotes = {s["code"]: s.get("quote", {}) for s in news.get("stocks") or []}

    hits = partial = misses = 0
    # by-confidence aggregation
    conf_buckets: dict[str, list[float]] = {"high": [0, 0], "medium": [0, 0], "low": [0, 0]}
    directional_correct = 0
    directional_total = 0
    attrib = {"news_misread": 0, "overnight_misled": 0, "priced_in_underestimated": 0, "overnight_helped": 0}

    for stock in prediction.get("stocks") or []:
        code = stock["code"]
        rec = stock.get("recommendation")
        conf = stock.get("confidence") or "medium"
        actual_quote = evening_quotes.get(code) or {}

        actual_pct = _parse_pct(
            actual_quote.get("change_pct_num")
            or actual_quote.get("change_pct")
        )
        if actual_pct is None or not rec:
            stock["result"] = {"outcome": "n/a", "label": "데이터 없음", "note": "종가 또는 투자의견 없음"}
            continue

        outcome, note = classify(rec, actual_pct)
        pred_dir = matrix_direction(rec)
        actual_dir = direction_from_pct(actual_pct)

        # Snapshot the prediction fields separately, since stock.quote will be overwritten
        stock["predicted"] = {
            "recommendation": rec,
            "news_sentiment": stock.get("news_sentiment"),
            "overnight_signal": (
                stock["overnight_signal"].get("direction")
                if isinstance(stock.get("overnight_signal"), dict)
                else stock.get("overnight_signal")
            ),
            "priced_in": stock.get("priced_in"),
            "confidence": conf,
            "price_change_pct": stock.get("quote", {}).get("change_pct_num"),
        }
        stock["result"] = {
            "outcome": outcome,
            "actual_change_pct": actual_pct,
            "predicted_direction": pred_dir,
            "actual_direction": actual_dir,
            "note": note,
        }
        # Overwrite quote with evening scrape (today's actual close).
        stock["quote"] = {**stock.get("quote", {}), **actual_quote}

        if outcome == "hit":
            hits += 1
            conf_buckets[conf][0] += 1
        elif outcome == "partial":
            partial += 1
            conf_buckets[conf][0] += 0.5
        else:
            misses += 1
        conf_buckets[conf][1] += 1

        if pred_dir and pred_dir == actual_dir:
            directional_correct += 1
        directional_total += 1

        onsig = stock.get("overnight_signal")
        onsig_dir = onsig.get("direction") if isinstance(onsig, dict) else onsig
        news_sent = stock.get("news_sentiment")

        if outcome == "miss":
            if (news_sent == "positive" and actual_dir == "down") or (news_sent == "negative" and actual_dir == "up"):
                attrib["news_misread"] += 1
            if (onsig_dir == "up" and actual_dir == "down") or (onsig_dir == "down" and actual_dir == "up"):
                attrib["overnight_misled"] += 1
            if stock.get("priced_in") is False and abs(actual_pct) < 0.5:
                attrib["priced_in_underestimated"] += 1
        elif outcome == "hit" and onsig_dir in ("up", "down") and onsig_dir == actual_dir:
            attrib["overnight_helped"] += 1

    total = hits + partial + misses
    hit_rate = (hits + 0.5 * partial) / total if total else 0
    dir_acc = directional_correct / directional_total if directional_total else 0

    def _idx_snap(key: str) -> dict:
        idx = (news.get("macro", {}).get("indices", {}) or {}).get(key) or {}
        raw = (news.get("macro", {}).get("indices", {}) or {}).get(f"{key}_change", "")
        if isinstance(idx, dict) and idx:
            return {
                "value": idx.get("value"),
                "change_abs": idx.get("change_abs"),
                "change_pct": idx.get("change_pct"),
                "direction": idx.get("direction"),
                "raw": raw,
            }
        return {"raw": raw}

    session_change = {
        "kospi":  _idx_snap("KOSPI"),
        "kosdaq": _idx_snap("KOSDAQ"),
    }
    review = {
        "generated_at": datetime.now(KST).isoformat(),
        "session_change": session_change,
        "accuracy": {
            "total": total,
            "hits": hits,
            "partial": partial,
            "misses": misses,
            "hit_rate": round(hit_rate, 3),
            "directional_accuracy": round(dir_acc, 3),
            "by_confidence": {
                k: {
                    "hits": round(v[0], 1),
                    "total": v[1],
                    "rate": round(v[0] / v[1], 3) if v[1] else 0,
                }
                for k, v in conf_buckets.items() if v[1] > 0
            },
        },
        "signal_attribution": attrib,
    }
    prediction["review"] = review
    # Update the top-level generated_at so the page header shows the review time.
    prediction["generated_at"] = review["generated_at"]

    # 20:00 NXT close overlay — accuracy above has already been computed from
    # the 15:30 KRX close, so this only affects the archived display (coffee
    # section gainers, per-stock price card). Stocks without NXT listings
    # keep their KRX close; the overlay is best-effort.
    #
    # We mirror the overlay into news.json quote fields too — render.py runs
    # after this and calls _merge_quotes_from_news which would otherwise
    # re-merge news.json's KRX close OVER our NXT overlay. Writing NXT into
    # news.json makes that merge idempotent.
    stocks_list = prediction.get("stocks") or []
    nxt_map = _fetch_nxt_closes([s.get("code", "") for s in stocks_list])
    news_stocks_by_code = {s.get("code"): s for s in (news.get("stocks") or [])}
    overlaid = 0
    for stock in stocks_list:
        entry = nxt_map.get(stock.get("code"))
        if not entry:
            continue
        quoted = _nxt_to_quote(entry)
        if not quoted:
            continue
        stock["quote"] = {**stock.get("quote", {}), **quoted}
        news_stock = news_stocks_by_code.get(stock.get("code"))
        if news_stock is not None:
            news_stock["quote"] = {**news_stock.get("quote", {}), **quoted}
        overlaid += 1
    print(f"  NXT close overlay: {overlaid}/{len(stocks_list)} stocks")

    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(prediction, ensure_ascii=False, indent=2), encoding="utf-8")
    if overlaid:
        news_path.write_text(json.dumps(news, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✓ Wrote {out_path.relative_to(ROOT)}")
    print(f"  Hits/Partial/Misses: {hits}/{partial}/{misses} (total {total})")
    print(f"  Hit rate: {hit_rate*100:.1f}% · Directional: {dir_acc*100:.1f}%")
    print(f"  By confidence: {review['accuracy']['by_confidence']}")
    print(f"  Attribution: {attrib}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
