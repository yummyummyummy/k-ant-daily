---
description: Generate and publish today's pre-market stock briefing
---

Generate today's pre-market briefing for the stocks in `stocks.yml` and publish it to GitHub Pages.

## Steps

1. **Fetch raw news.** Run `.venv/bin/python scripts/fetch_news.py`. Writes `.tmp/news.json`
   with: `macro.news`, `macro.indices`, `macro.fx`, `macro.overnight` (간밤 해외시장),
   and per-stock `news[]` + `disclosures[]`.

2. **Read the raw data.** Read `.tmp/news.json`. Scan all stock news, disclosures, macro
   news, overnight markets, and indices together. Identify recurring themes, sector-level
   stories, and anything material.

3. **Deep-dive research (for stocks with `deep_dive: true` in `stocks.yml`).**
   For each such stock, **use WebSearch and WebFetch** to research:
   - **주력 사업·제품**: 회사가 만드는 제품/서비스, 기술 스택
   - **시장성**: TAM 추정, 성장률, 핵심 고객사, 최근 주문/계약 공개 자료
   - **경쟁 구도**: 국내외 경쟁사, 차별화 요소
   - **R&D/논문·특허 동향**: 최근 논문 인용, 특허 출원, 학회 발표 (바이오/기술 섹터 중요)
   - **리스크**: 재무 리스크, 규제, 기술 대체재, 주요 이슈
   Use any `keywords` from `stocks.yml` as search seed. Always cite source URLs.

4. **Compose the summary.** Write `.tmp/summary.json` matching the schema below.
   Language: **중립·사실 기반**. No hype, no investment advice beyond the requested
   recommendation label. Lead with "what happened" before "what it means". Every claim
   needs a source from the fetched/searched data; never fabricate URLs.

5. **Render.** Run `.venv/bin/python scripts/render.py .tmp/summary.json`.

6. **Commit & push.**
   ```
   git add docs/ stocks.yml
   git commit -m "report: YYYY-MM-DD briefing"
   git push
   ```

7. **Report the URL + one-line summary** (headline + what today emphasizes).

## summary.json schema

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 with +09:00",
  "headline": "한 줄 헤드라인 (30자 이내)",
  "tldr": "카톡 미리보기용 한 줄 요약 (80자 이내, 투자 권유 금지)",

  "top_stories": [
    {
      "headline": "오늘 가장 중요한 뉴스 (최대 3개)",
      "why_it_matters": "한국 시장/선정 종목에 왜 중요한지 1~2문장",
      "impact": "positive | neutral | negative",
      "sources": [{"title": "...", "url": "..."}]
    }
  ],

  "macro": {
    "overall_impact": "positive | neutral | negative",
    "summary": "오늘 거시 흐름 2~3문장",
    "indicators": [
      {"name": "KOSPI", "value": "2,680", "change": "+0.5%", "impact": "positive"}
    ],
    "overnight": [
      {"name": "S&P 500", "value": "...", "change": "+1.2%", "impact": "positive"}
    ],
    "key_points": [
      {
        "point": "핵심 포인트 헤드라인",
        "detail": "1~2문장",
        "impact": "positive | neutral | negative",
        "sources": [{"title": "...", "url": "..."}]
      }
    ]
  },

  "sectors": [
    {
      "name": "반도체",
      "summary": "섹터 흐름 1~2문장",
      "impact": "positive | neutral | negative",
      "affected": ["삼성전자", "SK하이닉스"],
      "key_points": [{"point": "...", "detail": "...", "impact": "...", "sources": [...]}]
    }
  ],

  "stocks": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "recommendation": "strong_buy | buy | hold | sell | strong_sell",
      "rationale": "해당 의견의 근거 한 문장 (뉴스 흐름 기반, 가치평가 아님)",
      "summary": "오늘 해당 종목 포인트 2~3문장",
      "key_points": [
        {"point": "...", "detail": "...", "impact": "...", "sources": [...]}
      ],
      "deep_dive": {
        "business": "주력 제품/기술 설명",
        "market": "TAM, 성장률, 주요 고객",
        "competitors": ["경쟁사1", "경쟁사2"],
        "research_notes": "최근 논문/특허/학회 동향",
        "risks": "주요 리스크 요약",
        "sources": [{"title": "...", "url": "..."}]
      },
      "disclosures": [{"title": "...", "url": "...", "date": "YY.MM.DD"}]
    }
  ]
}
```

## 투자의견 (recommendation) 기준

어디까지나 **단기(1~5일) 뉴스 플로우 해석**이라는 전제로 부여. 가치평가·장기 전망 아님.

- `strong_buy` (풀매수): 강한 호재 다수 + 거시/섹터 순풍 + 공시·실적 기대감 확인
- `buy` (매수): 우호적 뉴스 우위, 반대 시그널 없음
- `hold` (존버): 혼조 / 특이 이슈 없음 / 추세 관망
- `sell` (매도): 부정적 뉴스 우위, 단기 악재 확인
- `strong_sell` (풀매도): 중대 악재 (실적 쇼크·규제·치명적 이슈) + 섹터도 부정적

## Rules

- **Source URLs must come from fetched data or web tool results** — do not invent.
- `stocks` array must preserve `stocks.yml` order and include every stock.
- For deep_dive stocks, `deep_dive` 섹션 필수. Other stocks는 생략 가능.
- For no-material-news days, `recommendation: "hold"`, `rationale: "특이 이슈 없음"` OK.
- `impact`는 **한국 시장 / 해당 종목**에 대한 영향 기준.
  - KOSPI +1% 같은 지수 지표: `positive` (상승=호재)
  - USD/KRW 상승: 수출주엔 긍정, 수입주엔 부담 — 종합해서 `neutral` 또는 `negative` 기본값
  - VIX 상승: `negative`
- `top_stories`는 최대 3개. 4개 이상은 핵심이 희석됨.
- `overall_impact`는 전체 macro 분위기. 지표 상승 + 긍정 뉴스 우위면 `positive`.
- If `.tmp/news.json` missing/empty, stop and report — do not fabricate.
