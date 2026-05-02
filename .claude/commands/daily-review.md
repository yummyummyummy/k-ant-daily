---
description: Post-market review — compare morning prediction vs actual close
---

## 목적 — NXT 마감(20:00 KST) 후 오늘 예측 검증

아침 07:30에 `/daily-report` 가 발행한 예측이 오늘 장에서 실제로 맞았는지 검증하고, 같은 페이지에 리뷰 블록을 덧씌운다. 운영 시점은 **매일 오후 20:10 KST (NXT 연속거래 마감 + 10분 버퍼)**.

입력:
- `docs/YYYY-MM-DD.summary.json` — 오늘 아침 예측 아티팩트 (render.py가 자동 생성해 커밋해 둠)
- KRX 15:30 종가 (fetch_news.py 재실행 → news.json 의 stock quote) — 적중률 계산에 사용
- NXT 20:00 종가 (compute_review.py 가 Worker `/nxt-quotes` 호출) — 아카이브 표시에 overlay, 커피 섹션·종목 카드의 "오늘 움직임" 이 full-day (KRX + NXT after-hours) 반영

출력:
- 같은 URL `docs/YYYY-MM-DD.html` 에 리뷰 배너 + 종목별 적중 뱃지 + "오늘 세션 결과" 블록 덧씌움
- `docs/YYYY-MM-DD.summary.json` 업데이트 (review 섹션 포함)
- `git commit -m "review: YYYY-MM-DD post-session review"` + push

## Steps

1. **예측 아티팩트 존재 확인.** `docs/$(date +%Y-%m-%d).summary.json` 파일이 있는지 확인.
   없으면 "오늘 아침 브리핑이 없어 검증 생략"으로 종료.

2. **오늘 종가 fetch.** `.venv/bin/python scripts/fetch_news.py` 재실행 →
   `.tmp/news.json` 의 `stocks[].quote` 가 오늘 실제 종가로 갱신됨 (스크레이핑 시점이 장 마감 후라).

3. **리뷰 계산.** `.venv/bin/python scripts/compute_review.py [YYYY-MM-DD]`
   - 예측 vs 실제 매칭 → 종목별 `result.outcome` (hit/partial/miss)
   - 집계 지표: hit_rate, directional_accuracy, by_confidence
   - 신호 기여도: news_misread, overnight_misled, priced_in_underestimated, overnight_helped, speculative_flow
   - `.tmp/summary.json` 에 병합 결과 저장

4. **회고 분석 작성.** `.tmp/summary.json` 을 읽고 `review.analysis` 섹션을 직접 편집해서 채워 넣는다.
   이 회고가 `docs/accuracy/YYYY-MM-DD.html` 별도 페이지로 렌더링된다. 스키마 · 규칙은 아래 "회고 분석" 절 참고.

5. **재렌더.** `.venv/bin/python scripts/render.py .tmp/summary.json`
   - `docs/YYYY-MM-DD.html` 에 review 블록 덧씌워짐
   - `docs/YYYY-MM-DD.summary.json` 도 업데이트 (review + analysis 섹션 포함)
   - `docs/accuracy/YYYY-MM-DD.html` 회고 페이지 생성
   - `docs/index.html` · `docs/accuracy.html` · `docs/archive.html` 도 최신본으로 교체

6. **커밋/푸시.**
   ```bash
   git add docs/
   git commit -m "review: $(date +%Y-%m-%d) post-session review"

   # 리뷰 실행 중 main에 다른 커밋이 올라왔을 수 있음 (e.g. 수동 refactor).
   # 이 경우 바로 push 하면 non-fast-forward 로 실패하고 리뷰가 GitHub Pages 에
   # 올라가지 않는다. rebase 한 번 태우고 push 재시도.
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

7. **결과 요약 보고.** 다음 고정 포맷으로 한 단락. JSON 필드를 그대로 문자열화해서 붙여넣지 말 것 — 숫자·값만 뽑아서 자연어로 기술.

   ```
   적중률 X% (hits/partial/misses) · 방향 정확도 Y%
   · KOSPI <값> (<부호+-><pct>) · KOSDAQ <값> (<부호+-><pct>)
   · 가장 맞춘 종목: <이름> <부호+-><실제%> (<rec_label> 예측)
   · 가장 틀린 종목: <이름> <부호+-><실제%> (<rec_label> 예측)
   · 기여도: news_misread N / overnight_misled N / priced_in_underestimated N / overnight_helped N / speculative_flow N
   ```

   예시:
   ```
   적중률 45% (8/2/12) · 방향 정확도 54%
   · KOSPI 6,475.81 (+0.90%) · KOSDAQ 1,174.31 (+0.58%)
   · 가장 맞춘 종목: HD현대일렉트릭 +3.02% (강한 상승 기대 예측)
   · 가장 틀린 종목: 알테오젠 -4.80% (관망 예측)
   · 기여도: news_misread 3 / overnight_misled 1 / priced_in_underestimated 2 / overnight_helped 4 / speculative_flow 2
   ```

   값 출처는 `.tmp/summary.json` 의 `review.accuracy`, `review.session_change`, `stocks[].result`, `review.signal_attribution`. session_change 는 dict 이므로 `kospi.value` · `kospi.change_pct` 식으로 필드 접근해서 포맷.

## 환경 셋업 (필요시)

원격 에이전트 환경엔 Python 가상환경이 없을 수 있다.
```bash
python3 -m venv .venv 2>/dev/null || true
.venv/bin/pip install -q -r requirements.txt
```

## Hit/Partial/Miss 기준 (compute_review.py가 자동 적용)

| 예측 | 기준 |
|---|---|
| `strong_buy` | ≥+2% 적중 / 0~+2% 부분 / <0% 실패 |
| `buy` | >+0.5% 적중 / -0.5~+0.5% 부분 / <-0.5% 실패 |
| `hold` | |Δ|<1.5% 적중 / 1.5~3% 부분 / >3% 실패 |
| `sell` | <-0.5% 적중 / -0.5~+0.5% 부분 / >+0.5% 실패 |
| `strong_sell` | ≤-2% 적중 / -2~0% 부분 / >0% 실패 |

## 회고 분석 (review.analysis) — step 4

`compute_review.py` 가 기계적 집계를 낸 뒤, **agent가 직접 서술**해 넣는다. 목적: "왜 맞았고 왜 틀렸나" 를 다음 날 자신이 읽고 큐레이션·판단을 조정할 수 있게 남기는 것.

### 스키마

```json
"review": {
  "accuracy": { ... },
  "signal_attribution": { ... },
  "analysis": {
    "day_summary": "한 문장 — 지수 방향 + 오늘 hit rate + 가장 지배적인 miss 패턴",

    "what_worked": {
      "lead": "한 문장 — 어떤 섹터·패턴이 잘 맞혔는지",
      "examples": [
        {"code": "096770", "name": "SK이노베이션", "change_pct": 3.65,
         "reason": "WTI +2.8% 급등 직접 수혜 + K배터리 ESS 신사업"}
      ],
      "takeaway": "선택 — 공통 패턴 한 줄"
    },

    "what_missed": {
      "lead": "한 문장 — 어떤 패턴에서 틀렸나 (주된 miss 원인)",
      "examples": [
        {"code": "174900", "name": "앱클론", "change_pct": -12.72,
         "reason": "'뉴스 부재 = hold' 오판 — 소형 바이오 섹터 약세 휩쓸림"}
      ],
      "takeaway": "선택 — 교훈 한 줄"
    },

    "stocks": {
      "<code>": {
        "why": "왜 실패/부분 적중했는지 2~3문장 요약",
        "misread": {  // 선택 — 뉴스 오독 케이스(news_misread)에만 깊이 있게
          "news_cited":      "무슨 뉴스를 근거로 판단했나 (원 제목·핵심 수치)",
          "how_interpreted": "그 뉴스를 어떻게 해석해서 예측으로 연결했나",
          "what_was_wrong":  "해석 중 어떤 부분이 실제와 어긋났나 (구체적으로)",
          "lesson":          "같은 상황이 또 오면 어떻게 해석해야 하나 (선택)"
        }
      }
    },

    "lessons": [  // 독자·다음날 /daily-report 에이전트가 읽을 오늘의 교훈
      {
        "title":  "짧은 제목 (20자 내외)",
        "detail": "왜 이 패턴이 중요한지 2~3문장",
        "rule":   "앞으로의 판단에 적용할 규칙 한 줄 (선택)"
      }
    ],

    "apology": "hit_rate < 0.5 인 날에만 작성. 고객에게 손실을 끼친 애널리스트·자산관리사 관점에서 쓴 반성문 — 3~5문장. 아래 작성 규칙 참조."
  }
}
```

### 작성 규칙

- **`day_summary`**: 한 문장. 지수 흐름 + 적중률 + 가장 도드라진 빗나감 패턴을 압축.
- **`what_worked.examples` / `what_missed.examples`**: 각 **3~5개**. 10개 이상 쓰지 말 것 (UI 가독성). 가장 대표적 예시만.
- **`examples[].change_pct`**: 숫자 (부호 포함). `-12.72` · `3.65` 식. 문자열 금지.
- **`examples[].reason`**: **한 문장 25~45자**. "WTI +2.8% 급등 직접 수혜 + K배터리 ESS 신사업" 처럼 촉매 + 구체 근거.
- **`takeaway`**: 선택. 있으면 "공통 패턴 / 교훈" 한 줄.
- **`analysis.stocks`**: **실패 · 부분 적중 종목에만** 작성. 적중 종목은 생략 (페이지에서 "적중 — 별도 분석 생략"으로 표시).
  - `why`: "왜 예측이 틀렸나" 를 **가설 톤** 으로. "…압도한 것으로 보임", "…를 과소평가한 것으로 해석" 같이. 단정 금지.
  - 3~5문장은 과함. 2~3문장 목표.
- **`analysis.stocks[code].misread`**: **뉴스 오독(news_misread) 케이스에만** 작성 — 뉴스 톤이 실제 방향과 반대로 나간 종목. 4개 필드 모두 채우는 것 권장 (`lesson` 은 선택).
  - `news_cited`: 원 뉴스 핵심. 제목·출처·수치를 구체적으로. "AACR 학회 발표 예정 (4/25) + 종근당과 이중항체 공동개발 MOU" 같이.
  - `how_interpreted`: 이 뉴스를 어떤 논리로 읽고 예측까지 갔는지. "중장기 호재 2건 + 개별 당일 촉매 부재 → 관망으로 처리" 처럼 연결고리 명시.
  - `what_was_wrong`: 어떤 부분의 해석이 실제와 어긋났는지. "당일 촉매 부재 = 중립 이라는 연결이 틀림. 섹터 약세 중이면 중립이 아니라 섹터 흐름에 그대로 노출됨" 처럼 구체적으로.
  - `lesson`: 같은 상황 재발 시 어떻게 할지. 선택이지만 강권장.
- **`analysis.lessons`**: 오늘 미스 패턴에서 **일반화 가능한** 교훈 3~5개. 사용자·다음날 에이전트 둘 다 읽는다.
  - 특정 종목 이름은 예시로만 잠깐 언급. 규칙 자체는 종목 무관하게 적용 가능해야.
  - `rule` 은 가능한 한 구체적 조건 형태로 — "X 상황에서 Y 하라" 식.
  - 매일 같은 교훈을 반복해 쓰지 말 것. 이미 최근 N일에 같은 lesson이 있으면 skip 하거나 "재확인" 으로 가볍게.
- **`analysis.apology`** — hit_rate < 0.5 인 날에만 작성. 조건 불충족 시 필드 생략.
  - **관점**: "고객 자산을 위탁받은 애널리스트/자산관리사"가 쓴 공식 반성문. 냉정한 보고서 어조 X — 진심 어린 사과와 책임감이 느껴져야 함.
  - **포함 필수**: ① 오늘 구체적으로 무엇을 잘못 판단했는지 (수치 포함), ② 그 판단이 고객에게 어떤 영향을 미쳤는지, ③ 앞으로 같은 실수를 막기 위해 구체적으로 무엇을 바꿀 것인지.
  - **근본 마인드**: 이 예측을 믿고 자산을 움직인 사람이 실제로 존재한다. 틀리면 그 사람의 돈이 사라진다. 반성문은 그 무게를 온전히 짊어지는 글이어야 한다. "아쉬웠습니다" "노력하겠습니다" 수준의 사무적 사과는 금지.
  - **톤 가이드**: 자산관리사가 고객 계좌에 실제 손실을 낸 날 쓰는 글. 수치로 손실의 규모를 직시하고, 무엇이 판단 착오였는지 스스로 해부하고, 같은 실수가 다시 일어나지 않을 구체적 방지책을 약속한다. 감정을 억누르지 않되 자기변명은 한 줄도 없어야 한다.
  - **길이**: 4~6문장 (250~400자). 짧으면 진정성 없어 보이고, 길면 변명처럼 읽힌다.
  - **예시 (참고용, 그대로 쓰지 말 것)**:
    > "오늘 저는 20개 종목 중 9건을 틀렸습니다. 제 의견을 보고 매수를 유지하신 분이 계셨다면, 오늘 하락장에서 실제 손실을 입으셨을 겁니다. 삼성전자 실적 긍정 뉴스를 매수 신호로 읽은 건 명백한 오판이었습니다 — 실적 확정 당일 시장이 '소문에 사고 뉴스에 판다'는 패턴을 알면서도 무시했습니다. 한국금융지주는 같은 날 키움증권에 하락 경계를 냈으면서 섹터 일관성을 지키지 않았습니다. 이 두 가지 규칙을 내일부터 강제 적용합니다. 오늘의 틀림은 내일의 판단으로만 갚을 수 있습니다."

- **톤**: 자기 비판 OK, 과도한 낙관·패닉 금지. 다음 날 자신이 읽고 조정할 힌트가 되어야 함.
- **다른 종목 비교**: "섹터 동조로…" 식 인용은 OK. 단 실제 데이터에 없는 종목은 들먹이지 말 것.

### 서술형 본문에서 **금지 용어 (코드·영어 스키마 식별자)**

`day_summary` · `lead` · `reason` · `takeaway` · `stocks[].why` 는 독자(사용자)가 읽는 텍스트다. JSON 필드명·내부 코드 식별자를 그대로 쓰지 말고, 아래 자연 한국어로 치환할 것:

| 쓰지 말 것 | 쓸 것 |
|---|---|
| `news_misread` · "news misread" | "뉴스 톤 오독" · "뉴스 해석 실패" |
| `overnight_misled` · "overnight misled" | "간밤 신호가 방향을 잘못 가리킴" |
| `priced_in_underestimated` | "이미 주가에 반영된 정도를 과소평가" |
| `overnight_helped` | "간밤 해외 신호가 적중을 지원" |
| `priced_in=True` · "priced in" (형용사) | "이미 주가에 반영됨" · **"선반영"** OK |
| `priced_in=False` | "아직 주가에 반영 안 됨" · "선반영 아님" |
| `overnight_signal=neutral/up/down` | "간밤 해외 신호 중립/강세/약세" |
| `news_sentiment=positive/neutral/negative` | "뉴스 톤 긍정/중립/부정" |
| `recommendation=buy/sell/hold/strong_buy/strong_sell` | "상승 기대/하락 경계/관망/강한 상승 기대/강한 하락 경계" |
| `hit/partial/miss` (영어 그대로) | "적중/부분 적중/실패·빗나감" |
| `hit rate` · `hit_rate` | "적중률" |
| `override` · `override한` | "한 단계 상향/하향" · "재량 조정" |
| `confidence=high/medium/low` | "신뢰도 높음/중간/낮음" |
| `matrix` · "매트릭스" (코드 맥락) | "기본 판정 규칙" · "매트릭스"는 가능하지만 풀어쓰기 우선 |

예시:
- ❌ "priced_in=True 였는데 miss 함 — news_misread 패턴"
- ✅ "선반영으로 봤는데 빗나감 — 뉴스 톤을 잘못 읽은 패턴"

JSON 필드명·수치 라벨 그 자체(예: `accuracy.hit_rate` 가 55%) 는 그대로 둬도 된다. 금지는 **서술 본문 안**에서의 사용에만 해당.

### 작성 절차

```python
# .tmp/summary.json 을 읽고 편집
import json
from pathlib import Path
p = Path(".tmp/summary.json")
d = json.loads(p.read_text())

# 종목별 result, predicted, rationale, news 를 훑어 miss 패턴 파악
# 각 stock 의 s['news_sentiment'], s['overnight_signal'], s['priced_in'],
# s['rationale'], s['result']['outcome'], s['result']['actual_change_pct'] 를 보면 충분.

d.setdefault("review", {})["analysis"] = {
    "day_summary": "...",
    "what_worked": {"lead": "...", "examples": [...], "takeaway": "..."},
    "what_missed": {"lead": "...", "examples": [...], "takeaway": "..."},
    "stocks": {
        "<miss/partial code>": {"why": "..."},
    },
}
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
```

그 다음 step 4b 로 넘어간다.

4b. **승격 규칙 갱신.** analysis 작성 직후 promote_rules.py 를 실행해 반복 패턴을 `docs/promoted_rules.md` 에 반영한다.

    ```bash
    .venv/bin/python scripts/promote_rules.py
    ```

    - 실행 결과 (몇 개 promoted, 어떤 topic) 를 결과 요약에 한 줄 포함.
    - 실패하거나 아무것도 promote 되지 않아도 무시하고 step 5 로 진행. (없는 날도 정상)

그 다음 step 5 (재렌더) 로 넘어간다.

## 신호 기여도 판정 기준

- `news_misread`: 예측 실패 + (뉴스 긍정 → 실제 하락) or (뉴스 부정 → 실제 상승)
- `overnight_misled`: 예측 실패 + 간밤 신호와 실제 방향이 정반대
- `priced_in_underestimated`: 예측 실패 + priced_in=false 였는데 실제 거의 무변동 (|Δ|<0.5%)
- `overnight_helped`: 예측 적중 + 간밤 신호와 실제 방향이 일치
- `speculative_flow`: 예측 실패 + 오늘 거래량이 20일 평균의 2× 이상 — 뉴스 근거로는 설명 안 되는 수급 급등/급락. `stocks[].history.volume_20d_avg` 와 `stocks[].quote.volume` 비교로 compute_review.py 가 자동 집계.

이 수치가 누적되면 `stocks.yml` 의 `overnight_proxy` 매핑이나 종목 선정 자체를 조정할 근거가 된다 (예: 투기 수급이 반복되는 종목은 rationale 에 "거래량 쏠림 주의" 태그 추가).

## Rules

- 예측 아티팩트가 **없으면** 아무 것도 하지 말고 종료. 없는데 임의로 만들지 말 것.
- `.tmp/news.json` 이 없거나 비어있으면 중단하고 이유 보고.
- 리뷰 배너 텍스트는 **중립·사실 기반**. 한 줄 평을 추가할 경우 "과도한 낙관 / 비관 경계" 수준을 넘지 말 것.
- 커밋 메시지 바닥글에 `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` 추가.
- `stocks.yml` 은 건드리지 말 것. 리뷰는 `docs/` 만 변경.
