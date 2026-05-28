---
description: Refresh the monthly events calendar and holdings tracker
---

## 컨셉

**예측이나 베팅이 아닌 "월간 이벤트 캘린더 + 보유종목 일일 트래킹"** 서비스의 일일 갱신 작업입니다.

매일 아침 07:30 KST 에 실행되어:
1. 보유종목 시세/뉴스/공시 최신화 (트래킹 패널)
2. 캘린더 이벤트 소스 갱신 (ClinicalTrials.gov, DART)
3. `events.yml` 큐레이션 — 새로 알게 된 일정 추가
4. 캘린더 + 인덱스 HTML 렌더링
5. commit + push

**예측 / 추천 / 베팅 / 회고 (review) 는 없음.** 모든 산출물은 사실/일정 기반.

## Steps

### 0. 오늘 KST 날짜 확정
시스템에서 직접 확인 (`date "+%Y-%m-%d"`). 기억에 의존하지 말 것.

### 1. 데이터 fetch
```bash
.venv/bin/python scripts/fetch_news.py             # 보유종목 시세/뉴스/공시
.venv/bin/python scripts/fetch_clinical_trials.py  # CT.gov 임상 일정
.venv/bin/python scripts/fetch_dart.py             # DART 공시 (DART_API_KEY 필요)
```

각각 실패해도 다음 단계는 진행. 실패한 source 는 빈 결과로 처리됨.

### 1.5. 지난 이벤트 결과 채우기 (`result` 필드)

`events.yml` 에서 **이미 지난** 이벤트 (date+time 이 현재보다 과거) 중 `result` 가 비어있는 것을 찾아 실제 결과를 조사해 채운다.

- 대상: FOMC, CPI, 고용보고서, 한은 금통위, 실적, 학회 readout 등 "발표/결과" 성격 이벤트
- WebSearch/WebFetch 로 실제 결과 + 시장 반응 확인
- schema:
  ```yaml
  result:
    outcome: positive | negative | neutral | asexpected   # 시장 관점
    summary: "기준금리 2.25%로 동결. 원화 강보합. 코스닥 +0.4%."  # 사실 + 시장 반응 1~2줄
    filled_at: "2026-05-28"
  ```
- `outcome` 기준: 위험자산에 우호적이었으면 positive, 부담이었으면 negative, 무반응 neutral, 컨센서스 부합 asexpected
- 추측 금지 — 확인된 사실만. 아직 결과를 못 찾으면 비워두고 다음 실행에서 재시도
- 휴장일 등 "결과" 가 의미없는 이벤트는 건드리지 말 것

### 2. 이벤트 큐레이션 (`events.yml` 갱신)

`events.yml` 은 사람이 검증한 일정만 들어가는 신뢰 source. 다음을 검토하고 필요하면 추가:

> **원칙: forward 이벤트만.** "수주 났다 / 실적 나왔다" 같은 **사후 공시는 캘린더에 넣지 않는다**. 오직 **예정된 미래 일정** (확정 발표일 or 규칙적 발표일) 만. 사후 결과는 이벤트의 `result` 필드로 채운다 (별도).
>
> **바이오 편향 금지 — 전 섹터 커버.** 아래 2-5 섹터별 체크리스트로 모든 보유 종목의 forward 이벤트를 매일 점검한다.

#### 2-1. 거시 지표 발표일 (이번 달 + 다음 달, 확정일만)
매달 다가오는 1~2개월치를 **확정 일자**로 추가 (월간 반복 지표는 발표 때마다 다음 회차 보충):
- **FOMC** (importance 3): federalreserve.gov. 2026: 6/16-17, 7/28-29, 9/15-16, 10/27-28, 12/8-9
- **한은 금통위 (통화정책방향)** (imp 3): 2026 확정 — 7/16, 8/27, 10/22, 11/26
- **미 CPI** (imp 3): 2026 확정 — 6/10(5월), 7/14(6월), 8/12(7월), 9/11(8월), 10/14(9월), 11/10(10월), 12/10(11월). 모두 등록됨
- **미 고용보고서(NFP)** (imp 3): BLS·ALFRED 가 WebFetch 차단(403) → **매달 WebSearch "US jobs report release date [월] 2026" 로 확정일 확인 후 보충**. 현재 6/5(5월분)만 등록 — 확인되는 대로 다음 달치 추가 (추측 금지)
- **미 PCE** (imp 2): BEA, 매월 말. 2026: 5월분 6/25, 6월분 7/30 …
- **잭슨홀** (imp 3): 매년 8월 말 (2026 8/27-29, 연설 8/28)
- **선물옵션 동시만기** (imp 2): 분기 2번째 목요일 (3·6·9·12월) — 2026: 6/11, 9/10, 12/10
- **한국 수출입동향** (imp 1): 매월 1일 / **한국 CPI** (imp 2): 매월 초
- **MSCI 정기변경** (imp 2): 반기(5·11월)·분기(2·8월)

**중요**: 미 CPI·고용은 BLS 가 막혀 WebFetch 안 되면 WebSearch 로 "US CPI release date [월] 2026" 확인. 확정 안 되면 넣지 말 것 — 추측 금지. 매달 실제 발표 후 다음 달치 보충.

#### 2-2. 바이오 학회 (보유 바이오 종목 영향)
보유 바이오: 알테오젠 (196170), 에이비엘바이오 (298380), 앱클론 (174900),
보로노이 (310210), 큐리옥스 (445680), 코아스템켐온 (166480), 셀리드 (299660),
디앤디파마텍 (347850).

학회별 매년 일정:
- AACR (4월), ASCO (6월 초), EHA (6월), ESMO (9~10월), ASH (12월), JPM Healthcare (1월)
- 디앤디파마텍 (GLP-1) 은 ADA (6월), EASD (9월) 도 주목

#### 2-3. KRX 휴장일
음력 기반 (설, 추석, 부처님오신날) 은 매년 다름. 한국거래소 공식 일정 확인 후 평일에 떨어지는 휴장일만 추가.

#### 2-4. 보유 종목 임상 readout / IR
보도자료/뉴스에서 "OOO 분기 톱라인 예정" 같은 forward-looking 문구 발견하면 추가. "예상" 으로 명시 (`tags: [..., "estimated"]`).

#### 2-5. 섹터별 forward 이벤트 체크리스트 (전 보유 종목)
매일 아래를 점검하고 **확정/규칙적 발표일이 잡히면** events.yml 에 추가 (forward only, per_stock 작성):

- **공통 (전 종목)**: 분기 실적 발표일. 한국 기업은 잠정실적 공시예정 (DART) 또는 IR 공지로 확인. 미정이면 추가하지 말고, 발표일이 잡히면 추가. (대략: Q2→7월말~8월중, Q3→10월말~11월중)
- **반도체** (삼성전자 005930·SK하이닉스 000660·한미반도체 042700·넥스트칩 396270): 글로벌 피어 실적 (마이크론·엔비디아·TSMC — 발표일 확정적, HBM/메모리 선행지표), CES(1월), 삼성·SK 잠정실적
- **자동차** (현대차 005380): 월간 판매실적 (매월 1일경), 분기 실적, 글로벌 피어 (테슬라 등)
- **전력기기** (HD현대일렉트릭 267260·LS일렉트릭 010120): 분기 실적, 대형 수주 IR·전력망 정책 발표 일정
- **조선** (HD한국조선해양 009540): 분기 실적, 수주 가이던스 IR
- **건설/플랜트** (삼성E&A 028050): 분기 실적, 중동 발주 일정
- **증권** (한국금융지주 071050): 분기 실적
- **카지노** (파라다이스 034230): 월간 카지노 매출 (매월 초)
- **플랫폼** (카카오 035720): 분기 실적, 규제·신규 서비스 발표 예정일

글로벌 피어 실적일은 WebSearch 로 확정일 확인 ("Nvidia/Micron/Tesla earnings date"). 한국 종목 실적일은 미확정이면 넣지 말 것 — 추측 금지.

#### 2-6. 종목별 매핑된 산업·학술 학회 (매년 일정 재확인)
이미 events.yml 에 등록된 매핑 — 매년 날짜만 WebSearch 로 갱신:
- 반도체 (005930·000660·042700): Hot Chips(8월), CES(1월). HBM 관련 GTC 등
- 넥스트칩 (396270): AutoSens Europe(9월) — ADAS 비전
- 전력기기 (267260·010120): CIGRE Paris Session(격년 짝수해 8월)
- 조선 (009540): Posidonia(격년 짝수해 6월), Gastech(9월, LNG)
- 건설/플랜트 (028050): ADIPEC(11월), Gastech(9월)
- 카지노 (034230): G2E(9~10월)
- 바이오 종양 (196170·298380·174900·310210): ASCO·ESMO, SITC(11월, 면역항암)
- 바이오 혈액 (174900·166480): EHA·ASH
- 디앤디파마텍 (347850): ADA(6월)·EASD(9월) — GLP-1
- 셀리드 (299660): World Vaccine Congress(10월), SITC
- 큐리옥스 (445680): CYTO(6월, ISAC) — Laminar Wash/NIST 표준화

학회 촉매가 약한 종목: 한국금융지주(증권), KODEX(ETF) — 실적/거래대금/지수 추종이라 학회 없음. 카카오는 ifkakao(가을) 일정 공개되면 추가.

#### 2-7. 종목별 이벤트 레이더 (`watch_queries`, 있으면)
`stocks.yml` 에 `watch_queries` 가 있는 종목은 그 검색어를 WebSearch 로 돌려 "남이 우리 기술을 쓴/표준화한" 류 간접 신호를 탐지. **구체적 미래 날짜(발표·워크숍·결과공개)가 나오면** events.yml 에 forward 이벤트로, 사후 신호(논문·표준 발표·채택 사례)는 종목 뉴스 컨텍스트로만 (캘린더 X).

#### 추가 시 schema
```yaml
- date: "2026-06-04"        # 다일은 date_range: ["2026-06-04", "2026-06-08"]
  category: "conference"     # macro|conference|holiday|earnings|ir|clinical|disclosure|other
  title: "ASCO 2026 Annual Meeting"
  description: "이 이벤트가 뭔지 factual 한 줄"
  related_codes: ["196170", "298380"]
  per_stock:                 # 종목 특정 이벤트의 핵심 — 캘린더가 종목별로 쪼개 보여줌
    "196170": "이 종목에서 봐야 할 핵심 — 무엇을, 왜 (구체적으로)"
    "298380": "..."
  tags: ["bio", "oncology"]
  source: "https://asco.org/..."
  importance: 3   # 1~3
```

**캘린더는 (종목 × 이벤트) 단위로 표시**된다 — `related_codes` 가 여러 개면 종목 수만큼 칩이 분리되고, 각 칩은 그 종목의 `per_stock` 주목 포인트를 보여줌.

**per_stock 작성 규칙** (가장 중요):
- 종목 특정 이벤트 (학회·임상·실적·공시 등 related_codes 있는 것) 는 **반드시 `per_stock` 작성**
- 각 종목별로 **구체적이고 서로 다르게** — "이 종목은 이 이벤트에서 무엇을 봐야 하는가". 회사의 실제 파이프라인/제품과 연결
- 확실하지 않은 세부(정확한 임상명·phase)는 단정하지 말고 "발표 여부", "관련 데이터 주목" 식으로 hedge
- generic 한 매파/비둘기 시나리오 나열 금지 — 그건 의미 없음. 종목별 관전 포인트가 핵심

**시장 전체 이벤트** (FOMC·CPI·휴장 등 related_codes 없음) 는 `impact` 에 **"📁 보유 영향" 한 단락**만 간결하게 (어떤 보유 종목이 왜 민감한지). 장황한 시나리오 금지.

**원칙**:
- 확정되지 않은 일자는 추가 금지 / 중복 (같은 date + title) 금지
- 거시 일정은 반드시 출처 URL 첨부

### 3. 캘린더 빌드
```bash
.venv/bin/python scripts/build_calendar.py
```

### 4. 렌더링
```bash
.venv/bin/python scripts/render.py
```

### 5. Smoke check
```bash
ls -la docs/calendar.html docs/index.html docs/events.json
```

### 6. Commit + push
```bash
git add docs/ events.yml
git commit -m "report: $(date +%Y-%m-%d) calendar 갱신 + 보유종목 트래킹"
git push origin main
```

## 출력 규칙

- 사용자 대면 텍스트는 자연스러운 한국어. 영어 schema 키 노출 금지
- 추측성 단어 ("예측", "전망", "강력 추천") 금지
- 종목 추천이나 매매 의견 절대 작성 금지
