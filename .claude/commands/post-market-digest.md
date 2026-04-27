---
description: 23:00 KST post-market news digest — aggregate news that may impact tomorrow's KRX
---

## 목적 — 장 마감 후부터 다음 브리핑 전까지의 시장 영향 뉴스 모음

매일 **23:00 KST** 발행. 한국 장 마감 (15:30) 이후부터 발행 시점까지 발생한, 내일 시장에 영향을 줄 만한 뉴스만 raw 형태로 집계한다. 오늘 회고나 종목별 예측은 하지 않음 — 그건 다음 날 07:30 `/daily-report` 의 일.

**평일 발행본**: 4 섹션 (한국 마감 후 / 미국 시초 / 글로벌 매크로 / 포트폴리오 시간외 공시)
**주말 발행본**: 2 섹션 (글로벌 매크로 / 미국 시장)

## 입력

- `.tmp/news.json` — `fetch_news.py` 가 발행 직전에 생성한 raw 스크랩
- `stocks.yml` — 포트폴리오 종목 코드 (공시 필터에 사용)
- 23:00 KST 시점 미국 시장 데이터 — yfinance 또는 Worker `/ticker` 로 직접 확인

## 출력

- `.tmp/digest.json` — 큐레이팅 결과 + agent 가 작성한 요약 / impact 라벨
- `docs/digest.html` — render.py 가 위 JSON 으로 렌더링
- `git commit -m "digest: YYYY-MM-DD post-market"` + push

## Steps

1. **환경 확인** + 환경 셋업 (필요시)
   ```bash
   python3 -m venv .venv 2>/dev/null || true
   .venv/bin/pip install -q -r requirements.txt
   ```

2. **뉴스 수집.** `.venv/bin/python scripts/fetch_news.py` 재실행 → `.tmp/news.json` 갱신.

3. **시간 윈도우 필터링.** 오늘 15:30 KST 이후 `published_at` 만 후보로. 주말이면 어제 (또는 금요일) 15:30 이후 윈도우.

4. **섹션별 큐레이션.** `.tmp/digest.json` 작성:

   ```json
   {
     "date": "2026-04-27",
     "generated_at": "2026-04-27T23:00:00+09:00",
     "next_briefing": "2026-04-28 07:30",
     "tldr": "한 줄 요약 30자 이내, 내일 시장 영향 핵심 (선택)",
     "korea_after_close": [
       {
         "headline": "...",
         "summary": "1-2 문장, 영향 추정",
         "impact": "positive|neutral|negative",
         "source": "출처 매체",
         "url": "https://...",
         "published_at": "2026-04-27T18:10:00+09:00"
       }
     ],
     "us_market": {
       "indices": [
         {"name": "S&P 500", "value": "5,512.30", "change_pct": "+0.42%", "direction": "up"},
         {"name": "NASDAQ", "value": "...", "change_pct": "...", "direction": "up"},
         {"name": "SOX",    "value": "...", "change_pct": "...", "direction": "up"},
         {"name": "VIX",    "value": "...", "change_pct": "...", "direction": "down"}
       ],
       "proxies": [
         {"symbol": "NVDA", "value": "$132.40", "change_pct": "+2.30%", "direction": "up"},
         {"symbol": "MU",   "value": "...",     "change_pct": "...",     "direction": "up"}
       ],
       "headlines": [
         {"headline": "...", "summary": "...", "impact": "...", "source": "...", "url": "..."}
       ]
     },
     "macro": [
       {"headline": "FOMC 회의록 — '...'", "summary": "...", "impact": "negative",
        "source": "...", "url": "...", "published_at": "..."}
     ],
     "disclosures": [
       {"code": "005930", "name": "삼성전자", "title": "주요사항보고서 — 자기주식 취득 결정",
        "url": "https://dart.fss.or.kr/...", "impact": "positive",
        "published_at": "2026-04-27T17:45:00+09:00"}
     ]
   }
   ```

5. **렌더.** `.venv/bin/python scripts/render.py .tmp/digest.json --digest`
   - `docs/digest.html` 생성/갱신
   - `index.html` 은 이 시점에 건드리지 않음 — 별도 JS 라우팅이 시간대 보고 digest.html 로 redirect

6. **커밋 & 푸시.**
   ```bash
   git add docs/digest.html .tmp/news.json 2>/dev/null
   git commit -m "digest: $(date +%Y-%m-%d) post-market"
   git pull --rebase origin main || true
   git push
   ```

## 큐레이션 기준

각 섹션의 게이트 — "내일 KRX 에 영향 줄 만한가?" 가 단일 기준. 영향 없으면 컷.

### 🇰🇷 한국 장 마감 후 (5-10 항목)
- ✅ **포함**: 한국은행 통화정책 발표, 금융위·금감원 규제, 정부 부양책, 산업정책, KRX 시장 운영 변경, 대기업 호악재 (실적 발표·M&A·소송), 주요 섹터 이슈
- ❌ **제외**: 정치 일반, 사회 일반, 단순 보도자료, 어제 이미 나온 얘기

### 🇺🇸 미국 장 (시초)
- 인덱스: S&P 500 / NASDAQ / SOX / VIX 4개 고정. 23:00 시점 (장 시작 30분 후) 값.
- 프록시 종목: 우리 포트폴리오의 `overnight_proxy` 에 자주 등장하는 5-7개 종목 시초가 (NVDA, MU, GEV, ETN, XBI, IBB, AMAT 등). yfinance 로 직접 fetch.
- 헤드라인 3-5건: 미국 빅테크 호악재, FOMC, 매크로 데이터 발표 (CPI/PPI/고용지표), 워싱턴 정책

### 🌏 글로벌 매크로 (3-5 항목)
- ✅ FOMC, ECB, PBoC, BOJ 통화정책 / 회의록
- ✅ CPI, PPI, 고용지표 발표
- ✅ 무역 / 관세 / 규제 (미·중, 미·EU)
- ✅ 원유 / 금 / BTC 큰 변동 + 배경
- ✅ 주요국 정세 (지정학적 리스크)
- ❌ 단순 환율 변동 (코멘트 없는 시세)

### 💼 포트폴리오 시간외 공시 (있을 때만)
- 우리 포트폴리오 (`stocks.yml` 코드 21개) 가 한국 장 마감 후 (15:30~) 발표한 공시
- 주요사항보고서 / 실적 / 자사주 / 유증 / 분할 / M&A 등 가격 영향 큰 것만
- 정기보고서 (분기보고서 일반) 는 별 영향 없으면 제외

## Rules

- **중복 차단**: 같은 사건이 여러 매체에 나오면 **가장 reliable / 한국어 매체** 1개 선택. 똑같은 헤드라인 여러 번 X.
- **빈 섹션**: 해당 윈도우에 게이트 통과한 뉴스가 0개면 그 섹션 자체를 `digest.json` 에서 빈 배열 / 빈 객체로 두면 템플릿이 자동 숨김. "특이 공시 없음" 같은 placeholder 표시 X.
- **주말**: 한국 장이 안 열리므로 `korea_after_close` · `disclosures` 는 빈 배열. `us_market` (전 영업일 마감 데이터 또는 라이브) + `macro` 만 채움.
- **영어 / 코드 표기**: 헤드라인은 한국어. 매체명·종목 티커는 원어 (예: "Bloomberg", "NVDA").
- **Source URL**: 반드시 fetched 데이터 또는 web tool 결과에서. 임의 생성 금지.
- **`tldr` 필드**: 선택. 채우면 OG description 으로도 쓰임. 30자 이내, 내일 시장 영향 핵심.
- **`next_briefing` 필드**: "YYYY-MM-DD HH:MM" 형식. 평일 23:00 발행본은 다음 평일 07:30, 금요일 23:00 발행본은 월요일 07:30.

## 결과 보고

발행 후 한 단락 요약:
```
📰 4/27 23:00 다이제스트 발행
- 한국 마감 후 N건 / 미국 시초 헤드라인 N건 / 매크로 N건 / 공시 N건
- TL;DR: <tldr>
- 다음 브리핑: 2026-04-28 07:30
```
