---
description: 방금 끝난 이벤트의 실제 결과를 events.yml 에 채우는 경량 인트라데이 작업
---

## 목적

발표/결과성 이벤트 (FOMC·CPI·고용보고서·한은 금통위·실적 등) 가 끝난 직후, 실제 결과를 빠르게 조사해 `events.yml` 의 `result` 를 채운다. 07:30/23:00 정규 실행을 기다리지 않고 "바로바로" 반영하기 위한 좁은 목적의 작업.

**전체 캘린더 재큐레이션은 하지 않는다.** 오직 지난 이벤트 result 채우기만.

## Steps

### 1. 대상 식별
```bash
.venv/bin/python scripts/pending_results.py   # 결과 대기 이벤트 개수
```
0 이면 할 일 없음 — 즉시 종료. (wrapper 가 이미 걸러주지만 재확인)

`docs/events.json` 에서 다음 조건을 모두 만족하는 이벤트를 찾는다:
- `result` 가 비어있음
- `category` 가 `holiday` 가 아님
- resolve 시각 (다일 이벤트는 마지막 날 + `time`, 없으면 23:59 KST) 이 **최근 4시간 내** 경과

### 2. 결과 조사
각 대상 이벤트에 대해 WebSearch / WebFetch 로 **실제 결과 + 시장 반응**을 확인:
- FOMC → 금리 결정 (동결/인하/인상) + 점도표 변화 + 미 증시 반응
- CPI/PPI/고용 → 실제 수치 vs 컨센서스 + 시장 반응
- 한은 금통위 → 기준금리 결정 + 원화/코스피 반응
- 실적 → 매출/영업이익 vs 컨센서스 (beat/miss)
- 학회 readout → 데이터 긍/부정 + 해당 종목 주가 반응

아직 결과가 공표되지 않았으면 **그 이벤트는 건너뛴다** (다음 tick 또는 정규 실행이 재시도). 추측 금지.

### 3. events.yml 갱신
해당 이벤트 항목에 `result` 추가:
```yaml
result:
  outcome: positive | negative | neutral | asexpected   # 위험자산 관점
  summary: "기준금리 2.25% 동결. 원화 강보합, 코스닥 +0.4% 마감."  # 사실 + 시장 반응 1~2줄
  filled_at: "2026-05-28"
```
- `outcome`: 위험자산 우호=positive, 부담=negative, 무반응=neutral, 컨센서스 부합=asexpected
- `summary`: 자연스러운 한국어, 사실 + 시장 반응. 영어 schema 키 노출 금지

### 4. 빌드 + 렌더 + 커밋
```bash
.venv/bin/python scripts/build_calendar.py
.venv/bin/python scripts/render.py
git add docs/ events.yml
git commit -m "results: $(date +%Y-%m-%d' '%H:%M) 이벤트 결과 반영"
git push origin main
```

채운 이벤트가 없으면 (모두 아직 미공표) commit 하지 말 것.

## 출력 규칙

- 사실만. "예측"/"전망" 금지. 확인된 결과 + 실제 시장 반응만
- 자연스러운 한국어
- 결과 못 찾으면 비워두고 다음 실행에 맡김 — 절대 추측으로 채우지 말 것
