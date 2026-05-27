#!/usr/bin/env python3
"""Render the calendar + holdings tracker page (and optionally the digest).

Modes:
  python render.py                  → docs/calendar.html  + docs/index.html
  python render.py --digest         → docs/digest.html  (reads .tmp/digest.json)

Reads:
  .tmp/news.json           — output of fetch_news.py
  docs/events.json         — output of scripts/build_calendar.py
  stocks.yml               — holdings master
  .tmp/digest.json         — for --digest mode (agent-written)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
TEMPLATES = ROOT / "templates"
DOCS = ROOT / "docs"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _change_class(direction: str | None) -> str:
    if direction == "up":
        return "pos"
    if direction == "down":
        return "neg"
    return "neu"


def _build_holding(stock_cfg: dict, news_entry: dict | None) -> dict:
    out = {
        "code": stock_cfg["code"],
        "name": stock_cfg["name"],
        "market": stock_cfg.get("market", ""),
        "sector": stock_cfg.get("sector", ""),
        "owners": stock_cfg.get("owners", []),
        "leader": stock_cfg.get("leader"),
        "quote": {},
        "news": [],
        "disclosures": [],
        "lead_news": None,
    }
    if not news_entry:
        return out
    q = news_entry.get("quote") or {}
    out["quote"] = {
        "price": q.get("price", ""),
        "change": q.get("change", ""),
        "change_pct": q.get("change_pct", ""),
        "direction": q.get("direction", ""),
        "cls": _change_class(q.get("direction")),
    }
    out["news"] = news_entry.get("news") or []
    out["disclosures"] = news_entry.get("disclosures") or []
    if out["news"]:
        n = out["news"][0]
        out["lead_news"] = {"title": n.get("title", ""), "url": n.get("url", "")}
    return out


def _build_macro_line(macro: dict) -> list[dict]:
    chunks: list[dict] = []
    indices = macro.get("indices") or {}
    fx = macro.get("fx") or []
    crypto = macro.get("crypto_krw") or {}

    def _index_chunk(label: str, key: str):
        item = indices.get(key)
        if not item:
            return
        val = item.get("value") or item.get("price") or ""
        chg = item.get("change_pct") or item.get("change") or ""
        cls = _change_class(item.get("direction"))
        chunks.append({"label": label, "value": val, "chg": chg, "cls": cls})

    _index_chunk("KOSPI", "kospi")
    _index_chunk("KOSDAQ", "kosdaq")
    _index_chunk("S&P 500", "sp500")
    _index_chunk("NASDAQ", "nasdaq")

    if isinstance(fx, list):
        for f in fx[:2]:
            if isinstance(f, dict):
                chunks.append({
                    "label": f.get("symbol", "FX"),
                    "value": f.get("price", ""),
                    "chg": f.get("change_pct", ""),
                    "cls": _change_class(f.get("direction")),
                })

    for ticker, info in (crypto or {}).items():
        if not isinstance(info, dict):
            continue
        label = ticker.replace("KRW-", "")
        chunks.append({
            "label": label,
            "value": info.get("price", ""),
            "chg": info.get("change_pct", ""),
            "cls": _change_class(info.get("direction")),
        })
    return chunks


def _read_optional_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_index() -> None:
    """Static router — points to calendar.html by default, digest off-hours."""
    html = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>k-ant-daily</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<link rel="canonical" href="https://yummyummyummy.github.io/k-ant-daily/calendar.html">
<style>
  body { background: #f9fafb; color: #6b7280;
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", sans-serif;
    display: flex; align-items: center; justify-content: center;
    min-height: 100vh; margin: 0; }
  @media (prefers-color-scheme: dark) {
    body { background: #0f172a; color: #94a3b8; }
  }
  .loading { font-size: 14px; }
</style>
</head>
<body>
<div class="loading">로딩 중…</div>
<script>
  const utc = Date.now() + new Date().getTimezoneOffset() * 60000;
  const kst = new Date(utc + 9 * 60 * 60000);
  const day = kst.getDay();
  const isWeekend = day === 0 || day === 6;
  const mm = kst.getHours() * 60 + kst.getMinutes();
  // 평일 23:00 ~ 다음날 07:30, 또는 주말 → digest. 그 외 → 캘린더.
  const showDigest = isWeekend || mm >= 23 * 60 || mm < 7 * 60 + 30;
  location.replace(showDigest ? "digest.html" : "calendar.html");
</script>
<noscript>
  <meta http-equiv="refresh" content="0; url=calendar.html">
  <p>JavaScript 가 비활성화돼 있어 <a href="calendar.html">캘린더</a>로 이동합니다.</p>
</noscript>
</body>
</html>
"""
    (DOCS / "index.html").write_text(html, encoding="utf-8")


def render_calendar() -> None:
    with (ROOT / "stocks.yml").open(encoding="utf-8") as f:
        stocks_cfg = yaml.safe_load(f) or {}
    news = _read_optional_json(ROOT / ".tmp" / "news.json") or {}

    news_by_code = {s["code"]: s for s in news.get("stocks", [])}
    holdings = [
        _build_holding(s, news_by_code.get(s["code"]))
        for s in stocks_cfg.get("stocks", [])
    ]
    # Sort by absolute change desc (most-moving first). No-quote stocks drop to end.
    def _sort_key(h: dict) -> tuple[int, float]:
        q = h.get("quote") or {}
        chg = q.get("change_pct", "")
        try:
            n = abs(float(str(chg).replace("%", "").replace("+", "")))
            return (0, -n)
        except (ValueError, AttributeError):
            return (1, 0.0)
    holdings.sort(key=_sort_key)

    macro_line = _build_macro_line(news.get("macro") or {})

    now = datetime.now(KST)
    today_iso = now.strftime("%Y-%m-%d")
    summary = {
        "today": now.strftime("%Y년 %m월 %d일 (%a)"),
        "today_iso": today_iso,
        "generated_label": now.strftime("%Y-%m-%d %H:%M KST 생성"),
        "macro_line": macro_line,
    }

    env = _env()
    template = env.get_template("calendar.html.j2")
    html = template.render(summary=summary, stocks=holdings)

    out = DOCS / "calendar.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ Wrote {out.relative_to(ROOT)} ({len(holdings)} holdings, {len(macro_line)} macro chunks)")

    _write_index()
    print(f"✓ Wrote {(DOCS / 'index.html').relative_to(ROOT)}")


def render_digest() -> None:
    digest = _read_optional_json(ROOT / ".tmp" / "digest.json") or {}
    now = datetime.now(KST)
    digest.setdefault("generated_at", now.isoformat())
    digest.setdefault("date", now.strftime("%Y-%m-%d"))
    digest.setdefault("title", "포스트마켓 다이제스트")
    digest.setdefault("sections", [])
    digest.setdefault("generated_label", now.strftime("%Y-%m-%d %H:%M KST 생성"))

    env = _env()
    template = env.get_template("digest.html.j2")
    html = template.render(digest=digest)
    out = DOCS / "digest.html"
    out.write_text(html, encoding="utf-8")
    print(f"✓ Wrote {out.relative_to(ROOT)} ({len(digest.get('sections', []))} sections)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--digest", action="store_true", help="Render docs/digest.html instead of calendar")
    args = ap.parse_args()
    if args.digest:
        render_digest()
    else:
        render_calendar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
