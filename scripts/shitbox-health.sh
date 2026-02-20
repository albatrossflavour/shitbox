#!/bin/bash
# Quick health check for the shitbox telemetry system.
# Run on login or ad-hoc to see if everything is alive.

set -euo pipefail

DB="/var/lib/shitbox/telemetry.db"
DATA_DIR="/var/lib/shitbox"
PROMETHEUS_HOST="prometheus.albatrossflavour.com"
PROMETHEUS_PORT=80

# Colors
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

ok()   { printf "  %-12s${GREEN}●${RESET} %s\n" "$1:" "$2"; }
warn() { printf "  %-12s${YELLOW}●${RESET} %s\n" "$1:" "$2"; }
fail() { printf "  %-12s${RED}●${RESET} %s\n" "$1:" "$2"; }

echo -e "${BOLD}shitbox health${RESET}"
echo "──────────────"

# --- Service ---
if systemctl is-active --quiet shitbox-telemetry 2>/dev/null; then
    ts=$(systemctl show -p ActiveEnterTimestamp --value shitbox-telemetry 2>/dev/null)
    if [ -n "$ts" ]; then
        start=$(date -d "$ts" +%s 2>/dev/null) || start=""
        if [ -n "$start" ]; then
            elapsed=$(( $(date +%s) - start ))
            days=$(( elapsed / 86400 ))
            hours=$(( (elapsed % 86400) / 3600 ))
            mins=$(( (elapsed % 3600) / 60 ))
            if [ "$days" -gt 0 ]; then
                uptime="${days}d ${hours}h ${mins}m"
            elif [ "$hours" -gt 0 ]; then
                uptime="${hours}h ${mins}m"
            else
                uptime="${mins}m"
            fi
            ok "service" "running (uptime ${uptime})"
        else
            ok "service" "running"
        fi
    else
        ok "service" "running"
    fi
else
    fail "service" "not running"
fi

# --- GPS ---
if systemctl is-active --quiet gpsd 2>/dev/null; then
    ok "gps" "gpsd active"
else
    fail "gps" "gpsd not running"
fi

# --- Video ---
if pgrep -f 'ffmpeg.*segment' >/dev/null 2>&1; then
    ok "video" "ffmpeg recording"
else
    warn "video" "ffmpeg not running"
fi

# --- Database ---
if [ -f "$DB" ]; then
    size_bytes=$(stat -c %s "$DB" 2>/dev/null || stat -f %z "$DB" 2>/dev/null || echo "0")
    if [ "$size_bytes" -gt 1073741824 ]; then
        size="$(( size_bytes / 1073741824 )) GB"
    elif [ "$size_bytes" -gt 1048576 ]; then
        size="$(( size_bytes / 1048576 )) MB"
    else
        size="$(( size_bytes / 1024 )) KB"
    fi

    if command -v sqlite3 >/dev/null 2>&1; then
        total=$(sqlite3 "$DB" "SELECT COUNT(*) FROM readings;" 2>/dev/null || echo "?")
        recent=$(sqlite3 "$DB" "SELECT COUNT(*) FROM readings WHERE timestamp > strftime('%s','now') - 60;" 2>/dev/null || echo "?")
        # Format total with commas
        if [ "$total" != "?" ]; then
            total=$(printf "%'d" "$total" 2>/dev/null || echo "$total")
        fi
        ok "database" "${total} rows, ${size}, ${recent} readings/min"
    else
        ok "database" "${size} (sqlite3 not in PATH)"
    fi
else
    fail "database" "$DB not found"
fi

# --- Disk ---
if [ -d "$DATA_DIR" ]; then
    pct_used=$(df "$DATA_DIR" | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
    avail=$(df -h "$DATA_DIR" | awk 'NR==2 {print $4}')
    pct_free=$(( 100 - pct_used ))
    if [ "$pct_free" -lt 5 ]; then
        fail "disk" "${pct_free}% free (${avail} avail)"
    elif [ "$pct_free" -lt 10 ]; then
        warn "disk" "${pct_free}% free (${avail} avail)"
    else
        ok "disk" "${pct_free}% free (${avail} avail)"
    fi
else
    fail "disk" "$DATA_DIR not found"
fi

# --- CPU Temp ---
thermal="/sys/class/thermal/thermal_zone0/temp"
if [ -f "$thermal" ]; then
    raw=$(cat "$thermal")
    temp_c=$(( raw / 1000 ))
    if [ "$temp_c" -ge 80 ]; then
        fail "cpu temp" "${temp_c}°C"
    elif [ "$temp_c" -ge 70 ]; then
        warn "cpu temp" "${temp_c}°C"
    else
        ok "cpu temp" "${temp_c}°C"
    fi
else
    warn "cpu temp" "sensor not found"
fi

# --- Sensors (data flowing?) ---
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DB" ]; then
    for stype in imu environment power; do
        age=$(sqlite3 "$DB" "SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type = '${stype}' ORDER BY id DESC LIMIT 1;" 2>/dev/null || echo "")
        if [ -z "$age" ]; then
            fail "sensor" "${stype}: no data"
        elif [ "$age" -gt 300 ]; then
            fail "sensor" "${stype}: stale (${age}s ago)"
        elif [ "$age" -gt 60 ]; then
            warn "sensor" "${stype}: ${age}s ago"
        else
            ok "sensor" "${stype}: ${age}s ago"
        fi
    done
fi

# --- Prometheus ---
if (echo >/dev/tcp/"$PROMETHEUS_HOST"/"$PROMETHEUS_PORT") 2>/dev/null; then
    ok "prometheus" "${PROMETHEUS_HOST} reachable"
else
    fail "prometheus" "${PROMETHEUS_HOST} unreachable"
fi

# --- Recent Errors ---
if command -v journalctl >/dev/null 2>&1; then
    err_count=$(journalctl -u shitbox-telemetry -p err --since "5 min ago" --no-pager -q 2>/dev/null | wc -l | tr -d ' ')
    if [ "$err_count" -gt 0 ]; then
        fail "errors" "${err_count} errors (last 5m)"
    else
        ok "errors" "0 errors (last 5m)"
    fi
else
    warn "errors" "journalctl not available"
fi

# --- Watchdog ---
if command -v journalctl >/dev/null 2>&1; then
    last_health=$(journalctl -u shitbox-telemetry --no-pager -q --since "10 min ago" 2>/dev/null \
        | grep -E 'health_check_issues|health_check_all_clear' | tail -1 || true)
    if echo "$last_health" | grep -q "health_check_all_clear"; then
        ok "watchdog" "all clear"
    elif echo "$last_health" | grep -q "health_check_issues"; then
        issues=$(echo "$last_health" | grep -oP "issues=\[.*?\]" || echo "see journal")
        fail "watchdog" "issues: ${issues}"
    else
        warn "watchdog" "no recent health checks"
    fi
else
    warn "watchdog" "journalctl not available"
fi
