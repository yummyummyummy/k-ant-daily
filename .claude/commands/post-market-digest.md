---
description: 23:00 KST post-market news digest — aggregate news that may impact tomorrow's KRX
---

## 목적

매일 **23:00 KST** 발행. 한국 장 마감 (15:30) 이후부터 발행 시점까지 발생한 뉴스 / 미국 시장 동향 / 보유종목 시간외 공시를 사실 기반으로 정리한다.

**예측 / 종목 추천 / 매매 의견 금지.** 사실 + 시점 + 출처 위주의 raw 다이제스트.

**평일**: 4 섹션 (한국 마감 후 / 미국 장중 / 글로벌 매크로 / 포트폴리오 공시)
**주말**: 2 섹션 (글로벌 매크로 / 미국 시장)

## 입력

- `.tmp/news.json` — 발행 직전 `fetch_news.py` 가 다시 만든 raw 스크랩
- `stocks.yml` — 포트폴리오 종목
- `docs/events.json` — 캘린더 (다가오는 이벤트 섹션에 활용)
- 23:00 KST 시점 미국 시장 데이터 — WebFetch 또는 yfinance

## 출력

- `.tmp/digest.json`
- `docs/digest.html` — `render.py --digest` 가 위 JSON 으로 렌더링
- `git commit -m "digest: YYYY-MM-DD post-market"` + push

### digest.json schema

```json
{
  "date": "2026-05-27",
  "tldr": "한 줄 핵심 — 옵션",
  "sections": [
    {"heading": "🇰🇷 한국 장 마감 후 (15:30~)", "bullets": ["..."]},
    {"heading": "🇺🇸 미국 장중 (현지 시간 09:30~)", "bullets": ["..."]},
    {"heading": "🌏 글로벌 매크로", "bullets": ["..."]},
    {"heading": "📁 포트폴리오 공시 (시간외)", "bullets": ["..."]}
  ],
  "highlights": [
    {"kind": "stock", "title": "...", "detail": "...", "url": "..."}
  ],
  "upcoming": [
    {"date": "2026-05-28", "title": "...", "category": "macro"}
  ]
}
```

## Steps

### 0. 환경 셋업
```bash
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt
```

### 1. 데이터 재수집
```bash
.venv/bin/python scripts/fetch_news.py
```

### 2. 시간 윈도우 필터링
- 평일: 오늘 15:30 KST 이후 발행된 뉴스/공시만
- 주말: 금요일 15:30 이후 ~ 현재까지

### 3. 미국 시장 스냅샷 확인
23:00 KST = 미국 동부시간 9:00~10:00. WebFetch 로 S&P 500 / NASDAQ / SOX 등락률 + 주요 헤드라인 확인.

### 4. 섹션별 큐레이션
각 섹션에 들어갈 항목:
- **🇰🇷 한국 장 마감 후**: 시간외 공시, 한국 산업/정책 뉴스, 인접 아시아 시장
- **🇺🇸 미국 장중**: 주요 지수 흐름, 메가캡 등락, 보유 바이오 종목 미국 proxy (XBI, IBB) 흐름
- **🌏 글로벌 매크로**: FX (USD/KRW), 원자재 (WTI, 금), 비트코인, 미국채 수익률
- **📁 포트폴리오 공시**: 보유 종목 시간외 공시 / 보도자료

각 bullet 은:
- 사실만 (예측/판단 금지)
- 시점 명시 ("23:10 한경", "21:45 로이터")
- 짧고 명확 (1~2줄)

### 4.5. 지난 이벤트 결과 채우기 (`events.yml` 의 `result`)
오늘 발표된 이벤트 (FOMC, CPI, 고용보고서, 한은 금통위, 실적 등) 가 `events.yml` 에 있고 `result` 가 비어있으면, 실제 결과 + 시장 반응을 조사해 채운다.
```yaml
result:
  outcome: positive | negative | neutral | asexpected
  summary: "사실 + 시장 반응 1~2줄"
  filled_at: "YYYY-MM-DD"
```
채운 뒤 `build_calendar.py` + `render.py` (캘린더 모드) 도 재실행해서 docs/events.json 갱신. 추측 금지 — 확인된 사실만.

### 5. Highlights (3~6개)
오늘~내일 영향이 가장 큰 항목을 별도로 뽑아냄. 보유 종목 관련 공시 우선.

### 6. Upcoming
`docs/events.json` 에서 향후 3~7일 이벤트를 뽑아 `upcoming` 에 채움.

### 7. 렌더 + commit
```bash
.venv/bin/python scripts/render.py --digest
git add docs/digest.html
git commit -m "digest: $(date +%Y-%m-%d) post-market"
git push origin main
```

## 출력 규칙

- 자연스러운 한국어. 영어 schema 키 노출 금지
- "예측", "전망", "강력 매수" 같은 directional language 금지
- 사실 동사만 ("올랐다", "발표됐다")
- 출처 (매체명 + 시점) 모든 bullet 에 포함

## Caveat

- DART 공시는 17:00 까지 마감되므로 23:00 digest 에는 거의 없음 — 평일 포트폴리오 섹션이 비어있을 수 있음
- 미국 시장은 시작 직후라 "장중 흐름" 일 뿐이고 종가가 아님. bullet 에 명시
