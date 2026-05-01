#!/usr/bin/env bash
# Install Waveshare touchscreen calibration config to the system xorg.conf.d.
# Run with sudo on the Pi.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF_SRC="${SCRIPT_DIR}/../systemd/99-waveshare-touchscreen.conf"
CONF_DST="/etc/X11/xorg.conf.d/99-waveshare-touchscreen.conf"

if [ ! -f "$CONF_SRC" ]; then
    echo "ERROR: source config not found at $CONF_SRC" >&2
    exit 1
fi

mkdir -p "$(dirname "$CONF_DST")"
cp "$CONF_SRC" "$CONF_DST"
echo "Installed touchscreen calibration to $CONF_DST"
echo "Restart X or reboot for changes to take effect."
