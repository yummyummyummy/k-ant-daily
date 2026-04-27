#!/bin/bash
# Post-market digest (23:00 KST daily — both weekdays + weekends).
# Wraps `claude /post-market-digest` for launchd-scheduled execution.
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/digest-$TS.log"

exec >"$LOG" 2>&1

echo "=== k-ant-daily digest @ $(date) ==="

export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

# Pull whatever the review (or any other run) pushed before we touch docs.
git fetch origin main >/dev/null 2>&1 && git reset --hard origin/main

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

claude --dangerously-skip-permissions --print "/post-market-digest"
STATUS=$?

echo "=== exit status: $STATUS @ $(date) ==="
exit $STATUS
