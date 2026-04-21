---
description: Generate and publish today's pre-market stock briefing
---

## Framing — this is a PRE-MARKET briefing

**운영 시점은 매일 오전 07:30 KST (한국 장 시작 전).**

분석은 "오늘을 사후 해석"이 아니라 **"오늘 개장 후 한국 장 방향 예측"** 입니다.
의견과 언어는 항상 forward-looking:

- **확정 입력 (과거)**
  - 어제 한국 증시 종가·등락률·공시·장중 뉴스
  - 밤사이 미국/유럽 증시 종가 (S&P, 다우, 나스닥, SOX, VIX, WTI, 금, BTC, 달러인덱스)
  - 어제 밤~오늘 새벽 사이 나온 거시·정책·전쟁 이슈
- **예측 대상 (미래)**
  - 오늘 장 개장 시 갭 방향·섹터 분위기
  - 오늘 종가까지의 1일 흐름 (1~5일 단기)

종목 `quote` 필드의 가격은 **어제 종가**입니다. 이걸 "오늘 실적"이 아니라 "예측의 출발점"으로 취급하세요.

## Steps

1. **Fetch raw news.** Run `.venv/bin/python scripts/fetch_news.py`. Writes `.tmp/news.json`
   with: `macro.news`, `macro.indices`, `macro.fx`, `macro.overnight` (간밤 해외시장),
   per-stock `news[]` + `disclosures[]` + `quote` (어제 종가) + `overnight_signal`
   (종목별 간밤 해외 프록시 평균 등락률).

2. **Read the raw data.** Read `.tmp/news.json`. Scan all stock news, disclosures, macro
   news, overnight markets, and indices together. Identify recurring themes, sector-level
   stories, and anything material.

3. **Deep-dive research (for stocks with `deep_dive: true` in `stocks.yml`).**
   For each such stock, **use WebSearch and WebFetch** to research:
   - **주력 사업·제품**, **시장성**, **경쟁 구도**, **R&D/논문·특허 동향**, **리스크**
   Use any `keywords` from `stocks.yml` as search seed. Always cite source URLs.

4. **Compose the summary.** Write `.tmp/summary.json` matching the schema below.
   Language: **중립·사실 기반**. Forward-looking ("오늘 장 열릴 때...", "갭 ~% 예상",
   "오늘 약세 시작 가능성"). No hype, no investment advice beyond the requested
   recommendation label. Every claim needs a source from the fetched/searched data.

5. **Render.** Run `.venv/bin/python scripts/render.py .tmp/summary.json`. This also writes
   `docs/YYYY-MM-DD.summary.json` — a persistent copy that the evening `/daily-review`
   job reads back to compare predictions against actual closes.

6. **Commit & push.** `git add docs/ stocks.yml; git commit -m "report: YYYY-MM-DD briefing"; git push`

7. **Report the URL + one-line summary.**

## summary.json schema (stock-level decision fields explained below)

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 with +09:00",
  "headline": "한 줄 헤드라인 (30자 이내)",
  "tldr": "카톡 미리보기용 한 줄 요약 (80자 이내, 투자 권유 금지)",

  "mood_dashboard": {
    "policy":      {"impact": "positive|neutral|negative", "note": "한 줄 근거 (30자 이내)"},
    "geopolitics": {"impact": "...", "note": "..."},
    "overnight":   {"impact": "...", "note": "..."},
    "sectors":     {"impact": "...", "note": "..."},
    "fx_macro":    {"impact": "...", "note": "..."}
  },

  "top_stories": [
    {"category": "policy|geopolitics|macro|sector|market",
     "headline": "...", "why_it_matters": "...",
     "impact": "positive|neutral|negative",
     "sources": [{"title": "...", "url": "..."}]}
  ],

  "focus": {
    "title": "미국·이란 전쟁과 호르무즈 해협",
    "impact": "negative",
    "status": {
      "level": "closed|restricted|open",
      "label": "봉쇄 중",
      "detail": "...",
      "ship_count": {"value": "일 14척 통과", "date": "2026-04-19 (일)", "note": "...",
                     "source": {"title": "...", "url": "..."}}
    },
    "summary": "...",
    "news_items": [
      {"title": "...", "summary": "...", "source": "...", "url": "...",
       "published_at": "2026-04-20T15:35:00+09:00", "impact": "..."}
    ]
  },

  "macro": {
    "overall_impact": "positive|neutral|negative",
    "indicators_impact": "positive|neutral|negative",
    "overnight_impact": "positive|neutral|negative",
    "summary": "오늘 장 전반 흐름 2~3문장 (top_stories 상단 노출)",
    "indicators": [{"name": "KOSPI", "value": "6,219.09",
                    "change_abs": "+27.17", "change_pct": "+0.44%",
                    "impact": "positive"}],
    "overnight":  [{"name": "S&P 500", "value": "7,126.06",
                    "change_abs": "+85.12", "change_pct": "+1.20%",
                    "impact": "positive"}]
  },

  "sectors": [
    {"name": "반도체",
     "emoji": "🔧",
     "impact": "positive|neutral|negative",
     "headline": "한 줄 내러티브 (예: 'AI 슈퍼사이클 모멘텀 재확인')",
     "news": [
       {"title": "뉴스 헤드라인",
        "impact": "positive|neutral|negative",
        "published_at": "2026-04-21T04:30:00+09:00",
        "source": {"title": "언론사", "url": "..."},
        "note": "optional — 한 줄 부연"}
     ]}
  ],

  "stocks": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "news_sentiment": "positive|neutral|negative",
      "priced_in": true,
      "overnight_signal": "up|neutral|down",
      "recommendation": "strong_buy|buy|hold|sell|strong_sell",
      "confidence": "high|medium|low",
      "rationale": "한 문장 근거 — 뉴스·어제종가·간밤신호의 조합 설명",
      "summary": "오늘 세션 예측 2~3문장 (forward-looking)",
      "key_points": [
        {"point": "...", "detail": "...", "impact": "...",
         "published_at": "2026-04-20T15:57:00+09:00",
         "sources": [...]}
      ],
      "deep_dive": { "business": "...", "market": "...", "competitors": [...],
                     "research_notes": "...", "risks": "...", "sources": [...] },
      "disclosures": [{"title": "...", "url": "...", "date": "YY.MM.DD"}]
    }
  ]
}
```

## 투자의견 (recommendation) 결정 규칙 — 결정 매트릭스

전제: **오늘 개장 후 한국 장에서의 1~5일 방향 예측**. 가치평가·장기전망 아님.

### 단계 1: 세 가지 신호를 독립적으로 판단

| 신호 | 값 | 판단 기준 |
|---|---|---|
| `news_sentiment` | positive / neutral / negative | 종목·섹터 뉴스 플로우 (톤만, 주가는 제외) |
| `overnight_signal` | up / neutral / down | `quote.overnight_signal`가 자동 계산됨. 그대로 반영 |
| `priced_in` | true / false | 어제 주가 변동이 이미 해당 뉴스를 반영했나? (어제 ±5% 이상 + 뉴스 방향 일치면 true) |

### 단계 2: 조합 매트릭스

| news_sentiment | overnight_signal | priced_in | 권장 |
|---|---|---|---|
| positive | up | false | `strong_buy` |
| positive | up | true | `buy` (갭 상승 후 피로 가능) |
| positive | neutral | false | `buy` |
| positive | neutral | true | `hold` |
| positive | down | * | `hold` (상충 — 갭다운 리스크) |
| neutral | up | * | `buy` |
| neutral | neutral | * | `hold` |
| neutral | down | * | `hold` or `sell` |
| negative | up | false | `hold` (베어트랩 의심) |
| negative | up | true | `hold` (어제 급락 반영됨, 반등 여지) |
| negative | neutral | * | `sell` |
| negative | down | * | `strong_sell` |

**이 매트릭스는 기본값**입니다. 개별 종목의 강한 특수 이벤트(실적 쇼크·규제·M&A 공시) 는 한 단계 override 가능. 단, override 시 `rationale`에 명시.

### 단계 3: `confidence` 부여
- `high`: 세 신호가 모두 같은 방향
- `medium`: 두 신호가 같은 방향, 하나만 다름
- `low`: 신호들이 상충하거나, 종목 뉴스 부재 + 섹터만 있음

## Forward-looking 언어 가이드

- ❌ "오늘 +3% 급등했다" → ✅ "어제 +3% 강세에 이어, 간밤 나스닥도 +1.5%로 오늘 개장 초 강세 예상"
- ❌ "오늘 -2% 하락" → ✅ "어제 -2% 마감했으나, 간밤 해당 섹터 미국주는 +0.5%로 반등 가능성"
- ❌ "매수 의견" 단독 → ✅ "매수 (뉴스 긍정 + 간밤 강세 + priced_in 아님)"

## Rules

- **Source URLs must come from fetched data or web tool results** — do not invent.
- `stocks` array must preserve `stocks.yml` order and include every stock.
- For deep_dive stocks, `deep_dive` 섹션 필수.
- For no-material-news days, `recommendation: "hold"`, `confidence: "low"`, `rationale: "개별 뉴스 부재"` OK.
- `news_sentiment`, `priced_in`, `overnight_signal`, `confidence` 는 **모든 종목에 필수**.
- `top_stories` 규칙:
  - **개별 종목 뉴스 금지**. "SK하이닉스 +3.37% 신고가" 같은 건 전체 "반도체 섹터 강세 — 간밤 SOX 상승"으로 흡수.
  - 정책·규제·국제정세·거시·섹터 전반 동향 중심.
  - **개수 제한 없음**. 오늘 새롭게 움직인 재료면 다 포함. 다만 "오늘 새 정보"여야 함 (어제 이미 나온 얘기는 생략).
  - 각 항목에 `category` 필수: `policy` / `geopolitics` / `macro` / `sector` / `market`.
  - 거시 경제 해석은 `top_stories` 안으로 녹여 넣고, 별도 `macro.key_points`는 쓰지 않는다.
- `mood_dashboard` 5축 필수 작성:
  - `policy` — 세제·감독·산업 육성책·밸류업·주주환원
  - `geopolitics` — 전쟁·외교·무역·제재
  - `overnight` — 어제 밤 미국·유럽 지수, VIX, SOX, XBI 등
  - `sectors` — 주요 한국 섹터 (반도체/바이오/금융/에너지 등) 종합 기류
  - `fx_macro` — 원/달러, WTI, 금, 비트코인, 원자재
  - 각 축 값: `{"impact": "positive|neutral|negative", "note": "한 줄 근거 30자 이내"}`
  - `neutral` 은 "혼조" 의미로도 씀 (긍정·부정 신호 섞여 있음).

---

## 뉴스 큐레이션 — **"오늘 주가에 영향을 줄 만한가?"** (핵심 규칙)

섹터 news와 종목 news 모두에 적용되는 필터. Agent는 raw news(`news.json`)를 **정제**해서 summary.json에 다시 쓴다. 그냥 베껴넣지 말 것.

### ✅ 포함 (Material) — 오늘 세션에 직접 영향 가능

- **실적·가이던스**: 분기 실적 발표, 잠정 실적 공시, 가이던스 변경, 어닝 서프라이즈/쇼크
- **대형 공시**: 자사주 매입·소각, 배당 변경, 감자/증자, M&A, 대주주 지분 변동
- **계약·수주**: 대형 계약 체결, 공급 계약, 라이선스 딜, 수주 공시
- **규제·정책**: 해당 종목/섹터 직접 영향 (예: 반도체 보조금, 배터리 보조금, 환경 규제)
- **애널리스트 액션**: 투자의견 변경, 목표가 상향/하향, 커버리지 개시
- **파이프라인 진전**: 신약 임상 결과, 허가 승인, 신제품 출시, 특허
- **경영진 변경**: CEO 교체, 핵심 임원 변경
- **매크로 → 개별 종목 연결**: 예) 금리 변동 → 은행주, 유가 변동 → 정유주 등 명확한 인과

### ❌ 제외 (Non-material) — 단순 관련 언급

- **시황 recap**: "코스피 6200선 회복", "코스닥 강보합 마감" 등 broad market. 개별 종목 언급만 있는 포함 뉴스
- **운영 루틴**: 정기주총결과, 동반성장협의회, IR 개최 공지, 감사보고서 제출, 사장 인사말/인터뷰
- **기술적 알림**: 가격제한폭 확대 도달, 주식매수선택권 행사
- **stale 뉴스**: 1주일 이상 지난 항목 (오늘 새로 재부각되지 않는 한)
- **풍문 해명 공시**: 실질 내용 없는 경우
- **수급 flow**: 단순 외국인/기관 순매수/순매도 집계

### 오늘 영향 여부 판단 기준

- **종목 뉴스 (`stocks[].news`)**: **24시간 내 발행된 것만 포함**. render.py가 24h 넘은 항목을 자동으로 drop함. Agent는 24h 내 material 아이템만 추려서 `why_material` 달면 됨.
- **섹터 뉴스 (`sectors[].news`)**: 72h 기본 포함. 거시/지정학 이슈는 오늘까지 영향 지속되면 하루 이상 지난 것도 OK. 3일 넘은 건 오늘 재부각된 경우만 (예: "지난주 실적 후 타겟 상향 릴레이 오늘도 지속").

### 필드 규칙

각 curated news 항목:
```json
{
  "title": "...",
  "impact": "positive|neutral|negative",
  "why_material": "왜 오늘 주가에 영향? 한 줄 (30자 이내, 필수)",
  "published_at": "ISO 또는 YYYY.MM.DD HH:MM",
  "source": {"title": "언론사", "url": "..."}
}
```

- `why_material` **필수**: "실적 기대치 상향" / "대형 수주 발표" / "신약 허가 임박" 등. 제외 기준 아닌 이유를 한 줄로.
- 종목별 큐레이션 결과 **3~7건** 권장. 정말 material 한 게 없으면 `"news": []` (빈 배열) — UI에서 블록 자체가 사라짐.
- 섹터도 동일. 큐레이션 후 3~5건 권장.

### 섹터 news vs 종목 news 역할

- **섹터 news**: 내 보유 종목과 **독립**. 섹터 자체의 시황·매크로·규제. `affected` 안 씀.
- **종목 news**: 해당 기업 고유 이슈. `news.json` 의 raw news 중에서 material만 골라 `why_material` 붙임. render가 24h 필터 + 헤드라인 keyword로 impact 자동 라벨(호재/악재/중립) 함 — agent가 더 정확한 판단이 있으면 명시적으로 `impact` 덮어써라 (예: 헤드라인은 "매각 검토" 같은 중립적 표현이지만 주가에는 호재로 해석되는 케이스).

---

## 렌더 편의

- Render가 `published_at` 내림차순 자동 정렬, `time_ago` 계산, impact 라벨.
- `"news": []` 는 "오늘 material 없음"으로 해석돼 블록 자체 숨김 + 🔥 N 뱃지 안 뜸.
- `impact` 해석:
  - KOSPI +1% → `positive` (상승=호재)
  - USD/KRW 상승: 수출주 긍정/수입주 부담 → 종합 `neutral` 기본값
  - VIX 상승: `negative`
- If `.tmp/news.json` missing/empty, stop and report — do not fabricate.
