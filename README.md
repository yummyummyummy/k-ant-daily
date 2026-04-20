# k-ant-daily

평일 아침 **07:30 KST** — 장전 브리핑 자동 발행.
평일 저녁 **20:10 KST** — NXT 마감 후 오늘의 예측을 실제 종가와 비교해 같은 페이지에 리뷰 오버레이.

친구들 포트폴리오를 기반으로 한 개인용 한국 증시 브리핑이라, "오늘 커피는 누가 사나요?" 수준의 캐주얼한 UX와 실제 투자 의사결정에 도움될 정도의 분석을 동시에 추구합니다.

**공개 URL:** https://yummyummyummy.github.io/k-ant-daily/

## 하루 사이클

```
  07:30 KST               15:30 KST          20:00 KST            20:10 KST
  [/daily-report]   →   KRX 마감   →   NXT 마감   →   [/daily-review]
     ↓ 예측                                             ↓ 검증 + 리포트
  docs/YYYY-MM-DD.html                                같은 페이지에 오버레이
   (예측만)                                            (예측 + 실제 결과)
```

매일 같은 URL(`docs/YYYY-MM-DD.html`)이 두 번 갱신됩니다. 아침은 예측, 저녁은 예측+검증.

## 페이지 구성

- ☕ **커피 배너** — 친구별 보유 종목 카드. 호가창 스타일(가격·변화량·상승률) + 장중엔 60초마다 실시간 업데이트(Cloudflare Worker 프록시 경유). 상승률 1위 친구 이름이 상단에 표시됨.
- 📊 **예측 검증 배너** (저녁에만) — 적중률, 신뢰도별 정확도, 신호 기여도.
- ⭐ **오늘의 핵심** — 최대 3개 헤드라인, 접어/펼쳐 볼 수 있음.
- 🚨 **집중 이슈 (focus)** — 호르무즈 같은 지정학 이슈. 상태 뱃지(봉쇄/제한/개방) + 일 통행량 + 시간 정렬된 관련 뉴스.
- 📊 / 🌙 **국내 지표 / 간밤 해외 시장** — KOSPI·KOSDAQ·환율, S&P·나스닥·VIX·WTI·금·비트코인·달러인덱스. `▲ 27.17 +0.44%` 형식.
- 🏭 **섹터 흐름** — 접어/펼쳐.
- 📈 **종목별** — 가나다 순 카드 리스트. 어제 종가, 간밤 프록시 신호(🌙 ▲/▼), 투자의견(풀매수/매수/관망/매도/풀매도), 신뢰도, 보유자 칩. 카드 펼치면 결정 근거 블록(뉴스 톤·간밤 신호·이미 반영됨 여부)과 시간 정렬된 주요 뉴스.

## 투자의견 결정 — 3-신호 매트릭스

"어제 주가에 앵커링되는" 편향을 줄이려고, 의견은 **다음 3개 신호의 조합**으로 결정됩니다 (가치평가 아님, 1~5일 단기 뉴스 플로우 예측).

| 신호 | 값 | 출처 |
|---|---|---|
| **뉴스 톤** (`news_sentiment`) | positive / neutral / negative | LLM이 어제·간밤 뉴스 톤 판단 |
| **간밤 신호** (`overnight_signal`) | up / neutral / down | 종목별 해외 프록시(예: 반도체→`^SOX, NVDA, MU`) 평균 등락률, 자동 계산 |
| **반영 여부** (`priced_in`) | true / false | 어제 ±5%+ 움직임 + 뉴스 방향 일치면 true |

**조합 매트릭스 요약:**
- 뉴스 긍정 + 간밤 강세 + 반영 안 됨 → `strong_buy`
- 뉴스 긍정 + 간밤 강세 + 이미 반영 → `buy` (과열 경계)
- 뉴스 부정 + 간밤 약세 + 반영 안 됨 → `strong_sell`
- 뉴스 긍정 + 간밤 약세 → `hold` (상충)
- 뉴스 부정 + 간밤 강세 + 이미 반영 → `hold` (어제 급락 반영, 반등 여지)

자세한 매트릭스와 신뢰도(high/medium/low) 부여 기준은 [.claude/commands/daily-report.md](.claude/commands/daily-report.md).

## 저녁 검증

`/daily-review`는 아침의 `docs/YYYY-MM-DD.summary.json`을 읽고, 저녁에 새로 긁은 종가와 비교해:

- **종목별**: `hit` / `partial` / `miss` (매트릭스 맵핑, [compute_review.py](scripts/compute_review.py))
- **집계**: 적중률, 방향 정확도, **신뢰도 버킷별 정확도** (high 버킷이 실제로 맞는 비율이 높아야 의미 있음)
- **신호 기여도**: 실패 케이스를 `news_misread` / `overnight_misled` / `priced_in_underestimated` 로 분류, 누적되면 `stocks.yml` 의 `overnight_proxy` 매핑을 조정할 근거.

## 디렉터리 구조

```
k-ant-daily/
├── stocks.yml                          # 종목 + 보유자(owners) + overnight_proxy + deep_dive 플래그
├── scripts/
│   ├── fetch_news.py                   # Naver/yfinance에서 news.json 구성
│   ├── render.py                       # summary.json → HTML + 영구 summary.json 아티팩트
│   ├── compute_review.py               # 예측 vs 실제 매칭
│   └── launchd/                        # macOS 로컬 스케줄 (아래 참조)
├── templates/
│   ├── report.html.j2                  # 일간 브리핑 템플릿
│   └── archive.html.j2                 # 아카이브 목록
├── worker/                             # Cloudflare Worker (실시간 시세 프록시)
│   ├── src/index.js
│   └── README.md
├── .claude/commands/
│   ├── daily-report.md                 # 아침 브리핑 스킬
│   └── daily-review.md                 # 저녁 리뷰 스킬
├── docs/                               # GitHub Pages
│   ├── YYYY-MM-DD.html                 # 일간 리포트 (아침 발행 + 저녁 오버레이)
│   ├── YYYY-MM-DD.summary.json         # 영구 아티팩트 (저녁 리뷰가 읽음)
│   ├── index.html                      # 최신본 사본
│   └── archive.html                    # 날짜별 리스트
└── .tmp/                               # 런타임 scratch (gitignored)
    ├── news.json                       # fetch_news.py 출력
    └── summary.json                    # agent가 작성 → render 입력
```

## `stocks.yml` 스키마

```yaml
stocks:
  - code: "000660"
    name: "SK하이닉스"
    market: KOSPI
    owners: ["한윤근", "장한솔", "장윤영", "이영준"]
    overnight_proxy: ["^SOX", "NVDA", "MU"]     # 간밤 해외 프록시 (yfinance 티커)
    deep_dive: true                              # 딥다이브 리서치 대상 (WebSearch/WebFetch)
    keywords:                                    # 리서치 seed
      - "SK하이닉스"
      - "HBM"
```

- `owners`: 여러 명 가능. 모든 친구는 여러 종목 보유 가능.
- `overnight_proxy`: 섹터별 가이드 — 반도체=`^SOX,NVDA,MU` / 바이오=`XBI,IBB` / 방산=`ITA,LMT,RTX` / 배터리=`XLE,CL=F,TSLA` / 전력=`GEV,ETN,XLU` / 플랜트=`XLE,FLR` / 엔터=`SPOT,WMG` / 카지노=`LVS,WYNN,MGM` 등.
- `deep_dive: true`: 아침 브리핑 때 LLM이 추가 웹 리서치 수행 (토큰 소비 큼, 신중히 지정).

## 스케줄링

### macOS launchd (기본 — Mac mini 24/7 운용)

```bash
./scripts/launchd/install.sh   # 최초 1회
```

두 LaunchAgent 설치:
- `com.yummyummyummy.k-ant-daily.briefing` — 평일 **07:30 KST**
- `com.yummyummyummy.k-ant-daily.review`   — 평일 **20:10 KST**

로그: `~/Library/Logs/k-ant-daily/`. 상세: [scripts/launchd/README.md](scripts/launchd/README.md).

### 클라우드 (백업)

동일한 스케줄이 `claude.ai/code/scheduled` 에 비활성 상태로 등록되어 있음. Mac 장시간 미가동 시 [claude.ai/code/scheduled](https://claude.ai/code/scheduled) 에서 enable로 전환.

## 실시간 시세 (Cloudflare Worker)

커피 배너의 친구 종목 카드는 장중(09:00–15:30 KST) **60초마다 실시간 시세로 자동 갱신**됩니다. 가격 변동 시 빨강/파랑 플래시.

Worker가 Naver 폴링 API(EUC-KR)를 CORS 프록시 + 30초 edge 캐시로 감싸고 있음. 배포:

```bash
cd worker
wrangler deploy        # 최초 1회 `wrangler login` 필요
```

상세: [worker/README.md](worker/README.md).

## 로컬 수동 실행

```bash
source .venv/bin/activate
pip install -r requirements.txt
python scripts/fetch_news.py                     # → .tmp/news.json

# Option A: Claude CLI로 전자동
claude --dangerously-skip-permissions --print "/daily-report"

# Option B: summary.json을 직접 작성한 뒤 수동 렌더
# (.tmp/summary.json 을 스키마에 맞춰 작성)
python scripts/render.py .tmp/summary.json

# 저녁 리뷰
python scripts/compute_review.py [YYYY-MM-DD]
python scripts/render.py .tmp/summary.json
```

`scripts/launchd/run-briefing.sh` 를 직접 실행하면 production과 동일한 시퀀스로 돌아갑니다.

## 요구사항

- **Python 3.11+** + `requirements.txt` (requests, beautifulsoup4, PyYAML, Jinja2, yfinance, feedparser, lxml)
- **Claude Code CLI** — `claude -p` 가 non-interactive 모드로 슬래시 커맨드 실행 (구독 사용량 소비)
- **macOS** (launchd 사용 시) — 또는 cron/systemd 등으로 대체 가능
- **Cloudflare 계정** (실시간 시세 원하는 경우) — 무료 Workers 플랜이면 충분
- **GitHub Pages** — `main` 브랜치 `docs/` 폴더 기반 자동 배포

## 주의

- **투자 권유 아님.** LLM이 뉴스 플로우를 해석한 단기(1~5일) 방향 전망일 뿐, 종목 가치평가·장기 전망 아님.
- 투자의견(`풀매수/매수/관망/매도/풀매도`)은 어디까지나 **뉴스·간밤 시장·선반영 여부** 의 조합 휴리스틱입니다. 중요한 판단은 원문 링크를 확인하세요.
- 클라우드 인프라·Worker 모두 개인 사용 규모를 전제로 설정. 트래픽 증가 시 Naver 레이트리밋 or Cloudflare 무료 한도 확인 필요.
