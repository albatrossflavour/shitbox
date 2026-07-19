#!/usr/bin/env bash
#
# Rebuild each day's rally timelapse with a branded intro video + a title slate,
# matching the look of the event clips (0x0d1117 card, DejaVu Sans, gold accents).
#
# For every <captures>/<YYYY-MM-DD>/timelapse.mp4 it produces:
#     intro.mp4  +  slate (3s)  +  the existing timelapse body
# The slate reads:  "Shitbox Rally 2026 Autumn"
#                   "Day N · 17 July 2026"
#                   "Port Douglas → Melbourne"   (from agenda.json day title)
#
# Idempotent-ish: the original is backed up to timelapse.orig.mp4 the first time,
# and rebuilds always start from that backup, so re-running never double-stacks
# the intro. Dry-run by default — prints the plan, writes nothing.
#
# Usage:
#   CAPTURES=/path/to/captures ./scripts/rebuild-timelapses.sh          # dry run
#   CAPTURES=/path/to/captures ./scripts/rebuild-timelapses.sh --yes    # do it
#
# Env overrides: AGENDA, INTRO, FONT, RALLY_TITLE, SLATE_SECONDS.
set -euo pipefail

CAPTURES="${CAPTURES:-/captures}"
AGENDA="${AGENDA:-$CAPTURES/agenda.json}"
INTRO="${INTRO:-$CAPTURES/intro.mp4}"
FONT="${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}"
RALLY_TITLE="${RALLY_TITLE:-Shitbox Rally 2026 Autumn}"
SLATE_SECONDS="${SLATE_SECONDS:-3}"
W=1280; H=720; FPS=24

DO_IT=0; [[ "${1:-}" == "--yes" || "${1:-}" == "-y" ]] && DO_IT=1

for f in "$AGENDA" "$INTRO" "$FONT"; do
  [[ -e "$f" ]] || { echo "missing required file: $f" >&2; exit 2; }
done
command -v ffmpeg >/dev/null || { echo "ffmpeg not found" >&2; exit 2; }

echo "=== rebuild rally timelapses ==="
echo "captures : $CAPTURES"
echo "mode     : $([[ $DO_IT -eq 1 ]] && echo 'WRITE (--yes)' || echo 'dry run')"
echo

has_audio() { ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$1" | grep -q .; }

# Common video-normalise filter → identical params so concat demuxer is happy.
VF="scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2,fps=${FPS},format=yuv420p,setsar=1"
AAC=(-c:a aac -b:a 128k -ar 48000 -ac 2)
X264=(-c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p)

# Pull "day_number|17 July 2026|Start → Dest" for a given date from agenda.json.
day_meta() {
  python3 - "$AGENDA" "$1" <<'PY'
import sys, json, datetime
agenda, date = sys.argv[1], sys.argv[2]
days = json.load(open(agenda)).get("days", [])
d = next((x for x in days if x.get("date") == date), None)
if not d: sys.exit(1)
dt = datetime.date.fromisoformat(date)
pretty = f"{dt.day} {dt.strftime('%B %Y')}"        # "17 July 2026"
print(f"{d.get('day_number','?')}|{pretty}|{d.get('title','')}")
PY
}

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# Normalise the intro once (keep its audio; add silence if it has none).
INTRO_N="$tmp/intro.mp4"
build_intro() {
  if has_audio "$INTRO"; then
    ffmpeg -y -loglevel error -i "$INTRO" -map 0:v:0 -map 0:a:0 -vf "$VF" "${X264[@]}" "${AAC[@]}" "$INTRO_N"
  else
    ffmpeg -y -loglevel error -i "$INTRO" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
      -map 0:v:0 -map 1:a:0 -shortest -vf "$VF" "${X264[@]}" "${AAC[@]}" "$INTRO_N"
  fi
}

count=0
for daydir in "$CAPTURES"/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]; do
  [[ -d "$daydir" ]] || continue
  date="$(basename "$daydir")"
  src="$daydir/timelapse.mp4"; orig="$daydir/timelapse.orig.mp4"
  # Prefer the pristine backup as the body source so reruns don't stack intros.
  body="$src"; [[ -f "$orig" ]] && body="$orig"
  [[ -f "$body" ]] || continue

  meta="$(day_meta "$date" || true)"
  [[ -n "$meta" ]] || { echo "skip $date: not in agenda"; continue; }
  IFS='|' read -r daynum pretty route <<<"$meta"
  echo "$date  →  Day $daynum · $pretty · ${route:-<no route>}"
  count=$((count+1))
  [[ $DO_IT -eq 1 ]] || continue

  [[ -f "$orig" ]] || cp "$src" "$orig"     # first run: back up the pristine body
  [[ -f "$INTRO_N" ]] || build_intro

  # Slate: title card with the three text lines on the same card colour as the clips.
  printf '%s' "$RALLY_TITLE"        >"$tmp/l1.txt"
  printf 'Day %s · %s' "$daynum" "$pretty" >"$tmp/l2.txt"
  printf '%s' "$route"              >"$tmp/l3.txt"
  DT="drawtext=fontfile=${FONT}"
  slate="$tmp/slate.mp4"
  ffmpeg -y -loglevel error \
    -f lavfi -i "color=0x0d1117:s=${W}x${H}:r=${FPS}:d=${SLATE_SECONDS}" \
    -f lavfi -i "anullsrc=r=48000:cl=stereo" -map 0:v:0 -map 1:a:0 -shortest \
    -vf "${DT}:textfile=${tmp}/l1.txt:fontsize=56:fontcolor=white:x=(w-text_w)/2:y=h/2-150,\
${DT}:textfile=${tmp}/l2.txt:fontsize=40:fontcolor=0xf0dbb8:x=(w-text_w)/2:y=h/2-40,\
${DT}:textfile=${tmp}/l3.txt:fontsize=48:fontcolor=white:x=(w-text_w)/2:y=h/2+50,\
${DT}:text='shit-of-theseus.com':fontsize=22:fontcolor=0x8b949e:x=(w-text_w)/2:y=h-60" \
    "${X264[@]}" "${AAC[@]}" "$slate"

  # Normalise the body (add silent audio, unify params) then concat via demuxer.
  bodyn="$tmp/body.mp4"
  ffmpeg -y -loglevel error -i "$body" -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -map 0:v:0 -map 1:a:0 -shortest -vf "$VF" "${X264[@]}" "${AAC[@]}" "$bodyn"

  list="$tmp/concat.txt"
  printf "file '%s'\nfile '%s'\nfile '%s'\n" "$INTRO_N" "$slate" "$bodyn" >"$list"
  ffmpeg -y -loglevel error -f concat -safe 0 -i "$list" -c copy -movflags +faststart "$src.new"
  mv "$src.new" "$src"
  echo "   wrote $src"
done

echo
echo "$count day(s) matched.  $([[ $DO_IT -eq 1 ]] && echo 'Rebuilt.' || echo 'Dry run — re-run with --yes to write.')"
