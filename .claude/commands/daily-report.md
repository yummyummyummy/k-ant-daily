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

#### 2-1. 거시 지표 발표일 (이번 달 + 다음 달)
- **FOMC**: federalreserve.gov 일정
- **한국은행 금통위**: bok.or.kr 일정
- **미국 CPI/PPI/고용보고서**: BLS 일정
- **한국 수출입 동향**: 매월 1일
- **MSCI/FTSE 정기변경**: 분기말

WebFetch 또는 WebSearch 로 확정 일자 확인 후 추가. 추측 금지.

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
