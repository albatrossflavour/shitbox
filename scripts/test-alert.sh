#!/bin/bash
# Simulate an alert on the running shitbox-telemetry service.
# Sends SIGUSR2 to the engine process, which plays a buzzer beep and speaks "Event detected."

PID=$(systemctl show -p MainPID --value shitbox-telemetry 2>/dev/null)

if [ -z "$PID" ] || [ "$PID" = "0" ]; then
    # Fall back to finding the process directly
    PID=$(pgrep -f 'python.*shitbox\.events\.engine' | head -1)
fi

if [ -z "$PID" ]; then
    echo "shitbox-telemetry is not running"
    exit 1
fi

kill -USR2 "$PID"
echo "Test alert triggered (PID $PID)"
