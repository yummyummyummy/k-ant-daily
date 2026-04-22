#!/bin/bash
# Intraday news refresh — every 10 min during KRX market hours.
# Re-runs fetch_news.py + render.py so the dated report page picks up fresh
# Naver articles and intraday quote data without touching the morning LLM
# analysis (rationale / key_points stay frozen, only news + prices refresh).
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"

# Self-gate: only run on weekdays between 09:00 and 15:30 KST. Anything else
# is a cheap no-op so launchd's 10-min tick can fire 24/7 without wasting
# cycles at night.
DOW="$(date +%u)"          # 1=Mon … 7=Sun
HM="$(date +%H%M)"
if [ "$DOW" -gt 5 ]; then exit 0; fi
if [ "$HM" -lt 0900 ] || [ "$HM" -gt 1530 ]; then exit 0; fi

TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/refresh-$TS.log"
exec >"$LOG" 2>&1

echo "=== k-ant-daily intraday refresh @ $(date) ==="

export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

TODAY="$(date +%Y-%m-%d)"
SUMMARY="docs/${TODAY}.summary.json"

# If morning briefing hasn't run yet (no today's summary), nothing to refresh.
if [ ! -f "$SUMMARY" ]; then
    echo "no summary for $TODAY yet — skipping"
    exit 0
fi

# Refresh the news + quote scrape
.venv/bin/python scripts/fetch_news.py || {
    echo "fetch_news failed — skipping render"
    exit 1
}

# Re-render from today's summary (agent analysis stays, news + quotes update).
# --intraday skips archive.html / accuracy.html / accuracy/*.html — those are
# driven by the evening review block which only changes once per day, so
# regenerating them every 10 min just churns timestamps into git.
.venv/bin/python scripts/render.py "$SUMMARY" --intraday || {
    echo "render failed"
    exit 1
}

# Push so GitHub Pages picks up the fresh HTML. Commit is conservative — if
# nothing actually changed (rare), skip. Ignore push conflicts from concurrent
# work by rebasing; aggregate pages are regeneratable so --ours is safe.
git add docs/
if git diff --cached --quiet; then
    echo "no diff — nothing to commit"
    exit 0
fi
git commit -m "refresh: $(date +%Y-%m-%d' '%H:%M) intraday news/quote update"
if ! git pull --rebase origin main; then
    git checkout --ours -- docs/index.html docs/archive.html docs/accuracy.html docs/accuracy/ 2>/dev/null || true
    .venv/bin/python scripts/render.py "$SUMMARY" --intraday
    git add docs/
    git rebase --continue
fi
git push origin main
echo "=== refresh done @ $(date) ==="
