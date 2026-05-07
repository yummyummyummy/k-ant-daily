# CLAUDE.md — k-ant-daily

Automated daily KRX (Korea Exchange) briefing system for a friend group's stock portfolio.
Static site on GitHub Pages + Claude Code CLI agent + Cloudflare Worker for live quotes.

## Daily Cycle

| Time (KST) | Job | Skill / Script | Output |
|---|---|---|---|
| 07:30 | Pre-market briefing | `/daily-report` | `docs/YYYY-MM-DD.html` + `.summary.json` |
| 08:45 | NXT snapshot | `snapshot_nxt.py` | NXT pre-open data baked into summary.json |
| 20:10 | Post-session review | `/daily-review` | Review overlay on same HTML |
| 23:00 | Post-market digest | `/post-market-digest` | `docs/digest.html` |

## Tech Stack

- **Python 3.11+** — data collection & rendering (`requests`, `beautifulsoup4`, `yfinance`, `Jinja2`, `PyYAML`)
- **Jinja2 templates** — `templates/*.html.j2` → `docs/*.html`
- **Cloudflare Worker** — `worker/src/index.js`, live quote CORS proxy (Naver/Upbit)
- **GitHub Pages** — static deploy from `docs/` folder
- **macOS launchd** — `scripts/launchd/` scheduler (Mac mini 24/7)
- **Claude Code CLI** — `claude --dangerously-skip-permissions --print "/daily-report"` non-interactive execution

## Directory Structure

```
stocks.yml                     # Stock master — code, name, owners, leader, overnight_proxy, deep_dive
scripts/
  fetch_news.py                # Naver/yfinance/Upbit → .tmp/news.json
  render.py                    # summary.json → HTML + docs/YYYY-MM-DD.summary.json persistent artifact
  compute_review.py            # Prediction vs actual close → .tmp/summary.json with review block
  promote_rules.py             # Cluster repeated lessons → docs/promoted_rules.md promotion
  snapshot_nxt.py              # 08:45 NXT pre-open snapshot → baked into summary.json
  labels.py                    # Shared label maps (recommendation, impact, outcome, etc.)
  launchd/                     # macOS schedule: plists + wrapper shells + install.sh
templates/
  report.html.j2               # Daily briefing (main UI)
  digest.html.j2               # Post-market digest
  accuracy_day.html.j2         # Per-day review detail
  accuracy.html.j2             # Cumulative stats
  archive.html.j2              # Archive listing
  _theme.css.j2                # Shared CSS
worker/
  src/index.js                 # Cloudflare Worker (GET /quote, /ticker, /stock-news, /nxt-quotes)
.claude/commands/
  daily-report.md              # Morning briefing skill (schema, curation rules, decision matrix)
  daily-review.md              # Evening review skill
  post-market-digest.md        # 23:00 digest skill
docs/                          # GitHub Pages (git-tracked output)
  YYYY-MM-DD.html              # Daily report
  YYYY-MM-DD.summary.json      # Persistent prediction artifact (read by review)
  accuracy/YYYY-MM-DD.html     # Per-day review page
  digest.html                  # Post-market digest
  index.html                   # JS router (time-of-day routing)
  archive.html                 # Archive listing
  promoted_rules.md            # Auto-promoted rules
.tmp/                          # Runtime scratch (gitignored)
  news.json                    # fetch_news.py output
  summary.json                 # Agent-written → render input
```

## Core Data Flow

```
fetch_news.py → .tmp/news.json
                    ↓
        Claude agent analysis & judgment
                    ↓
            .tmp/summary.json
                    ↓
render.py → docs/YYYY-MM-DD.html + docs/YYYY-MM-DD.summary.json
```

Evening review:
```
docs/YYYY-MM-DD.summary.json (morning prediction)
  + .tmp/news.json (evening close prices)
      ↓
  compute_review.py → .tmp/summary.json (review block merged)
      ↓
  Agent writes retrospective analysis
      ↓
  render.py → HTML overlay + accuracy pages
```

## Development Rules

### stocks.yml Management
- If `owners` becomes empty, delete the entry immediately — never leave `owners: []`
- `leader` is optional. When set, shown as the representative in the coffee banner (crown icon)
- `overnight_proxy` is an array of overseas proxy tickers per sector (yfinance symbols)

### When Changing Code
- **Keep README.md in sync** — update README.md in the same commit as any code/schema/UI/skill change
- `labels.py` holds shared label maps used by render.py and compute_review.py — manage label additions/changes here
- `render.py` flags: `--digest` for digest mode, `--intraday` to skip archive/accuracy regeneration

### Commit Message Convention
- `report: YYYY-MM-DD briefing` — morning briefing
- `nxt-snapshot: YYYY-MM-DD HH:MM NXT 반영` — NXT snapshot
- `review: YYYY-MM-DD post-session review` — evening review
- `digest: YYYY-MM-DD post-market` — post-market digest
- General changes: `feat:` / `fix:` / `chore:` / `refactor:`

### Prose Language Rules (Korean UI text)
In user-facing text fields (`rationale`, `summary`, `why_material`, `day_summary`, etc.):
- No raw JSON field names or English schema identifiers — use natural Korean
- `priced_in=True` → "선반영", `overnight_signal=up` → "간밤 강세"
- `buy/sell/hold` → "상승 기대/하락 경계/관망"

## Local Development

```bash
# Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Fetch news
python scripts/fetch_news.py           # → .tmp/news.json

# Manual render (when summary.json is ready)
python scripts/render.py .tmp/summary.json

# Review calculation
python scripts/compute_review.py [YYYY-MM-DD]

# Promote rules
python scripts/promote_rules.py [--dry-run]

# NXT snapshot
python scripts/snapshot_nxt.py [YYYY-MM-DD]

# Worker deploy
cd worker && wrangler deploy
```

## Scheduled Automation

Install launchd agents: `./scripts/launchd/install.sh` (one-time).
Logs: `~/Library/Logs/k-ant-daily/`.

Four LaunchAgents:
- `briefing` (07:30 weekdays) — `run-briefing.sh` → `claude /daily-report`
- `nxt-snapshot` (08:45 weekdays) — `run-nxt-snapshot.sh` → `snapshot_nxt.py` + `render.py --intraday`
- `review` (20:10 weekdays) — `run-review.sh` → `claude /daily-review`
- `digest` (23:00 daily) — `run-digest.sh` → `claude /post-market-digest`

Wrapper safety: exits with code 2 if working tree is dirty; runs `git reset --hard origin/main` before execution.

## Worker Endpoints

`k-ant-daily-quotes.yummyummyummy.workers.dev`:
- `GET /quote?codes=...` — stock quotes (30s edge cache)
- `GET /ticker?items=KOSPI,KOSDAQ,USDKRW,BTC,ETH` — unified indicators
- `GET /stock-news?codes=...` — stock news (5min edge cache)
- `GET /nxt-quotes?codes=...` — NXT change rates (2min edge cache)

## Important Notes

- HTML/JSON in `docs/` is generated by render.py — do not edit manually (overwritten on next render)
- `.tmp/` is gitignored runtime scratch — persistent data lives in `docs/*.summary.json`
- Real names of friends are exposed in public HTML — switch to private repo if sensitive
- Not investment advice — LLM-based short-term directional heuristic
