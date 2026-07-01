#!/bin/bash
# Front-camera tone-grade tuning instrument.
#
# Applies a candidate ffmpeg `curves` grade to real footage and measures what
# it does to the foreground (road) and the sky, so the grade can be tuned
# against actual rally light in a tight access window instead of by eye.
#
# The grade lives in config as `capture.video_buffer.front_grade` (curves
# master control points). This script lets you try a candidate value, read the
# luma numbers, eyeball a preview, and only then push it to the Pi.
#
# Source footage: either a saved clip, OR — better — raw front ring-buffer
# segments pulled off the Pi (`/var/lib/shitbox/video_buffer/seg_*.ts`). Raw
# segments are ungraded, so they show the camera's true tone in current light.
#
# Usage:
#   regrade-test.sh <input.mp4|seg_dir> ["curve points"] [seek_seconds]
#
#   regrade-test.sh clip.mp4
#       Measure + preview the DEFAULT shipped curve against clip.mp4.
#   regrade-test.sh clip.mp4 "0/0 0.18/0.40 0.4/0.62 0.7/0.84 1/1" 35
#       Try a candidate curve, sampling at t=35s.
#   regrade-test.sh ./segments
#       Concatenate seg_*.ts in ./segments, then measure + preview.
#
# Targets to aim for (luma 0-255):
#   road YAVG  ~95-110   (foreground readable, not greyed)
#   sky  YMAX  < 240     (white protected, no clipping)
#
# Outputs land in /tmp/regrade/: graded preview clip, before/after still.

set -euo pipefail

INPUT="${1:?usage: regrade-test.sh <input.mp4|seg_dir> [\"curve\"] [seek_s]}"
CURVE="${2:-0/0 0.15/0.36 0.35/0.58 0.7/0.83 1/1}"
SEEK="${3:-}"

OUT=/tmp/regrade
mkdir -p "$OUT"

# Region crops tuned for 1920x1080 dashcam framing: a centre band of road
# surface above the bonnet line, and an upper-middle band of sky. Override via
# ROAD_CROP / SKY_CROP env vars if the framing differs.
ROAD_CROP="${ROAD_CROP:-600:140:700:600}"
SKY_CROP="${SKY_CROP:-1100:250:400:120}"

# Resolve input to a single playable file. A directory of segments is
# concatenated losslessly first.
if [[ -d "$INPUT" ]]; then
  list="$OUT/concat.txt"
  : > "$list"
  for s in $(ls -1 "$INPUT"/seg_*.ts 2>/dev/null | sort); do
    echo "file '$(cd "$INPUT" && pwd)/$(basename "$s")'" >> "$list"
  done
  [[ -s "$list" ]] || { echo "no seg_*.ts found in $INPUT" >&2; exit 1; }
  CLIP="$OUT/source.mp4"
  ffmpeg -y -loglevel error -f concat -safe 0 -i "$list" -c copy "$CLIP"
  echo "concatenated $(wc -l < "$list" | tr -d ' ') segments -> $CLIP"
else
  CLIP="$INPUT"
fi

# Default seek to the clip midpoint if not given, so we sample live footage
# rather than the intro/slate at the head.
if [[ -z "$SEEK" ]]; then
  dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$CLIP" 2>/dev/null || echo 0)
  SEEK=$(awk -v d="$dur" 'BEGIN{printf "%.0f", (d>4)? d/2 : 0}')
fi

measure() { # crop  ->  "YAVG=.. YMIN=.. YMAX=.."
  ffmpeg -hide_banner -nostats -ss "$SEEK" -i "$CLIP" -frames:v 1 \
    -vf "${1:+$1,}crop=$2,signalstats,metadata=mode=print:file=-" -f null - 2>/dev/null \
    | grep -E "YAVG|YMIN|YMAX" | sed 's/.*signalstats\.//' | head -3 | paste -sd' ' -
}

FILT="curves=master='$CURVE'"

echo
echo "  source : $CLIP"
echo "  sample : t=${SEEK}s"
echo "  curve  : $CURVE"
echo
printf "  %-8s %-28s %-28s\n" "" "ROAD (foreground)" "SKY"
printf "  %-8s %-28s %-28s\n" "before" "$(measure '' "$ROAD_CROP")" "$(measure '' "$SKY_CROP")"
printf "  %-8s %-28s %-28s\n" "after"  "$(measure "$FILT" "$ROAD_CROP")" "$(measure "$FILT" "$SKY_CROP")"
echo

# Before/after still (top = before, bottom = after) for an eyeball check.
ffmpeg -y -loglevel error -ss "$SEEK" -i "$CLIP" -frames:v 1 -filter_complex \
  "[0:v]scale=960:-1[a];[0:v]${FILT},scale=960:-1[b];[a][b]vstack" \
  "$OUT/still.png"

# 10s graded preview clip to catch pumping/flicker the still can't show.
ffmpeg -y -loglevel error -ss "$SEEK" -t 10 -i "$CLIP" -vf "$FILT" \
  -c:v libx264 -preset veryfast -an "$OUT/preview.mp4"

echo "  still   : $OUT/still.png   (before over after)"
echo "  preview : $OUT/preview.mp4 (10s graded)"
echo
echo "  aim for: road YAVG ~95-110, sky YMAX < 240"
echo "  happy?  set capture.video_buffer.front_grade to the curve above, restart service."
