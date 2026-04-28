#!/bin/bash
# Install the four LaunchAgents:
#   - briefing      07:30 weekdays (morning prediction)
#   - nxt-snapshot  08:45 weekdays (NXT pre-open snapshot baked to summary.json)
#   - review        20:10 weekdays (post-session verification)
#   - digest        23:00 daily    (post-market news digest, US-open + 30min)
#
# Intraday news refresh used to live here as a fourth agent (10-min cron);
# it's now served by the browser polling the Cloudflare Worker /stock-news
# endpoint, so no server-side cron is needed. The `refresh` plist + wrapper
# are kept in the repo as reference but are no longer installed by default.
set -e

SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/k-ant-daily"

mkdir -p "$DST" "$LOGS"

# If a previous install put the refresh agent in place, make sure it's
# unloaded — leaving it around would force redundant commits that the
# browser-side refresh now avoids.
LEGACY="$DST/com.yummyummyummy.k-ant-daily.refresh.plist"
if [ -f "$LEGACY" ]; then
    launchctl unload -w "$LEGACY" 2>/dev/null || true
    rm -f "$LEGACY"
    echo "· removed legacy refresh agent (news now refreshed client-side via Worker)"
fi

for name in com.yummyummyummy.k-ant-daily.briefing com.yummyummyummy.k-ant-daily.nxt-snapshot com.yummyummyummy.k-ant-daily.review com.yummyummyummy.k-ant-daily.digest; do
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
echo "To disable later:  launchctl unload -w $DST/com.yummyummyummy.k-ant-daily.{briefing,nxt-snapshot,review,digest}.plist"
echo "To test manually:  $SRC/run-briefing.sh   (or run-nxt-snapshot.sh / run-review.sh / run-digest.sh)"
