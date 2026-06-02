#!/usr/bin/env python3
"""Extract stock watchlist candidates from exported KakaoTalk chat text.

The script reads local KakaoTalk export files, matches stock names/codes/aliases,
and writes sanitized candidate summaries. Chat originals should stay local and
gitignored under kakao_exports/.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

ROOT = Path(__file__).resolve().parent.parent
KAKAO_DATE_RE = re.compile(r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일")
DESKTOP_MSG_RE = re.compile(r"^\[(?P<speaker>[^\]]+)\]\s+\[(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<mi>\d{2})\]\s*(?P<text>.*)$")
MOBILE_MSG_RE = re.compile(
    r"^(?P<date>\d{4}년\s*\d{1,2}월\s*\d{1,2}일)\s+"
    r"(?P<ampm>오전|오후)\s*(?P<h>\d{1,2}):(?P<mi>\d{2}),\s*"
    r"(?P<speaker>[^:]+)\s*:\s*(?P<text>.*)$"
)
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

INVESTMENT_KEYWORDS = {
    "주식", "종목", "주가", "시총", "상장", "코스피", "코스닥", "나스닥",
    "매수", "매도", "샀", "산다", "살까", "팔", "추매", "손절", "익절", "물타",
    "수익", "손실", "평단", "계좌", "보유", "비중", "목표가", "리포트",
    "실적", "공시", "뉴스", "호재", "악재", "수주", "계약", "임상", "승인",
    "상한가", "하한가", "급등", "급락", "반등", "조정", "돌파", "배당",
    "per", "pbr", "roe", "eps", "etf", "레버리지",
}

NON_STOCK_HINTS = {
    "카카오톡", "톡방", "단톡", "오픈채팅", "카톡", "택시", "페이", "맵",
}


@dataclass
class Message:
    date: str | None
    speaker: str
    text: str


@dataclass
class Stock:
    code: str
    name: str
    aliases: set[str] = field(default_factory=set)
    source: str = "stocks.yml"


def normalize(text: str) -> str:
    return re.sub(r"[\s\-_·.,/(){}\[\]+'\"`~!?:;|]", "", str(text)).lower()


def parse_date(text: str) -> str | None:
    m = KAKAO_DATE_RE.search(text)
    if not m:
        return None
    return f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"


def parse_kakao(path: Path) -> list[Message]:
    messages: list[Message] = []
    current_date: str | None = None

    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip("\ufeff")
        if not line.strip():
            continue

        mobile = MOBILE_MSG_RE.match(line)
        if mobile:
            current_date = parse_date(mobile.group("date"))
            messages.append(Message(current_date, mobile.group("speaker").strip(), mobile.group("text").strip()))
            continue

        if "---------------" in line:
            found = parse_date(line)
            if found:
                current_date = found
            continue

        desktop = DESKTOP_MSG_RE.match(line)
        if desktop:
            messages.append(Message(current_date, desktop.group("speaker").strip(), desktop.group("text").strip()))
            continue

        if messages:
            messages[-1].text += "\n" + line.strip()

    return messages


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def merge_stock(target: dict[str, Stock], code: str, name: str, aliases: Iterable[str], source: str) -> None:
    stock = target.setdefault(code, Stock(code=code, name=name, source=source))
    if name and stock.name != name and stock.source != "stocks.yml":
        stock.name = name
    stock.aliases.update(a for a in aliases if a)
    stock.aliases.add(code)
    stock.aliases.add(name)


def load_universe(stocks_path: Path, aliases_path: Path) -> list[Stock]:
    merged: dict[str, Stock] = {}

    stocks = load_yaml(stocks_path).get("stocks") or []
    for item in stocks:
        merge_stock(merged, str(item["code"]), str(item["name"]), [], "stocks.yml")

    aliases = load_yaml(aliases_path).get("stocks") or []
    for item in aliases:
        merge_stock(
            merged,
            str(item["code"]),
            str(item["name"]),
            [str(a) for a in item.get("aliases") or []],
            str(aliases_path.name),
        )

    return sorted(merged.values(), key=lambda s: (s.name, s.code))


def has_investment_context(text: str) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in INVESTMENT_KEYWORDS)


def is_likely_non_stock(alias: str, text: str) -> bool:
    if alias != "카카오":
        return False
    return any(h in text for h in NON_STOCK_HINTS) and not has_investment_context(text)


def matched_aliases(stock: Stock, text: str, norm_text: str) -> set[str]:
    found: set[str] = set()

    for code in CODE_RE.findall(text):
        if code == stock.code:
            found.add(code)

    for alias in stock.aliases:
        alias = alias.strip()
        if not alias or alias == stock.code:
            continue
        norm_alias = normalize(alias)
        if len(norm_alias) < 2:
            continue
        if norm_alias in norm_text and not is_likely_non_stock(alias, text):
            found.add(alias)

    return found


def score_candidate(mentions: int, speakers: int, context_hits: int, recent_days: int | None) -> float:
    mention_score = min(0.30, math.log1p(mentions) / 10)
    speaker_score = min(0.18, speakers * 0.045)
    context_score = min(0.28, (context_hits / max(mentions, 1)) * 0.28)
    recency_score = 0.0
    if recent_days is not None:
        if recent_days <= 7:
            recency_score = 0.20
        elif recent_days <= 30:
            recency_score = 0.14
        elif recent_days <= 90:
            recency_score = 0.08
    return round(min(0.99, 0.20 + mention_score + speaker_score + context_score + recency_score), 2)


def analyze(messages: list[Message], universe: list[Stock], today: datetime) -> list[dict]:
    stats: dict[str, dict] = defaultdict(lambda: {
        "mentions": 0,
        "speakers": Counter(),
        "aliases": Counter(),
        "context_hits": 0,
        "first_mentioned": None,
        "last_mentioned": None,
        "examples": [],
    })

    for msg in messages:
        norm_text = normalize(msg.text)
        context = has_investment_context(msg.text)
        for stock in universe:
            aliases = matched_aliases(stock, msg.text, norm_text)
            if not aliases:
                continue
            row = stats[stock.code]
            row["stock"] = stock
            row["mentions"] += 1
            row["speakers"][msg.speaker] += 1
            row["aliases"].update(aliases)
            row["context_hits"] += 1 if context else 0
            if msg.date:
                row["first_mentioned"] = min(filter(None, [row["first_mentioned"], msg.date])) if row["first_mentioned"] else msg.date
                row["last_mentioned"] = max(filter(None, [row["last_mentioned"], msg.date])) if row["last_mentioned"] else msg.date
            if len(row["examples"]) < 3 and context:
                sample = re.sub(r"\s+", " ", msg.text).strip()
                row["examples"].append(sample[:120])

    out = []
    for code, row in stats.items():
        stock: Stock = row["stock"]
        recent_days = None
        if row["last_mentioned"]:
            try:
                last = datetime.strptime(row["last_mentioned"], "%Y-%m-%d")
                recent_days = (today.date() - last.date()).days
            except ValueError:
                pass
        confidence = score_candidate(row["mentions"], len(row["speakers"]), row["context_hits"], recent_days)
        out.append({
            "code": code,
            "name": stock.name,
            "mentions": row["mentions"],
            "context_mentions": row["context_hits"],
            "speakers": sorted(row["speakers"], key=lambda s: (-row["speakers"][s], s)),
            "first_mentioned": row["first_mentioned"],
            "last_mentioned": row["last_mentioned"],
            "matched_aliases": [a for a, _ in row["aliases"].most_common(8)],
            "confidence": confidence,
            "status": "candidate",
            "examples": row["examples"],
        })

    out.sort(key=lambda r: (-r["confidence"], -r["mentions"], r["name"]))
    return out


def write_outputs(candidates: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "watchlist": candidates}

    class QuotedDumper(yaml.SafeDumper):
        pass

    def quoted_str(dumper: yaml.SafeDumper, data: str) -> yaml.nodes.ScalarNode:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="'")

    QuotedDumper.add_representer(str, quoted_str)
    output.write_text(
        yaml.dump(payload, Dumper=QuotedDumper, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    json_path = output.with_suffix(".json")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    csv_path = output.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "code", "name", "mentions", "context_mentions", "speakers",
            "last_mentioned", "confidence", "matched_aliases",
        ])
        writer.writeheader()
        for row in candidates:
            writer.writerow({
                "code": row["code"],
                "name": row["name"],
                "mentions": row["mentions"],
                "context_mentions": row["context_mentions"],
                "speakers": ", ".join(row["speakers"]),
                "last_mentioned": row["last_mentioned"] or "",
                "confidence": row["confidence"],
                "matched_aliases": ", ".join(row["matched_aliases"]),
            })


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract stock watchlist candidates from KakaoTalk export text.")
    parser.add_argument("files", nargs="+", type=Path, help="KakaoTalk exported .txt file(s)")
    parser.add_argument("--stocks", type=Path, default=ROOT / "stocks.yml", help="Base stock universe YAML")
    parser.add_argument("--aliases", type=Path, default=ROOT / "watchlist_aliases.yml", help="Alias/candidate universe YAML")
    parser.add_argument("--output", type=Path, default=ROOT / ".tmp" / "kakao_watchlist.yml", help="Output YAML path")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Hide candidates below this confidence")
    args = parser.parse_args()

    universe = load_universe(args.stocks, args.aliases)
    messages: list[Message] = []
    for path in args.files:
        messages.extend(parse_kakao(path))

    candidates = analyze(messages, universe, datetime.now())
    if args.min_confidence > 0:
        candidates = [c for c in candidates if c["confidence"] >= args.min_confidence]

    write_outputs(candidates, args.output)

    print(f"✓ Parsed {len(messages)} messages")
    print(f"✓ Matched {len(candidates)} stock candidates")
    print(f"✓ Wrote {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")
    print(f"✓ Wrote {args.output.with_suffix('.json').relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output.with_suffix('.json')}")
    print(f"✓ Wrote {args.output.with_suffix('.csv').relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output.with_suffix('.csv')}")

    for row in candidates[:10]:
        speakers = ", ".join(row["speakers"][:3])
        print(f"- {row['name']}({row['code']}): {row['mentions']}회, confidence {row['confidence']:.2f}, speakers {speakers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
