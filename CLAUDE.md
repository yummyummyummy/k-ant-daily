# CLAUDE.md — k-ant-daily

친구 그룹의 한국 주식 포트폴리오 기반 **월간 이벤트 캘린더 + 일일 보유종목 트래커**.
GitHub Pages 정적 사이트 + Claude Code CLI 에이전트 + Cloudflare Worker (시세 프록시).

## 컨셉

매일 아침 캘린더와 보유종목 시세를 갱신해 publish. **예측·베팅·매매 의견 없음** — 사실/일정 기반 트래킹만.

## Behavioral Guidelines

> Adapted from [forrestchang/andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills/blob/main/CLAUDE.md).
> Bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

---

## Daily Cycle

| Time (KST) | Job | Skill / Script | Output |
|---|---|---|---|
| 평일 07:30 | 캘린더 + 보유종목 갱신 | `/daily-report` | `docs/calendar.html`, `docs/events.json` |
| 매일 23:00 | 포스트마켓 다이제스트 | `/post-market-digest` | `docs/digest.html` |

## Tech Stack

- **Python 3.11+** — `requests`, `beautifulsoup4`, `PyYAML`, `Jinja2`
- **Jinja2 templates** — `templates/*.html.j2` → `docs/*.html`
- **Cloudflare Worker** — `worker/src/index.js`, 시세 CORS 프록시 (Naver/Upbit)
- **GitHub Pages** — static deploy from `docs/`
- **macOS launchd** — `scripts/launchd/`
- **Claude Code CLI** — `claude --dangerously-skip-permissions --print "/daily-report"` non-interactive 실행

## Directory Structure

```
stocks.yml                     # 종목 — code, name, owners, leader, overnight_proxy
                               # 옵션: clinical_sponsor (CT.gov 검색), dart_corp_code (DART)
events.yml                     # 수동 큐레이션 이벤트 (학회/거시/IR/휴장)
scripts/
  fetch_news.py                # Naver/Upbit → .tmp/news.json (시세/뉴스/공시)
  fetch_clinical_trials.py     # ClinicalTrials.gov v2 → .tmp/events_clinical.json
  fetch_dart.py                # DART OpenAPI → .tmp/events_dart.json (DART_API_KEY)
  build_calendar.py            # events.yml + .tmp/events_*.json → docs/events.json
  render.py                    # → docs/calendar.html + docs/index.html (또는 --digest)
  launchd/                     # macOS schedule + wrapper shells
templates/
  calendar.html.j2             # 메인 — 월간 캘린더 + 보유종목 패널
  digest.html.j2               # 포스트마켓 다이제스트
  _theme.css.j2                # 공통 색상/리셋
worker/
  src/index.js                 # /quote · /ticker · /stock-news · /nxt-quotes
.claude/commands/
  daily-report.md              # 아침 갱신 스킬 (이벤트 큐레이션 규칙)
  post-market-digest.md        # 23:00 다이제스트 스킬
docs/                          # GitHub Pages (git-tracked)
  calendar.html                # 메인
  digest.html                  # 포스트마켓
  events.json                  # 캘린더 데이터 (client-side fetch)
  index.html                   # JS 라우터 (시간대 기반)
.tmp/                          # 런타임 scratch (gitignored)
```

## Data Flow

**아침 (07:30):**
```
fetch_news.py               → .tmp/news.json
fetch_clinical_trials.py    → .tmp/events_clinical.json
fetch_dart.py               → .tmp/events_dart.json
        ↓
events.yml (agent 가 큐레이션 갱신)
        ↓
build_calendar.py           → docs/events.json
        ↓
render.py                   → docs/calendar.html + docs/index.html
```

**저녁 (23:00):**
```
fetch_news.py            → .tmp/news.json (23:00 재실행)
        ↓
agent → .tmp/digest.json (sections + highlights + upcoming)
        ↓
render.py --digest       → docs/digest.html
```

## Development Rules

### stocks.yml Management
- `owners` 가 비면 entry 즉시 삭제 — 절대 `owners: []` 두지 말 것
- `leader` 옵션. 지정 시 UI 대표자 (👑)
- `clinical_sponsor` 추가하면 ClinicalTrials.gov 자동 수집 활성화
- `dart_corp_code` 추가하면 DART 공시 자동 수집 활성화 (`DART_API_KEY` env 필요)

### events.yml Management
- 확정된 일자만 추가. 추측 금지
- "예상" 인 경우 description 에 명시 + tags 에 `estimated`
- 거시 일정은 출처 URL (`source`) 필수
- 결과 시나리오 / 보유종목 영향은 `impact` 필드에 작성
- 발표/결과성 이벤트는 `time` (HH:MM KST) 추가 → 시간 지나면 UI 가 "결과 집계 중" 표시
- 지난 이벤트는 daily-report/digest 실행 시 `result` (outcome/summary/filled_at) 채움 — 실제 결과 + 시장 반응

### When Changing Code
- **Keep README.md in sync** — README.md 를 코드/스키마/UI/스킬 변경과 같은 commit 에 업데이트
- `render.py` 플래그: `--digest` for digest mode
- **🚨 작업 후 반드시 commit + push** — launchd briefing/digest wrapper 가 매 실행마다 `git reset --hard origin/main` 으로 작업 트리를 원격에 강제 동기화함. commit 안 한 변경은 다음 wake-up 에 모두 날아감

### Commit Message Convention
- `report: YYYY-MM-DD calendar 갱신` — 아침 갱신
- `digest: YYYY-MM-DD post-market` — 포스트마켓 다이제스트
- 일반 변경: `feat:` / `fix:` / `chore:` / `refactor:`

### Prose Language Rules (Korean UI text)
사용자 대면 텍스트 (events.yml 의 title/description/impact, digest sections 등):
- 영어 schema 키 / 약어 노출 금지 — 자연스러운 한국어
- "예측", "강력 매수" 같은 directional language 금지
- 사실 동사만 ("발표됐다", "공시됐다")

## Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python scripts/fetch_news.py
python scripts/fetch_clinical_trials.py
DART_API_KEY=xxx python scripts/fetch_dart.py    # 옵션

python scripts/build_calendar.py
python scripts/render.py            # → docs/calendar.html + docs/index.html
python scripts/render.py --digest   # → docs/digest.html (.tmp/digest.json 필요)

cd worker && wrangler deploy
```

## Scheduled Automation

Install launchd agents: `./scripts/launchd/install.sh` (one-time).
Logs: `~/Library/Logs/k-ant-daily/`.

두 LaunchAgents:
- `briefing` (07:30 평일) — `run-briefing.sh` → `claude /daily-report`
- `digest` (23:00 매일) — `run-digest.sh` → `claude /post-market-digest`

Wrapper safety: `git reset --hard origin/main` before execution. **Push 안 된 로컬 변경 보호 안 됨.**

## Worker Endpoints

`k-ant-daily-quotes.yummyummyummy.workers.dev`:
- `GET /quote?codes=...` — 종목 시세 (30s edge 캐시)
- `GET /ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH` — 지표/FX/암호화폐
- `GET /stock-news?codes=...` — 종목별 뉴스 (5분 edge 캐시)
- `GET /nxt-quotes?codes=...` — NXT 대체거래 등락률 (2분 edge 캐시)

## Important Notes

- `docs/calendar.html` · `docs/events.json` · `docs/digest.html` 은 render 가 자동 생성 — 수동 편집 금지
- `.tmp/` 는 gitignore — 영구 데이터 없음
- 친구 실명이 공개 HTML 에 노출됨. 민감하면 private repo
- 투자 권유 아님 — 일정 트래킹 도구

## Legacy (보존만)

이전 예측 컨셉의 산출물은 git history 와 `docs/` 에 남아있음:
- `docs/YYYY-MM-DD.html` / `.summary.json`, `docs/accuracy/`, `docs/promoted_rules.md`, `docs/archive.html`, `docs/accuracy.html`
- 새 컨셉에서 생성 안 함. 시간 지나면 분리 archive 로 옮길 예정
