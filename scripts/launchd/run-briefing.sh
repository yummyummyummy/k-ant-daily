#!/bin/bash
# Daily pre-market briefing (07:30 KST weekdays).
# Wraps `claude /daily-report` for launchd-scheduled execution.
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/briefing-$TS.log"

exec >"$LOG" 2>&1

echo "=== k-ant-daily briefing @ $(date) ==="

# PATH — launchd does not inherit user shell PATH.
export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

cd "$REPO" || { echo "FATAL: cannot cd to $REPO"; exit 1; }

# Make sure we're in sync with remote (otherwise push fails later).
git fetch origin main >/dev/null 2>&1 && git reset --hard origin/main

# Ensure venv exists with deps.
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# Run Claude Code in non-interactive mode with /daily-report.
# --dangerously-skip-permissions: auto-approve all tool calls (required for unattended).
# --print: non-interactive stdout mode.
claude --dangerously-skip-permissions --print "/daily-report"
STATUS=$?

echo "=== exit status: $STATUS @ $(date) ==="
exit $STATUS
