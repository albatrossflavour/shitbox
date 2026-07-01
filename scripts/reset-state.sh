#!/bin/bash
# Null out the runtime state before the rally — wipe accumulated data so the
# Pi starts the event with a clean DB and empty disk, WITHOUT destroying the
# expensive assets that live in the same tree.
#
# WIPES (regenerated automatically on next start):
#   telemetry.db (+ -wal/-shm)   SQLite — readings, events, sync cursors
#   video_buffer/                dashcam ring segments + pending slates
#   video_buffer_pip/            legacy PiP buffer (if present)
#   captures/                    saved event clips + timelapse frames/output + events.json
#   events/                      per-event JSON metadata + CSV bursts
#   tts/cache/                   rendered speech cache (model is KEPT)
#
# KEEPS (never touched — slow/annoying to regenerate):
#   tts/*.onnx, tts/*.onnx.json  TTS voice model + sidecar
#   intro.mp4                    branded intro video
#   tiles/                       offline map tiles (rally.mbtiles) — the big one
#
# SAFETY: dry-run by default. Prints what it would delete and how much space it
# frees, and changes NOTHING until you re-run with --yes.
#
# Usage:
#   ./scripts/reset-state.sh             # dry run — show the plan, touch nothing
#   ./scripts/reset-state.sh --yes       # stop service, wipe, restart clean
#   ./scripts/reset-state.sh --yes --no-restart
#
# DATA_DIR / SERVICE overridable by env for off-Pi testing.

set -uo pipefail

DATA_DIR="${DATA_DIR:-/var/lib/shitbox}"
SERVICE="${SERVICE:-shitbox-telemetry}"

DO_IT=0
RESTART=1
for arg in "$@"; do
  case "$arg" in
    --yes|-y)     DO_IT=1 ;;
    --no-restart) RESTART=0 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

# Guard against a catastrophically wrong DATA_DIR.
case "$DATA_DIR" in
  ""|"/"|"/var"|"/var/lib"|"/home"|"$HOME")
    echo "refusing to operate on DATA_DIR='$DATA_DIR' — too broad" >&2; exit 2 ;;
esac
if [[ ! -d "$DATA_DIR" ]]; then
  echo "DATA_DIR does not exist: $DATA_DIR" >&2; exit 2
fi

# Explicit wipe targets. Files are removed; directories have their CONTENTS
# removed but the directory itself is kept (the daemon expects it to exist).
FILE_TARGETS=(
  "$DATA_DIR/telemetry.db"
  "$DATA_DIR/telemetry.db-wal"
  "$DATA_DIR/telemetry.db-shm"
)
DIR_TARGETS=(
  "$DATA_DIR/video_buffer"
  "$DATA_DIR/video_buffer_pip"
  "$DATA_DIR/captures"
  "$DATA_DIR/events"
  "$DATA_DIR/tts/cache"
)
# Explicit keepers — verified to still exist after a real wipe.
KEEPERS=(
  "$DATA_DIR/intro.mp4"
  "$DATA_DIR/tiles"
)

size() { du -sh "$1" 2>/dev/null | cut -f1; }

echo "=== shitbox state reset ==="
echo "data dir : $DATA_DIR"
echo "mode     : $([[ $DO_IT -eq 1 ]] && echo 'WIPE (--yes)' || echo 'dry run (no changes)')"
echo
echo "Disk before:"
df -h "$DATA_DIR" | sed 's/^/  /'
echo
echo "Would remove:"
total_listed=0
for f in "${FILE_TARGETS[@]}"; do
  [[ -e "$f" ]] && printf '  %-44s %s\n' "$f" "$(size "$f")"
done
for d in "${DIR_TARGETS[@]}"; do
  if [[ -d "$d" ]]; then
    n=$(find "$d" -mindepth 1 2>/dev/null | wc -l | tr -d ' ')
    printf '  %-44s %s  (%s items, dir kept)\n' "$d/*" "$(size "$d")" "$n"
  fi
done
echo
echo "Keeping (never touched):"
# TTS models live directly under tts/, alongside the cache dir we DO wipe.
for m in "$DATA_DIR"/tts/*.onnx "$DATA_DIR"/tts/*.onnx.json; do
  [[ -e "$m" ]] && printf '  %-44s %s\n' "$m" "$(size "$m")"
done
for k in "${KEEPERS[@]}"; do
  [[ -e "$k" ]] && printf '  %-44s %s\n' "$k" "$(size "$k")"
done
echo

if [[ $DO_IT -eq 0 ]]; then
  echo "Dry run only. Nothing changed."
  echo "Heads up: captures/ may include event clips not yet synced to the NAS —"
  echo "check the website/NAS before wiping if any footage matters."
  echo
  echo "Re-run to actually wipe:   $0 --yes"
  exit 0
fi

# --- real wipe from here ---
sudo_maybe() { if [[ $EUID -ne 0 ]]; then sudo "$@"; else "$@"; fi; }

if command -v systemctl >/dev/null 2>&1; then
  echo "Stopping $SERVICE ..."
  sudo_maybe systemctl stop "$SERVICE" || echo "  (could not stop $SERVICE — continuing)"
fi

echo "Wiping ..."
for f in "${FILE_TARGETS[@]}"; do
  [[ -e "$f" ]] && { sudo_maybe rm -f "$f" && echo "  rm $f"; }
done
for d in "${DIR_TARGETS[@]}"; do
  if [[ -d "$d" ]]; then
    # Delete contents, keep the directory. -mindepth 1 never touches $d itself.
    sudo_maybe find "$d" -mindepth 1 -delete 2>/dev/null && echo "  emptied $d/"
  fi
done

# Safety assertion: the keepers must still be here.
echo
echo "Verifying keepers survived:"
fail=0
for m in "$DATA_DIR"/tts/*.onnx; do
  [[ -e "$m" ]] && echo "  ok  $m" || { echo "  MISSING $m"; fail=1; }
done
for k in "${KEEPERS[@]}"; do
  [[ -e "$k" ]] && echo "  ok  $k" || echo "  absent (was not present before): $k"
done
[[ $fail -eq 1 ]] && echo "  WARNING: a TTS model is missing — investigate before starting."

if [[ $RESTART -eq 1 && $(command -v systemctl) ]]; then
  echo
  echo "Starting $SERVICE (recreates DB + dirs clean) ..."
  sudo_maybe systemctl start "$SERVICE" || echo "  (could not start $SERVICE — start it manually)"
fi

echo
echo "Disk after:"
df -h "$DATA_DIR" | sed 's/^/  /'
echo
echo "Done. State nulled."
