---
description: Post-market review — compare morning prediction vs actual close
---

## 목적 — NXT 마감(20:00 KST) 후 오늘 예측 검증

아침 07:30에 `/daily-report` 가 발행한 예측이 오늘 장에서 실제로 맞았는지 검증하고, 같은 페이지에 리뷰 블록을 덧씌운다. 운영 시점은 **매일 오후 20:10 KST (NXT 연속거래 마감 + 10분 버퍼)**.

입력:
- `docs/YYYY-MM-DD.summary.json` — 오늘 아침 예측 아티팩트 (render.py가 자동 생성해 커밋해 둠)
- NXT 마감 후 스크랩한 실제 종가 (fetch_news.py를 evening에 다시 돌리면 quote에 오늘 종가 들어옴)

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
   - 신호 기여도: news_misread, overnight_misled, priced_in_underestimated, overnight_helped
   - `.tmp/summary.json` 에 병합 결과 저장

4. **재렌더.** `.venv/bin/python scripts/render.py .tmp/summary.json`
   - `docs/YYYY-MM-DD.html` 에 review 블록 덧씌워짐
   - `docs/YYYY-MM-DD.summary.json` 도 업데이트 (review 섹션 포함)
   - `docs/index.html` 도 최신본으로 교체

5. **커밋/푸시.**
   ```bash
   git add docs/
   git commit -m "review: $(date +%Y-%m-%d) post-session review"
   git push
   ```

6. **결과 요약 보고.** 적중률, 방향 정확도, 가장 맞춘 / 틀린 종목 각 1개, 기여도 요약을 한 단락으로.

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

## 신호 기여도 판정 기준

- `news_misread`: 예측 실패 + (뉴스 긍정 → 실제 하락) or (뉴스 부정 → 실제 상승)
- `overnight_misled`: 예측 실패 + 간밤 신호와 실제 방향이 정반대
- `priced_in_underestimated`: 예측 실패 + priced_in=false 였는데 실제 거의 무변동 (|Δ|<0.5%)
- `overnight_helped`: 예측 적중 + 간밤 신호와 실제 방향이 일치

이 수치가 누적되면 `stocks.yml` 의 `overnight_proxy` 매핑을 조정할 근거가 된다 (예: 간밤 오도가 반복되는 프록시는 교체).

## Rules

- 예측 아티팩트가 **없으면** 아무 것도 하지 말고 종료. 없는데 임의로 만들지 말 것.
- `.tmp/news.json` 이 없거나 비어있으면 중단하고 이유 보고.
- 리뷰 배너 텍스트는 **중립·사실 기반**. 한 줄 평을 추가할 경우 "과도한 낙관 / 비관 경계" 수준을 넘지 말 것.
- 커밋 메시지 바닥글에 `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` 추가.
- `stocks.yml` 은 건드리지 말 것. 리뷰는 `docs/` 만 변경.
