#!/usr/bin/env python3
"""promote_rules.py — scan all review lessons, cluster by topic taxonomy,
promote rules that appear on 3+ distinct trading days to docs/promoted_rules.md.

Run automatically at the end of /daily-review, or manually:
    python scripts/promote_rules.py [--min-days N] [--dry-run]
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
OUT  = DOCS / "promoted_rules.md"

PROMOTE_THRESHOLD = 3  # distinct trading days to trigger promotion

# ---------------------------------------------------------------------------
# Topic taxonomy — each topic maps to a list of trigger keywords (OR logic).
# A lesson is tagged with a topic if title+rule contains ANY of its keywords.
# Topics are checked in order; a lesson can match multiple topics.
# ---------------------------------------------------------------------------
TOPICS: list[dict] = [
    {
        "id": "bio_proxy",
        "title": "바이오·XBI 약세 대응",
        "keywords": ["xbi", "ibb", "바이오", "소형 바이오", "임상", "파이프라인"],
    },
    {
        "id": "sector_consistency",
        "title": "섹터 내 판단 일관성",
        "keywords": ["섹터 일관", "동일 섹터", "같은 섹터", "피어", "동종"],
    },
    {
        "id": "sector_index_priority",
        "title": "섹터 지수 우선 (SOX·XBI·XLE 등)",
        "keywords": ["sox", "섹터 지수", "개별 프록시", "혼조", "엇갈림"],
    },
    {
        "id": "overheat_filter",
        "title": "과열 구간 필터",
        "keywords": ["과열", "20일", "+30%", "+40%", "급등 후", "되돌림", "재량 상향 금지"],
    },
    {
        "id": "priced_in",
        "title": "선반영 과소평가 방지",
        "keywords": ["선반영", "기대감 소화", "소문에 사고", "이미 반영"],
    },
    {
        "id": "shortsell_bearish",
        "title": "공매도·복수 부정 신호 = 하락 경계 필수",
        "keywords": ["공매도", "과열종목 지정", "복수 부정", "구조적 약세", "가격제한폭"],
    },
    {
        "id": "sector_news_vs_individual",
        "title": "섹터 시황 기사 ≠ 개별 촉매",
        "keywords": ["테마 시황", "섹터 기사", "개별 촉매", "개별 공시", "개별 재료"],
    },
    {
        "id": "earnings_day",
        "title": "실적 확정 당일 보수적 처리",
        "keywords": ["실적 확정", "실적 발표 당일", "어닝", "1q", "2q", "3q", "4q", "분기"],
    },
    {
        "id": "credit_not_catalyst",
        "title": "신용등급·회사채는 당일 촉매 아님",
        "keywords": ["신용등급", "회사채", "수요예측", "신용"],
    },
    {
        "id": "proxy_discount",
        "title": "프록시 신호 할인·원인 확인 필수",
        "keywords": ["프록시 급락", "프록시 원인", "프록시 평균", "맹신", "할인"],
    },
]


def _normalize(text: str) -> str:
    """Lowercase + strip Korean particles from token endings for matching."""
    text = text.lower()
    # Strip common Korean endings so "약세에" → "약세", "프록시의" → "프록시" etc.
    text = re.sub(r"([가-힣])(은|는|이|가|을|를|에|의|로|으로|와|과|도|만|에서|에게|시|도|만|부터|까지|이며|이고|하고|하여|하면|이면|이라|이라면|이지만|이었|였|했|됐|됩|합|있|없|하는|한|된|되는|인|적|을|를)\b", r"\1", text)
    return text


def tag_lesson(lesson: dict) -> list[str]:
    """Return list of topic IDs matching this lesson."""
    haystack = _normalize(
        lesson.get("title", "") + " " + lesson.get("rule", "") + " " + lesson.get("detail", "")
    )
    matched = []
    for topic in TOPICS:
        if any(kw in haystack for kw in topic["keywords"]):
            matched.append(topic["id"])
    return matched


# ---------------------------------------------------------------------------
# Load all lessons
# ---------------------------------------------------------------------------

def load_all_lessons() -> list[dict]:
    lessons = []
    for path in sorted(DOCS.glob("2*.summary.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        date = d.get("date") or path.name[:10]
        for lesson in (d.get("review") or {}).get("analysis", {}).get("lessons") or []:
            if lesson.get("rule"):
                lessons.append({"date": date, **lesson})
    return lessons


# ---------------------------------------------------------------------------
# Build promoted rules
# ---------------------------------------------------------------------------

def build_promotions(lessons: list[dict], min_days: int) -> list[dict]:
    """Group lessons by topic, collect distinct days, pick best representative."""
    by_topic: dict[str, list[dict]] = defaultdict(list)

    for lesson in lessons:
        for tid in tag_lesson(lesson):
            by_topic[tid].append(lesson)

    # Untagged lessons — cluster by exact title to catch remaining repeats
    tagged_dates_by_rule: dict[str, set[str]] = defaultdict(set)
    for lesson in lessons:
        if not tag_lesson(lesson):
            key = lesson.get("title", "").strip()
            tagged_dates_by_rule[key].add(lesson["date"])

    promoted = []

    # Taxonomy-based promotions
    for topic in TOPICS:
        tid = topic["id"]
        members = by_topic.get(tid, [])
        if not members:
            continue
        distinct_days = sorted({l["date"] for l in members})
        if len(distinct_days) < min_days:
            continue

        # Best representative: most recent, most detailed
        rep = sorted(members, key=lambda l: (l["date"], len(l.get("detail", ""))))[-1]
        # Collect all unique rules across days for this topic
        rules_by_day = {}
        for l in sorted(members, key=lambda x: x["date"]):
            rules_by_day[l["date"]] = l.get("rule", "")
        recent_examples = [
            f"- **{d}** {r}" for d, r in sorted(rules_by_day.items())[-3:]
        ]

        promoted.append({
            "topic_title": topic["title"],
            "canonical_rule": rep.get("rule", ""),
            "detail": rep.get("detail", ""),
            "days": distinct_days,
            "recent_examples": recent_examples,
            "count": len(distinct_days),
        })

    # Exact-title repeats (untagged)
    for title, days in tagged_dates_by_rule.items():
        if len(days) < min_days:
            continue
        matching = [l for l in lessons if l.get("title", "").strip() == title]
        rep = sorted(matching, key=lambda l: l["date"])[-1]
        promoted.append({
            "topic_title": title,
            "canonical_rule": rep.get("rule", ""),
            "detail": rep.get("detail", ""),
            "days": sorted(days),
            "recent_examples": [],
            "count": len(days),
        })

    promoted.sort(key=lambda p: p["count"], reverse=True)
    return promoted


# ---------------------------------------------------------------------------
# Render promoted_rules.md
# ---------------------------------------------------------------------------

def render_md(promoted: list[dict], total_lessons: int, total_days: int, min_days: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    lines = [
        "# Promoted Rules",
        "",
        f"> **자동 생성** — {now}",
        f">",
        f"> `promote_rules.py` 가 {total_days}일치 {total_lessons}개 lesson 을 스캔해",
        f"> **{min_days}일 이상** 반복된 패턴 {len(promoted)}개를 아래에 승격했습니다.",
        ">",
        "> ## 사용 방법 (`daily-report` 에이전트용)",
        ">",
        "> 이 파일은 `step 1c` 에서 읽힙니다.",
        "> 아래 규칙들은 최근 5일 lessons 보다 **높은 우선순위**로 적용하십시오.",
        "> 단, 오늘의 구체적 시장 상황이 명백히 다르다면 rationale 에 이유를 명시하고 예외 처리 가능.",
        "",
        "---",
        "",
    ]

    for i, p in enumerate(promoted, 1):
        days = p["days"]
        lines += [
            f"## {i}. {p['topic_title']}",
            "",
            f"**적용 규칙**",
            f"> {p['canonical_rule']}",
            "",
            f"**반복 횟수**: {p['count']}일 ({', '.join(days)})",
            "",
        ]
        if p["recent_examples"]:
            lines += [
                "**최근 사례 (날짜별 rule)**",
            ] + p["recent_examples"] + [""]
        if p["detail"]:
            lines += [
                "**배경**",
                p["detail"],
                "",
            ]
        lines += ["---", ""]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    dry_run  = "--dry-run" in argv
    min_days = PROMOTE_THRESHOLD
    for arg in argv:
        if arg.startswith("--min-days="):
            min_days = int(arg.split("=")[1])

    lessons = load_all_lessons()
    if not lessons:
        print("[promote_rules] no lessons found — nothing to do", file=sys.stderr)
        return 0

    distinct_days = len({l["date"] for l in lessons})
    promoted = build_promotions(lessons, min_days)

    print(f"[promote_rules] {len(lessons)} lessons / {distinct_days} days "
          f"→ {len(promoted)} promoted (≥{min_days} days)")
    for p in promoted:
        print(f"  [{p['count']}d] {p['topic_title']}")

    if dry_run:
        print("[promote_rules] dry-run — not writing file")
        return 0

    md = render_md(promoted, len(lessons), distinct_days, min_days)
    OUT.write_text(md, encoding="utf-8")
    print(f"[promote_rules] wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
