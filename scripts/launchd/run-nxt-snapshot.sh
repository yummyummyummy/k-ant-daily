#!/bin/bash
# 08:45 KST NXT pre-open snapshot (weekdays).
# Runs `snapshot_nxt.py` which fetches /nxt-quotes from the Worker, bakes
# the result into today's docs/<date>.summary.json, re-renders the page,
# and commits + pushes. No agent/claude — pure Python + git.
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/nxt-snapshot-$TS.log"

exec >"$LOG" 2>&1

echo "=== k-ant-daily nxt-snapshot @ $(date) ==="

export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

# Pull whatever the morning briefing pushed before we touch summary.json.
git fetch origin main >/dev/null 2>&1 && git reset --hard origin/main

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

DATE="$(date +%Y-%m-%d)"
.venv/bin/python scripts/snapshot_nxt.py "$DATE"
STATUS=$?

if [ $STATUS -eq 0 ]; then
    git add "docs/$DATE.summary.json" "docs/$DATE.html" docs/index.html docs/archive.html docs/accuracy.html 2>/dev/null
    if ! git diff --cached --quiet; then
        git commit -m "nxt-snapshot: $DATE 08:45 NXT 반영" || true
        git pull --rebase origin main || true
        git push || true
    else
        echo "no changes after snapshot — skip commit"
    fi
fi

echo "=== exit status: $STATUS @ $(date) ==="
exit $STATUS
