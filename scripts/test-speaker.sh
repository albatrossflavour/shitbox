#!/bin/bash
# Test Piper TTS and USB speaker playback.
# Writes a WAV to /tmp for inspection, then plays it via aplay.
# Usage: ./scripts/test-speaker.sh [optional message]

set -euo pipefail

VENV="${HOME}/shitbox/.venv/bin/python"
MODEL="/var/lib/shitbox/tts/en_US-lessac-medium.onnx"
WAV="/tmp/piper_test.wav"
TEXT="${1:-Testing one two three}"

# Detect USB speaker
CARD=$(grep -n "UACDemo" /proc/asound/cards 2>/dev/null | head -1 | awk '{print $2}' | tr -d ' ')
if [ -z "$CARD" ]; then
    echo "USB speaker not detected in /proc/asound/cards"
    exit 1
fi
DEVICE="plughw:${CARD},0"
echo "Speaker: ${DEVICE}"

# Synthesise WAV
echo "Synthesising: \"${TEXT}\""
"$VENV" -c "
from piper.voice import PiperVoice
import wave
v = PiperVoice.load('${MODEL}')
wf = wave.open('${WAV}', 'wb')
v.synthesize_wav('${TEXT}', wf)
wf.close()
print('WAV written to ${WAV}')
"

# Show WAV info
echo ""
echo "--- WAV info ---"
"$VENV" -c "
import wave
with wave.open('${WAV}', 'rb') as w:
    print(f'Channels: {w.getnchannels()}')
    print(f'Sample width: {w.getsampwidth()}')
    print(f'Frame rate: {w.getframerate()}')
    print(f'Frames: {w.getnframes()}')
    print(f'Duration: {w.getnframes() / w.getframerate():.2f}s')
"

# Play
echo ""
echo "Playing on ${DEVICE}..."
aplay -D "${DEVICE}" "${WAV}"

echo ""
echo "WAV kept at ${WAV} for inspection"
