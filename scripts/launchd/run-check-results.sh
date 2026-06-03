#!/bin/bash
# Intraday result-check — fills `result` for just-passed events.
# Fires every 30 min (launchd StartInterval). Cheap-gates so off-event ticks
# cost nothing: only invokes Codex when an event result is actually due.
set -u

REPO="/Users/woong/projects/k-ant-daily"
LOG_DIR="$HOME/Library/Logs/k-ant-daily"
mkdir -p "$LOG_DIR"

export PATH="/Users/woong/.nvm/versions/node/v20.16.0/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
cd "$REPO" || exit 1

# 1. Cheap gate — read-only, no git, no LLM. Exit fast on the common no-op case.
if [ ! -x .venv/bin/python ]; then exit 0; fi
PENDING="$(.venv/bin/python scripts/pending_results.py 2>/dev/null || echo 0)"
if [ "$PENDING" -eq 0 ] 2>/dev/null; then exit 0; fi

# 2. Protect uncommitted work — never git reset over a dirty tree.
if [ -n "$(git status --porcelain)" ]; then
    echo "$(date) dirty tree — skip intraday result-check" >>"$LOG_DIR/check-results.log"
    exit 0
fi

# 3. Only now do the heavier path (this run will use Codex usage).
TS="$(date +%Y-%m-%d_%H%M%S)"
LOG="$LOG_DIR/check-results-$TS.log"
exec >"$LOG" 2>&1
echo "=== k-ant-daily check-results @ $(date) (pending=$PENDING) ==="

git fetch origin main >/dev/null 2>&1 && git reset --hard origin/main

# Re-check against synced remote state — a prior run may have filled it.
PENDING="$(.venv/bin/python scripts/pending_results.py 2>/dev/null || echo 0)"
if [ "$PENDING" -eq 0 ] 2>/dev/null; then echo "nothing pending after sync"; exit 0; fi

.venv/bin/pip install -q -r requirements.txt
scripts/launchd/run-codex-command.sh "$REPO" "$REPO/.claude/commands/check-results.md" "check-results"
STATUS=$?
echo "=== exit status: $STATUS @ $(date) ==="
exit $STATUS
