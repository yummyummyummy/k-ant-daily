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


def _normalize(summary: dict) -> dict:
    """Fill derived fields the template relies on."""
    macro = summary.get("macro", {}) or {}
    for ind in (macro.get("indicators") or []) + (macro.get("overnight") or []):
        if "direction" not in ind:
            ind["direction"] = _infer_direction(ind.get("change"))
        _annotate_impact(ind)
    for pt in macro.get("key_points") or []:
        _annotate_impact(pt)

    for ts in summary.get("top_stories") or []:
        _annotate_impact(ts)

    for sec in summary.get("sectors") or []:
        _annotate_impact(sec)
        for pt in sec.get("key_points") or []:
            _annotate_impact(pt)

    for stock in summary.get("stocks") or []:
        rec = stock.get("recommendation")
        if rec and "recommendation_label" not in stock:
            stock["recommendation_label"] = RECOMMENDATION_LABEL.get(rec, rec)
        # backward compat: accept sentiment as alias
        if not rec and stock.get("sentiment"):
            legacy = {"positive": "buy", "negative": "sell", "neutral": "hold"}
            stock["recommendation"] = legacy.get(stock["sentiment"], "hold")
            stock["recommendation_label"] = RECOMMENDATION_LABEL[stock["recommendation"]]
        for pt in stock.get("key_points") or []:
            _annotate_impact(pt)
    return summary


def _display_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def render_report(summary: dict, base_url: str) -> tuple[str, str]:
    summary = _normalize(summary)
    date = summary.get("date") or datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{date}.html"
    canonical = f"{base_url.rstrip('/')}/{filename}"

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
        macro=summary.get("macro", {}) or {},
        sectors=summary.get("sectors", []) or [],
        stocks=summary.get("stocks", []) or [],
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

    filename, html = render_report(summary, base_url)
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
