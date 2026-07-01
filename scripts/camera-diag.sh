#!/bin/bash
# Camera / video diagnostic collector.
#
# Run this ON THE PI. It gathers everything needed to reason about the front-
# camera exposure and the save-time tone grade into ONE bundle, so the loop
# stops being "run a command, copy, paste" and becomes "run this, send the file".
#
# Collects:
#   - both cameras' full v4l2 control dumps (-L) and the front's format list
#   - requested-vs-applied control values from the daemon log (camera_ctrl_*)
#   - the deployed config's camera_controls + front_grade
#   - the running git commit + whether the working tree is dirty (i.e. whether
#     the grade / read-back changes are actually deployed)
#   - the live ffmpeg command line (mode, devices)
#   - a frame from a RAW front buffer segment (ungraded baseline) and from the
#     LATEST saved clip (graded), each measured for road/sky luma — the delta
#     proves whether the grade is working live
#
# Output:
#   ~/camera-diag-<timestamp>/report.txt   <- text, paste-able on its own
#   ~/camera-diag-<timestamp>/*.png        <- sample frames
#   ~/camera-diag-<timestamp>.tgz          <- the lot, one scp back to the laptop
#
# Usage:  ./scripts/camera-diag.sh
#         scp <pi>:~/camera-diag-*.tgz .     # then hand me the tgz (or the report.txt)
#
# Paths are overridable by env var for off-Pi testing (FRONT_DEV, BUFFER_DIR, ...).

# NOTE: deliberately NOT `set -e` — a diagnostic must collect every section even
# when individual commands fail (missing camera, no journal, etc).
set -uo pipefail

FRONT_DEV="${FRONT_DEV:-/dev/camera-front}"
CABIN_DEV="${CABIN_DEV:-/dev/camera-cabin}"
BUFFER_DIR="${BUFFER_DIR:-/var/lib/shitbox/video_buffer}"
CAPTURES_DIR="${CAPTURES_DIR:-/var/lib/shitbox/captures}"
SERVICE="${SERVICE:-shitbox-telemetry}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG="${CONFIG:-$REPO_DIR/config/config.yaml}"

# Region crops for 1920x1080 front framing — matched to regrade-test.sh so the
# numbers are comparable across both tools.
ROAD_CROP="${ROAD_CROP:-600:140:700:600}"
SKY_CROP="${SKY_CROP:-1100:250:400:120}"

TS="$(date +%Y%m%d-%H%M%S)"
OUT="$HOME/camera-diag-$TS"
REPORT="$OUT/report.txt"
mkdir -p "$OUT"

# Everything written to the report also echoes nothing to stdout — keep the
# terminal quiet, the file is the product.
# Single append target — every writer uses >>"$REPORT" so file positions stay
# consistent (a held-open fd alongside separate >> redirects overwrites itself).
: >"$REPORT"
section() { printf '\n========== %s ==========\n' "$1" >>"$REPORT"; }
note()    { printf '%s\n' "$*" >>"$REPORT"; }
run() {  # run "label" cmd args...   -> capture stdout+stderr or a failure note
  local label="$1"; shift
  printf '\n--- %s ---\n$ %s\n' "$label" "$*" >>"$REPORT"
  if command -v "$1" >/dev/null 2>&1; then
    "$@" >>"$REPORT" 2>&1 || printf '(command exited %d)\n' "$?" >>"$REPORT"
  else
    printf '(not available: %s)\n' "$1" >>"$REPORT"
  fi
}

# luma "label" file crop  -> appends "YMIN/YAVG/YMAX" line for the cropped region
luma() {
  local label="$1" file="$2" crop="$3" seek="${4:-}"
  local stats
  stats=$(ffmpeg -hide_banner -nostats ${seek:+-ss "$seek"} -i "$file" -frames:v 1 \
            -vf "crop=$crop,signalstats,metadata=mode=print:file=-" -f null - 2>/dev/null \
          | grep -E 'YAVG|YMIN|YMAX' | sed 's/.*signalstats\.//' | head -3 | paste -sd' ' -)
  printf '  %-20s %s\n' "$label" "${stats:-(measure failed)}" >>"$REPORT"
}

note "Shitbox camera diagnostic"
note "host: $(hostname 2>/dev/null)   date: $(date 2>/dev/null)"
note "report: $REPORT"

section "DEPLOYED CODE"
run "git commit"  git -C "$REPO_DIR" rev-parse --short HEAD
run "working tree (dirty = grade/read-back not committed)" git -C "$REPO_DIR" status --porcelain
run "config camera block" grep -nE 'camera_controls|front_grade|brightness|contrast|saturation|gamma|auto_exposure|exposure_time|backlight' "$CONFIG"

section "CAMERA DEVICES"
run "symlinks" ls -l "$FRONT_DEV" "$CABIN_DEV"
run "all video nodes" ls -l /dev/video*

section "FRONT CAMERA ($FRONT_DEV)"
run "controls (-L)"        v4l2-ctl -d "$FRONT_DEV" -L
run "formats (-ext)"       v4l2-ctl -d "$FRONT_DEV" --list-formats-ext

section "CABIN CAMERA ($CABIN_DEV)"
run "controls (-L)"        v4l2-ctl -d "$CABIN_DEV" -L

section "APPLIED CONTROLS (from daemon log, this boot)"
# camera_ctrl_set verified=True/False, camera_ctrl_mismatch, camera_ctrl_rejected
run "camera_ctrl* lines" bash -c "journalctl -u '$SERVICE' -b --no-pager 2>/dev/null | grep -E 'camera_ctrl|v4l2ctl|_configure_cameras|front_grade|concat_overlay' | tail -60"

section "LIVE FFMPEG"
run "process" bash -c "ps -eo pid,args 2>/dev/null | grep -E 'ffmpeg' | grep -v grep | tail -5"

section "DISK / RECENT FILES"
run "buffer dir"   bash -c "ls -lt '$BUFFER_DIR' 2>/dev/null | head -8"
run "captures"     bash -c "ls -lt '$CAPTURES_DIR'/*/ 2>/dev/null | head -12"
run "disk usage"   df -h "$BUFFER_DIR" "$CAPTURES_DIR"

section "TONE MEASUREMENT (road vs sky luma, 0-255)"
note "Target: road YAVG ~95-110, sky YMAX < 240. Raw = camera tone (ungraded);"
note "saved = after the front_grade curve. A big road delta means the grade is working."

# Raw front buffer segment (ungraded baseline).
RAW_SEG=$(ls -t "$BUFFER_DIR"/seg_*.ts 2>/dev/null | head -1)
if [[ -n "${RAW_SEG:-}" && -f "$RAW_SEG" ]]; then
  note ""
  note "RAW front segment: $RAW_SEG"
  ffmpeg -y -hide_banner -loglevel error -i "$RAW_SEG" -frames:v 1 "$OUT/front_raw.png" 2>/dev/null
  luma "raw road" "$RAW_SEG" "$ROAD_CROP"
  luma "raw sky"  "$RAW_SEG" "$SKY_CROP"
else
  note "RAW front segment: (none found in $BUFFER_DIR)"
fi

# Latest saved capture (graded). Sample at its midpoint to skip intro/slate.
SAVED=$(ls -t "$CAPTURES_DIR"/*/*.mp4 2>/dev/null | head -1)
if [[ -n "${SAVED:-}" && -f "$SAVED" ]]; then
  DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$SAVED" 2>/dev/null || echo 0)
  MID=$(awk -v d="$DUR" 'BEGIN{printf "%.0f", (d>4)? d/2 : 0}')
  note ""
  note "SAVED capture: $SAVED  (dur ${DUR}s, sampling t=${MID}s)"
  ffmpeg -y -hide_banner -loglevel error -ss "$MID" -i "$SAVED" -frames:v 1 "$OUT/saved_front.png" 2>/dev/null
  luma "saved road" "$SAVED" "$ROAD_CROP" "$MID"
  luma "saved sky"  "$SAVED" "$SKY_CROP" "$MID"
else
  note "SAVED capture: (none found in $CAPTURES_DIR)"
fi

# Bundle it up for a single scp back.
TGZ="$HOME/camera-diag-$TS.tgz"
tar -czf "$TGZ" -C "$HOME" "camera-diag-$TS" 2>/dev/null

echo "Done."
echo "  report : $REPORT"
echo "  bundle : $TGZ"
echo
echo "Send me the bundle:   scp <pi>:$TGZ ."
echo "Or just paste:        cat $REPORT"
