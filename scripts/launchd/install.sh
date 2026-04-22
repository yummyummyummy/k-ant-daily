#!/bin/bash
# Install the three LaunchAgents:
#   - briefing  07:30 weekdays (morning prediction)
#   - review    20:10 weekdays (post-session verification)
#   - refresh   every 10 min weekdays 09:00–15:30 (intraday news/quote pull)
# Run once, then all schedules are live.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/k-ant-daily"

mkdir -p "$DST" "$LOGS"

for name in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.review com.yummyummyummy.k-ant-daily.refresh; do
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
echo "To disable later:  launchctl unload -w $DST/com.yummyummyummy.k-ant-daily.{briefing,review,refresh}.plist"
echo "To test manually:  $SRC/run-briefing.sh   |   $SRC/run-refresh.sh"
