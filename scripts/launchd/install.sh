#!/bin/bash
# Install the LaunchAgents:
#   - briefing       07:30 weekdays  (morning calendar refresh + holdings tracking)
#   - digest         23:00 daily     (post-market news digest)
#   - check-results  every 30 min    (fills event results promptly; cheap-gated)
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/k-ant-daily"

mkdir -p "$DST" "$LOGS"

# Clean up removed agents from older installs.
for legacy in com.yummyummyummy.k-ant-daily.refresh \
              com.yummyummyummy.k-ant-daily.nxt-snapshot \
              com.yummyummyummy.k-ant-daily.review; do
    plist="$DST/$legacy.plist"
    if [ -f "$plist" ]; then
        launchctl unload -w "$plist" 2>/dev/null || true
        rm -f "$plist"
        echo "· removed legacy agent $legacy"
    fi
done

for name in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.digest com.yummyummyummy.k-ant-daily.check-results; do
    plist="$DST/$name.plist"
    cp -f "$SRC/$name.plist" "$plist"
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
echo "To disable later:  launchctl unload -w $DST/com.yummyummyummy.k-ant-daily.{briefing,digest,check-results}.plist"
echo "To test manually:  $SRC/run-briefing.sh   (or run-digest.sh / run-check-results.sh)"
