# Phase 11 — Dead code audit close-out

| Item | Status | Evidence |
|------|--------|----------|
| D-15 pip_compositor.py | deleted | wave 4 task 1 — file never existed on v2 branch; grep returns nothing |
| D-16 INA219 power.py | deleted and rewrote | wave 2 task 2 — `src/shitbox/collectors/power.py` now INA226Collector |
| D-17 MCP9808 temperature.py | deleted and rewrote | wave 2 task 1 — `src/shitbox/collectors/temperature.py` now DS18B20Collector |
| D-18 MPU6050 sampler | deleted and rewrote | wave 1 task 1 — `src/shitbox/events/sampler.py` now HighRateSampler/LSM6DSOX |
| D-19 ring_buffer dead imports | clean | `grep -c "_nice" src/shitbox/events/ring_buffer.py` == 0; `grep -c "^import os" src/shitbox/events/ring_buffer.py` == 0 |
| D-20 `_event_json_paths` lock | clean | engine.py line 627 declares `self._event_paths_lock = threading.Lock()`; all read/write access at lines 956, 993, 1006 guarded by `with self._event_paths_lock:` |
| D-21 capture_sync background | clean | `capture_sync.py` line 58: `self._thread = threading.Thread(target=self._sync_loop, daemon=True)`; `_do_sync` called only from `_sync_loop` (line 85), never from telemetry thread |

## Verification commands

```bash
# D-15
test ! -f src/shitbox/capture/pip_compositor.py && echo "D-15 CLEAN"
grep -rn "pip_compositor" src/ tests/ 2>/dev/null | wc -l  # must be 0

# D-19
grep -c "_nice" src/shitbox/events/ring_buffer.py  # 0
grep -c "^import os" src/shitbox/events/ring_buffer.py  # 0

# D-20
grep -n "_event_json_paths" src/shitbox/events/engine.py
# all accesses must be wrapped in 'with self._event_paths_lock:'

# D-21
grep -n "daemon=True" src/shitbox/sync/capture_sync.py
# thread is daemon; _do_sync() is only called from _sync_loop
```

## Final state

Phase 11 code-only work complete. All dead-code items resolved. Full test suite green (168 passed), ruff clean. Physical cutover (Pi 5 hardware swap) remains out of scope for this phase.
