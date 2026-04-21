# k-ant-daily

평일 아침 **07:30 KST** — 장전 브리핑 자동 발행.
평일 저녁 **20:10 KST** — NXT 마감 후 오늘의 예측을 실제 종가와 비교해 같은 페이지에 리뷰 오버레이.

친구들 포트폴리오를 기반으로 한 개인용 한국 증시 브리핑이라, "오늘 커피는 누가 사나요?" 수준의 캐주얼한 UX와 프로 트레이더의 아침 뉴스 체크 루틴을 동시에 지원합니다.

**공개 URL:** https://yummyummyummy.github.io/k-ant-daily/

---

## 하루 사이클

```
  07:30 KST               15:30 KST          20:00 KST            20:10 KST
  [/daily-report]   →   KRX 마감   →   NXT 마감   →   [/daily-review]
     ↓ 예측                                             ↓ 검증 + 리포트
  docs/YYYY-MM-DD.html                                같은 페이지에 오버레이
   (예측만)                                            (예측 + 실제 결과)
```

매일 같은 URL(`docs/YYYY-MM-DD.html`)이 두 번 갱신됩니다. 아침은 예측, 저녁은 예측+검증.

---

## 페이지 구성 (상단 → 하단)

### 📊 Ticker 마키 (sticky, 상단 고정)
장중 60초 폴링으로 실시간 업데이트. 24/7 동작:
- **KOSPI · KOSDAQ** — Naver `SERVICE_INDEX` 폴링
- **USD/KRW** — Naver marketindex HTML 스크랩 (JSON 엔드포인트 없어 HTML 파싱)
- **BTC · ETH** — Upbit 공개 API (KRW 기준)

호버 시 스크롤 일시정지, `prefers-reduced-motion` 시 정적 표시.

### ☕ 커피 배너
친구별 보유 종목 카드. 2-컬럼 압축 레이아웃 (이름·오너칩 / 가격·변화량+%).
- **대장(leader)** 지정 가능 — 대표 1명 + "+N" 형태로 축약, 호버/탭 시 전체 보유자 팝오버
- 오늘 가장 오른 친구 종목을 배너 헤드라인 ("오늘 커피는 X님이!")에 표시
- 장중 60초 폴링으로 카드 시세 + 배너 탑게이너 + 카드 순서(FLIP 애니메이션) 모두 실시간 갱신

### ⭐ 오늘의 핵심 (2-레이어)

**📊 5축 Mood 대시보드**:
- 🏛️ 정책·규제 / 🌏 국제정세 / 🌙 간밤 해외 / 🏭 섹터 기류 / 💱 환율·원자재
- 각 축: 🟢 우호 / 🟡 혼조 / 🔴 부담 + 한 줄 근거

**📰 핵심 뉴스** (개수 제한 없음, 3개 넘으면 "더 보기" 펼침):
- 개별 종목 헤드라인 금지 — 정책·국제·매크로·섹터 전반만
- 각 항목 카테고리 태그: `policy` / `geopolitics` / `macro` / `sector` / `market`

### 🚨 집중 이슈 (focus)
지정학 이슈 같은 중요 상황 (예: 호르무즈 봉쇄):
- 상태 뱃지 (봉쇄/제한/통행) + 일 통행량
- 시간순 정렬된 관련 뉴스, 자세히 보기로 펼침

### 🌙 간밤 해외 시장
S&P·나스닥·VIX·WTI·금·비트코인·달러인덱스 카드 표. `▲ 27.17 +0.44%` 형식 (삼각형=변화량, +/-%=변화율, 혼용 없음).

> 📊 국내 시장 지표 섹션은 상단 ticker로 통합되어 제거됨.

### 🏭 섹터 흐름 (뉴스 중심 브리핑)
**내 보유 종목과 독립** — 섹터 자체의 시황·매크로 뉴스.

각 섹터 카드:
- 이모지 + 이름 + 🟢/🟡/🔴 mood
- 한 줄 내러티브 (`headline`)
- **상위 2개 뉴스 preview** (항상 노출) — impact dot + time_ago + source
- 나머지 뉴스는 "더 보기" 펼침
- 각 뉴스에 `📈 why_material` 캡션 (왜 주가에 영향?)

### 📈 종목별 (개별 종목 뉴스 다이제스트)
**트레이더 아침 루틴 포커스** — 내 보유 종목 각각 오늘 새 뉴스 뭐있나.

**접힌 카드 (요약 행)**:
```
SK하이닉스 000660  🔥 7   +3.37%   매수   👤 이영준 +3
```
- 🔥 N = 오늘 material news 개수

**펼친 body 순서**:
1. **📊 가격 맥락** — 20일 스파크라인(방향별 색상) + 52주 고점·저점 레인지 바 + 현재 위치 핀 + 고점 대비 %
2. **📰 오늘의 뉴스** (**24시간 내** + material만, 5건 + 더보기) — 메인 콘텐츠. render가 24h 넘은 항목은 자동으로 drop. 각 뉴스에 호재/악재/중립 라벨(agent가 주요 건은 직접 라벨, 나머지는 render의 헤드라인 키워드 heuristic으로 자동 분류). 색상 dot + 칩 형태로 표시. 각 뉴스 우측에 👍/👎 피드백 버튼 — 상태는 localStorage 에 저장되어 다음 방문 시 유지 (Iteration 2에서 Worker sync 예정).
3. 결정 근거 블록 (뉴스톤 · 간밤 신호 · 반영 여부 · 신뢰도 · rationale)
4. 🏁 리뷰 결과 (저녁 업데이트 후)
5. 🔬 심층 분석 (`deep_dive: true` 만)
6. 📋 공시

**정렬**: 기본은 오늘 뉴스 수 내림차순 (가장 핫한 종목이 위로).

### 📊 예측 검증 배너 (저녁에만 노출)
`/daily-review` 가 적용한 오버레이:
- 적중/부분/실패 집계
- 신뢰도 버킷별 정확도 (high / medium / low)
- 신호 기여도 (overnight_helped, news_misread, overnight_misled, priced_in_underestimated)

---

## 투자의견 결정 — 3-신호 매트릭스

가치평가·장기전망 아님. **1~5일 단기 뉴스 플로우 예측**.

| 신호 | 값 | 출처 |
|---|---|---|
| **뉴스 톤** (`news_sentiment`) | positive / neutral / negative | LLM이 어제·간밤 뉴스 판단 |
| **간밤 신호** (`overnight_signal`) | up / neutral / down | 종목별 해외 프록시(예: `^SOX, NVDA, MU`) 평균 등락률, 자동 계산 |
| **반영 여부** (`priced_in`) | true / false | 어제 ±5%+ 움직임 + 뉴스 방향 일치면 true |

**조합 매트릭스 요약**:
- 뉴스 긍정 + 간밤 강세 + 반영 안 됨 → `strong_buy`
- 뉴스 긍정 + 간밤 강세 + 이미 반영 → `buy` (과열 경계)
- 뉴스 부정 + 간밤 약세 + 반영 안 됨 → `strong_sell`
- 뉴스 긍정 + 간밤 약세 → `hold` (상충)
- 뉴스 부정 + 간밤 강세 + 이미 반영 → `hold` (어제 급락 반영, 반등 여지)

자세한 매트릭스와 신뢰도(high/medium/low) 부여 기준은 [.claude/commands/daily-report.md](.claude/commands/daily-report.md).

---

## 뉴스 큐레이션 — "오늘 주가에 영향?"

섹터 뉴스와 종목 뉴스 모두에 적용. Agent가 raw news를 정제해서 material만 선별.

**포함 기준** (market-moving):
- 실적·가이던스 변경, 어닝 서프라이즈
- 대형 공시 (자사주 소각, 배당, M&A, 대주주 변동)
- 계약·수주·라이선스 딜
- 규제·정책 (해당 종목 직접 영향)
- 애널리스트 액션 (목표가·의견 변경)
- 파이프라인 진전 (임상, 허가, 특허)
- 경영진 교체
- 매크로 → 개별 종목 인과

**제외**:
- 시황 recap ("KOSPI 6200 마감")
- 운영 루틴 (정기주총, 동반성장협의회, IR 개최)
- 기술적 알림 (가격제한폭, 주식매수선택권)
- stale (>1주, 재부각 없으면)
- 풍문 해명, 단순 수급 flow

각 curated 뉴스에 `why_material` 한 줄 필수 — 왜 주가에 영향인지 설명.

`news: []` (빈 배열)은 agent가 "오늘 material 없음" 선언 → 블록 자체 숨김 + 🔥 N 뱃지 안 뜸.

---

## 저녁 검증

`/daily-review` (20:10 KST)가 아침의 `docs/YYYY-MM-DD.summary.json`을 읽고, 저녁에 새로 긁은 종가와 비교:

- **종목별**: `hit` / `partial` / `miss` (매트릭스 맵핑, [compute_review.py](scripts/compute_review.py))
- **집계**: 적중률, 방향 정확도, 신뢰도 버킷별 정확도
- **신호 기여도**: 실패 케이스를 `news_misread` / `overnight_misled` / `priced_in_underestimated` 로 분류. 누적되면 `stocks.yml` 의 `overnight_proxy` 매핑을 조정할 근거.

---

## 디렉터리 구조

```
k-ant-daily/
├── stocks.yml                          # 종목 + owners + leader + overnight_proxy + deep_dive
├── scripts/
│   ├── fetch_news.py                   # Naver/yfinance/Upbit에서 news.json 조립
│   ├── render.py                       # summary.json → HTML + 영구 summary.json 아티팩트
│   ├── compute_review.py               # 예측 vs 실제 매칭
│   └── launchd/                        # macOS 로컬 스케줄 (install.sh / plists / README.md)
├── templates/
│   ├── report.html.j2                  # 일간 브리핑 (모든 UI)
│   └── archive.html.j2                 # 아카이브 목록
├── worker/                             # Cloudflare Worker (실시간 시세 프록시)
│   ├── src/index.js                    # /quote + /ticker 엔드포인트
│   ├── wrangler.toml
│   └── README.md
├── .claude/commands/
│   ├── daily-report.md                 # 아침 브리핑 스킬 (스키마 · 큐레이션 기준)
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

---

## `stocks.yml` 스키마

```yaml
stocks:
  - code: "000660"
    name: "SK하이닉스"
    market: KOSPI
    owners: ["한윤근", "장한솔", "장윤영", "이영준"]
    leader: "한윤근"                                 # 선택. 대표자 — 지정 안 하면 가나다 첫번째
    overnight_proxy: ["^SOX", "NVDA", "MU"]
    deep_dive: true                                 # WebSearch 기반 딥다이브 대상
    keywords: ["SK하이닉스", "HBM"]                  # 딥다이브 리서치 seed
```

- `owners`: 여러 명 가능. 한 친구가 여러 종목 보유 가능.
- `leader`: 대표자. render 가 owners를 leader 먼저 + 나머지 가나다 순으로 정렬. UI에는 대표 1명 + "+N" 형식으로 축약.
- `overnight_proxy`: 섹터별 가이드
  - 반도체 `["^SOX", "NVDA", "MU"]`
  - 바이오 `["XBI", "IBB"]`
  - 방산 `["ITA", "LMT", "RTX"]`
  - 배터리/정유 `["XLE", "CL=F", "TSLA"]`
  - 전력 `["GEV", "ETN", "XLU"]`
  - 자동차 `["F", "GM", "STLA"]`
  - 인터넷/플랫폼 `["META", "GOOGL", "^IXIC"]`
  - 엔터 `["SPOT", "WMG"]`
  - 카지노/관광 `["LVS", "WYNN", "MGM"]`
  - 코스닥 ETF `["^IXIC", "QQQ"]`
- `deep_dive: true`: 브리핑 때 WebSearch/WebFetch로 심층 리서치 (토큰 소비 크므로 2~3개로 제한 권장).

---

## 스케줄링

### macOS launchd (기본 — Mac mini 24/7 운용)

```bash
./scripts/launchd/install.sh   # 최초 1회
```

두 LaunchAgent:
- `com.yummyummyummy.k-ant-daily.briefing` — 평일 **07:30 KST**
- `com.yummyummyummy.k-ant-daily.review`   — 평일 **20:10 KST**

Wrapper 안전장치:
- working tree dirty 면 `exit 2` — 로컬 수정 날아가는 것 방지
- `git reset --hard origin/main` + `git pull` 로 최신 동기화
- Claude CLI: `claude --dangerously-skip-permissions --print "/daily-report"`

로그: `~/Library/Logs/k-ant-daily/`. 상세: [scripts/launchd/README.md](scripts/launchd/README.md).

### 클라우드 (비활성, 백업용)

동일한 스케줄이 `claude.ai/code/scheduled` 에 `enabled: false` 로 등록됨. Mac 장시간 미가동 시 [claude.ai/code/scheduled](https://claude.ai/code/scheduled) 에서 enable로 전환.

---

## 실시간 시세 인프라 (Cloudflare Worker)

커피 배너 · 상단 ticker 모두 **장중 60초 폴링**. Worker가 CORS 프록시 + 30초 edge 캐시:

```bash
cd worker
wrangler deploy        # 최초 1회 wrangler login 필요
```

엔드포인트:
- `GET /quote?codes=005930,000660,...` — 종목 시세 (Naver realtime polling)
- `GET /ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH` — 지표·FX·암호화폐 통합

상세: [worker/README.md](worker/README.md).

**아카이브 무결성**:
- `<body data-date="YYYY-MM-DD">` 와 JS `isLivePage()` 비교로 과거 페이지는 폴링 차단
- 과거 날짜 열람 시 "📁 아카이브 — 스냅샷" 표시, 당일 종가·지표 그대로 보존

---

## 로컬 수동 실행

```bash
source .venv/bin/activate
pip install -r requirements.txt                  # pinned versions
python scripts/fetch_news.py                     # → .tmp/news.json

# Option A: Claude CLI로 전자동
claude --dangerously-skip-permissions --print "/daily-report"

# Option B: summary.json 직접 작성 후 수동 렌더
python scripts/render.py .tmp/summary.json

# 저녁 리뷰
python scripts/compute_review.py [YYYY-MM-DD]
python scripts/render.py .tmp/summary.json
```

Production과 동일 시퀀스는 `scripts/launchd/run-briefing.sh` / `run-review.sh`.

---

## 요구사항

- **Python 3.11+** — `requirements.txt` pinned (requests, beautifulsoup4, PyYAML, Jinja2, yfinance, feedparser, lxml)
- **Claude Code CLI** — `claude -p` non-interactive 모드 · 구독 사용량 소비
- **macOS** (launchd 사용 시) — 또는 cron/systemd 등으로 대체 가능
- **Cloudflare 계정** — Workers 무료 플랜이면 충분
- **GitHub Pages** — `main` 브랜치 `docs/` 폴더 기반 자동 배포

---

## 주의

- **투자 권유 아님.** LLM이 뉴스 플로우를 해석한 단기(1~5일) 방향 전망일 뿐, 종목 가치평가·장기 전망 아님.
- 투자의견(`풀매수/매수/관망/매도/풀매도`)은 **뉴스·간밤 시장·선반영 여부** 의 조합 휴리스틱. 중요한 판단은 원문 링크 확인.
- 클라우드 인프라·Worker 모두 개인 사용 규모. 트래픽 증가 시 Naver 레이트리밋 or Cloudflare 무료 한도 확인 필요.
- 친구 실명·보유 내역이 공개 `docs/*.html` 에 노출됨. 민감하면 private 리포지토리 or 렌더 시 이니셜화.

---

## 로드맵

"아침 스캔 도구로서 정점을 찍는" 방향 (HTS·TradingView 영역 중복 지양).

**Phase 1 — 진행 중**
- ✅ **스파크라인** (20일 종가 미니차트) — 구현 완료
- ✅ **52주 고점·저점 거리** — 구현 완료
- 🔨 **누적 리뷰 대시보드** — 주간/월간 적중률, 신뢰도별 성과 트렌드 (리뷰 데이터 누적 필요)
- 🟡 **큐레이션 피드백 버튼** (👍👎) — **Iteration 1 완료** (localStorage 저장). 다음: Worker sync + agent prompt 주입

**Phase 2 — 데이터 쌓인 후**
- 큐레이션 기준 튜닝 (누적 리뷰 기반)
- 섹터 ETF 성과 카드
- Agent 프롬프트 튜닝 (누적 review + 피드백 로그 기반)

**명시적으로 안 할 것** (ROI 낮음 / 다른 도구가 더 잘함)
- ❌ 실적 캘린더 — HTS 가 이미 잘 보여줌, 무료 데이터 fragile
- ❌ 컨센서스 목표가 — 유료 데이터 없인 품질 보장 불가
- ❌ 기술 지표 (MA, MACD, RSI) — TradingView 가 월등
- ❌ 중간 알림 — 인프라 복잡도 과다, ROI 낮음
- ❌ 매매 연동 — 규제·책임 이슈
