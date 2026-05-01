#!/usr/bin/env bash
# validate-cold-boot.sh — Post-hoc cold boot validation for shitbox-telemetry
#
# Analyses the systemd journal for the most recent N boots (default 5) and
# checks each one for:
#   1. No watchdog_kill or start-limit-hit
#   2. unified_engine_started was reached
#   3. boot_capture_triggered was logged (boot video fired)
#   4. A boot capture video file exists in /var/lib/shitbox/captures/
#
# Usage:
#   sudo ./validate-cold-boot.sh          # check last 5 boots
#   sudo ./validate-cold-boot.sh 3        # check last 3 boots
#
# Run on the Pi after performing the cold boot cycles. The actual reboots
# are manual (power cycle) — this script analyses the journal post-hoc.
# Requires root for journalctl --list-boots access.

set -euo pipefail

NUM_BOOTS="${1:-5}"
SERVICE="shitbox-telemetry"
CAPTURE_DIR="/var/lib/shitbox/captures"

# Colour output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { printf "${GREEN}PASS${NC} %s\n" "$1"; }
fail() { printf "${RED}FAIL${NC} %s\n" "$1"; }
info() { printf "${CYAN}INFO${NC} %s\n" "$1"; }
header() { printf "\n${BOLD}%s${NC}\n" "$1"; }

# Require root (journalctl --list-boots needs it for full history)
if [[ $EUID -ne 0 ]]; then
    printf "${RED}ERROR${NC} Run with sudo: sudo %s\n" "$0"
    exit 1
fi

# Check the service exists
if ! systemctl cat "$SERVICE" &>/dev/null; then
    printf "${RED}ERROR${NC} Service %s not found\n" "$SERVICE"
    exit 1
fi

header "Cold Boot Validation — checking last ${NUM_BOOTS} boots"
echo "Service: ${SERVICE}"
echo "Capture dir: ${CAPTURE_DIR}"
echo ""

# Get boot list (most recent N)
mapfile -t BOOT_IDS < <(journalctl --list-boots -q | tail -n "$NUM_BOOTS" | awk '{print $1}')

if [[ ${#BOOT_IDS[@]} -eq 0 ]]; then
    printf "${RED}ERROR${NC} No boots found in journal\n"
    exit 1
fi

if [[ ${#BOOT_IDS[@]} -lt $NUM_BOOTS ]]; then
    printf "${YELLOW}WARN${NC} Only %d boots available in journal (requested %d)\n" "${#BOOT_IDS[@]}" "$NUM_BOOTS"
fi

TOTAL=0
PASSED=0

for BOOT_ID in "${BOOT_IDS[@]}"; do
    TOTAL=$((TOTAL + 1))
    BOOT_PASS=true

    # Get boot timestamp for display
    BOOT_TS=$(journalctl -b "$BOOT_ID" -o short-iso -n 1 -q 2>/dev/null | head -1 | awk '{print $1}' || echo "unknown")
    header "Boot ${TOTAL}/${#BOOT_IDS[@]} (boot offset ${BOOT_ID}, started ${BOOT_TS})"

    # Grab journal for this boot + service once
    JOURNAL=$(journalctl -b "$BOOT_ID" -u "$SERVICE" --no-pager -q 2>/dev/null || true)

    if [[ -z "$JOURNAL" ]]; then
        fail "No journal entries for ${SERVICE} in this boot"
        BOOT_PASS=false
        # Still check remaining criteria for completeness
    fi

    # Check 1: No watchdog kill or start-limit-hit
    if echo "$JOURNAL" | grep -qiE "watchdog_kill|watchdog.*killed|start-limit-hit"; then
        fail "Watchdog kill or start-limit-hit detected"
        echo "$JOURNAL" | grep -iE "watchdog_kill|watchdog.*killed|start-limit-hit" | head -3
        BOOT_PASS=false
    else
        pass "No watchdog kill or start-limit-hit"
    fi

    # Also check the full boot journal for systemd-level failures
    FULL_JOURNAL=$(journalctl -b "$BOOT_ID" --no-pager -q -g "$SERVICE" 2>/dev/null || true)
    if echo "$FULL_JOURNAL" | grep -qiE "start-limit-hit|Failed to start.*shitbox"; then
        fail "systemd start-limit-hit or service failure detected"
        echo "$FULL_JOURNAL" | grep -iE "start-limit-hit|Failed to start" | head -3
        BOOT_PASS=false
    else
        pass "No systemd-level service failure"
    fi

    # Check 2: unified_engine_started was reached
    if echo "$JOURNAL" | grep -q "unified_engine_started"; then
        pass "unified_engine_started reached"
    else
        fail "unified_engine_started not found in journal"
        BOOT_PASS=false
    fi

    # Check 3: boot_capture_triggered was logged
    if echo "$JOURNAL" | grep -q "boot_capture_triggered"; then
        pass "boot_capture_triggered logged"
    elif echo "$JOURNAL" | grep -q "boot_capture_skipped"; then
        REASON=$(echo "$JOURNAL" | grep "boot_capture_skipped" | head -1)
        fail "boot capture was skipped: ${REASON}"
        BOOT_PASS=false
    else
        fail "No boot_capture_triggered or boot_capture_skipped found"
        BOOT_PASS=false
    fi

    # Check 4: Boot capture video file exists
    # Look for capture files created around the boot timestamp
    BOOT_DATE=$(journalctl -b "$BOOT_ID" -o short-iso -n 1 -q 2>/dev/null | head -1 | awk '{print $1}' | cut -dT -f1 || echo "")
    if [[ -n "$BOOT_DATE" ]] && [[ -d "${CAPTURE_DIR}/${BOOT_DATE}" ]]; then
        BOOT_VIDEOS=$(find "${CAPTURE_DIR}/${BOOT_DATE}" -name "BOOT_*.mp4" -type f 2>/dev/null | wc -l)
        if [[ "$BOOT_VIDEOS" -gt 0 ]]; then
            pass "Boot capture video exists (${BOOT_VIDEOS} BOOT_*.mp4 file(s) in ${CAPTURE_DIR}/${BOOT_DATE}/)"
        else
            fail "No BOOT_*.mp4 files in ${CAPTURE_DIR}/${BOOT_DATE}/"
            BOOT_PASS=false
        fi
    else
        fail "Capture directory ${CAPTURE_DIR}/${BOOT_DATE:-<unknown>}/ not found"
        BOOT_PASS=false
    fi

    # Summary for this boot
    if $BOOT_PASS; then
        printf "${GREEN}>>> Boot %d: ALL CHECKS PASSED${NC}\n" "$TOTAL"
        PASSED=$((PASSED + 1))
    else
        printf "${RED}>>> Boot %d: FAILED${NC}\n" "$TOTAL"
    fi
done

# Overall verdict
header "Overall Verdict"
echo "${PASSED}/${TOTAL} boots passed"
echo ""

if [[ $PASSED -eq $TOTAL ]]; then
    printf "${GREEN}${BOLD}VERDICT: PASS${NC} — all %d cold boots completed successfully\n" "$TOTAL"
    exit 0
else
    printf "${RED}${BOLD}VERDICT: FAIL${NC} — %d/%d boots failed\n" "$((TOTAL - PASSED))" "$TOTAL"
    exit 1
fi
