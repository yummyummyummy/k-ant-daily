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
from markupsafe import Markup, escape

_HIGHLIGHT_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)


def _highlight_drivers(text: str | None) -> Markup:
    """Jinja filter: wrap ``**phrase**`` markers in the agent's prose with
    ``<mark class="driver">phrase</mark>`` so장중 변동성 핵심 변수 etc. get a
    visual highlighter. HTML-escapes the input first so the marker is the only
    thing that can produce tags — prevents accidental markup injection from
    summary.json content."""
    if not text:
        return Markup("")
    escaped = str(escape(text))
    highlighted = _HIGHLIGHT_RE.sub(r'<mark class="driver">\1</mark>', escaped)
    return Markup(highlighted)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATES = ROOT / "templates"
KST = timezone(timedelta(hours=9))

# Set this in config.yml later if we want. For now derive from git remote at runtime.
DEFAULT_BASE_URL = "https://yummyummyummy.github.io/k-ant-daily"


def _env() -> Environment:
    # Explicit list including `.html.j2` / `.j2` because select_autoescape()
    # only matches the final suffix — a template named `foo.html.j2` has the
    # final suffix `.j2`, not `.html`, so the default `["html","xml"]` would
    # silently leave it unescaped.
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(
            enabled_extensions=("html", "xml", "html.j2", "j2"),
            default_for_string=True,
        ),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["highlight"] = _highlight_drivers
    return env


def _render_template(template_name: str, **context: object) -> str:
    """Thin wrapper around `_env().get_template(...).render(...)` — the env
    setup and extension suffix caveats are consolidated in one place."""
    return _env().get_template(template_name).render(**context)


from labels import (
    IMPACT_LABEL, RECOMMENDATION_LABEL, OUTCOME_LABEL, STATUS_LABEL,
    SENTIMENT_LABEL, OVERNIGHT_LABEL, CONFIDENCE_LABEL, MOOD_LABEL,
    CATEGORY_LABEL, MOOD_AXES, SECTOR_EMOJI_FALLBACK,
)


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


# Heuristic impact classifier for stock news titles. Agent is supposed to
# label each item, but when it doesn't (raw Naver scrape passthrough) we
# fall back to keyword matching so the 호재/악재/중립 chip still shows up.
_POS_PATTERNS = re.compile(
    r"(상승|급등|강세|반등|신고가|최고치|돌파|호실적|실적\s*개선|영업이익\s*증가|"
    r"어닝\s*서프라이즈|상향|수주|체결|공급\s*계약|라이선스|승인|허가|특허|"
    r"자사주\s*매입|자사주\s*소각|배당\s*(인상|증가|확대)|흑자\s*전환|"
    r"수혜|성장|호재|랠리|폭등|대박|인수|인수\s*합병|M&A|골든크로스|"
    r"최대\s*실적|사상\s*최대|어닝\s*비트|목표가\s*상향|매수\s*추천|"
    r"투자의견\s*상향|긍정적|기대감|수주잔고|호조|낙관)"
)
_NEG_PATTERNS = re.compile(
    r"(하락|급락|약세|부진|적자|쇼크|저조|감소|하향|실패|철회|취소|"
    r"리스크|부담|제재|과징금|횡령|배임|소송|경고|우려|손실|위기|"
    r"낙폭|추락|불안|악재|하회|둔화|슬럼프|논란|감원|구조조정|"
    r"적자\s*전환|매도\s*추천|투자의견\s*하향|목표가\s*하향|부정적|"
    r"데드크로스|실망감|어닝\s*쇼크|실적\s*쇼크|규제|조사|경영권\s*분쟁)"
)

def _auto_impact(title: str) -> str:
    """Best-guess impact label from a headline. Returns positive / negative /
    neutral. Conservative — ambiguous titles default to neutral."""
    if not title:
        return "neutral"
    pos = bool(_POS_PATTERNS.search(title))
    neg = bool(_NEG_PATTERNS.search(title))
    if pos and not neg:
        return "positive"
    if neg and not pos:
        return "negative"
    return "neutral"


def _sparkline_path(closes: list, width: float = 80.0, height: float = 24.0) -> str:
    """Turn a sequence of closes into an SVG path string (M x,y L x,y L ...)."""
    if not closes or len(closes) < 2:
        return ""
    try:
        vals = [float(c) for c in closes if c is not None]
    except Exception:
        return ""
    if len(vals) < 2:
        return ""
    pmin, pmax = min(vals), max(vals)
    span = (pmax - pmin) or 1.0
    n = len(vals)
    pts = []
    for i, p in enumerate(vals):
        x = i * width / (n - 1)
        y = height - ((p - pmin) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")
    return "M" + " L".join(pts)


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
        for key in ("owners", "overnight_proxy", "is_etf", "leader", "sector"):
            if src.get(key) is not None and not stock.get(key):
                stock[key] = src[key]


def _merge_quotes_from_news(summary: dict, news_path: Path) -> None:
    """Pull fresh quote + overnight_signal + news + disclosures from sibling
    news.json into summary stocks by code. The agent doesn't need to echo
    these fields back — they're raw scrape data that render pulls directly."""
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
        # Stock news list — **always** overwrite from the raw 24h scrape so
        # intraday refresh runs (10-min crawl during market hours) surface new
        # articles as they appear. Agent-curated high-signal items live in
        # `key_points`; the news block is a chronological reference feed, not
        # an editorial selection.
        if src.get("news"):
            stock["news"] = list(src["news"])
        if not stock.get("disclosures") and src.get("disclosures"):
            stock["disclosures"] = list(src["disclosures"])
        # Historical price context (20-day close series + 52-week levels)
        if src.get("history"):
            stock["history"] = dict(src["history"])


def _reference_now(summary: dict) -> datetime:
    """Choose the reference instant for time-ago calculations. Prefer the
    summary's own `generated_at` so re-renders stay stable (otherwise every
    rebuild would tick time_ago forward)."""
    try:
        now = datetime.fromisoformat(summary.get("generated_at", ""))
        if now.tzinfo is None:
            now = now.replace(tzinfo=KST)
        return now
    except Exception:
        return datetime.now(KST)


def _normalize_macro(summary: dict) -> None:
    """Annotate macro.indicators/overnight/key_points with direction + labels."""
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


def _normalize_top_stories(summary: dict) -> None:
    for ts in summary.get("top_stories") or []:
        _annotate_impact(ts)
        if ts.get("category") and "category_label" not in ts:
            ts["category_label"] = CATEGORY_LABEL.get(ts["category"], ts["category"])


def _normalize_mood_dashboard(summary: dict) -> None:
    dash = summary.get("mood_dashboard")
    if not isinstance(dash, dict):
        return
    for _axis_key, m in dash.items():
        if isinstance(m, dict) and m.get("impact"):
            m["impact_label"] = MOOD_LABEL.get(m["impact"], m["impact"])


def _normalize_focus(summary: dict, now: datetime) -> None:
    focus = summary.get("focus")
    if not focus:
        return
    _annotate_impact(focus)
    status = focus.get("status") or {}
    if status:
        lvl = status.get("level")
        if lvl and "label" not in status:
            status["label"] = STATUS_LABEL.get(lvl, lvl)
        # Ship-count data isn't published daily (news-angle only), so the
        # cited article can be days old. Compute staleness so the template
        # can warn the reader explicitly instead of letting the date sit
        # silently in parentheses.
        ship = status.get("ship_count") or {}
        date_str = ship.get("date")
        today = summary.get("date") or now.date().isoformat()
        if date_str and today:
            m = re.match(r"(\d{4}-\d{2}-\d{2})", str(date_str))
            if m:
                try:
                    d1 = datetime.strptime(m.group(1), "%Y-%m-%d").date()
                    d2 = datetime.strptime(today, "%Y-%m-%d").date()
                    ship["days_ago"] = max(0, (d2 - d1).days)
                    ship["is_stale"] = ship["days_ago"] >= 2
                except ValueError:
                    pass
    # news_items: sort by published_at desc, annotate time_ago + impact_label
    items = focus.get("news_items") or []
    for n in items:
        _annotate_impact(n)
        n["time_ago"] = _time_ago(n.get("published_at"), now)
    items.sort(key=lambda n: n.get("published_at") or "", reverse=True)
    focus["news_items"] = items
    for pt in focus.get("key_points") or []:
        _annotate_impact(pt)


def _normalize_sectors(summary: dict, now: datetime) -> None:
    for sec in summary.get("sectors") or []:
        _annotate_impact(sec)
        # Emoji fallback if agent didn't supply one.
        if not sec.get("emoji") and sec.get("name"):
            for key, emj in SECTOR_EMOJI_FALLBACK.items():
                if key in sec["name"]:
                    sec["emoji"] = emj
                    break
        # Accept either `news` (new schema) or `key_points` (legacy). Coerce
        # legacy items into news shape: title/note/source/impact/published_at.
        news_items = sec.get("news")
        if news_items is None:
            news_items = []
            for kp in sec.get("key_points") or []:
                item = {
                    "title": kp.get("point") or "",
                    "note":  kp.get("detail") or "",
                    "impact": kp.get("impact"),
                    "published_at": kp.get("published_at"),
                    "sources": kp.get("sources") or [],
                }
                # If the legacy item had exactly one source, expose it as `source`
                # too so the new template's 'title · time · source' line works.
                if len(item["sources"]) == 1:
                    item["source"] = item["sources"][0]
                news_items.append(item)
        for n in news_items:
            _annotate_impact(n)
            n["time_ago"] = _time_ago(n.get("published_at"), now)
        news_items.sort(key=lambda n: n.get("published_at") or "0", reverse=True)
        sec["news"] = news_items
        sec.pop("key_points", None)  # consolidate on `news`


def _normalize_stock_quote(stock: dict, *, pre_market: bool = False) -> None:
    """Derive price_display, price_change_* from stock.quote.

    When pre_market=True (07:30 baseline render, no review yet), we force
    pct=0 / abs=— on every card because Naver's item endpoint at 07:30 still
    returns yesterday's intraday delta — showing that as 'today's move' is
    misleading. The client then overlays live values during 08:00-20:00;
    the 20:10 review re-renders with pre_market=False so 20:00 NXT close
    (plus 15:30 KRX close for NXT-uncovered names) sticks in the archive."""
    quote = stock.get("quote") or {}
    pct_num = quote.get("change_pct_num")
    if pct_num is None and quote.get("change_pct"):
        try:
            pct_num = float(str(quote["change_pct"]).replace("%", "").replace("+", ""))
        except ValueError:
            pct_num = None

    change_abs_raw = quote.get("change")

    if pre_market:
        pct_num = 0.0
        change_abs_raw = 0
    elif not pct_num:
        pct_num = 0.0
        change_abs_raw = 0

    if pct_num is not None:
        stock["price_change_pct_num"] = pct_num
        stock["price_direction"] = "up" if pct_num > 0 else ("down" if pct_num < 0 else "flat")
        sign = "+" if pct_num > 0 else ""
        stock["price_change_display"] = f"{sign}{pct_num:.2f}%"
    if quote.get("price"):
        stock["price_display"] = quote["price"]
    # Always reset abs-change display — summary.json persists prior renders,
    # and a stale "▲ 32,000" survives across re-renders if we only overwrite
    # on truthy raw values. Treat falsy or numeric-zero as explicit no-move.
    raw = str(change_abs_raw).strip() if change_abs_raw not in (None, "") else ""
    try:
        bare_num = float(raw.lstrip("+-").replace(",", "")) if raw else 0
    except ValueError:
        bare_num = None
    if not raw or bare_num == 0:
        stock["price_change_abs_display"] = "—"
    else:
        direction = stock.get("price_direction") or quote.get("direction") or ""
        bare = raw.lstrip("+-")
        if direction == "up":
            stock["price_change_abs_display"] = f"▲ {bare}"
        elif direction == "down":
            stock["price_change_abs_display"] = f"▼ {bare}"
        else:
            stock["price_change_abs_display"] = raw


def _normalize_volume_signal(stock: dict) -> None:
    """Derive volume_ratio = today's cumulative volume / 20-day average.

    Triggers the 🚨 배지 at the template level when the ratio clears
    VOLUME_SPIKE_THRESHOLD (2.0×) — a proxy for intraday speculative inflow
    that exceeds normal trading rhythm. compute_review.py reads the same
    ratio at end-of-day to populate the speculative_flow attribution."""
    vol_today = (stock.get("quote") or {}).get("volume")
    vol_avg = (stock.get("history") or {}).get("volume_20d_avg")
    if not vol_today or not vol_avg or vol_avg <= 0:
        return
    ratio = vol_today / vol_avg
    stock["volume_ratio"] = round(ratio, 2)
    stock["volume_spike"] = ratio >= 2.0


def _normalize_stock_signals(stock: dict) -> None:
    """Attach human-readable labels for the decision signals the template shows
    in the confidence/rationale block (뉴스 톤, 간밤, 신뢰도) and for the
    session-review outcome badge."""
    if stock.get("news_sentiment"):
        stock["news_sentiment_label"] = SENTIMENT_LABEL.get(stock["news_sentiment"], stock["news_sentiment"])
    onsig = stock.get("overnight_signal")
    if isinstance(onsig, dict) and onsig.get("direction"):
        onsig["label"] = OVERNIGHT_LABEL.get(onsig["direction"], onsig["direction"])
    if stock.get("confidence"):
        stock["confidence_label"] = CONFIDENCE_LABEL.get(stock["confidence"], stock["confidence"])
    result = stock.get("result")
    if isinstance(result, dict) and result.get("outcome"):
        result["label"] = OUTCOME_LABEL.get(result["outcome"], result["outcome"])


def _normalize_stock_news(stock: dict, now: datetime) -> None:
    """Filter stock news to the last 24h + annotate time_ago/impact. The 24h
    cutoff prevents Naver's "top-10" stale articles (sometimes weeks old) from
    crowding the trader's morning scan. Also caches the most recent news
    timestamp (`latest_news_at` / `latest_news_ago`) so the card header can
    show "n분 전" before the user expands the card."""
    stock_news = stock.get("news") or []
    cutoff_24h = now - timedelta(hours=24)
    kept = []
    latest_dt: datetime | None = None
    for n in stock_news:
        # Uniform shape: treat `date` as the published timestamp.
        if "published_at" not in n and n.get("date"):
            n["published_at"] = n["date"]
        dt = _parse_published(n.get("published_at"))
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo or KST)
        if dt < cutoff_24h:
            continue
        n["time_ago"] = _time_ago(n.get("published_at"), now)
        if "url" not in n and n.get("link"):
            n["url"] = n["link"]
        if not n.get("impact"):
            n["impact"] = _auto_impact(n.get("title", ""))
        _annotate_impact(n)
        kept.append(n)
        if latest_dt is None or dt > latest_dt:
            latest_dt = dt
    # Sort most recent first so the card's news list shows newest at top.
    kept.sort(key=lambda n: n.get("published_at") or "", reverse=True)
    stock["news"] = kept
    stock["news_count"] = len(kept)
    if latest_dt is not None:
        stock["latest_news_at"] = latest_dt.isoformat()
        stock["latest_news_ago"] = _time_ago(stock["latest_news_at"], now)


def _normalize_stocks(summary: dict, now: datetime) -> None:
    # Pre-market = before today's session has produced a review. Once review
    # (compute_review.py) runs at 20:10, stock.quote carries real KRX 15:30
    # close / NXT 20:00 overlay and we should NOT zero them out.
    pre_market = not summary.get("review")
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

        _normalize_stock_quote(stock, pre_market=pre_market)
        _normalize_volume_signal(stock)
        _normalize_stock_signals(stock)

        # Forward-looking direction + one-line outlook for the card summary row.
        dir_meta = DIRECTION_META.get(stock.get("recommendation"), DIRECTION_META["hold"])
        stock["direction_arrow"] = dir_meta["arrow"]
        stock["direction_label"] = dir_meta["label"]
        stock["direction_cls"]   = dir_meta["cls"]
        stock["outlook_line"]    = _outlook_line(stock.get("rationale"))

        pts = stock.get("key_points") or []
        for pt in pts:
            _annotate_impact(pt)
            pt["time_ago"] = _time_ago(pt.get("published_at"), now)
        pts.sort(key=lambda p: p.get("published_at") or "0", reverse=True)
        stock["key_points"] = pts

        _normalize_stock_news(stock, now)

        # Price-context block (sparkline + 52w range) if history is available.
        hist = stock.get("history") or {}
        closes = hist.get("closes_20d") or []
        if closes:
            hist["sparkline_path"] = _sparkline_path(closes, width=80, height=24)
            hist["sparkline_direction"] = (
                "up" if closes[-1] > closes[0]
                else "down" if closes[-1] < closes[0]
                else "flat"
            )
            stock["history"] = hist


def _normalize(summary: dict) -> dict:
    """Fill derived fields the template relies on — labels, time_ago, price
    display, sparklines, etc. Dispatches to concern-focused sub-functions;
    order matters only for stock-level (needs rec first, signals next)."""
    now = _reference_now(summary)
    _normalize_macro(summary)
    _normalize_top_stories(summary)
    _normalize_mood_dashboard(summary)
    _normalize_focus(summary, now)
    _normalize_sectors(summary, now)
    _normalize_stocks(summary, now)
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
    """One card per friend-stock for the coffee banner. Primary sort: today's
    change% desc. Tiebreak: name 가나다순 — needed because pre-market all
    pcts are 0 and we still want a stable, readable order."""
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
    out.sort(key=lambda c: (-c["pct"], c["name"]))
    return out


def _display_time(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso


def render_report(summary: dict, base_url: str, news_path: Path | None = None) -> tuple[str, str]:
    _merge_config_from_stocks_yml(summary, ROOT / "stocks.yml")
    # Resolve the actual news.json path once, with a fallback to .tmp/news.json
    # so re-rendering from docs/*.summary.json (where the sibling doesn't
    # exist) still merges fresh quote + news data.
    resolved_news_path = None
    for candidate in (news_path, ROOT / ".tmp" / "news.json"):
        if candidate and candidate.exists():
            resolved_news_path = candidate
            break
    if resolved_news_path is not None:
        _merge_quotes_from_news(summary, resolved_news_path)
    news_data = {}
    if resolved_news_path is not None:
        try:
            news_data = json.loads(resolved_news_path.read_text(encoding="utf-8"))
        except Exception:
            news_data = {}
    summary = _normalize(summary)
    date = summary.get("date") or datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{date}.html"
    canonical = f"{base_url.rstrip('/')}/{filename}"

    stocks = summary.get("stocks", []) or []
    # Order owners: designated leader first, then the remaining names in
    # 가나다 (unicode) order. This feeds both the coffee friend-card primary
    # chip and the stock-card summary row's primary chip, so the "대장"
    # name consistently appears first everywhere.
    for s in stocks:
        owners = s.get("owners") or []
        if not owners:
            continue
        leader = s.get("leader")
        if leader and leader in owners:
            rest = sorted(o for o in owners if o != leader)
            s["owners"] = [leader, *rest]
        else:
            s["owners"] = sorted(owners)
    # Display order within each recommendation group: stocks with the most
    # recent news surface first (the trader's "what moved in the last hour?"
    # scan). Stocks without news go to the bottom, ordered by 가나다. ISO
    # timestamp strings compare lexically so reverse sort = newest first.
    with_news    = [s for s in stocks if s.get("latest_news_at")]
    without_news = [s for s in stocks if not s.get("latest_news_at")]
    with_news.sort(key=lambda s: s["latest_news_at"], reverse=True)
    without_news.sort(key=lambda s: s.get("name", ""))
    stocks_display = with_news + without_news

    # Group by recommendation — action-first layout. Each group shown as its
    # own block with a header; within a group we keep the news-desc order.
    # Groups with 0 stocks are suppressed by the template.
    stock_groups = _group_stocks_by_recommendation(stocks_display)
    # Section-top aggregate view: "친구들 포트폴리오 오늘 전망" — answers
    # "대체로 오르는 날 vs 내리는 날?" before the reader scans individual cards.
    portfolio_snapshot = _portfolio_snapshot(stocks_display)

    html = _render_template(
        "report.html.j2",
        date=date,
        tldr=summary.get("tldr", ""),
        headline=summary.get("headline", ""),
        generated_at=summary.get("generated_at", ""),
        generated_at_display=_display_time(summary.get("generated_at", "")),
        base_url=base_url,
        canonical_url=canonical,
        top_stories=summary.get("top_stories", []) or [],
        focus=summary.get("focus") or None,
        macro=summary.get("macro", {}) or {},
        sectors=summary.get("sectors", []) or [],
        stocks=stocks_display,
        stock_groups=stock_groups,
        portfolio_snapshot=portfolio_snapshot,
        coffee_buyer=_coffee_buyer(stocks),
        friends_overview=_friends_overview(stocks),
        review=summary.get("review") or None,
        ticker=_build_ticker(news_data),
        mood_dashboard=summary.get("mood_dashboard") or None,
        mood_axes=MOOD_AXES,
    )
    return filename, html


# Metadata for the 📈 종목별 grouping view. Order = display order (top→down).
# Group labels are forward-looking (direction-oriented) — they mirror the
# DIRECTION_META labels so the group header serves as the per-card direction
# indicator; individual cards no longer need a separate direction badge.
# Directional groups (상승/하락) come first since the reader cares about
# action-worthy stocks most; `hold` is the tail bucket — same-day 관망 is
# less scannable and typically the largest group.
STOCK_GROUP_META = [
    {"key": "strong_buy",  "label": "강한 상승 기대", "emoji": "🔥", "accent": "strong_buy"},
    {"key": "buy",         "label": "상승 기대",     "emoji": "🟢", "accent": "buy"},
    {"key": "sell",        "label": "하락 경계",     "emoji": "🔴", "accent": "sell"},
    {"key": "strong_sell", "label": "강한 하락 경계", "emoji": "⛔", "accent": "strong_sell"},
    {"key": "hold",        "label": "관망",          "emoji": "🟡", "accent": "hold"},
]

# Forward-looking direction language for the per-card chip + portfolio snapshot.
# Separate from the action-oriented label (매수/매도) above; answers "오늘 이
# 종목이 오를까?" rather than "지금 사/팔까?".
DIRECTION_META = {
    "strong_buy":  {"arrow": "↑↑", "label": "강한 상승 기대",   "cls": "up-strong"},
    "buy":         {"arrow": "↑",  "label": "상승 기대",        "cls": "up"},
    "hold":        {"arrow": "—",  "label": "관망",            "cls": "flat"},
    "sell":        {"arrow": "↓",  "label": "하락 경계",        "cls": "down"},
    "strong_sell": {"arrow": "↓↓", "label": "강한 하락 경계",   "cls": "down-strong"},
}


# Matches a sentence boundary: a period, exclamation, or question mark followed
# by whitespace OR end-of-string. Keeps the punctuation with the sentence.
_SENT_END = re.compile(r'(?<=[.!?])(\s+|$)')


def _outlook_line(rationale: str | None, max_len: int = 60) -> str:
    """Extract the per-stock 'oneline outlook' for the card summary row.
    Per the /daily-report skill convention, rationale's first sentence is
    supposed to be a ~50-char forward-looking lede; we take that and truncate
    with an ellipsis if it's longer than ``max_len``. Returns empty string if
    the rationale is missing or empty."""
    if not rationale:
        return ""
    s = str(rationale).strip()
    if not s:
        return ""
    parts = _SENT_END.split(s, maxsplit=1)
    first = parts[0].rstrip(" .!?").strip()
    if len(first) > max_len:
        first = first[: max_len - 1].rstrip() + "…"
    return first


def _portfolio_snapshot(stocks: list[dict]) -> dict:
    """Aggregate all tracked stocks into the section-top 'friends portfolio'
    snapshot: count by forward-looking direction and breakdown by sector.
    Sectors come from stocks.yml; stocks without a sector field fall into a
    '기타' bucket."""
    from collections import defaultdict

    by_direction = {"up_strong": 0, "up": 0, "flat": 0, "down": 0, "down_strong": 0}
    sector_buckets: dict[str, dict] = defaultdict(lambda: {"count": 0, "up": 0, "down": 0})
    dir_key_from_rec = {
        "strong_buy": "up_strong",
        "buy": "up",
        "hold": "flat",
        "sell": "down",
        "strong_sell": "down_strong",
    }
    for s in stocks:
        rec = s.get("recommendation") or "hold"
        dkey = dir_key_from_rec.get(rec, "flat")
        by_direction[dkey] += 1
        sector = s.get("sector") or "기타"
        sector_buckets[sector]["count"] += 1
        if dkey in ("up_strong", "up"):
            sector_buckets[sector]["up"] += 1
        elif dkey in ("down_strong", "down"):
            sector_buckets[sector]["down"] += 1
    sectors_list = sorted(
        ({"name": name, **data} for name, data in sector_buckets.items()),
        key=lambda d: (-d["count"], d["name"]),
    )
    return {
        "total": len(stocks),
        "by_direction": by_direction,
        "by_sector": sectors_list,
    }


def _group_stocks_by_recommendation(stocks: list[dict]) -> list[dict]:
    """Partition the pre-sorted stocks list into blocks keyed by recommendation.
    Returns ``[{key, label, emoji, accent, stocks: [...]}]`` in display order —
    **always all 5 STOCK_GROUP_META buckets**, even empty ones, so the client-
    side NXT adjustment code can move cards between any two groups (including
    into groups that had zero stocks at 07:30). The template hides empty
    groups via CSS `:has()` — no visual clutter, full DOM for JS.
    Unrecognized/missing recommendations fall into a trailing "기타" group."""
    buckets = {meta["key"]: [] for meta in STOCK_GROUP_META}
    other = []
    for s in stocks:
        rec = s.get("recommendation")
        if rec in buckets:
            buckets[rec].append(s)
        else:
            other.append(s)
    groups = [{**meta, "stocks": buckets[meta["key"]]} for meta in STOCK_GROUP_META]
    if other:
        groups.append({
            "key": "other", "label": "기타", "emoji": "·", "accent": "other",
            "stocks": other,
        })
    return groups


def persist_summary_artifact(summary: dict, date: str) -> Path:
    """Write the normalized summary.json alongside the HTML so the evening
    review job can read back the morning's prediction. Committed to git
    so the remote evening agent can pull it after checkout."""
    path = DOCS / f"{date}.summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _timeline_svg(records: list[dict], width: int = 680, height: int = 120) -> str:
    """Stacked bar chart — one column per day, stacking hits/partial/misses."""
    if not records:
        return ""
    pad_top, pad_bottom, pad_left, pad_right = 6, 18, 28, 6
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n = len(records)
    # Bar width with small gap between bars
    bw = max(2.0, plot_w / n * 0.78)
    step = plot_w / n
    # Y scale based on max total calls across days
    max_total = max((r.get("total") or 0) for r in records) or 1

    parts = [f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none">']
    # Y gridlines (25%, 50%, 75%, 100%)
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = pad_top + plot_h * (1 - frac)
        parts.append(f'<line class="grid-line" x1="{pad_left}" x2="{width - pad_right}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="y-label" x="{pad_left - 3}" y="{y + 3:.1f}" text-anchor="end">{int(max_total * frac)}</text>')

    # Bars
    for i, r in enumerate(records):
        hits    = r.get("hits") or 0
        partial = r.get("partial") or 0
        misses  = r.get("misses") or 0
        x = pad_left + step * i + (step - bw) / 2
        y_cursor = pad_top + plot_h  # bottom
        for val, cls in ((hits, "bar-hit"), (partial, "bar-partial"), (misses, "bar-miss")):
            if val <= 0:
                continue
            h = (val / max_total) * plot_h
            y_cursor -= h
            parts.append(f'<rect class="{cls}" x="{x:.1f}" y="{y_cursor:.1f}" width="{bw:.1f}" height="{h:.1f}"/>')
        # X label (MM/DD) — only every ~6 days to avoid crowding
        if n <= 14 or i % max(1, n // 7) == 0:
            date = r.get("date", "")
            short = date[5:] if len(date) == 10 else date
            parts.append(f'<text class="x-label" x="{x + bw/2:.1f}" y="{pad_top + plot_h + 11}" text-anchor="middle">{short}</text>')
    parts.append('</svg>')
    return "".join(parts)


def build_accuracy(base_url: str) -> str:
    """Scan every docs/*.summary.json that carries a `review` block and
    assemble a cumulative accuracy page. Rebuilt on every render — the
    computation is cheap (tens of files) and keeps the page fresh without
    a separate trigger."""
    records = []
    for p in sorted(DOCS.glob("*.summary.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        review = data.get("review")
        if not review:
            continue
        acc = review.get("accuracy") or {}
        date = data.get("date") or p.stem.replace(".summary", "")
        records.append({
            "date": date,
            "hits":    acc.get("hits") or 0,
            "partial": acc.get("partial") or 0,
            "misses":  acc.get("misses") or 0,
            "total":   acc.get("total") or 0,
            "hit_rate": acc.get("hit_rate") or 0,
            "directional_accuracy": acc.get("directional_accuracy") or 0,
            "by_confidence": acc.get("by_confidence") or {},
            "signal_attribution": review.get("signal_attribution") or {},
            "has_retro": (DOCS / "accuracy" / f"{date}.html").exists(),
        })

    # Aggregate
    total_hits    = sum(r["hits"]    for r in records)
    total_partial = sum(r["partial"] for r in records)
    total_misses  = sum(r["misses"]  for r in records)
    total_calls   = sum(r["total"]   for r in records)
    total_dir_correct = sum(round((r["directional_accuracy"] or 0) * (r["total"] or 0)) for r in records)
    totals = {
        "hits":    total_hits,
        "partial": total_partial,
        "misses":  total_misses,
        "total":   total_calls,
        "hit_rate": (total_hits + 0.5 * total_partial) / total_calls if total_calls else 0,
        "directional_accuracy": total_dir_correct / total_calls if total_calls else 0,
        "days": len(records),
    }

    # Cumulative by confidence bucket
    by_confidence = {"high": {"hits": 0, "total": 0}, "medium": {"hits": 0, "total": 0}, "low": {"hits": 0, "total": 0}}
    for r in records:
        for bucket, stat in (r.get("by_confidence") or {}).items():
            if bucket not in by_confidence:
                continue
            by_confidence[bucket]["hits"]  += stat.get("hits")  or 0
            by_confidence[bucket]["total"] += stat.get("total") or 0
    for b, s in by_confidence.items():
        s["rate"] = s["hits"] / s["total"] if s["total"] else 0

    # Cumulative signal attribution
    attrib = {}
    for r in records:
        for k, v in (r.get("signal_attribution") or {}).items():
            attrib[k] = attrib.get(k, 0) + (v or 0)
    attrib_sorted = sorted(attrib.items(), key=lambda kv: kv[1], reverse=True)

    return _render_template(
        "accuracy.html.j2",
        base_url=base_url,
        records=records,
        totals=totals,
        by_confidence=by_confidence,
        attrib_sorted=attrib_sorted,
        timeline_svg=_timeline_svg(records),
        generated_at_display=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    )


def _session_indices(session_change: dict | None) -> list[dict]:
    """Normalize review.session_change into a list[dict] with keys
    {name, value, change_abs, change_pct, direction, raw}. Handles three legacy
    shapes:
      - dict of dicts (current): {"kospi": {value, change_abs, ...}, ...}
      - dict of strings (pre-2026-04): {"kospi": "169.38 +2.72% 상승", ...}
      - missing
    The string form holds only the change (Δ), NOT the closing level — we parse
    it into change_abs/change_pct so the template can still label it clearly.
    """
    if not session_change or not isinstance(session_change, dict):
        return []
    out: list[dict] = []
    for key in ("kospi", "kosdaq"):
        entry = session_change.get(key)
        name = key.upper()
        if entry is None:
            continue
        if isinstance(entry, dict):
            out.append({
                "name": name,
                "value": entry.get("value"),
                "change_abs": entry.get("change_abs"),
                "change_pct": entry.get("change_pct"),
                "direction": entry.get("direction"),
                "raw": entry.get("raw"),
            })
            continue
        # Legacy flat string — parse "169.38 +2.72% 상승" into parts.
        s = str(entry).strip()
        if not s:
            continue
        m = re.match(r"([+-]?\s*[\d,.]+)\s+([+-]?\s*[\d.]+%)\s*(상승|하락|보합)?", s)
        if m:
            abs_raw = m.group(1).replace(" ", "")
            pct     = m.group(2).replace(" ", "")
            label   = m.group(3) or ""
            direction = {"상승": "up", "하락": "down", "보합": "flat"}.get(label, "flat")
            # abs_raw has no sign in legacy; attach sign from direction
            if direction == "down" and not abs_raw.startswith("-"):
                abs_raw = f"-{abs_raw}"
            elif direction == "up" and not abs_raw.startswith("+"):
                abs_raw = f"+{abs_raw}"
            out.append({
                "name": name, "value": None,
                "change_abs": abs_raw, "change_pct": pct,
                "direction": direction, "raw": s,
            })
        else:
            out.append({"name": name, "value": None, "change_abs": None,
                        "change_pct": None, "direction": "flat", "raw": s})
    return out


def build_accuracy_day(summary: dict, base_url: str) -> str | None:
    """Render a single-day retrospective page from a summary.json that
    carries `review`. Returns None if there is no review block yet."""
    review = summary.get("review")
    if not review:
        return None
    accuracy = review.get("accuracy") or {}
    analysis = review.get("analysis") or {}
    # Normalize stocks.analysis into a dict keyed by code for template lookup.
    if isinstance(analysis.get("stocks"), list):
        analysis["stocks"] = {entry.get("code"): entry for entry in analysis["stocks"] if entry.get("code")}

    attrib = review.get("signal_attribution") or {}
    attrib_sorted = sorted(((k, v) for k, v in attrib.items() if v), key=lambda kv: kv[1], reverse=True)

    return _render_template(
        "accuracy_day.html.j2",
        base_url=base_url,
        date=summary.get("date") or "",
        session_indices=_session_indices(review.get("session_change")),
        accuracy=accuracy,
        analysis=analysis,
        attrib_sorted=attrib_sorted,
        stocks=summary.get("stocks") or [],
        generated_at_display=datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
    )


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
        date = m.group(1)
        has_retro = (DOCS / "accuracy" / f"{date}.html").exists()
        entries.append({"date": date, "filename": p.name, "tldr": tldr, "has_retro": has_retro})

    return _render_template("archive.html.j2", entries=entries, base_url=base_url)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = {a for a in argv[1:] if a.startswith("--")}
    if not args:
        print("usage: render.py <summary.json> [base_url] [--intraday]", file=sys.stderr)
        return 2
    # `--intraday` skips the aggregate pages (archive / accuracy / per-day
    # retrospective) — those only change when the evening review runs, so
    # regenerating them on every 10-min refresh just churns timestamps.
    intraday = "--intraday" in flags
    summary_path = Path(args[0])
    base_url = args[1] if len(args) > 1 else DEFAULT_BASE_URL

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

    # index.html = MOST RECENT dated report (not necessarily the one we just
    # rendered). Prevents a backfill render for 2026-04-22 from overwriting
    # index with yesterday's content when 2026-04-23 already exists.
    index = DOCS / "index.html"
    _dated_name = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
    _latest = None
    for p in DOCS.glob("*.html"):
        m = _dated_name.match(p.name)
        if m and (_latest is None or m.group(1) > _latest[0]):
            _latest = (m.group(1), p)
    shutil.copyfile(_latest[1] if _latest else dated, index)

    if not intraday:
        # Per-day retrospective FIRST — its existence on disk drives the
        # `has_retro` flag inside build_accuracy / build_archive_index, so the
        # cumulative page correctly shows a "🔍 회고" link for today on the
        # same pass that just generated the retrospective file.
        day_html = build_accuracy_day(summary, base_url)
        if day_html:
            day_dir = DOCS / "accuracy"
            day_dir.mkdir(exist_ok=True)
            day_path = day_dir / f"{date_key}.html"
            day_path.write_text(day_html, encoding="utf-8")
            print(f"✓ Wrote {day_path.relative_to(ROOT)}")

        archive_html = build_archive_index(base_url)
        (DOCS / "archive.html").write_text(archive_html, encoding="utf-8")

        accuracy_html = build_accuracy(base_url)
        (DOCS / "accuracy.html").write_text(accuracy_html, encoding="utf-8")

    # .nojekyll for GitHub Pages (skip Jekyll processing)
    (DOCS / ".nojekyll").touch()

    print(f"✓ Wrote {dated.relative_to(ROOT)}")
    print(f"✓ Wrote {artifact.relative_to(ROOT)}")
    print(f"✓ Updated {index.relative_to(ROOT)}")
    if not intraday:
        print(f"✓ Updated archive.html + accuracy.html")
    else:
        print(f"  (intraday mode — skipping archive/accuracy regeneration)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
