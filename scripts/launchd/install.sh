#!/bin/bash
# Install the two LaunchAgents for daily briefing + review.
# Run once, then both schedules are live.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/k-ant-daily"

mkdir -p "$DST" "$LOGS"

for name in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.review; do
    plist="$DST/$name.plist"
    # Copy (not symlink) — launchctl dislikes symlinks in LaunchAgents.
    cp -f "$SRC/$name.plist" "$plist"

    # Reload so changes take effect if already installed.
    launchctl unload "$plist" 2>/dev/null || true
    launchctl load -w "$plist"

    echo "✓ installed $name"
done

echo ""
echo "Next scheduled runs:"
launchctl list | grep k-ant-daily || true
echo ""
echo "Logs: $LOGS"
echo ""
echo "To disable later:  launchctl unload -w $DST/com.yummyummyummy.k-ant-daily.{briefing,review}.plist"
echo "To test manually:  $SRC/run-briefing.sh"
