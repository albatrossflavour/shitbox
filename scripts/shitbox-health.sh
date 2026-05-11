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

ok() { printf "  %-14s${GREEN}●${RESET} %s\n" "$1:" "$2"; }
warn() { printf "  %-14s${YELLOW}●${RESET} %s\n" "$1:" "$2"; }
fail() { printf "  %-14s${RED}●${RESET} %s\n" "$1:" "$2"; }

echo -e "${BOLD}shitbox health${RESET}"
echo "──────────────"

# --- Service ---
if systemctl is-active --quiet shitbox-telemetry 2>/dev/null; then
  ts=$(systemctl show -p ActiveEnterTimestamp --value shitbox-telemetry 2>/dev/null)
  if [ -n "$ts" ]; then
    start=$(date -d "$ts" +%s 2>/dev/null) || start=""
    if [ -n "$start" ]; then
      elapsed=$(($(date +%s) - start))
      days=$((elapsed / 86400))
      hours=$(((elapsed % 86400) / 3600))
      mins=$(((elapsed % 3600) / 60))
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
    size="$((size_bytes / 1073741824)) GB"
  elif [ "$size_bytes" -gt 1048576 ]; then
    size="$((size_bytes / 1048576)) MB"
  else
    size="$((size_bytes / 1024)) KB"
  fi

  if command -v sqlite3 >/dev/null 2>&1; then
    # Single sqlite invocation. MAX(id) replaces COUNT(*) which full-scanned
    # readings — the old query took multiple seconds on a multi-million-row
    # DB. The label says "~rows" because deletions make MAX(id) an upper
    # bound, not an exact count. The "recent" predicate uses timestamp_utc
    # (TEXT, indexed); the previous version referenced a non-existent
    # timestamp column and silently returned 0.
    db_data=$(sqlite3 "$DB" "SELECT MAX(id) FROM readings; SELECT COUNT(*) FROM readings WHERE timestamp_utc > datetime('now', '-60 seconds');" 2>/dev/null || echo "")
    max_id=$(echo "$db_data" | sed -n '1p')
    recent=$(echo "$db_data" | sed -n '2p')
    if [ -n "$max_id" ]; then
      total_fmt=$(printf "%'d" "$max_id" 2>/dev/null || echo "$max_id")
      ok "database" "~${total_fmt} rows, ${size}, ${recent:-?} readings/min"
    else
      ok "database" "${size}"
    fi
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
  pct_free=$((100 - pct_used))
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
  temp_c=$((raw / 1000))
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
# Expanded set — gps and temp matter as much as the original three. The full
# list (light, power, particulate) is excluded to keep the login output tight;
# add them if a quiet sensor needs to be louder. Single sqlite invocation
# (UNION ALL) instead of 5 separate ones to cut open/close overhead; IFNULL
# emits a sentinel age=-1 so a missing sensor still produces a row.
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DB" ]; then
  sensor_data=$(sqlite3 -separator ' ' "$DB" "
SELECT 'imu', IFNULL((SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type='imu' ORDER BY id DESC LIMIT 1), -1)
UNION ALL SELECT 'gps', IFNULL((SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type='gps' ORDER BY id DESC LIMIT 1), -1)
UNION ALL SELECT 'environment', IFNULL((SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type='environment' ORDER BY id DESC LIMIT 1), -1)
UNION ALL SELECT 'temp', IFNULL((SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type='temp' ORDER BY id DESC LIMIT 1), -1)
UNION ALL SELECT 'system', IFNULL((SELECT CAST((strftime('%s','now') - strftime('%s', timestamp_utc)) AS INTEGER) FROM readings WHERE sensor_type='system' ORDER BY id DESC LIMIT 1), -1);
" 2>/dev/null || echo "")
  while IFS=' ' read -r stype age; do
    [ -z "$stype" ] && continue
    if [ "$age" = "-1" ] || [ -z "$age" ]; then
      fail "sensor" "${stype}: no data"
    elif [ "$age" -gt 300 ]; then
      fail "sensor" "${stype}: stale (${age}s ago)"
    elif [ "$age" -gt 60 ]; then
      warn "sensor" "${stype}: ${age}s ago"
    else
      ok "sensor" "${stype}: ${age}s ago"
    fi
  done <<< "$sensor_data"
fi

# --- I2C Bus (devices visible?) ---
# Expected 8 devices: 0x10 0x19 0x1c 0x3c 0x40 0x5c 0x6a 0x77.
# Empty bus = TCA4307 latched into protective isolation; recovery is either
# the EN-pin pulse (once GPIO 12 is wired) or a hard power-cycle of the Pi.
I2CDETECT=$(command -v i2cdetect 2>/dev/null || command -v /usr/sbin/i2cdetect 2>/dev/null || echo "")
if [ -n "$I2CDETECT" ]; then
  output=$(sudo -n "$I2CDETECT" -y 1 2>/dev/null || echo "")
  if [ -n "$output" ]; then
    count=$(echo "$output" | awk 'NR>1 && /^[0-9a-f][0-9a-f]?:/ {for(i=2;i<=NF;i++) if($i!="--") n++} END {print n+0}')
    if [ "$count" -ge 8 ]; then
      ok "i2c bus" "${count} devices"
    elif [ "$count" -ge 1 ]; then
      warn "i2c bus" "${count}/8 devices visible"
    else
      fail "i2c bus" "empty — bus locked? hard power-cycle to recover"
    fi
  else
    warn "i2c bus" "i2cdetect needs passwordless sudo"
  fi
else
  warn "i2c bus" "i2cdetect not installed"
fi

# --- I2C Recovery (last 24h) ---
# Surfaces lockup-and-recover cycles that would otherwise hide between logins.
# Single journalctl invocation with -g (regex pre-filter at journal level) +
# awk for categorical counts. Was 4-5s with three separate calls; should now
# be ~1s. -g requires systemd v229+ (2016), fine on current Pi OS.
if command -v journalctl >/dev/null 2>&1; then
  lockups=0; attempts=0; recovered=0
  i2c_counts=$(
    journalctl -u shitbox-telemetry --no-pager -q --since "24 hours ago" \
      -g 'i2c_bus_lockup_detected|i2c_recovery_attempt|i2c_recovery_via_tca_en_pulse|i2c_bus_recovery_successful' 2>/dev/null \
    | awk '
        /i2c_bus_lockup_detected/       {l++}
        /i2c_recovery_attempt/          {a++}
        /i2c_recovery_via_tca_en_pulse/ {r++}
        /i2c_bus_recovery_successful/   {r++}
        END {print (l+0), (a+0), (r+0)}
      ' || echo "0 0 0"
  )
  read -r lockups attempts recovered <<< "$i2c_counts"
  if [ "$attempts" -eq 0 ] && [ "$lockups" -eq 0 ]; then
    ok "i2c recovery" "no events (24h)"
  elif [ "$attempts" -gt 0 ] && [ "$attempts" -eq "$recovered" ]; then
    warn "i2c recovery" "${lockups} lockups, ${recovered}/${attempts} recovered (24h)"
  else
    fail "i2c recovery" "${lockups} lockups, ${recovered}/${attempts} recovered (24h)"
  fi
fi

# --- Speaker ---
if [ -f "/var/lib/shitbox/tts/en_GB-northern_english_male-medium.onnx" ]; then
  if aplay -l 2>/dev/null | grep -qi "UACDemo"; then
    ok "speaker" "USB speaker detected, TTS model present"
  else
    warn "speaker" "TTS model present, USB speaker not detected (buzzer fallback)"
  fi
else
  warn "speaker" "TTS model not installed (/var/lib/shitbox/tts/)"
fi

# --- HDMI Display ---
# Port-agnostic — match any HDMI-A-N. Survives swaps between A-1 and A-2
# without a config edit, mirrors probe_hdmi() in src/shitbox/hardware/probes.py.
hdmi_state=""
for status_file in /sys/class/drm/*HDMI-A-*/status; do
  [ -f "$status_file" ] || continue
  v=$(cat "$status_file" 2>/dev/null || echo "")
  if [ -n "$v" ] && [ "$v" != "disconnected" ]; then
    port=$(basename "$(dirname "$status_file")" | grep -oE 'HDMI-A-[0-9]+')
    hdmi_state="${port}: ${v}"
    break
  fi
done
if [ -n "$hdmi_state" ]; then
  ok "hdmi" "$hdmi_state"
else
  warn "hdmi" "no display detected on any HDMI-A port"
fi

# --- Throttle ---
if command -v vcgencmd >/dev/null 2>&1; then
  throttled=$(vcgencmd get_throttled 2>/dev/null | cut -d= -f2)
  if [ "$throttled" = "0x0" ]; then
    ok "throttle" "none"
  else
    fail "throttle" "flags: ${throttled}"
  fi
else
  warn "throttle" "vcgencmd not available"
fi

# --- Trip State ---
# Single sqlite invocation for all three values. IFNULL keeps the row count
# constant even when a key is missing, so sed -n line addressing works.
if command -v sqlite3 >/dev/null 2>&1 && [ -f "$DB" ]; then
  trip_data=$(sqlite3 "$DB" "
SELECT IFNULL((SELECT value_real FROM trip_state WHERE key='odometer_km'), '');
SELECT IFNULL((SELECT value_real FROM trip_state WHERE key='daily_km'), '');
SELECT COUNT(*) FROM waypoints_reached;
" 2>/dev/null || echo "")
  odo=$(echo "$trip_data" | sed -n '1p')
  daily=$(echo "$trip_data" | sed -n '2p')
  waypoints=$(echo "$trip_data" | sed -n '3p')
  if [ -n "$odo" ]; then
    odo_fmt=$(printf "%.1f" "$odo" 2>/dev/null || echo "$odo")
    daily_fmt=$(printf "%.1f" "$daily" 2>/dev/null || echo "${daily:-0}")
    ok "trip" "odo ${odo_fmt} km, today ${daily_fmt} km, ${waypoints:-0} waypoint(s)"
  else
    warn "trip" "no trip data yet"
  fi
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

# --- Watchdog (systemd kills) ---
# Catches systemd's own WatchdogSec kills — different failure mode from the
# app-level health_check below. Cold-start GPS used to burn the budget on
# its own; engine.py now pings WATCHDOG=1 inside _wait_for_gps_fix and the
# unit budget is 30s, but a kill here means we've regressed.
if command -v journalctl >/dev/null 2>&1; then
  kills=$(journalctl -u shitbox-telemetry --no-pager -q --since "1 hour ago" 2>/dev/null \
    | grep -cE "Watchdog timeout|killing.*watchdog" || true)
  if [ "$kills" -eq 0 ]; then
    ok "wdog kills" "0 (last 1h)"
  else
    fail "wdog kills" "${kills} kills (last 1h)"
  fi
fi

# --- Watchdog (app-level health checks) ---
if command -v journalctl >/dev/null 2>&1; then
  last_health=$(journalctl -u shitbox-telemetry --no-pager -q --since "10 min ago" 2>/dev/null |
    grep -E 'health_check_issues|health_check_all_clear' | tail -1 || true)
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
