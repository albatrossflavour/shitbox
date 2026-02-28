#!/bin/bash
# Clear the pre-rendered TTS voice cache.
# Run after changing voice model, pitch, or speed settings.

CACHE_DIR="/var/lib/shitbox/tts/cache"

if [ -d "$CACHE_DIR" ]; then
    rm -rf "$CACHE_DIR"
    echo "TTS cache cleared: $CACHE_DIR"
else
    echo "No cache to clear: $CACHE_DIR does not exist"
fi
