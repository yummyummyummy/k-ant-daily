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

import yaml
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
    "hold": "관망",
    "sell": "매도",
    "strong_sell": "풀매도",
}

OUTCOME_LABEL = {
    "hit":     "적중",
    "partial": "부분",
    "miss":    "실패",
    "n/a":     "데이터 없음",
}

STATUS_LABEL = {
    "closed": "봉쇄",
    "restricted": "제한 통행",
    "open": "통행 중",
}

SENTIMENT_LABEL = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
OVERNIGHT_LABEL = {"up": "강세", "neutral": "중립", "down": "약세"}
CONFIDENCE_LABEL = {"high": "높음", "medium": "중간", "low": "낮음"}
MOOD_LABEL = {"positive": "우호", "neutral": "혼조", "negative": "부담"}
CATEGORY_LABEL = {
    "policy":      "🏛️ 정책",
    "geopolitics": "🌏 국제",
    "macro":       "💱 거시",
    "sector":      "🏭 섹터",
    "market":      "📊 시장",
}
MOOD_AXES = [
    {"key": "policy",      "emoji": "🏛️", "name": "정책·규제"},
    {"key": "geopolitics", "emoji": "🌏", "name": "국제정세"},
    {"key": "overnight",   "emoji": "🌙", "name": "간밤 해외"},
    {"key": "sectors",     "emoji": "🏭", "name": "섹터 기류"},
    {"key": "fx_macro",    "emoji": "💱", "name": "환율·원자재"},
]


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


def _parse_published(raw: str | None) -> datetime | None:
    """Accept ISO-8601 or Naver-style 'YYYY.MM.DD HH:MM[:SS]' timestamps."""
    if not raw:
        return None
    s = str(raw).strip()
    # ISO first (covers "+09:00" etc.)
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    # Naver: '2026.04.20 15:57' or '2026.04.20 15:57:53'
    for fmt in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _time_ago(iso_str: str | None, now: datetime) -> str:
    dt = _parse_published(iso_str)
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=now.tzinfo or KST)
    delta = now - dt
    secs = int(delta.total_seconds())
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


def _merge_config_from_stocks_yml(summary: dict, yml_path: Path) -> None:
    """Backfill config-only fields from stocks.yml so the agent doesn't have
    to copy them every time.

    Agents writing summary.json sometimes drop fields that don't appear in
    the schema example (owners / overnight_proxy / is_etf). Those are pure
    configuration, not analysis output — we pull them straight from the
    source of truth instead of relying on the agent to propagate them."""
    if not yml_path.exists():
        return
    try:
        with yml_path.open(encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return
    by_code = {s.get("code"): s for s in (cfg.get("stocks") or [])}
    for stock in summary.get("stocks") or []:
        src = by_code.get(stock.get("code"))
        if not src:
            continue
        for key in ("owners", "overnight_proxy", "is_etf"):
            if src.get(key) is not None and not stock.get(key):
                stock[key] = src[key]


def _merge_quotes_from_news(summary: dict, news_path: Path) -> None:
    """Pull fresh quote + overnight_signal from sibling news.json into summary stocks by code."""
    if not news_path.exists():
        return
    try:
        news = json.loads(news_path.read_text(encoding="utf-8"))
    except Exception:
        return
    by_code = {s.get("code"): s for s in news.get("stocks") or []}
    for stock in summary.get("stocks") or []:
        src = by_code.get(stock.get("code")) or {}
        if not src:
            continue
        # Quote (price/change/pct)
        qdst = stock.setdefault("quote", {})
        for k, v in (src.get("quote") or {}).items():
            if v not in (None, ""):
                qdst[k] = v
        # Overnight signal (direction + avg_pct + proxies). Summary may override `direction`
        # via a top-level `overnight_signal: "up|neutral|down"` string; keep the proxies data.
        news_sig = src.get("overnight_signal") or {}
        existing = stock.get("overnight_signal")
        if isinstance(existing, str):
            stock["overnight_signal"] = {
                "direction": existing,
                "avg_pct": news_sig.get("avg_pct"),
                "proxies": news_sig.get("proxies") or [],
            }
        elif not existing and news_sig:
            stock["overnight_signal"] = dict(news_sig)


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
        # Legacy `change` split: treat %-bearing strings as percentage, others as absolute.
        if ind.get("change"):
            raw = str(ind["change"])
            if "%" in raw and "change_pct" not in ind:
                ind["change_pct"] = raw
            elif "%" not in raw and "change_abs" not in ind:
                ind["change_abs"] = raw
        if "direction" not in ind:
            ind["direction"] = _infer_direction(ind.get("change_pct") or ind.get("change_abs"))
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
        if ts.get("category") and "category_label" not in ts:
            ts["category_label"] = CATEGORY_LABEL.get(ts["category"], ts["category"])

    dash = summary.get("mood_dashboard")
    if isinstance(dash, dict):
        for axis_key, m in dash.items():
            if isinstance(m, dict) and m.get("impact"):
                m["impact_label"] = MOOD_LABEL.get(m["impact"], m["impact"])

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
        pts = sec.get("key_points") or []
        for pt in pts:
            _annotate_impact(pt)
            pt["time_ago"] = _time_ago(pt.get("published_at"), now)
        # newest first; points without timestamps sink to the bottom
        pts.sort(key=lambda p: p.get("published_at") or "0", reverse=True)
        sec["key_points"] = pts

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
                    stock["price_change_abs_display"] = "—"
                elif direction == "up":
                    stock["price_change_abs_display"] = f"▲ {bare}"
                elif direction == "down":
                    stock["price_change_abs_display"] = f"▼ {bare}"
                else:
                    stock["price_change_abs_display"] = raw
            except ValueError:
                stock["price_change_abs_display"] = raw
        # decision-signal labels (news_sentiment, overnight_signal, confidence)
        if stock.get("news_sentiment"):
            stock["news_sentiment_label"] = SENTIMENT_LABEL.get(stock["news_sentiment"], stock["news_sentiment"])
        onsig = stock.get("overnight_signal")
        if isinstance(onsig, dict) and onsig.get("direction"):
            onsig["label"] = OVERNIGHT_LABEL.get(onsig["direction"], onsig["direction"])
        if stock.get("confidence"):
            stock["confidence_label"] = CONFIDENCE_LABEL.get(stock["confidence"], stock["confidence"])
        # session-review result label
        result = stock.get("result")
        if isinstance(result, dict) and result.get("outcome"):
            result["label"] = OUTCOME_LABEL.get(result["outcome"], result["outcome"])
        pts = stock.get("key_points") or []
        for pt in pts:
            _annotate_impact(pt)
            pt["time_ago"] = _time_ago(pt.get("published_at"), now)
        pts.sort(key=lambda p: p.get("published_at") or "0", reverse=True)
        stock["key_points"] = pts
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


def _build_ticker(news: dict) -> list[dict]:
    """Initial (server-rendered) ticker-strip data from the latest news.json
    scrape. The Worker refreshes these live on the client, but the values
    need to be populated on first paint.
    """
    if not news:
        return []
    macro = news.get("macro") or {}
    indices = macro.get("indices") or {}
    fx = macro.get("fx") or []
    crypto = macro.get("crypto_krw") or {}

    def entry(key, name, value="", change_abs="", change_pct=None, direction=""):
        return {
            "key": key, "name": name, "value": value,
            "change_abs": change_abs, "change_pct": change_pct, "direction": direction,
        }

    out: list[dict] = []

    # KOSPI / KOSDAQ from structured indices
    for code, label in (("KOSPI", "KOSPI"), ("KOSDAQ", "KOSDAQ")):
        info = indices.get(code) or {}
        if isinstance(info, dict) and info.get("value"):
            out.append(entry(code, label,
                             value=info.get("value", ""),
                             change_abs=info.get("change_abs", ""),
                             change_pct=info.get("change_pct", ""),
                             direction=info.get("direction", "")))

    # USD/KRW from fx list. fetch_fx returns 'name': '미국 USD'.
    usd = next((f for f in fx if "USD" in (f.get("name") or "")), None)
    if usd:
        change = str(usd.get("change", "")).strip()
        # fx scrape gives absolute change unsigned; no reliable direction from scrape.
        # Leave direction "" so UI renders neutral. Live poll will supply proper direction.
        out.append(entry("USDKRW", "USD/KRW",
                         value=usd.get("value", ""),
                         change_abs=change, change_pct=None, direction=""))

    # BTC / ETH from Upbit snapshot
    for key, market, label in (("BTC", "KRW-BTC", "BTC"), ("ETH", "KRW-ETH", "ETH")):
        info = crypto.get(market) or {}
        if info.get("value"):
            out.append(entry(key, label,
                             value=info.get("value", ""),
                             change_abs=info.get("change_abs", ""),
                             change_pct=info.get("change_pct", ""),
                             direction=info.get("direction", "")))

    return out


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
    _merge_config_from_stocks_yml(summary, ROOT / "stocks.yml")
    if news_path is not None:
        _merge_quotes_from_news(summary, news_path)
    # Load news.json for the ticker's initial server-render values. Try the
    # provided path first (sibling of summary.json), then the conventional
    # .tmp/news.json fallback so re-rendering from docs/*.summary.json works.
    news_data = {}
    for candidate in (news_path, ROOT / ".tmp" / "news.json"):
        if candidate and candidate.exists():
            try:
                news_data = json.loads(candidate.read_text(encoding="utf-8"))
                break
            except Exception:
                continue
    summary = _normalize(summary)
    date = summary.get("date") or datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{date}.html"
    canonical = f"{base_url.rstrip('/')}/{filename}"

    stocks = summary.get("stocks", []) or []
    # Alphabetize owners on each stock once so both the card summary row and
    # the coffee friend-cards render them in the same order.
    for s in stocks:
        if s.get("owners"):
            s["owners"] = sorted(s["owners"])
    # Display order for the 📈 종목별 section: alphabetical (가나다 순).
    # Leaves summary["stocks"] untouched for any downstream consumer.
    stocks_display = sorted(stocks, key=lambda s: s.get("name", ""))

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
        stocks=stocks_display,
        coffee_buyer=_coffee_buyer(stocks),
        friends_overview=_friends_overview(stocks),
        review=summary.get("review") or None,
        ticker=_build_ticker(news_data),
        mood_dashboard=summary.get("mood_dashboard") or None,
        mood_axes=MOOD_AXES,
    )
    return filename, html


def persist_summary_artifact(summary: dict, date: str) -> Path:
    """Write the normalized summary.json alongside the HTML so the evening
    review job can read back the morning's prediction. Committed to git
    so the remote evening agent can pull it after checkout."""
    path = DOCS / f"{date}.summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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

    # Persist the normalized summary (with any review overlay) for re-use.
    date_key = filename.removesuffix(".html")
    artifact = persist_summary_artifact(summary, date_key)

    index = DOCS / "index.html"
    shutil.copyfile(dated, index)

    archive_html = build_archive_index(base_url)
    (DOCS / "archive.html").write_text(archive_html, encoding="utf-8")

    # .nojekyll for GitHub Pages (skip Jekyll processing)
    (DOCS / ".nojekyll").touch()

    print(f"✓ Wrote {dated.relative_to(ROOT)}")
    print(f"✓ Wrote {artifact.relative_to(ROOT)}")
    print(f"✓ Updated {index.relative_to(ROOT)}")
    print(f"✓ Updated archive.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
