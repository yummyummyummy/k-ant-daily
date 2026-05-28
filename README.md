# k-ant-daily

친구들 보유 한국 주식의 **월간 이벤트 캘린더** + **일일 보유종목 트래커**.

매일 아침 07:30 KST 에 시세·뉴스·임상/공시 일정을 자동으로 갱신해 GitHub Pages 로 배포한다. 예측이나 베팅 기능은 없음 — 사실/일정 기반 트래킹만.

**공개 URL:** https://yummyummyummy.github.io/k-ant-daily/

---

## 컨셉

이전 버전은 "오늘 장 예측" 서비스였지만, 현재는 **캘린더 + 트래킹** 으로 전환:

- ❌ 매일 종목별 매수/매도 추천 → 안 함
- ❌ 예측 검증, 정확도 통계, 베팅 게임 → 모두 제거
- ✅ **월간 이벤트 캘린더** — FOMC, 학회, 보유종목 임상 일정, KRX 휴장일 등
- ✅ **보유종목 일일 트래킹** — 매일 아침 시세/뉴스/공시 갱신

---

## 페이지 구성

### `/calendar.html` (메인)
- 상단: 매크로 리본 (KOSPI/KOSDAQ/S&P/NASDAQ + FX + BTC/ETH)
- **⭐ 오늘 이벤트** — 오늘 일자에 매칭되는 이벤트 카드. 없으면 자동 숨김
- 친구들 보유종목 카드 (시세 + 등락률 + 보유자 + 최신 헤드라인 + 다음 일정)
- 월간 그리드 캘린더 — 카테고리별 색상 (거시/학회/임상/IR/공시/휴장)
- 카테고리 필터, 월 이동, 이벤트 클릭 시 상세 패널 (description + 💡 시장 영향)
- 다가오는 7일 이벤트 목록

### `/digest.html` (포스트마켓)
매일 23:00 KST 발행:
- 🇰🇷 한국 장 마감 후 / 🇺🇸 미국 장중 / 🌏 글로벌 매크로 / 📁 포트폴리오 공시
- 주요 헤드라인, 다가오는 이벤트

### `/index.html` (라우터)
- 평일 07:30 ~ 23:00 → `calendar.html`
- 평일 23:00 ~ 다음날 07:30 + 주말 → `digest.html`

---

## 캘린더 이벤트 소스

3개 소스를 머지해서 `docs/events.json` 생성:

| 소스 | 파일 | 카테고리 | 비고 |
|---|---|---|---|
| 수동 큐레이션 | `events.yml` | 학회/거시/IR/휴장 | 사람이 검증한 가장 신뢰 가능한 source |
| ClinicalTrials.gov API | `.tmp/events_clinical.json` | clinical (예상) | 보유 바이오 종목의 임상 primary completion date |
| DART OpenAPI | `.tmp/events_dart.json` | disclosure | 보유 종목 최근 30일 공시 (`DART_API_KEY` 필요) |

### 자동 수집 활성화 — `stocks.yml` 옵션 필드

```yaml
- code: "196170"
  name: "알테오젠"
  ...
  clinical_sponsor: "Alteogen Inc."   # ClinicalTrials.gov 검색용
  dart_corp_code: "00567832"          # opendart.fss.or.kr 에서 조회한 8자리
```

### 한계

- ClinicalTrials.gov `primary_completion_date` 는 데이터 수집 완료 예상일이고 실제 readout 발표는 보통 3~6개월 뒤. `estimated` 태그로 구분
- DART 공시는 대부분 사후 announcement
- 한국 바이오의 readout 발표일은 사전 공지가 드물어 매일 뉴스 모니터링 필요

---

## 디렉터리 구조

```
k-ant-daily/
├── stocks.yml                          # 종목 + owners + leader (+ clinical_sponsor + dart_corp_code)
├── events.yml                          # 수동 큐레이션 이벤트
├── scripts/
│   ├── fetch_news.py                   # Naver/Upbit → .tmp/news.json
│   ├── fetch_clinical_trials.py        # ClinicalTrials.gov v2 → .tmp/events_clinical.json
│   ├── fetch_dart.py                   # DART OpenAPI → .tmp/events_dart.json
│   ├── build_calendar.py               # 머지 → docs/events.json
│   ├── render.py                       # → docs/calendar.html + index.html (또는 --digest)
│   ├── pending_results.py              # 결과 대기 이벤트 개수 (check-results gate)
│   └── launchd/                        # macOS 로컬 스케줄
├── templates/
│   ├── calendar.html.j2                # 메인 — 캘린더 + 보유종목 패널
│   ├── digest.html.j2                  # 포스트마켓
│   └── _theme.css.j2                   # 공통 색상/리셋
├── worker/                             # Cloudflare Worker (시세/뉴스 프록시)
│   ├── src/index.js                    # /quote · /ticker · /stock-news · /nxt-quotes
│   └── wrangler.toml
├── .claude/commands/
│   ├── daily-report.md                 # 아침 갱신 스킬
│   ├── post-market-digest.md           # 23:00 다이제스트 스킬
│   └── check-results.md                # 인트라데이 이벤트 결과 채우기 스킬
├── docs/                               # GitHub Pages
│   ├── calendar.html                   # 메인
│   ├── digest.html                     # 포스트마켓
│   ├── events.json                     # 캘린더 데이터
│   ├── index.html                      # JS 라우터
│   ├── YYYY-MM-DD.html / .summary.json # legacy, 새로 생성 안 함
│   └── accuracy/                       # legacy 보존
└── .tmp/                               # 런타임 scratch (gitignored)
```

---

## 일일 사이클

| 시각 (KST) | 잡 | 스크립트 / 스킬 | 산출 |
|---|---|---|---|
| 평일 07:30 | 캘린더 + 보유종목 갱신 | `/daily-report` | `docs/calendar.html` + `docs/events.json` |
| 매일 23:00 | 포스트마켓 다이제스트 | `/post-market-digest` | `docs/digest.html` |
| 30분 주기 | 이벤트 결과 반영 (cheap-gated) | `/check-results` | `events.yml` `result` 갱신 |

### 이벤트 결과 실시간 추적 (하이브리드)

발표성 이벤트 (FOMC·CPI·고용·금통위·학회 등) 가 끝나면 결과를 두 갈래로 반영:
- **A. 시장 반응 (즉시·무료)**: 클라이언트가 이벤트 `time` 경과 즉시 관련 종목/지수의 당일 등락률을 "📈 시장 반응 (자동)" 으로 표시. 이미 폴링 중인 시세 데이터 사용, LLM 불필요
- **B. 질적 결과 (~30분)**: `/check-results` 가 30분 주기로 방금 끝난 이벤트의 실제 결과(금리 동결/인하, 수치 beat/miss 등)를 WebSearch 로 조사해 `result` 채움. `pending_results.py` 가 게이트 — 결과 대기 이벤트 없으면 Claude 안 부름 (사용량 0)

`/daily-report` 의 내부 흐름:
1. `fetch_news.py` + `fetch_clinical_trials.py` + `fetch_dart.py` 병렬 실행
2. Agent 가 `events.yml` 검토/갱신 — 새 학회 일정, FOMC 등 외부 자료 확인 후 추가
3. `build_calendar.py` 가 모든 source 머지 → `docs/events.json`
4. `render.py` 가 HTML 생성
5. git commit + push

상세 룰북: [.claude/commands/daily-report.md](.claude/commands/daily-report.md), [.claude/commands/post-market-digest.md](.claude/commands/post-market-digest.md).

---

## 스케줄링

### macOS launchd (Mac mini 24/7)

```bash
./scripts/launchd/install.sh   # 최초 1회
```

세 LaunchAgent:
- `com.yummyummyummy.k-ant-daily.briefing`      — 평일 **07:30 KST**
- `com.yummyummyummy.k-ant-daily.digest`        — 매일 **23:00 KST**
- `com.yummyummyummy.k-ant-daily.check-results` — **30분 주기** (이벤트 결과 반영, cheap-gated)

Wrapper 가 `git reset --hard origin/main` 으로 동기화 후 `claude --dangerously-skip-permissions --print "/daily-report"` (또는 digest) 실행.

⚠️ **주의**: wrapper 가 매 실행마다 git reset 을 수행하므로 push 안 한 로컬 변경은 다음 실행 시 모두 날아감.

로그: `~/Library/Logs/k-ant-daily/`. 상세: [scripts/launchd/README.md](scripts/launchd/README.md).

---

## `stocks.yml` 스키마

```yaml
stocks:
  - code: "000660"
    name: "SK하이닉스"
    market: KOSPI
    sector: "반도체"
    owners: ["한윤근", "장한솔", "장윤영", "이영준"]
    leader: "한윤근"                          # 선택 — UI 대표자 (👑)
    overnight_proxy: ["^SOX", "NVDA", "MU"]   # 선택 — 표시용
    clinical_sponsor: "..."                   # 선택 — ClinicalTrials.gov 자동 수집
    dart_corp_code: "..."                     # 선택 — DART 공시 자동 수집
```

- `owners`: 친구 이름 배열. 비면 entry 즉시 삭제 (`owners: []` 금지)
- `leader`: UI 강조용 대표자 (없으면 가나다 첫번째)

---

## `events.yml` 스키마

```yaml
events:
  - date: "2026-06-04"                  # 또는 date_range: ["2026-06-04", "2026-06-08"]
    category: "conference"              # macro|conference|holiday|earnings|ir|clinical|disclosure|other
    title: "ASCO 2026 Annual Meeting"
    time: "21:30"                       # 선택 — 결과 발표 시각 (KST). 지나면 UI가 결과 추적
    description: "factual 한 줄"
    impact: |
      🎯 핵심: ...
      📊 보는 법: 시나리오별 시장 반응
      📁 우리 보유에: 종목별 영향
    related_codes: ["196170"]
    tags: ["bio", "oncology"]
    source: "https://asco.org/..."
    importance: 3                       # 1~3 (기본 2)
    result:                             # 선택 — 이벤트 종료 후 agent 가 채움
      outcome: positive                 # positive|negative|neutral|asexpected
      summary: "실제 결과 + 시장 반응 1~2줄"
      filled_at: "2026-06-04"
```

**결과 자동 추적**: `time` (또는 다일 이벤트의 마지막 날) 이 지나면 캘린더가 해당 이벤트에 "⏳ 결과 집계 중" 을 표시하고, 다음 `/daily-report` (07:30) 또는 `/post-market-digest` (23:00) 실행 때 agent 가 실제 결과를 조사해 `result` 를 채운다. 채워지면 "✅ 결과" 블록으로 전환 (outcome 에 따라 색상).

---

## 실시간 시세 인프라 (Cloudflare Worker)

장중 60초 폴링용 CORS 프록시 (Naver Finance / Upbit):

```bash
cd worker
wrangler deploy
```

엔드포인트:
- `GET /quote?codes=005930,000660,...` — 종목 시세 (30s edge 캐시)
- `GET /ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH` — 지표·FX·암호화폐
- `GET /stock-news?codes=...` — 종목별 뉴스 (5분 edge 캐시)
- `GET /nxt-quotes?codes=...` — NXT 대체거래 등락률 (2분 edge 캐시)

상세: [worker/README.md](worker/README.md).

---

## 로컬 수동 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/fetch_news.py
python scripts/fetch_clinical_trials.py
DART_API_KEY=xxx python scripts/fetch_dart.py   # 옵션

python scripts/build_calendar.py
python scripts/render.py            # → docs/calendar.html + docs/index.html
python scripts/render.py --digest   # → docs/digest.html (.tmp/digest.json 필요)
```

Claude CLI 로 자동화 (production 과 동일):
```bash
claude --dangerously-skip-permissions --print "/daily-report"
```

---

## 요구사항

- **Python 3.11+** — `requirements.txt` (requests · beautifulsoup4 · PyYAML · Jinja2 · yfinance · feedparser · lxml)
- **Claude Code CLI** — `claude -p` non-interactive 모드
- **macOS** (launchd) — 또는 cron 등으로 대체
- **Cloudflare Workers 무료 플랜** — 시세/뉴스 프록시
- **GitHub Pages** — `main` 브랜치 `docs/` 자동 배포
- **DART_API_KEY** (옵션) — opendart.fss.or.kr 무료 발급

---

## 주의

- **투자 권유 아님.** 일정 트래킹 도구일 뿐, 매매 의견 / 가치평가 / 추천 없음.
- 친구 실명·보유 내역이 공개 `docs/` 에 노출됨. 민감하면 private 리포지토리 사용.

---

## 이전 버전 (Legacy)

`docs/YYYY-MM-DD.html`, `docs/YYYY-MM-DD.summary.json`, `docs/accuracy/`, `docs/promoted_rules.md` 등은 이전 예측 컨셉의 산출물 — 보존만 하고 새로 생성 안 함.
