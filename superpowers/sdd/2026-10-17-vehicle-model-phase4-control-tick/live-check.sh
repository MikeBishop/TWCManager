#!/bin/bash
# Phase 4 live check on the twcmanager box (Task 6, Step 8). Not run by the
# implementer: the user schedules it. Deploys and restarts are pre-approved.
#
#   live-check.sh prepare    record HEAD, back up settings/config, DEBUG logs, pause watchdog
#   live-check.sh deploy     bundle <box HEAD>..vehicle-model/phase4, check out, restart
#   live-check.sh boot       step 2 checks (no stall, first SHB lines, no tick errors)
#   live-check.sh watch      follow the journal for steps 3-5 (Ctrl-C to stop)
#   live-check.sh tokens     step 6: refresh lines and stalls since the deploy
#   live-check.sh paid       step 7: paid-call count since the deploy
#   live-check.sh rollback   step 8: previous HEAD, settings, config, watchdog
#
# State lives on the box in ~/phase4-live/ (prev-head, start time, backups).
# rollback restores the settings.json backup, discarding settings changed
# during the window (kWh delivered, held limits); skip that line to keep them.
set -euo pipefail

BOX=twcmanager
REPO=/tmp/claude-1000/-home-mbishop-github-TWCManager--claude-worktrees-ble-threading-twcmanager-62cb96/8798f608-1fae-4176-a592-206045172d8d/scratchpad/wt-vm4
BRANCH=vehicle-model/phase4
ETC=/etc/twcmanager
STATE='~/phase4-live'

box() { ssh "$BOX" "$@"; }

prepare() {
    box "mkdir -p $STATE && cd ~/TWCManager && git rev-parse HEAD > $STATE/prev-head && cat $STATE/prev-head"
    box "cp $ETC/settings.json $STATE/settings.json.bak && cp $ETC/config.json $STATE/config.json.bak"
    # commandPolicy decides step 4's expectation: ble_only means zero
    # "Car API ... command/" lines; prefer_ble may let Fleet step in
    box "python3 -c 'import json; print(\"commandPolicy:\", json.load(open(\"$ETC/settings.json\")).get(\"commandPolicy\"))'"
    # DEBUG reaches the journal (INFO8 and Slave/Master DEBUG lines)
    box "sudo sed -i.phase4 's/\"logLevel\": *[0-9]*/\"logLevel\": 10/' $ETC/config.json && grep -n '\"logLevel\"' $ETC/config.json"
    # Pause the watchdog: keep the crontab, drop its line
    box "crontab -l > $STATE/crontab.bak 2>/dev/null || true; grep -v phase3-watchdog $STATE/crontab.bak | crontab -"
}

deploy() {
    local prev
    prev=$(box "cat $STATE/prev-head")
    git -C "$REPO" bundle create /tmp/phase4.bundle "$prev..$BRANCH"
    scp /tmp/phase4.bundle "$BOX:phase4-live/phase4.bundle"  # home-relative: SFTP scp may not expand ~
    box "cd ~/TWCManager && git fetch $STATE/phase4.bundle $BRANCH && git checkout --detach FETCH_HEAD && git log --oneline -1"
    box "date \"+%Y-%m-%d %H:%M:%S\" > $STATE/start && sudo systemctl restart twcmanager && sleep 5 && systemctl is-active twcmanager"
}

since() { box "cat $STATE/start"; }

boot() {
    local start
    start=$(since)
    echo "== stalls after boot (expect none)"
    box "journalctl -u twcmanager --since '$start' | grep 'Main loop stalled' || echo none"
    echo "== control tick failures (expect none; the tick logs nothing when healthy)"
    box "journalctl -u twcmanager --since '$start' | grep 'Control tick:' || echo none"
    echo "== first SHB lines: master byte M: 00 (no change) until the first tick, then 09"
    box "journalctl -u twcmanager --since '$start' | grep 'SHB ' | head -5"
}

watch() {
    # Step 3: restart with the car charging at 32 A -> the wire offer goes
    #   from 00 straight to 32 A, never 0000.
    # Step 4: Track Green flicker, or Charge Now 10 A, 4 A, 16 A ->
    #   offers follow within ~1 s; a decrease holds 5 s; below the minimum
    #   one BLE stop after 60 s; back above it, a start; no
    #   "Car API ... command/" line under ble_only.
    # Step 5 (by hand): Debug page, Send Custom Command FBEB... -> "Last
    #   Command Response" fills; the Spike Amps row is gone.
    box "journalctl -u twcmanager -f -o short-precise | grep --line-buffered -E 'SHB |M: |Car API|BLE|stop|start|stalled|Control tick'"
}

tokens() {
    local start
    start=$(since)
    # A refresh (only when due) logs "Car API request" (INFO2) and "Car API
    # auth response received" (INFO4) from the background thread; it must
    # never coincide with a "Main loop stalled" line. The first periodic
    # refresh runs 300 s after start.
    box "journalctl -u twcmanager --since '$start' -o short-precise | grep -E 'Car API request|auth response|Main loop stalled' || echo none"
}

paid() {
    local start
    start=$(since)
    echo "== paid calls since $start (expect none)"
    box "journalctl -u twcmanager --since '$start' | grep 'Car API' | grep -oE 'wake_up|vehicle_data|command/[a-z_]+' | sort | uniq -c || true"
}

rollback() {
    box "cd ~/TWCManager && git checkout --detach \$(cat $STATE/prev-head) && git log --oneline -1"
    box "sudo cp $STATE/settings.json.bak $ETC/settings.json && sudo cp $STATE/config.json.bak $ETC/config.json"
    box "crontab $STATE/crontab.bak"
    box "sudo systemctl restart twcmanager && sleep 5 && systemctl is-active twcmanager"
}

"${1:?usage: live-check.sh prepare|deploy|boot|watch|tokens|paid|rollback}"
