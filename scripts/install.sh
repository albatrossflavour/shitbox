#!/bin/bash
# Shitbox Telemetry Installation Script
# Run as: sudo ./install.sh

set -e

echo "=== Shitbox Rally Telemetry Installation ==="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo ./install.sh)"
    exit 1
fi

# Get the actual user (not root)
ACTUAL_USER=${SUDO_USER:-tgreen}
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)
INSTALL_DIR="$ACTUAL_HOME/shitbox"

echo "Installing for user: $ACTUAL_USER"
echo "Install directory: $INSTALL_DIR"

# Enable I2C interface and set bus speed to 100 kHz for reliability
echo ""
echo "=== Enabling I2C interface ==="
raspi-config nonint do_i2c 0

# Lower I2C bus speed from 400 kHz to 100 kHz — more tolerant of vibration
if ! grep -q "i2c_arm_baudrate" /boot/firmware/config.txt 2>/dev/null; then
    echo "dtparam=i2c_arm_baudrate=100000" >> /boot/firmware/config.txt
    echo "I2C bus speed set to 100 kHz"
else
    echo "I2C baudrate already configured"
fi

# Add user to required groups
usermod -aG i2c,gpio,audio $ACTUAL_USER

# Create data directory
echo ""
echo "=== Creating data directory ==="
mkdir -p /var/lib/shitbox
chown $ACTUAL_USER:$ACTUAL_USER /var/lib/shitbox
chmod 755 /var/lib/shitbox

# Install system dependencies
echo ""
echo "=== Installing system dependencies ==="
apt-get update
apt-get install -y python3-pip python3-venv python3-dev i2c-tools gpsd gpsd-clients alsa-utils fake-hwclock

# Configure gpsd for the GPS HAT
echo ""
echo "=== Configuring gpsd ==="
cat > /etc/default/gpsd << 'EOF'
# Shitbox Rally Telemetry - gpsd configuration
START_DAEMON="true"
USBAUTO="false"
DEVICES="/dev/serial0"
GPSD_OPTIONS="-n"
EOF

# Enable and start gpsd
systemctl enable gpsd
systemctl restart gpsd

# Create virtual environment
echo ""
echo "=== Setting up Python environment ==="
cd "$INSTALL_DIR"
sudo -u $ACTUAL_USER python3 -m venv .venv
sudo -u $ACTUAL_USER .venv/bin/pip install --upgrade pip
sudo -u $ACTUAL_USER .venv/bin/pip install -e .

# Download Piper TTS voice model
echo ""
echo "=== Setting up Piper TTS voice model ==="
TTS_DIR="/var/lib/shitbox/tts"
mkdir -p "$TTS_DIR"
chown $ACTUAL_USER:$ACTUAL_USER "$TTS_DIR"

PIPER_MODEL="en_GB-northern_english_male-medium"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium"

if [ ! -f "$TTS_DIR/${PIPER_MODEL}.onnx" ]; then
    echo "Downloading Piper voice model (${PIPER_MODEL}, ~63 MB)..."
    sudo -u $ACTUAL_USER wget -q --show-progress -O "$TTS_DIR/${PIPER_MODEL}.onnx" \
        "${PIPER_BASE}/${PIPER_MODEL}.onnx"
    sudo -u $ACTUAL_USER wget -q -O "$TTS_DIR/${PIPER_MODEL}.onnx.json" \
        "${PIPER_BASE}/${PIPER_MODEL}.onnx.json"
    echo "Voice model installed to $TTS_DIR"
else
    echo "Voice model already exists at $TTS_DIR/${PIPER_MODEL}.onnx"
fi

# Install systemd service
echo ""
echo "=== Installing systemd service ==="
cp "$INSTALL_DIR/systemd/shitbox-telemetry.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable shitbox-telemetry.service

# Copy config if not exists
echo ""
echo "=== Setting up configuration ==="
mkdir -p /etc/shitbox
if [ ! -f /etc/shitbox/config.yaml ]; then
    cp "$INSTALL_DIR/config/config.yaml" /etc/shitbox/config.yaml
    chown $ACTUAL_USER:$ACTUAL_USER /etc/shitbox/config.yaml
    echo "Configuration copied to /etc/shitbox/config.yaml"
    echo "Please edit this file to configure MQTT broker and other settings."
else
    echo "Configuration already exists at /etc/shitbox/config.yaml"
fi

# Test I2C
echo ""
echo "=== Testing I2C ==="
echo "Detected I2C devices:"
i2cdetect -y 1 || echo "I2C test failed - may need reboot"

# Test gpsd
echo ""
echo "=== Testing gpsd ==="
timeout 5 gpspipe -w -n 3 2>/dev/null || echo "gpsd not receiving data yet (may need GPS fix)"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "1. Edit /etc/shitbox/config.yaml with your settings"
echo "2. Reboot to apply hardware interface changes: sudo reboot"
echo "3. After reboot, verify gpsd is working: cgps"
echo "4. Test USB speaker: aplay /usr/share/sounds/alsa/Front_Center.wav"
echo "5. Start the service: sudo systemctl start shitbox-telemetry"
echo "6. Check status: sudo systemctl status shitbox-telemetry"
echo "7. View logs: journalctl -u shitbox-telemetry -f"
echo ""
