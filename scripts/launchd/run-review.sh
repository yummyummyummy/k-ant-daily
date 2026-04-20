#!/bin/bash
# Post-market review (20:10 KST weekdays, after NXT close).
# Wraps `claude /daily-review` for launchd-scheduled execution.
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/review-$TS.log"

exec >"$LOG" 2>&1

echo "=== k-ant-daily review @ $(date) ==="

export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

# Pull whatever the morning run pushed before we touch docs.
git fetch origin main >/dev/null 2>&1 && git reset --hard origin/main

if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

claude --dangerously-skip-permissions --print "/daily-review"
STATUS=$?

echo "=== exit status: $STATUS @ $(date) ==="
exit $STATUS
