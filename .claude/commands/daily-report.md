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

1b. **최근 회고의 교훈 읽기 (학습 피드백).** 최근 5개 평일의 `docs/YYYY-MM-DD.summary.json` 을
    훑어 `review.analysis.lessons` 배열이 있으면 모두 수집. 없으면 skip.

    ```python
    import json, glob, os
    paths = sorted(glob.glob("docs/2*.summary.json"))[-5:]
    recent_lessons = []
    for p in paths:
        try:
            r = json.load(open(p)).get("review", {}).get("analysis", {}).get("lessons") or []
            for les in r:
                recent_lessons.append({"date": os.path.basename(p)[:10], **les})
        except Exception:
            pass
    # recent_lessons 를 읽고 오늘 판정에 반영
    ```

    **적용 방식**: 각 lesson 의 `rule` 이 오늘 판정의 특정 종목에 해당하는 상황인지 검사.
    - 해당하면 rule 을 **따르고**, 해당 종목의 `rationale` 에 "(어제 회고 교훈 반영: …) " 식으로 명시.
    - 해당하지만 오늘은 다르게 갈 근거가 있으면 `rationale` 에 왜 예외인지 명시.
    - 매일 같은 lesson 이 적용돼도 OK — 누적 학습이 목적.

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

6. **Commit & push.**
   ```bash
   git add docs/ stocks.yml
   git commit -m "report: YYYY-MM-DD briefing"

   # Rebase onto origin in case a commit landed on main while we were running
   # (e.g. a refactor push mid-briefing). Without this the final push fails
   # non-fast-forward and the report never reaches GitHub Pages.
   if ! git pull --rebase origin main; then
     # 충돌 가능 파일: docs/index.html · archive.html · accuracy.html ·
     # accuracy/*.html — 전부 render.py가 생성하는 집계 페이지라 우리 쪽
     # 버전으로 잡고 재렌더하면 resolve 된다.
     git checkout --ours -- docs/index.html docs/archive.html docs/accuracy.html docs/accuracy/ 2>/dev/null || true
     .venv/bin/python scripts/render.py .tmp/summary.json
     git add docs/
     git rebase --continue
   fi
   git push
   ```

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
      "detail": "..."
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
      "rationale": "첫 문장은 50자 내외 forward-looking 한 줄 전망 (종목 카드 요약에 추출됨). 이후 문장은 신호 조합·근거 상술.",
      "summary": "오늘 세션 예측 2~3문장 (forward-looking)",
      "key_points": [
        {"point": "...", "detail": "...", "impact": "...",
         "published_at": "2026-04-20T15:57:00+09:00",
         "sources": [...]}
      ],
      "deep_dive": { "business": "...", "market": "...", "competitors": [...],
                     "research_notes": "...", "risks": "...", "sources": [...] },
      "disclosures": [{"title": "...", "url": "...", "date": "YY.MM.DD"}],
      "action_plan": {
        "position_size": "4%",
        "entry_zone": "224,000 ~ 226,000",
        "stop_loss": "-2.0%",
        "target": "+3.5%",
        "horizon": "1-3일 단기",
        "scenarios": {
          "if_gap_up":     "갭상승 +1% 이내 시초가 매수, +2% 이상이면 5분봉 음봉 1개 보고 재진입",
          "if_gap_down":   "갭다운 -1% 이상 진입 보류, -2% 이상 손절 자동 발동",
          "if_target_hit": "+3.5% 도달 시 절반 익절, 나머지 trailing stop -1%",
          "if_stop_hit":   "즉시 청산, 다음 날 재진입 금지"
        }
      }
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

### 단계 3: `confidence` 부여 (calibration 강화)

**기준 신호:** `news_sentiment` 와 `overnight_signal` 두 directional 신호의 일치도. `priced_in` 은 modifier (역신호 작용).

- `high`: news 와 overnight 가 명확히 같은 방향 (둘 다 positive/up 또는 둘 다 negative/down) **+ priced_in=False**
- `medium`: 두 directional 신호가 같은 방향이지만 priced_in=True (선반영 → 동력 약화), **또는** 한 신호만 명확하고 다른 하나는 정확히 neutral (반대 방향 X)
- `low`: 두 directional 신호가 상충 (positive vs down 등), 둘 다 neutral, 종목 뉴스 부재, 또는 어떤 신호라도 명백히 반대 방향

**금지 (4/21~4/27 5일치 누적 분석 결과 반영):**
- 어떤 신호라도 반대 방향이면 medium 부여 X — low 로 분류. 이전 정의 ("2 신호 동의" = medium) 가 너무 관대해서 medium(45%) < low(50%) calibration 역전 발생.
- "애매하니 medium" 식 default 회피 금지 — 신호 약하면 low 가 정답.

## `action_plan` — 운용 가이드 (필수)

기관 트레이더 룰북 형식. 종목별 진입/손절/익절/비중을 정량화. **가상 시나리오** 임을 disclaimer 에서 명시.

### 절대 원칙 — 템플릿 금지

**같은 문자열을 두 종목에 쓰지 마라.** 두 종목의 `action_plan` 의 어느 필드든 동일한 값이 나오려 하면, 멈추고 아래 4축 (`held`, `volatility_tier`, `nxt_gap_pct`, `event_window`) 중 무엇을 무시했는지 점검하라. 두 종목이 같은 (recommendation, confidence) 라도 보유 여부·변동성·NXT 갭·이벤트가 다르면 `position_size`·`stop_loss`·`scenarios` 모두 달라야 한다.

특히 `"0% — 신규 진입 X"` / `"-3% (보유 시 trailing)"` / `"전일 고가 도달 시 평가"` 같은 옛 템플릿 문자열은 **금지**. hold 라도 종목별로 sub-state 가 다르다 (아래 hold 4분류 참조).

### Step 0 — 입력 사실 추출 (모든 종목, action_plan 작성 전 필수)

각 종목마다 4개 변수를 먼저 계산하라. 이게 곧 action_plan 의 입력이 된다.

```python
# 1. held — 친구가 보유 중인가?
held = bool(stock.get("owners"))

# 2. volatility_tier — 20일 일평균 절대 변동률
closes = stock["history"]["closes_20d"]
moves = [abs((closes[i]-closes[i-1])/closes[i-1]*100) for i in range(1, len(closes))]
avg_abs = sum(moves) / len(moves)
if   avg_abs < 2.0: vol_tier = "low"     # 카카오·하이브 류
elif avg_abs < 3.0: vol_tier = "mid"     # 삼성전자·키움 류
elif avg_abs < 4.0: vol_tier = "high"    # SK하이닉스·한미반도체 류
else:               vol_tier = "extreme" # 셀리드·앱클론·삼성E&A 류

# 3. nxt_gap_pct — NXT 프리오픈 (참값 있으면 우선)
nxt_gap_pct = stock.get("nxt_pre_open", {}).get("change_pct")  # None 가능

# 4. event_window — 임박 이벤트 키워드 (호가 기간 확장 트리거)
EVENT_KEYWORDS = ["실적", "공시", "FDA", "임상", "M&A", "합병", "분할", "수주", "배당락"]
event_window = any(any(kw in (kp.get("point","") + kp.get("detail","")) for kw in EVENT_KEYWORDS)
                   for kp in stock.get("key_points", []))
```

이 4개 변수를 `rationale` 에 굳이 쓸 필요는 없으나, action_plan 의 모든 수치는 이걸 통과해야 한다.

### 변동성 보정 (`vol_buffer`) — stop_loss·target 의 폭

| vol_tier | 일평균 변동 | stop_loss 가중 | target 가중 |
|---|---|---|---|
| low | <2.0% | 기본 | 기본 |
| mid | 2.0~3.0% | +0.5%p | +0.5%p |
| high | 3.0~4.0% | +1.0%p | +1.0%p |
| extreme | >4.0% | +1.5%p | +1.5%p |

기본값에 가중치 더해서 종목별 stop·target 산출. 예: buy 기본 stop_loss `-2.0%` 인데 vol_tier=high 면 `-3.0%`. 이 가중은 **필수**, 무시 금지.

### 비중 (`position_size`) — held × recommendation 분기

#### 신규 진입 (held=False) — buy 계열만 의미 있음

| recommendation | high | medium | low |
|---|---|---|---|
| strong_buy | `"5%"` | `"3%"` | (action_plan 자체 생략) |
| buy | `"3%"` | `"2%"` | (action_plan 자체 생략) |
| hold/sell/strong_sell | (action_plan 자체 생략 — 신규 진입할 일 없음) | | |

#### 보유 관리 (held=True) — 모든 recommendation 에 대해 보유분 액션

| recommendation | position_size 표현 |
|---|---|
| strong_buy | `"보유분 유지 + 추가 매수 N% 검토"` (N은 high=3, medium=2) |
| buy | `"보유분 유지, -X% 조정 시 분할매수"` (X는 vol_buffer 반영) |
| **hold-accumulate** | `"비중 유지, 약세 시 분할매수 여지"` |
| **hold-neutral** | `"현재 비중 유지 — 별도 액션 없음"` |
| **hold-defensive** | `"보유분 1/3~1/2 익절 검토"` |
| sell | `"보유분 절반 청산, 잔여분 trailing"` |
| strong_sell | `"보유분 즉시 전량 청산"` |

`hold` 의 4분류는 다음 sub-state 규칙을 따른다.

#### `hold` sub-state 분기 (held 따라)

```
held=False                     → action_plan 자체 생략 (필드 전체 제거)
held=True ∧ news_sent=positive → hold-accumulate
held=True ∧ news_sent=negative → hold-defensive
held=True ∧ 그 외              → hold-neutral
```

이 4분류는 `position_size`·`scenarios` 가 모두 다르다. 같은 hold 라도 카카오(neutral)와 보로노이(neutral, 변동성 4%)는 stop_loss 폭이 달라야 한다.

### 진입가 (`entry_zone`)

- **held=False, buy 계열**: 전일 종가 ±0.5% (vol_tier=high/extreme 면 ±1.0%). NXT 갭 있으면 NXT 시초가 ±0.3% 도 병기. 예: `"443,000 ~ 448,000 (NXT 시초가 시 ±0.3%)"`.
- **held=True, buy 계열**: `"보유분 평단 무관 — 추가 매수는 -X% 조정 후"` (X는 vol_buffer)
- **hold/sell/strong_sell**: 필드 통째 생략 (빈 문자열 X)

### 손절 (`stop_loss`) — 변동성 보정 적용

| recommendation | low | mid | high | extreme |
|---|---|---|---|---|
| strong_buy | `-2.5%` | `-3.0%` | `-3.5%` | `-4.0%` |
| buy | `-2.0%` | `-2.5%` | `-3.0%` | `-3.5%` |
| hold-accumulate | `-2.5% (보유분)` | `-3.0%` | `-3.5%` | `-4.0%` |
| hold-neutral | (생략 가능) | `-3.0% (절반 익절)` | `-4.0%` | `-5.0%` |
| hold-defensive | `-2.0% (선제적)` | `-2.5%` | `-3.0%` | `-3.5%` |
| sell | `+2.0%` | `+2.5%` | `+3.0%` | `+3.5%` |
| strong_sell | `+2.5%` | `+3.0%` | `+3.5%` | `+4.0%` |

### 익절 (`target`) — 변동성 보정 적용

| recommendation | low | mid | high | extreme |
|---|---|---|---|---|
| strong_buy | `+5%` | `+6%` | `+7%` | `+8%` |
| buy | `+3%` | `+3.5%` | `+4.5%` | `+5.5%` |
| hold-accumulate | `+2.5%` | `+3.0%` | `+3.5%` | `+4.5%` |
| hold-neutral | 생략 | 생략 | 생략 | 생략 |
| hold-defensive | `+1.5% (1/2 익절)` | `+2.0%` | `+2.5%` | `+3.5%` |
| sell | `-3%` | `-3.5%` | `-4.5%` | `-5.5%` |
| strong_sell | `-5%` | `-6%` | `-7%` | `-8%` |

### 시간 (`horizon`)

- `event_window=False` → `"1-3일 단기"`
- `event_window=True` → `"1-2주 스윙 (이벤트: <키워드>)"`. 키워드는 `key_points` 에서 매칭된 단어.

### 시나리오 (`scenarios`) — NXT 갭 기반 정량 분기

`if_gap_up` / `if_gap_down` 분기점을 **NXT 갭 ± 0.5%** 로 잡아라. NXT 데이터 없으면 0% 기준.

**예: 삼성전자 NXT -2.03%, strong_sell, vol_tier=mid (전일 종가 220,000)**
```json
"scenarios": {
  "if_gap_up":     "갭이 NXT(-2.0%)보다 위 (-1.5% 이상) 마감 갭이면 시초가 매도 — NXT 매도세 약화 신호",
  "if_gap_down":   "NXT 수준(-2~-3%) 갭다운이면 추격 매도 자제, -4% 초과 시 -1차 청산 1/3",
  "if_target_hit": "-6% 도달 시 보유분 1/2 청산, 잔여분 trailing -1.5%",
  "if_stop_hit":   "+3% 반등 (stop) 도달 시 즉시 전량 청산, 재진입 금지"
}
```

**예: 카카오 NXT 데이터 없음, hold-neutral, vol_tier=low** → `scenarios` 자체 생략 (의미있는 행동 없음).

**예: 키움증권 NXT +0.5% 가정, buy/medium, vol_tier=mid (전일 종가 445,500)**
```json
"scenarios": {
  "if_gap_up":     "NXT(+0.5%) 부근 갭상승은 시초가 매수, +1.5% 초과 갭은 5분봉 음봉 1개 보고 진입",
  "if_gap_down":   "갭다운 -1% 이내면 지지선(440,000) 매수, -1.5% 초과면 진입 보류",
  "if_target_hit": "+4% 도달 시 절반 익절, 나머지 trailing -1.5%",
  "if_stop_hit":   "-2.5% (vol 보정) 도달 시 즉시 청산, 다음 날 재진입 금지"
}
```

### `scenarios` 작성 강제 규칙

1. 4개 키 (`if_gap_up`, `if_gap_down`, `if_target_hit`, `if_stop_hit`) 중 **두 종목이 동일 텍스트** 가 나오면 다시 써라. 가격·종목명·% 수치를 종목별로 박아 넣어라.
2. `hold-neutral` 은 `scenarios` 통째 생략. 행동이 없는데 시나리오를 적는 건 위선.
3. NXT 데이터가 있으면 반드시 `if_gap_*` 두 키 중 한 곳에는 NXT 가격 또는 NXT 변동률을 명시 (예: "NXT(-2.03%) 수준 갭다운이면…").

### action_plan 자체 생략 조건

다음 중 하나라도 해당하면 `action_plan` 키 자체를 stock 객체에서 제거 (빈 객체 X, null X):

- `held=False ∧ recommendation ∈ {hold, sell, strong_sell}` — 보유 안 하는데 매도 가이드는 의미 없음
- `held=False ∧ confidence=low ∧ recommendation ∈ {buy, strong_buy}` — 진입 강도 부족
- 종목 뉴스·공시 0건 + overnight_signal=neutral + held=False — 모니터 가치도 약함

이 경우 stock 카드는 단순 "관전" 으로 표시되도록 template 가 처리한다.

### 자체 검증 체크리스트 (summary.json 작성 후, render 전)

스스로 답하라:

1. ❓ 두 종목의 `position_size` 가 글자 단위로 같은 게 있나? → 있으면 다시 써라
2. ❓ 두 종목의 `stop_loss` % 가 같은데 vol_tier 가 다르면? → vol_buffer 무시한 것, 다시 써라
3. ❓ NXT 데이터가 있는 종목인데 `scenarios` 에 NXT 가 안 나오면? → 다시 써라
4. ❓ held=True 인데 `position_size` 가 `"0%"` 로 시작하면? → 보유 관리 표현으로 다시 써라
5. ❓ `hold` 종목 중 `hold-neutral`/`hold-defensive`/`hold-accumulate` 분류가 안 된 게 있나? → 분기 다시 하라

다섯 개 다 통과하면 OK.

### Disclaimer 강화 필수

action_plan 은 **가상 운용 시나리오 시뮬레이션**. 실제 매매 권유 절대 아님. 페이지 footer disclaimer 에 이 내용 명시 (template 처리됨).

## Forward-looking 언어 가이드

- ❌ "오늘 +3% 급등했다" → ✅ "어제 +3% 강세에 이어, 간밤 나스닥도 +1.5%로 오늘 개장 초 강세 예상"
- ❌ "오늘 -2% 하락" → ✅ "어제 -2% 마감했으나, 간밤 해당 섹터 미국주는 +0.5%로 반등 가능성"
- ❌ "매수 의견" 단독 → ✅ "매수 (뉴스 긍정 + 간밤 강세 + 선반영 아님)"

## `macro.summary` 하이라이트 — `**...**` 마커

`macro.summary` 는 "⭐ 오늘의 핵심" 섹션 최상단 한 줄 요약. 이 문장 안에
**장중 변동성 핵심 변수** 또는 **방향성 예측 문구**는 `**...**` 로 감싸면
렌더 시 노란 형광펜(`<mark class="driver">`) 으로 강조된다.

- 하이라이트 **해야 하는 것**: 장중 방향을 좌우할 이벤트·수치·발표 + 예측 방향
  - ✅ `**미·이란 휴전 만료(오늘 저녁)**` — 장중 변곡점 이벤트
  - ✅ `**오늘 갭다운 출발 가능성**` — 방향성 예측 문구
  - ✅ `**SK하이닉스 1Q 실적(장중 예정)**` — 당일 발표 재료
- 하이라이트 **하지 말 것**: 이미 확정된 과거 사실·지표
  - ❌ `**어제 코스피 6,388**` (과거 사실)
  - ❌ `**간밤 미 3대 지수 -0.6%**` (과거 수치, 맥락 제공용)
- **개수**: 한 문장에 **1~2개** 만. 3개 이상이면 다 하이라이트한 것처럼 되어 무의미해짐.
- 보안: 필터가 HTML-escape 먼저 한 뒤 `**X**` 만 `<mark>` 로 치환하므로 다른
  HTML 문법(`<b>` 등) 은 그대로 escape 돼서 안전함. 마커만 쓸 것.

## `rationale` 구조 — **첫 문장 = 요약 전망, 이후 = 근거**

`rationale` 의 **첫 문장**은 render 가 종목 카드 요약 row 에 한 줄 outlook 으로
추출한다 (`_outlook_line` 헬퍼가 첫 마침표까지 잘라 최대 60자 + 말줄임). 따라서
첫 문장은 아래 조건을 충족해야 독자 카드에서 의미 있다:

- **Forward-looking**: "오늘 어떻게 움직일지" 를 말할 것. 과거 수치 나열 금지.
- **50자 내외**: 60자 넘으면 잘림. 30~50자가 이상적.
- **자기완결**: 그 한 줄만 읽어도 오늘 전망이 이해되도록.

이후 문장들은 근거·신호 조합·선반영 여부·리스크 등 상술. `rationale` 전체는
결정 근거 블록(펼친 body)에 그대로 노출되므로 충실히 써도 OK.

**예시**
- ✅ "HBM 실적 모멘텀 강력, 상승 여력 존재. 1Q 영업익 +369% 컨센서스 + 목표가 200만원 논의, 간밤 SOX +0.5% 중립 우호, 아직 선반영 아님."
- ✅ "뉴스 긍정 vs 간밤 약세 상충, 갭다운 후 쉬어가는 흐름 예상. 20일 +21% 급등으로 상당 부분 선반영 + 간밤 XLI/DAC 약세."
- ❌ "한·미 무인함대 공동개발 + 동남아 K-방산 수출 + 1Q 잠정실적 호재로 뉴스 톤 긍정. 그러나 20일 +21% 급등으로 상당 부분 선반영…" (첫 문장이 재료 나열만, 결론 없음)

## `rationale` 서술 — 코드·영어 스키마 용어 금지

`rationale` 필드는 사용자가 보는 텍스트다. JSON 필드명이나 내부 식별자를 그대로 쓰지 말고, 자연 한국어로 쓸 것.

| 쓰지 말 것 | 쓸 것 |
|---|---|
| `priced_in=True` / `priced_in` | "선반영" · "이미 주가에 반영됨" |
| `priced_in=False` / `priced_in 아님` | "선반영 아님" · "아직 주가에 반영 안 됨" |
| `overnight_signal=up/down/neutral` | "간밤 강세/약세/중립" |
| `news_sentiment=positive/neutral/negative` | "뉴스 톤 긍정/중립/부정" |
| `hold` / `buy` / `sell` / `strong_buy` / `strong_sell` (영어 그대로) | "관망/상승 기대/하락 경계/강한 상승 기대/강한 하락 경계" |
| `override` | "한 단계 상향/하향" · "재량 조정" |
| `confidence=high/medium/low` | "신뢰도 높음/중간/낮음" |

JSON 필드 자체(예: `"priced_in": false`) 는 스키마라 영어 그대로 맞음. 금지는 **`rationale`·`summary`·`why_material` 같은 서술 본문**에서의 사용만.

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
- `focus.status` 는 `level` / `label` / `detail` 만 사용 — 일일 공개되지 않는 숫자 (예: 호르무즈 통과 선박 수) 는 넣지 말 것. 인용 기사가 며칠 묵어도 확인 어려워서 자주 스테일됨. 구조적 정보 (e.g., "선별 봉쇄 지속", "미·이란 2차 협상 불참") 만 표시.
- `mood_dashboard` 4축 필수 작성:
  - `policy` — 세제·감독·산업 육성책·밸류업·주주환원
  - `geopolitics` — 전쟁·외교·무역·제재
  - `overnight` — 어제 밤 미국·유럽 지수, VIX, SOX, XBI 등
  - `fx_macro` — 원/달러, WTI, 금, 비트코인, 원자재
  - 각 축 값: `{"impact": "positive|neutral|negative", "note": "한 줄 근거 30자 이내"}`
  - `neutral` 은 "혼조" 의미로도 씀 (긍정·부정 신호 섞여 있음).
  - 참고: 이전에 있던 `sectors` 축은 제거됨 (전용 🏭 섹터 흐름 섹션과 📈 종목별 섹터 breakdown 이 중복 커버하므로).

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
- **종목의 `news` 필드는 보통 생략하면 된다**. render 가 `.tmp/news.json` 의 raw 스크랩(최근 24h)을 backfill 해서 "📰 오늘의 뉴스" 블록에 시간순으로 붙여준다. agent 의 역할은 `key_points` 에 high-signal material 3~5개를 `why_material` 과 함께 엄선하는 것. raw 뉴스 피드는 사용자가 직접 훑는 참고용.
- 특수 케이스 — 에이전트가 **직접 선별**해서 `news` 블록을 덮어쓰고 싶으면 curated 리스트(`title`, `url`, `source`, `published_at`, `impact`, 선택적 `why_material`) 을 넣어라. 넣으면 raw backfill 안 일어남. 이 경우도 **빈 배열로 덮어쓰지 말 것** — 빈 배열은 "raw backfill 허용" 으로 해석된다.
- 섹터 `news` 는 동일. 큐레이션 후 3~5건 권장.

### 섹터 news vs 종목 news 역할

- **섹터 news**: 내 보유 종목과 **독립**. 섹터 자체의 시황·매크로·규제. `affected` 안 씀.
- **종목 news**: 해당 기업 고유 이슈. `news.json` 의 raw news 중에서 material만 골라 `why_material` 붙임. render가 24h 필터 + 헤드라인 keyword로 impact 자동 라벨(호재/악재/중립) 함 — agent가 더 정확한 판단이 있으면 명시적으로 `impact` 덮어써라 (예: 헤드라인은 "매각 검토" 같은 중립적 표현이지만 주가에는 호재로 해석되는 케이스).

---

## 렌더 편의

- Render 가 `published_at` 내림차순 자동 정렬, `time_ago` 계산, impact 라벨 부여.
- 종목 `news` 필드를 **생략하거나 빈 배열로 두면** render 가 `.tmp/news.json` 의 raw Naver 스크랩을 24h 필터 통과시켜 backfill. 24h 내 기사가 하나도 없으면 "📰 오늘의 뉴스" 블록 + 🔥 N 뱃지가 자동으로 안 뜸.
- `impact` 해석:
  - KOSPI +1% → `positive` (상승=호재)
  - USD/KRW 상승: 수출주 긍정/수입주 부담 → 종합 `neutral` 기본값
  - VIX 상승: `negative`
- If `.tmp/news.json` missing/empty, stop and report — do not fabricate.
