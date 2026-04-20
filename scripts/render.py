#!/usr/bin/env python3
"""Render summary JSON → HTML report.

Usage:
  python scripts/render.py .tmp/summary.json

Writes:
  docs/YYYY-MM-DD.html    (dated report)
  docs/index.html         (copy of latest)
  docs/archive.html       (list of all past reports)
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "templates"
KST = timezone(timedelta(hours=9))

# Set this in config.yml later if we want. For now derive from git remote at runtime.
DEFAULT_BASE_URL = "https://yummyummyummy.github.io/k-ant-daily"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


IMPACT_LABEL = {
    "positive": "호재",
    "negative": "악재",
    "neutral": "중립",
}

RECOMMENDATION_LABEL = {
    "strong_buy": "풀매수",
    "buy": "매수",
    "hold": "존버",
    "sell": "매도",
    "strong_sell": "풀매도",
}

STATUS_LABEL = {
    "closed": "봉쇄",
    "restricted": "제한 통행",
    "open": "통행 중",
}


def _infer_direction(change: str | None) -> str:
    if not change:
        return ""
    s = change.strip()
    if s.startswith("-") or "▼" in s or "하락" in s:
        return "down"
    if s.startswith("+") or "▲" in s or "상승" in s:
        return "up"
    return ""


def _annotate_impact(obj: dict) -> None:
    impact = obj.get("impact")
    if impact and "impact_label" not in obj:
        obj["impact_label"] = IMPACT_LABEL.get(impact, impact)


def _time_ago(iso_str: str | None, now: datetime) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo or KST)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 0:
        return "방금 전"
    if secs < 60:
        return "방금 전"
    if secs < 3600:
        return f"{secs // 60}분 전"
    if secs < 86400:
        return f"{secs // 3600}시간 전"
    days = secs // 86400
    if days < 7:
        return f"{days}일 전"
    return dt.strftime("%m/%d")


def _merge_quotes_from_news(summary: dict, news_path: Path) -> None:
    """If a sibling news.json exists, pull fresh quote data into summary stocks by code."""
    if not news_path.exists():
        return
    try:
        news = json.loads(news_path.read_text(encoding="utf-8"))
    except Exception:
        return
    by_code = {s.get("code"): s.get("quote", {}) for s in news.get("stocks") or []}
    for stock in summary.get("stocks") or []:
        src = by_code.get(stock.get("code")) or {}
        if not src:
            continue
        dst = stock.setdefault("quote", {})
        # Prefer freshly scraped values — news.json is the source of truth.
        for k, v in src.items():
            if v not in (None, ""):
                dst[k] = v


def _normalize(summary: dict) -> dict:
    """Fill derived fields the template relies on."""
    # reference "now" for time-ago calculations: prefer generated_at, fallback to system now
    try:
        now = datetime.fromisoformat(summary.get("generated_at", ""))
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
    except Exception:
        now = datetime.now(KST)

    macro = summary.get("macro", {}) or {}
    for ind in (macro.get("indicators") or []) + (macro.get("overnight") or []):
        if "direction" not in ind:
            ind["direction"] = _infer_direction(ind.get("change"))
        _annotate_impact(ind)
    for pt in macro.get("key_points") or []:
        _annotate_impact(pt)
    # overall impact for each indicator block (displayed as a badge next to the h2)
    for key in ("indicators_impact", "overnight_impact"):
        impact = macro.get(key)
        if impact:
            macro[f"{key}_label"] = IMPACT_LABEL.get(impact, impact)

    for ts in summary.get("top_stories") or []:
        _annotate_impact(ts)

    focus = summary.get("focus")
    if focus:
        _annotate_impact(focus)
        status = focus.get("status") or {}
        if status:
            lvl = status.get("level")
            if lvl and "label" not in status:
                status["label"] = STATUS_LABEL.get(lvl, lvl)
        # news_items: sort by published_at desc, annotate time_ago + impact_label
        items = focus.get("news_items") or []
        for n in items:
            _annotate_impact(n)
            n["time_ago"] = _time_ago(n.get("published_at"), now)
        items.sort(
            key=lambda n: n.get("published_at") or "",
            reverse=True,
        )
        focus["news_items"] = items
        for pt in focus.get("key_points") or []:
            _annotate_impact(pt)

    for sec in summary.get("sectors") or []:
        _annotate_impact(sec)
        for pt in sec.get("key_points") or []:
            _annotate_impact(pt)

    for stock in summary.get("stocks") or []:
        # backward-compat: accept single `owner` as `owners: [owner]`
        if stock.get("owner") and not stock.get("owners"):
            stock["owners"] = [stock["owner"]]
        rec = stock.get("recommendation")
        if rec and "recommendation_label" not in stock:
            stock["recommendation_label"] = RECOMMENDATION_LABEL.get(rec, rec)
        # backward compat: accept sentiment as alias
        if not rec and stock.get("sentiment"):
            legacy = {"positive": "buy", "negative": "sell", "neutral": "hold"}
            stock["recommendation"] = legacy.get(stock["sentiment"], "hold")
            stock["recommendation_label"] = RECOMMENDATION_LABEL[stock["recommendation"]]
        # derive quote display fields
        quote = stock.get("quote") or {}
        pct_num = quote.get("change_pct_num")
        if pct_num is None and quote.get("change_pct"):
            try:
                pct_num = float(str(quote["change_pct"]).replace("%", "").replace("+", ""))
            except ValueError:
                pct_num = None
        if pct_num is not None:
            stock["price_change_pct_num"] = pct_num
            stock["price_direction"] = "up" if pct_num > 0 else ("down" if pct_num < 0 else "flat")
            sign = "+" if pct_num > 0 else ""
            stock["price_change_display"] = f"{sign}{pct_num:.2f}%"
        # Absolute price + signed change amount (호가창 style)
        if quote.get("price"):
            stock["price_display"] = quote["price"]
        if quote.get("change"):
            direction = stock.get("price_direction") or quote.get("direction") or ""
            raw = str(quote["change"]).strip()
            # Strip any existing sign; re-sign from direction
            bare = raw.lstrip("+-")
            try:
                if float(bare.replace(",", "")) == 0:
                    stock["price_change_abs_display"] = "0"
                elif direction == "up":
                    stock["price_change_abs_display"] = f"+{bare}"
                elif direction == "down":
                    stock["price_change_abs_display"] = f"-{bare}"
                else:
                    stock["price_change_abs_display"] = raw
            except ValueError:
                stock["price_change_abs_display"] = raw
        for pt in stock.get("key_points") or []:
            _annotate_impact(pt)
    return summary


def _coffee_buyer(stocks: list[dict]) -> dict | None:
    """Return the top-gaining friend-stock (> 0%) with its owners. None if no green."""
    friend = [s for s in stocks if s.get("owners") and s.get("price_change_pct_num") is not None]
    up = [s for s in friend if s["price_change_pct_num"] > 0]
    if not up:
        return None
    up.sort(key=lambda s: s["price_change_pct_num"], reverse=True)
    top = up[0]
    return {
        "owners": top.get("owners") or [],
        "name": top["name"],
        "code": top["code"],
        "change_display": top.get("price_change_display", ""),
    }


def _friends_overview(stocks: list[dict]) -> list[dict]:
    """One card per friend-stock for the coffee banner, sorted by today's change desc."""
    out = [
        {
            "owners": s.get("owners") or [],
            "name": s["name"],
            "code": s["code"],
            "price_display": s.get("price_display", ""),
            "abs_change_display": s.get("price_change_abs_display", ""),
            "change_display": s.get("price_change_display", "-"),
            "direction": s.get("price_direction", ""),
            "pct": s.get("price_change_pct_num", 0) or 0,
        }
        for s in stocks if s.get("owners")
    ]
    out.sort(key=lambda c: c["pct"], reverse=True)
    return out


def _display_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def render_report(summary: dict, base_url: str, news_path: Path | None = None) -> tuple[str, str]:
    if news_path is not None:
        _merge_quotes_from_news(summary, news_path)
    summary = _normalize(summary)
    date = summary.get("date") or datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{date}.html"
    canonical = f"{base_url.rstrip('/')}/{filename}"

    stocks = summary.get("stocks", []) or []
    env = _env()
    tmpl = env.get_template("report.html.j2")
    html = tmpl.render(
        date=date,
        tldr=summary.get("tldr", ""),
        headline=summary.get("headline", ""),
        generated_at=summary.get("generated_at", ""),
        generated_at_display=_display_time(summary.get("generated_at", "")),
        canonical_url=canonical,
        top_stories=summary.get("top_stories", []) or [],
        focus=summary.get("focus") or None,
        macro=summary.get("macro", {}) or {},
        sectors=summary.get("sectors", []) or [],
        stocks=stocks,
        coffee_buyer=_coffee_buyer(stocks),
        friends_overview=_friends_overview(stocks),
    )
    return filename, html


def build_archive_index(base_url: str) -> str:
    entries: list[dict] = []
    pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
    for p in sorted(DOCS.glob("*.html"), reverse=True):
        m = pattern.match(p.name)
        if not m:
            continue
        tldr = ""
        try:
            text = p.read_text(encoding="utf-8")
            dm = re.search(r'<meta name="description" content="([^"]*)"', text)
            if dm:
                tldr = dm.group(1)
        except Exception:
            pass
        entries.append({"date": m.group(1), "filename": p.name, "tldr": tldr})

    env = _env()
    tmpl = env.get_template("archive.html.j2")
    return tmpl.render(entries=entries, base_url=base_url)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: render.py <summary.json> [base_url]", file=sys.stderr)
        return 2
    summary_path = Path(argv[1])
    base_url = argv[2] if len(argv) > 2 else DEFAULT_BASE_URL

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    DOCS.mkdir(exist_ok=True)

    # Auto-merge scraped quote data from sibling news.json when available.
    news_path = summary_path.parent / "news.json"
    filename, html = render_report(summary, base_url, news_path=news_path)
    dated = DOCS / filename
    dated.write_text(html, encoding="utf-8")

    index = DOCS / "index.html"
    shutil.copyfile(dated, index)

    archive_html = build_archive_index(base_url)
    (DOCS / "archive.html").write_text(archive_html, encoding="utf-8")

    # .nojekyll for GitHub Pages (skip Jekyll processing)
    (DOCS / ".nojekyll").touch()

    print(f"✓ Wrote {dated.relative_to(ROOT)}")
    print(f"✓ Updated {index.relative_to(ROOT)}")
    print(f"✓ Updated archive.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
