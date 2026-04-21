#!/usr/bin/env python3
"""Fetch raw news data for configured stocks and macro context.

Writes .tmp/news.json with the raw material for Claude to summarize.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def _get(url: str, referer: str | None = None) -> BeautifulSoup:
    headers = {"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}
    if referer:
        headers["Referer"] = referer
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    # Naver serves news endpoints as EUC-KR without explicit charset header;
    # main.naver and some others are UTF-8 with explicit header. Trust header if present.
    ct = r.headers.get("content-type", "").lower()
    if "charset" not in ct:
        r.encoding = "euc-kr"
    return BeautifulSoup(r.text, "html.parser")


def _abs_naver_link(href: str) -> str:
    # Desktop finance.naver.com article URLs drop their query on mobile and
    # land on the news list. Rewrite both /item/news_read and /news/news_read
    # to the universal n.news.naver.com path that works on both platforms.
    if "news_read" in href:
        office = re.search(r"office_id=(\d+)", href)
        article = re.search(r"article_id=(\d+)", href)
        if office and article:
            return f"https://n.news.naver.com/mnews/article/{office.group(1)}/{article.group(1)}"
    if href.startswith("/"):
        return "https://finance.naver.com" + href
    return href


def fetch_stock_quote(code: str) -> dict:
    """Current price & change for a stock from Naver Finance main page."""
    url = f"https://finance.naver.com/item/main.naver?code={code}"
    soup = _get(url)
    out: dict = {}
    # Current price block: div.today
    today = soup.select_one("div.today")
    if not today:
        return out
    now = today.select_one("p.no_today .blind")
    if now:
        out["price"] = now.get_text(strip=True)
    exday = today.select_one("p.no_exday")
    if exday:
        # Two spans: absolute change and percent change, each with .blind
        blinds = [b.get_text(strip=True) for b in exday.select("em .blind, span .blind")]
        # Direction from class (up/down) on the first em
        em = exday.select_one("em")
        direction = ""
        if em:
            cls = " ".join(em.get("class") or [])
            if "up" in cls:
                direction = "up"
            elif "down" in cls:
                direction = "down"
        if blinds:
            out["change"] = blinds[0] if len(blinds) >= 1 else ""
            pct = blinds[1] if len(blinds) >= 2 else ""
            if pct:
                sign = "-" if direction == "down" else "+" if direction == "up" else ""
                out["change_pct"] = f"{sign}{pct}"
                try:
                    out["change_pct_num"] = float(pct.replace("%", "")) * (-1 if direction == "down" else 1)
                except ValueError:
                    pass
            out["direction"] = direction
    return out


def fetch_stock_news(code: str, limit: int = 10) -> list[dict]:
    """Recent news articles for a stock from Naver Finance."""
    url = f"https://finance.naver.com/item/news_news.naver?code={code}&page=1&sm=title_entity_id.basic&clusterId="
    referer = f"https://finance.naver.com/item/main.naver?code={code}"
    soup = _get(url, referer=referer)

    items: list[dict] = []
    for tr in soup.select("table.type5 tbody tr"):
        # Skip cluster-related rows and separators
        if "relation_lst" in (tr.get("class") or []):
            continue
        title_a = tr.select_one("td.title a.tit")
        info_td = tr.select_one("td.info")
        date_td = tr.select_one("td.date")
        if not title_a:
            continue
        items.append(
            {
                "title": title_a.get_text(strip=True),
                "link": _abs_naver_link(title_a.get("href", "")),
                "source": info_td.get_text(strip=True) if info_td else "",
                "date": date_td.get_text(strip=True) if date_td else "",
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_stock_disclosures(code: str, limit: int = 5) -> list[dict]:
    """Recent disclosures (공시) for a stock from Naver Finance."""
    url = f"https://finance.naver.com/item/news_notice.naver?code={code}"
    referer = f"https://finance.naver.com/item/main.naver?code={code}"
    soup = _get(url, referer=referer)

    items: list[dict] = []
    for td in soup.select("td.title"):
        a = td.select_one("a.tit")
        if not a:
            continue
        date_td = td.find_next_sibling("td", class_="date")
        href = a.get("href", "")
        if href.startswith("/"):
            href = "https://finance.naver.com" + href
        items.append(
            {
                "title": a.get_text(strip=True),
                "link": href,
                "date": date_td.get_text(strip=True) if date_td else "",
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_macro_news(limit: int = 15) -> list[dict]:
    """Macro/market news from Naver Finance main news feed."""
    url = "https://finance.naver.com/news/mainnews.naver"
    soup = _get(url)

    items: list[dict] = []
    for li in soup.select("li.block1"):
        subj = li.select_one("dd.articleSubject a") or li.select_one("dt a")
        summ = li.select_one("dd.articleSummary")
        if not subj:
            continue
        href = _abs_naver_link(subj.get("href", ""))
        source = ""
        date = ""
        if summ:
            press = summ.select_one(".press")
            wdate = summ.select_one(".wdate")
            source = press.get_text(strip=True) if press else ""
            date = wdate.get_text(strip=True) if wdate else ""
        summary_text = ""
        if summ:
            for s in summ.select(".press, .wdate, .source"):
                s.extract()
            summary_text = summ.get_text(" ", strip=True)
        items.append(
            {
                "title": subj.get_text(strip=True),
                "link": href,
                "source": source,
                "date": date,
                "summary": summary_text,
            }
        )
        if len(items) >= limit:
            break
    return items


def _parse_index_change(raw: str) -> dict:
    """Parse '27.17 +0.44% 상승' → {abs, pct, direction}.

    Naver formats: '<abs> <pct_with_sign> 상승|하락|보합'.
    Abs is unsigned in the raw; we re-sign it based on the rise/fall label."""
    parts = raw.split()
    if len(parts) < 3:
        return {"abs": "", "pct": "", "direction": "flat"}
    raw_abs, raw_pct, rise_fall = parts[0], parts[1], parts[2]
    if rise_fall == "상승":
        direction, sign = "up", "+"
    elif rise_fall == "하락":
        direction, sign = "down", "-"
    else:
        direction, sign = "flat", ""
    return {
        "abs": f"{sign}{raw_abs}" if sign else raw_abs,
        "pct": raw_pct,  # already signed
        "direction": direction,
    }


def fetch_market_indices() -> dict:
    """KOSPI / KOSDAQ / KOSPI200 latest values from Naver main sise page.

    Returns structured entries:
      {"KOSPI":    {"value": "6,219.09", "change_abs": "+27.17",
                   "change_pct": "+0.44%", "direction": "up"},
       "KOSDAQ":   {...}, "KOSPI200": {...}}

    Also keeps the legacy flat `<NAME>_change` string for backward compat."""
    soup = _get("https://finance.naver.com/sise/")
    result: dict = {}
    mapping = [
        ("KOSPI",    "#KOSPI_now",  "#KOSPI_change"),
        ("KOSDAQ",   "#KOSDAQ_now", "#KOSDAQ_change"),
        ("KOSPI200", "#KPI200_now", "#KPI200_change"),
    ]
    for name, val_sel, chg_sel in mapping:
        val_el = soup.select_one(val_sel)
        chg_el = soup.select_one(chg_sel)
        if not val_el:
            continue
        value = val_el.get_text(" ", strip=True)
        raw_change = chg_el.get_text(" ", strip=True) if chg_el else ""
        parsed = _parse_index_change(raw_change) if raw_change else {"abs": "", "pct": "", "direction": "flat"}
        result[name] = {
            "value": value,
            "change_abs": parsed["abs"],
            "change_pct": parsed["pct"],
            "direction": parsed["direction"],
        }
        # Legacy keys — kept so existing summary.json authors that referenced them don't break.
        result[f"{name}_change"] = raw_change
    return result


def fetch_fx() -> dict:
    """Key FX rates (USD/KRW etc.) from Naver."""
    soup = _get("https://finance.naver.com/marketindex/")
    ex = soup.select("ul#exchangeList li")
    rates = []
    for li in ex[:4]:
        name = li.select_one("h3.h_lst span.blind")
        value = li.select_one("span.value")
        change = li.select_one("span.change")
        if name and value:
            rates.append(
                {
                    "name": name.get_text(strip=True),
                    "value": value.get_text(strip=True),
                    "change": change.get_text(strip=True) if change else "",
                }
            )
    return {"fx": rates}


def fetch_proxy_changes(tickers: list[str]) -> dict[str, float]:
    """Last-session % change for each ticker via yfinance (cached-once)."""
    import yfinance as yf
    out: dict[str, float] = {}
    for sym in tickers:
        try:
            h = yf.Ticker(sym).history(period="5d", auto_adjust=False)
            if len(h) < 2:
                continue
            prev = float(h.iloc[-2]["Close"])
            last = float(h.iloc[-1]["Close"])
            if prev:
                out[sym] = (last - prev) / prev * 100
        except Exception as e:
            print(f"[warn] proxy {sym}: {e}", file=sys.stderr)
    return out


def compute_overnight_signal(proxies: list[str], changes: dict[str, float]) -> dict:
    """Average proxy % change → direction bucket."""
    vals = [changes[p] for p in proxies if p in changes]
    if not vals:
        return {"direction": "", "avg_pct": None, "proxies": []}
    avg = sum(vals) / len(vals)
    if avg > 0.7:
        direction = "up"
    elif avg < -0.7:
        direction = "down"
    else:
        direction = "neutral"
    return {
        "direction": direction,
        "avg_pct": round(avg, 2),
        "proxies": [{"symbol": p, "change_pct": round(changes[p], 2)} for p in proxies if p in changes],
    }


def fetch_stock_history(code: str, market: str) -> dict:
    """20-day close series + 52-week high/low for a Korean stock.

    yfinance suffix: .KS for KOSPI, .KQ for KOSDAQ.
    Returns {} on failure so callers can skip the 가격 맥락 block gracefully.
    """
    import yfinance as yf

    primary_suffix = ".KS" if (market or "").upper() == "KOSPI" else ".KQ"
    # yfinance occasionally has a Korean stock under the opposite exchange
    # (e.g. 034230 파라다이스 is KOSDAQ but yfinance serves it as .KS).
    # Try the stocks.yml-declared market first, then the other.
    fallback = ".KQ" if primary_suffix == ".KS" else ".KS"
    h = None
    symbol = f"{code}{primary_suffix}"
    for suffix in (primary_suffix, fallback):
        try:
            cand = yf.Ticker(f"{code}{suffix}").history(period="1y", auto_adjust=False)
        except Exception:
            cand = None
        if cand is not None and len(cand) >= 2:
            symbol = f"{code}{suffix}"
            h = cand
            break

    if h is None or len(h) < 2:
        return {}

    closes = h["Close"].tolist()
    last20 = closes[-20:]
    high_52w = float(h["High"].max()) if not h.empty else None
    low_52w  = float(h["Low"].min()) if not h.empty else None
    last_close = float(closes[-1]) if closes else None

    # 20-day change %: compare last close to first close of the last-20 window.
    change_20d_pct = None
    if len(last20) >= 2 and last20[0]:
        change_20d_pct = round((last20[-1] - last20[0]) / last20[0] * 100, 2)

    # Position within 52w range (0% = at low, 100% = at high).
    pos_52w_pct = None
    if last_close is not None and high_52w is not None and low_52w is not None and high_52w > low_52w:
        pos_52w_pct = round((last_close - low_52w) / (high_52w - low_52w) * 100, 1)

    from_high_pct = None
    if last_close is not None and high_52w:
        from_high_pct = round((last_close - high_52w) / high_52w * 100, 2)

    return {
        "symbol": symbol,
        "closes_20d": [round(float(c), 2) for c in last20],
        "fifty_two_week_high": round(high_52w, 2) if high_52w else None,
        "fifty_two_week_low":  round(low_52w, 2) if low_52w else None,
        "last_close": round(last_close, 2) if last_close else None,
        "change_20d_pct": change_20d_pct,
        "pos_52w_pct": pos_52w_pct,
        "from_high_pct": from_high_pct,
        "as_of": str(h.index[-1].date()),
    }


def fetch_upbit_tickers(markets: list[str]) -> dict:
    """KRW-denominated crypto quotes from Upbit public API.

    Used for the marquee's BTC/ETH initial server render so the page
    isn't blank before the first client poll.
    """
    try:
        r = requests.get(
            "https://api.upbit.com/v1/ticker",
            params={"markets": ",".join(markets)},
            headers={"User-Agent": UA, "Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        arr = r.json()
    except Exception as e:
        print(f"[warn] upbit fetch failed: {e}", file=sys.stderr)
        return {}

    out: dict = {}
    for d in arr:
        market = d.get("market")
        if not market:
            continue
        direction = {"RISE": "up", "FALL": "down"}.get(d.get("change"), "flat")
        price = float(d.get("trade_price") or 0)
        abs_change = float(d.get("signed_change_price") or 0)
        pct = float(d.get("signed_change_rate") or 0) * 100
        abs_sign = "+" if abs_change > 0 else "-" if abs_change < 0 else ""
        pct_sign = "+" if pct > 0 else ""
        out[market] = {
            "value": f"{round(price):,}",
            "change_abs": f"{abs_sign}{abs(round(abs_change)):,}",
            "change_pct": f"{pct_sign}{pct:.2f}%",
            "direction": direction,
        }
    return out


def fetch_overnight_markets() -> dict:
    """간밤 해외 시장 (US indices, VIX, commodities, dollar index) via yfinance."""
    import yfinance as yf  # lazy — slow import

    tickers = [
        ("^GSPC", "S&P 500"),
        ("^DJI", "다우존스"),
        ("^IXIC", "나스닥"),
        ("^VIX", "VIX"),
        ("^KS200", "KOSPI200 (종가)"),
        ("CL=F", "WTI 원유"),
        ("GC=F", "금"),
        ("BTC-USD", "비트코인"),
        ("DX-Y.NYB", "달러인덱스"),
    ]
    out: list[dict] = []
    for sym, label in tickers:
        try:
            h = yf.Ticker(sym).history(period="5d", auto_adjust=False)
            if len(h) < 2:
                continue
            prev = float(h.iloc[-2]["Close"])
            last = float(h.iloc[-1]["Close"])
            diff = last - prev
            pct = (diff / prev * 100) if prev else 0.0
            pct_sign = "+" if pct >= 0 else ""
            abs_sign = "+" if diff >= 0 else "-"
            out.append(
                {
                    "symbol": sym,
                    "name": label,
                    "value": f"{last:,.2f}",
                    "change": f"{pct_sign}{pct:.2f}%",
                    "change_abs": f"{abs_sign}{abs(diff):,.2f}",
                    "change_pct": round(pct, 2),
                    "as_of": str(h.index[-1].date()),
                }
            )
        except Exception as e:
            print(f"[warn] yfinance {sym}: {e}", file=sys.stderr)
    return {"overnight": out}


def main() -> int:
    with open(ROOT / "stocks.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    now = datetime.now(KST)
    data: dict = {
        "generated_at": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "macro": {},
        "stocks": [],
    }

    try:
        data["macro"]["news"] = fetch_macro_news()
    except Exception as e:
        print(f"[warn] macro news fetch failed: {e}", file=sys.stderr)
        data["macro"]["news"] = []

    try:
        data["macro"]["indices"] = fetch_market_indices()
    except Exception as e:
        print(f"[warn] indices fetch failed: {e}", file=sys.stderr)
        data["macro"]["indices"] = {}

    try:
        data["macro"].update(fetch_fx())
    except Exception as e:
        print(f"[warn] fx fetch failed: {e}", file=sys.stderr)
        data["macro"]["fx"] = []

    try:
        data["macro"].update(fetch_overnight_markets())
    except Exception as e:
        print(f"[warn] overnight fetch failed: {e}", file=sys.stderr)
        data["macro"]["overnight"] = []

    try:
        data["macro"]["crypto_krw"] = fetch_upbit_tickers(["KRW-BTC", "KRW-ETH"])
    except Exception as e:
        print(f"[warn] crypto fetch failed: {e}", file=sys.stderr)
        data["macro"]["crypto_krw"] = {}

    # Collect all overnight proxy tickers upfront for a single batched fetch
    all_proxies = sorted({
        p for stock in config["stocks"] for p in (stock.get("overnight_proxy") or [])
    })
    try:
        proxy_changes = fetch_proxy_changes(all_proxies) if all_proxies else {}
    except Exception as e:
        print(f"[warn] proxy changes fetch failed: {e}", file=sys.stderr)
        proxy_changes = {}

    for stock in config["stocks"]:
        entry: dict = {
            "code": stock["code"],
            "name": stock["name"],
            "market": stock.get("market", ""),
        }
        if stock.get("owners"):
            entry["owners"] = stock["owners"]
        elif stock.get("owner"):
            entry["owners"] = [stock["owner"]]  # backward compat
        if stock.get("overnight_proxy"):
            entry["overnight_signal"] = compute_overnight_signal(stock["overnight_proxy"], proxy_changes)
        try:
            entry["quote"] = fetch_stock_quote(stock["code"])
        except Exception as e:
            print(f"[warn] quote failed for {stock['code']}: {e}", file=sys.stderr)
            entry["quote"] = {}
        try:
            entry["history"] = fetch_stock_history(stock["code"], stock.get("market", ""))
        except Exception as e:
            print(f"[warn] history failed for {stock['code']}: {e}", file=sys.stderr)
            entry["history"] = {}
        try:
            entry["news"] = fetch_stock_news(stock["code"])
        except Exception as e:
            print(f"[warn] news failed for {stock['code']}: {e}", file=sys.stderr)
            entry["news"] = []
        try:
            entry["disclosures"] = fetch_stock_disclosures(stock["code"])
        except Exception as e:
            print(f"[warn] disclosures failed for {stock['code']}: {e}", file=sys.stderr)
            entry["disclosures"] = []
        data["stocks"].append(entry)

    out = ROOT / ".tmp" / "news.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    n_stock_news = sum(len(s["news"]) for s in data["stocks"])
    n_macro = len(data["macro"].get("news", []))
    print(f"✓ Wrote {out.relative_to(ROOT)}: {len(data['stocks'])} stocks, "
          f"{n_stock_news} stock articles, {n_macro} macro articles.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
