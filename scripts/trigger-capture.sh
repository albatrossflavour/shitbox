#!/bin/bash
# Trigger a manual video capture on the running shitbox-telemetry service.
# Sends SIGUSR1 to the engine process, which saves ~30s pre + 30s post from the ring buffer.

PID=$(systemctl show -p MainPID --value shitbox-telemetry 2>/dev/null)

if [ -z "$PID" ] || [ "$PID" = "0" ]; then
    # Fall back to finding the process directly
    PID=$(pgrep -f 'python.*shitbox\.events\.engine' | head -1)
fi

if [ -z "$PID" ]; then
    echo "shitbox-telemetry is not running"
    exit 1
fi

kill -USR1 "$PID"
echo "Capture triggered (PID $PID)"
