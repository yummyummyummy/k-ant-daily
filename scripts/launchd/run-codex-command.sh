#!/bin/bash
# Run a repo command spec through Codex CLI in non-interactive mode.
set -u

REPO="$1"
PROMPT_FILE="$2"
TASK_NAME="$3"

if [ ! -f "$PROMPT_FILE" ]; then
    echo "FATAL: prompt file not found: $PROMPT_FILE"
    exit 1
fi

echo "=== codex task: $TASK_NAME ==="
echo "=== prompt: $PROMPT_FILE ==="

CODEX_BIN="$(command -v codex || true)"
if [ -z "$CODEX_BIN" ]; then
    for candidate in \
        "$HOME"/.vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex \
        /opt/homebrew/bin/codex \
        /usr/local/bin/codex; do
        if [ -x "$candidate" ]; then
            CODEX_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$CODEX_BIN" ]; then
    echo "FATAL: codex command not found. Run 'codex login' in an interactive shell and check launchd PATH."
    exit 1
fi

echo "=== codex bin: $CODEX_BIN ==="

PROMPT="$(cat "$PROMPT_FILE")

Execute the command spec above for this repository end to end.

Important automation requirements:
- Run unattended; do not ask the user for clarification.
- Use today's KST date from the system.
- Preserve unrelated user changes if any are encountered.
- Commit and push the required changes when the command spec asks for it.
- Keep the final response concise."

"$CODEX_BIN" --search exec \
    --cd "$REPO" \
    --sandbox danger-full-access \
    --ask-for-approval never \
    --dangerously-bypass-approvals-and-sandbox \
    "$PROMPT"
