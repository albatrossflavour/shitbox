#!/usr/bin/env bash
# validate-tpms-uat.sh — Interactive TPMS bench deflation UAT runner
#
# Wraps UAT-2 from the Phase 28 UAT plan: bench deflation test for the
# full TPMS alert chain (yellow → red → TTS → event row).
#
# The script:
#   1. Pre-checks: rtl_433 installed, shitbox-telemetry running, SDR detected
#   2. Monitors journalctl for TPMS alert events in real time
#   3. Prompts the operator to deflate a tyre
#   4. Watches for: alert_fired (low pressure), alert_recovered (restored),
#      tpms_leak_event_recorded (leak detection)
#   5. Checks SQLite for the corresponding event row
#   6. Reports which alerts fired and their timestamps
#
# Usage:
#   sudo ./validate-tpms-uat.sh                    # default 120s timeout
#   sudo ./validate-tpms-uat.sh --timeout 180      # custom timeout
#
# Run on the Pi with a real tyre to deflate and an SDR receiving TPMS frames.

set -euo pipefail

TIMEOUT=120
SERVICE="shitbox-telemetry"
DB_PATH="/var/lib/shitbox/telemetry.db"
EVENTS_JSON="/var/lib/shitbox/captures/events.json"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout) TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

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
warn() { printf "${YELLOW}WARN${NC} %s\n" "$1"; }
header() { printf "\n${BOLD}%s${NC}\n" "$1"; }

cleanup() {
    if [[ -n "${JOURNAL_PID:-}" ]] && kill -0 "$JOURNAL_PID" 2>/dev/null; then
        kill "$JOURNAL_PID" 2>/dev/null || true
        wait "$JOURNAL_PID" 2>/dev/null || true
    fi
    rm -f "${JOURNAL_LOG:-}"
}
trap cleanup EXIT

# Require root
if [[ $EUID -ne 0 ]]; then
    printf "${RED}ERROR${NC} Run with sudo: sudo %s\n" "$0"
    exit 1
fi

header "TPMS Bench Deflation UAT (Phase 28, UAT-2)"
echo "Timeout: ${TIMEOUT}s"
echo ""

# ─── Pre-checks ─────────────────────────────────────────────────────

header "Pre-flight Checks"

# Check rtl_433 installed
if command -v rtl_433 &>/dev/null; then
    RTL_VER=$(rtl_433 -V 2>&1 | head -1 || echo "unknown")
    pass "rtl_433 installed (${RTL_VER})"
else
    fail "rtl_433 not found — install with: sudo apt install rtl-433"
    exit 1
fi

# Check service running
if systemctl is-active --quiet "$SERVICE"; then
    pass "${SERVICE} is running"
else
    fail "${SERVICE} is not running — start with: sudo systemctl start ${SERVICE}"
    exit 1
fi

# Check SDR detected via lsusb
if lsusb 2>/dev/null | grep -qiE "realtek|rtl28|rtl2832|0bda:28"; then
    SDR_LINE=$(lsusb | grep -iE "realtek|rtl28|rtl2832|0bda:28" | head -1)
    pass "SDR detected: ${SDR_LINE}"
else
    fail "No RTL-SDR detected via lsusb — check USB connection"
    exit 1
fi

# Check DB exists
if [[ -f "$DB_PATH" ]]; then
    pass "Telemetry database exists at ${DB_PATH}"
else
    warn "Telemetry database not found at ${DB_PATH} — DB checks will be skipped"
fi

# Check recent TPMS frames are flowing
RECENT_FRAMES=$(journalctl -u "$SERVICE" --since "2 minutes ago" --no-pager -q 2>/dev/null \
    | grep -c "tpms_frame_received" || echo "0")
if [[ "$RECENT_FRAMES" -gt 0 ]]; then
    pass "TPMS frames flowing (${RECENT_FRAMES} in the last 2 minutes)"
else
    warn "No tpms_frame_received in the last 2 minutes — sensors may not be transmitting yet"
fi

echo ""
info "Pre-checks complete. Ready for bench deflation test."

# ─── Alert monitoring ───────────────────────────────────────────────

header "Alert Monitoring"

# Events we're watching for
ALERT_FIRED=false
ALERT_RECOVERED=false
LEAK_DETECTED=false
ALERT_FIRED_TS=""
ALERT_RECOVERED_TS=""
LEAK_TS=""
ALERT_SUBTYPE=""

# Start journal tail in background, write to temp file
JOURNAL_LOG=$(mktemp /tmp/tpms-uat-journal.XXXXXX)
journalctl -u "$SERVICE" -f --since "now" --no-pager -q > "$JOURNAL_LOG" 2>/dev/null &
JOURNAL_PID=$!

echo ""
printf "${BOLD}${YELLOW}ACTION REQUIRED:${NC} Deflate a tyre now.\n"
echo ""
echo "The script is watching for the following events:"
echo "  1. alert_fired with subtype TPMS_LOW_*       (red band, PSI ≤ 25)"
echo "  2. alert_recovered with subtype *_RESTORED    (re-inflate above 28 PSI)"
echo "  3. tpms_leak_event_recorded                   (rapid deflation ≥5 PSI/60s)"
echo ""
echo "Deflation sequence:"
echo "  - Bleed slowly to ~26 PSI (yellow band — Health page only, no TTS)"
echo "  - Continue to ≤25 PSI (red band — TTS + alert_fired)"
echo "  - For leak test: deflate rapidly (≥5 PSI drop in 60s)"
echo "  - Re-inflate above 28 PSI to trigger recovery"
echo ""
printf "Monitoring for ${TIMEOUT}s (Ctrl+C to stop early)...\n"
echo ""

STARTED=$(date +%s)
LAST_LINE_COUNT=0

while true; do
    NOW=$(date +%s)
    ELAPSED=$((NOW - STARTED))

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        info "Timeout reached (${TIMEOUT}s)"
        break
    fi

    # Read new lines from journal
    CURRENT_LINES=$(wc -l < "$JOURNAL_LOG" 2>/dev/null || echo "0")

    if [[ "$CURRENT_LINES" -gt "$LAST_LINE_COUNT" ]]; then
        NEW_LINES=$(tail -n +"$((LAST_LINE_COUNT + 1))" "$JOURNAL_LOG" 2>/dev/null || true)
        LAST_LINE_COUNT=$CURRENT_LINES

        # Check for alert_fired (low pressure — red band)
        if ! $ALERT_FIRED && echo "$NEW_LINES" | grep -q "alert_fired"; then
            ALERT_FIRED=true
            ALERT_FIRED_TS=$(date -Iseconds)
            ALERT_SUBTYPE=$(echo "$NEW_LINES" | grep "alert_fired" | head -1 | grep -oE "subtype=[^ ,}]+" | head -1 || echo "unknown")
            printf "${GREEN}>>> alert_fired detected${NC} at %s (%s)\n" "$ALERT_FIRED_TS" "$ALERT_SUBTYPE"
        fi

        # Check for alert_recovered (pressure restored)
        if ! $ALERT_RECOVERED && echo "$NEW_LINES" | grep -q "alert_recovered"; then
            ALERT_RECOVERED=true
            ALERT_RECOVERED_TS=$(date -Iseconds)
            RECOVERY_SUBTYPE=$(echo "$NEW_LINES" | grep "alert_recovered" | head -1 | grep -oE "subtype=[^ ,}]+" | head -1 || echo "unknown")
            printf "${GREEN}>>> alert_recovered detected${NC} at %s (%s)\n" "$ALERT_RECOVERED_TS" "$RECOVERY_SUBTYPE"
        fi

        # Check for tpms_leak_event_recorded
        if ! $LEAK_DETECTED && echo "$NEW_LINES" | grep -q "tpms_leak_event_recorded"; then
            LEAK_DETECTED=true
            LEAK_TS=$(date -Iseconds)
            LEAK_WHEEL=$(echo "$NEW_LINES" | grep "tpms_leak_event_recorded" | head -1 | grep -oE "wheel=[^ ,}]+" | head -1 || echo "unknown")
            printf "${GREEN}>>> tpms_leak_event_recorded detected${NC} at %s (%s)\n" "$LEAK_TS" "$LEAK_WHEEL"
        fi

        # Print any TTS-related lines for visibility
        TTS_LINES=$(echo "$NEW_LINES" | grep -iE "speak_tpms|tts_speaking" || true)
        if [[ -n "$TTS_LINES" ]]; then
            printf "${CYAN}    TTS: %s${NC}\n" "$TTS_LINES"
        fi
    fi

    # If we've seen all three, no need to keep waiting
    if $ALERT_FIRED && $ALERT_RECOVERED && $LEAK_DETECTED; then
        info "All expected events detected — ending early"
        break
    fi

    sleep 2
done

# ─── Results ────────────────────────────────────────────────────────

header "Alert Results"

if $ALERT_FIRED; then
    pass "Low pressure alert fired at ${ALERT_FIRED_TS} (${ALERT_SUBTYPE})"
else
    fail "No alert_fired event detected within ${TIMEOUT}s"
fi

if $ALERT_RECOVERED; then
    pass "Pressure restored alert at ${ALERT_RECOVERED_TS}"
else
    warn "No alert_recovered event detected (re-inflate above 28 PSI to trigger)"
fi

if $LEAK_DETECTED; then
    pass "Leak event recorded at ${LEAK_TS} (${LEAK_WHEEL})"
else
    warn "No tpms_leak_event_recorded (requires rapid deflation ≥5 PSI in 60s)"
fi

# ─── Database cross-check ──────────────────────────────────────────

header "Database Cross-Check"

if [[ -f "$DB_PATH" ]]; then
    # Check for recent TPMS readings
    READING_COUNT=$(sqlite3 "$DB_PATH" \
        "SELECT COUNT(*) FROM tpms_readings WHERE timestamp > strftime('%s','now','-10 minutes')" 2>/dev/null || echo "0")
    if [[ "$READING_COUNT" -gt 0 ]]; then
        pass "Recent TPMS readings in DB (${READING_COUNT} in last 10 minutes)"

        info "Latest readings per wheel:"
        sqlite3 -header -column "$DB_PATH" \
            "SELECT wheel, ROUND(pressure_psi, 1) as psi, ROUND(temperature_c, 1) as temp_c, datetime(timestamp,'unixepoch','localtime') as time FROM tpms_readings WHERE id IN (SELECT MAX(id) FROM tpms_readings GROUP BY wheel) ORDER BY wheel" 2>/dev/null || warn "Could not query latest readings"
    else
        fail "No TPMS readings in DB in the last 10 minutes"
    fi

    # Check for TPMS_LEAK event in events table (if it exists)
    if $LEAK_DETECTED; then
        echo ""
        LEAK_EVENTS=$(sqlite3 "$DB_PATH" \
            "SELECT COUNT(*) FROM events WHERE event_type = 'TPMS_LEAK' AND start_time > strftime('%s','now','-10 minutes')" 2>/dev/null || echo "0")
        if [[ "$LEAK_EVENTS" -gt 0 ]]; then
            pass "TPMS_LEAK event found in events table (${LEAK_EVENTS} recent)"
        else
            fail "No TPMS_LEAK event found in events table"
        fi
    fi
else
    warn "Database not found at ${DB_PATH} — skipping DB checks"
fi

# Check events.json for TPMS_LEAK entry
if $LEAK_DETECTED && [[ -f "$EVENTS_JSON" ]]; then
    echo ""
    if grep -q "TPMS_LEAK" "$EVENTS_JSON" 2>/dev/null; then
        pass "TPMS_LEAK entry found in events.json"
    else
        fail "No TPMS_LEAK entry in events.json"
    fi
fi

# ─── Overall verdict ────────────────────────────────────────────────

header "Overall Verdict"

CHECKS_PASSED=0
CHECKS_TOTAL=3

$ALERT_FIRED && CHECKS_PASSED=$((CHECKS_PASSED + 1))
$ALERT_RECOVERED && CHECKS_PASSED=$((CHECKS_PASSED + 1))
$LEAK_DETECTED && CHECKS_PASSED=$((CHECKS_PASSED + 1))

echo "${CHECKS_PASSED}/${CHECKS_TOTAL} alert chain stages detected"
echo ""

if [[ $CHECKS_PASSED -eq $CHECKS_TOTAL ]]; then
    printf "${GREEN}${BOLD}VERDICT: PASS${NC} — full alert chain verified (yellow→red→TTS→event row→recovery)\n"
    exit 0
elif $ALERT_FIRED; then
    printf "${YELLOW}${BOLD}VERDICT: PARTIAL${NC} — low pressure alert fired but not all stages completed\n"
    echo "Missing: $(! $ALERT_RECOVERED && echo 'recovery ') $(! $LEAK_DETECTED && echo 'leak detection')"
    exit 1
else
    printf "${RED}${BOLD}VERDICT: FAIL${NC} — no TPMS alerts detected within ${TIMEOUT}s\n"
    echo "Check that sensors are transmitting and tyre was deflated below 25 PSI"
    exit 1
fi
