"""Display-label maps shared across render / review code.

Pure data — no imports from other project modules. Any Python consumer that
needs to show a human-readable label for a schema enum value reads from here.
Jinja templates generally receive labels pre-resolved on the Python side, so
they don't import this module directly.
"""
from __future__ import annotations


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

# Fallback emoji for sector cards when the agent doesn't supply one.
SECTOR_EMOJI_FALLBACK = {
    "반도체": "🔧", "바이오": "🧬", "건설": "🏗️", "EPC": "🏗️", "플랜트": "🏗️",
    "조선": "🚢", "방산": "🚀", "조선·방산": "🚢",
    "자동차": "🚗", "배터리": "🔋", "에너지": "⛽", "정유": "⛽",
    "전력": "⚡", "통신": "📡", "엔터": "🎤", "게임": "🎮",
    "철강": "🏭", "화학": "🧪", "금융": "🏦", "은행": "🏦", "증권": "📈",
    "유통": "🛒", "식음료": "🍽️", "제약": "💊", "항공": "✈️",
    "플랫폼": "💻", "인터넷": "🌐", "전기전자": "🔌",
}
