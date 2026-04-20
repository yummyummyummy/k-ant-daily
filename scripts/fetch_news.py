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


def fetch_market_indices() -> dict:
    """KOSPI / KOSDAQ / KOSPI200 latest values from Naver main sise page."""
    soup = _get("https://finance.naver.com/sise/")
    result: dict = {}
    for key, selector in [
        ("KOSPI", "#KOSPI_now"),
        ("KOSPI_change", "#KOSPI_change"),
        ("KOSDAQ", "#KOSDAQ_now"),
        ("KOSDAQ_change", "#KOSDAQ_change"),
        ("KOSPI200", "#KPI200_now"),
        ("KOSPI200_change", "#KPI200_change"),
    ]:
        el = soup.select_one(selector)
        if el:
            result[key] = el.get_text(" ", strip=True)
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
            pct = (last - prev) / prev * 100 if prev else 0.0
            sign = "+" if pct >= 0 else ""
            out.append(
                {
                    "symbol": sym,
                    "name": label,
                    "value": f"{last:,.2f}",
                    "change": f"{sign}{pct:.2f}%",
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

    for stock in config["stocks"]:
        entry: dict = {
            "code": stock["code"],
            "name": stock["name"],
            "market": stock.get("market", ""),
        }
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
