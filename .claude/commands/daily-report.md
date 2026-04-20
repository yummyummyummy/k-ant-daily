---
description: Generate and publish today's pre-market stock briefing
---

Generate today's pre-market briefing for the stocks in `stocks.yml` and publish it to GitHub Pages.

## Steps

1. **Fetch raw news.**
   Run `.venv/bin/python scripts/fetch_news.py`. This writes `.tmp/news.json` with:
   - `macro.news`, `macro.indices`, `macro.fx`
   - For each stock: `news[]` (recent titles/links/dates) and `disclosures[]` (공시)

2. **Read the raw data.** Read `.tmp/news.json` and look across all stock news,
   disclosures, and macro news. Identify recurring themes, sector-level stories, and
   anything material (공시, 실적, 가이던스, 규제, 주요 계약 등).

3. **Compose the summary.** Write a file `.tmp/summary.json` matching the schema below.
   Keep language **중립적·사실 기반**. No investment advice, no hype. Lead with "what
   happened" before "what it means". When citing a claim, include a source link from the
   raw data; never fabricate URLs.

4. **Render.** Run `.venv/bin/python scripts/render.py .tmp/summary.json`. This writes
   `docs/YYYY-MM-DD.html`, updates `docs/index.html`, and rebuilds `docs/archive.html`.

5. **Commit & push.** From the repo root:
   ```
   git add docs/ stocks.yml
   git commit -m "report: YYYY-MM-DD briefing"
   git push
   ```
   (Skip push if no remote is configured yet — just report that.)

6. **Report the URL.** Print the published URL
   (`https://yummyummyummy.github.io/k-ant-daily/YYYY-MM-DD.html`) and a one-line summary
   of what today's briefing emphasizes.

## summary.json schema

```json
{
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 with KST offset",
  "headline": "한 줄 헤드라인 (30자 이내)",
  "tldr": "카톡 미리보기용 한 줄 요약 (80자 이내, 투자 권유 금지)",
  "macro": {
    "summary": "오늘 거시 흐름 2~3문장",
    "indicators": [
      {"name": "KOSPI", "value": "2,680.10", "change": "+0.5%"},
      {"name": "USD/KRW", "value": "1,370.50", "change": "-0.2%"}
    ],
    "key_points": [
      {
        "point": "핵심 포인트 헤드라인",
        "detail": "1~2문장 설명",
        "sources": [{"title": "연합뉴스", "url": "https://..."}]
      }
    ]
  },
  "sectors": [
    {
      "name": "반도체",
      "summary": "섹터 흐름 1~2문장",
      "affected": ["삼성전자", "SK하이닉스"],
      "key_points": [
        {"point": "...", "detail": "...", "sources": [{"title": "...", "url": "..."}]}
      ]
    }
  ],
  "stocks": [
    {
      "code": "005930",
      "name": "삼성전자",
      "market": "KOSPI",
      "sentiment": "positive | neutral | negative",
      "summary": "해당 종목의 오늘 포인트 2~3문장",
      "key_points": [
        {
          "point": "뉴스/이벤트 헤드라인",
          "detail": "1~2문장 설명",
          "sources": [{"title": "출처명", "url": "https://..."}]
        }
      ],
      "disclosures": [
        {"title": "공시 제목", "url": "https://...", "date": "YY.MM.DD"}
      ]
    }
  ]
}
```

## Rules

- **Source URLs must come from `.tmp/news.json`** — do not invent links.
- `stocks` array must preserve the order in `stocks.yml` and include every stock,
  even if there is little news (summarize as "주요 이슈 없음").
- `sentiment` is a sentiment about **news flow**, not a price prediction.
- Sections with no content should be omitted (empty arrays are fine, but don't invent filler).
- Keep `tldr` punchy — it shows up in KakaoTalk link previews.
- If `.tmp/news.json` is missing or empty, stop and report the problem; do not fabricate.
