# k-ant-daily-quotes (Cloudflare Worker)

실시간 시세/뉴스 프록시 Worker. Naver Finance, Naver MarketIndex, Upbit public API를 CORS 포함 JSON으로 돌려준다. GitHub Pages의 정적 캘린더 페이지에서 브라우저가 직접 호출한다.

## 배포

### 사전 준비 (최초 1회)

```bash
npm install -g wrangler
wrangler login   # Cloudflare 계정 OAuth
```

### 배포

```bash
cd worker
wrangler deploy
```

배포되면 출력에 URL이 표시됨 — 예: `https://k-ant-daily-quotes.<your-subdomain>.workers.dev`.
Worker URL이 바뀌면 [templates/calendar.html.j2](../templates/calendar.html.j2)의 `WORKER_BASE` 상수를 수정하고 `scripts/render.py`를 다시 실행한다.

## 엔드포인트

### `GET /quote?codes=005930,000660,...`

6자리 종목 코드를 콤마로 구분. 최대 32개. 리턴:

```json
{
  "005930": {
    "price": 214500,
    "change": 1500,
    "change_pct": -0.69,
    "direction": "down",
    "name": "삼성전자",
    "ts": 1713610800000
  },
  "000660": { ... }
}
```

- `direction`: `up` / `down` / `flat` (Naver `rf` 코드 매핑)
- `change`: 절대값 (부호는 `direction` 으로 추론)
- `change_pct`: 부호 포함 백분율
- `ts`: 응답 생성 시각 (Unix ms)

응답은 **edge에서 30초 캐시**됨. 동일 코드셋에 대한 반복 요청은 Naver로 업스트림 호출 없이 즉시 반환.

### `GET /ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH`

상단 마키용 지수·환율·암호화폐 데이터. 각 item은 `{value, change_abs, change_pct, direction}` 형태로 반환된다. 응답은 30초 캐시.

### `GET /stock-news?codes=005930,000660,...`

종목별 최신 뉴스 탭을 스크랩해 `{news, latest_at}` 형태로 반환한다. 응답은 5분 캐시.

### `GET /health`

헬스체크. `{"ok": true, "service": "k-ant-daily-quotes"}`.

## 비용

Cloudflare Workers 무료 플랜: 100k 요청/일. 예상 트래픽:
- 친구 1명 기준 장 시간(6시간) × 60초 폴링 = 360 요청/일 (배치 요청 가정)
- 여러 사용자도 edge cache 덕분에 upstream은 분당 2회 수준

걱정 수준 아님.

## 로컬 개발

```bash
cd worker
wrangler dev    # http://localhost:8787
curl "http://localhost:8787/quote?codes=005930,000660"
curl "http://localhost:8787/ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH"
```

## 관측·디버깅

`[observability]` 가 wrangler.toml에 켜져 있어 Cloudflare 대시보드 → Workers & Pages → k-ant-daily-quotes → Observability 에서 실시간 로그·에러·지연 확인 가능.
