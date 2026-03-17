#!/usr/bin/env python3
"""Retrospective event detection from stored 1 Hz IMU data.

Reads today's IMU readings from the SQLite database and applies the
same detection thresholds used by the live detector. Reports any
samples that crossed event thresholds.

NOTE: The live event detector runs on 100 Hz data. This database only
stores 1 Hz readings (the low-rate path). Minimum-duration checks are
not reliable at 1 Hz, so this report shows threshold crossings and
sustained windows rather than validated events. It will MISS brief events
that the live detector would catch, but is useful for finding missed events
that were sustained for >1 second.

Usage:
    python scripts/replay_events.py [--db PATH] [--date YYYY-MM-DD]

Calibration offsets are loaded automatically from the shitbox config so that
raw DB values recorded before calibration are corrected before detection.
Pass --no-offsets to skip this and use raw values.
"""

import argparse
import math
import sqlite3
import sys
from collections import deque
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_DB = "/var/lib/shitbox/telemetry.db"

# ── Thresholds (mirrors DetectorConfig defaults) ──────────────────────────────
HARD_BRAKE_THRESHOLD_G = -0.45
HARD_BRAKE_MIN_DURATION_S = 0.2   # 200 ms — at 1 Hz this is ~1 sample

BIG_CORNER_THRESHOLD_G = 0.6
BIG_CORNER_MIN_DURATION_S = 0.3

HIGH_G_THRESHOLD = 0.85
HIGH_G_MIN_DURATION_S = 0.15

ROUGH_ROAD_STDDEV_THRESHOLD = 0.3
ROUGH_ROAD_WINDOW_S = 1.0         # 1 second window = ~1 sample at 1 Hz

COOLDOWN_S = 10.0


def load_offsets() -> tuple[float, float, float]:
    """Load calibration offsets from shitbox config. Returns (ox, oy, oz)."""
    try:
        from shitbox.utils.config import load_config
        cfg = load_config()
        imu = cfg.sensors.imu
        return imu.accel_offset_x, imu.accel_offset_y, imu.accel_offset_z
    except Exception:
        return 0.0, 0.0, 0.0


def query_imu_today(conn: sqlite3.Connection, target_date: date) -> list[dict]:
    """Fetch all IMU readings for the given date, ordered by time."""
    date_str = target_date.isoformat()
    cursor = conn.execute(
        """
        SELECT timestamp_utc, accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z
        FROM readings
        WHERE sensor_type = 'imu'
          AND date(timestamp_utc) = ?
          AND accel_x IS NOT NULL
        ORDER BY timestamp_utc
        """,
        (date_str,),
    )
    rows = cursor.fetchall()
    return [
        {
            "ts": row[0],
            "ax": row[1],
            "ay": row[2],
            "az": row[3],
            "gx": row[4],
            "gy": row[5],
            "gz": row[6],
        }
        for row in rows
    ]


def ts_to_epoch(ts_str: str) -> float:
    """Parse ISO timestamp string to Unix epoch float."""
    dt = datetime.fromisoformat(ts_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def apply_offsets(rows: list[dict], ox: float, oy: float, oz: float) -> list[dict]:
    """Return a copy of rows with calibration offsets applied."""
    if ox == 0.0 and oy == 0.0 and oz == 0.0:
        return rows
    return [
        {**r, "ax": r["ax"] + ox, "ay": r["ay"] + oy, "az": r["az"] + oz}
        for r in rows
    ]


def detect_events(rows: list[dict]) -> list[dict]:
    """
    Scan IMU rows and return a list of detected event windows.

    Each returned event dict has:
      type, start_ts, end_ts, peak_value, peak_ax, peak_ay, peak_az, sample_count
    """
    events: list[dict] = []

    # State for each event type
    active: dict[str, dict | None] = {
        "HARD_BRAKE": None,
        "BIG_CORNER": None,
        "HIGH_G": None,
    }
    last_event_time: dict[str, float] = {}

    # Rolling window for ROUGH_ROAD
    az_window: deque = deque()
    last_rough_event_time = 0.0

    def on_cooldown(event_type: str, ts: float) -> bool:
        return (ts - last_event_time.get(event_type, 0.0)) < COOLDOWN_S

    def start_active(event_type: str, row: dict, trigger_val: float) -> None:
        if active[event_type] is not None or on_cooldown(event_type, ts_to_epoch(row["ts"])):
            return
        active[event_type] = {
            "start_ts": row["ts"],
            "start_epoch": ts_to_epoch(row["ts"]),
            "peak_value": abs(trigger_val),
            "peak_ax": row["ax"],
            "peak_ay": row["ay"],
            "peak_az": row["az"],
            "samples": [row],
        }

    def update_active(event_type: str, row: dict, current_val: float) -> None:
        ev = active[event_type]
        if ev is None:
            return
        ev["samples"].append(row)
        if abs(current_val) > ev["peak_value"]:
            ev["peak_value"] = abs(current_val)
            ev["peak_ax"] = row["ax"]
            ev["peak_ay"] = row["ay"]
            ev["peak_az"] = row["az"]

    def end_active(event_type: str, row: dict, min_duration_s: float) -> None:
        ev = active[event_type]
        if ev is None:
            return
        active[event_type] = None
        end_epoch = ts_to_epoch(row["ts"])
        duration_s = end_epoch - ev["start_epoch"]
        if duration_s >= min_duration_s:
            events.append({
                "type": event_type,
                "start_ts": ev["start_ts"],
                "end_ts": row["ts"],
                "duration_s": round(duration_s, 2),
                "peak_value": round(ev["peak_value"], 3),
                "peak_ax": round(ev["peak_ax"], 3),
                "peak_ay": round(ev["peak_ay"], 3),
                "peak_az": round(ev["peak_az"], 3),
                "sample_count": len(ev["samples"]),
            })
            last_event_time[event_type] = end_epoch

    for row in rows:
        ax, ay, az = row["ax"], row["ay"], row["az"]
        epoch = ts_to_epoch(row["ts"])

        # HARD_BRAKE
        if ax < HARD_BRAKE_THRESHOLD_G:
            if active["HARD_BRAKE"] is None:
                start_active("HARD_BRAKE", row, ax)
            else:
                update_active("HARD_BRAKE", row, ax)
        else:
            end_active("HARD_BRAKE", row, HARD_BRAKE_MIN_DURATION_S)

        # BIG_CORNER
        if abs(ay) > BIG_CORNER_THRESHOLD_G:
            if active["BIG_CORNER"] is None:
                start_active("BIG_CORNER", row, ay)
            else:
                update_active("BIG_CORNER", row, ay)
        else:
            end_active("BIG_CORNER", row, BIG_CORNER_MIN_DURATION_S)

        # HIGH_G
        combined_g = math.sqrt(ax ** 2 + ay ** 2)
        if combined_g > HIGH_G_THRESHOLD:
            if active["HIGH_G"] is None:
                start_active("HIGH_G", row, combined_g)
            else:
                update_active("HIGH_G", row, combined_g)
        else:
            end_active("HIGH_G", row, HIGH_G_MIN_DURATION_S)

        # ROUGH_ROAD — rolling stddev of az
        az_window.append((epoch, az))
        # Drop samples older than window
        while az_window and (epoch - az_window[0][0]) > ROUGH_ROAD_WINDOW_S:
            az_window.popleft()

        if len(az_window) >= 2:
            az_vals = [v for _, v in az_window]
            mean_az = sum(az_vals) / len(az_vals)
            variance = sum((v - mean_az) ** 2 for v in az_vals) / len(az_vals)
            stddev = math.sqrt(variance)

            if stddev > ROUGH_ROAD_STDDEV_THRESHOLD:
                if (epoch - last_rough_event_time) > COOLDOWN_S:
                    events.append({
                        "type": "ROUGH_ROAD",
                        "start_ts": az_window[0][0],
                        "end_ts": row["ts"],
                        "duration_s": round(epoch - az_window[0][0], 2),
                        "peak_value": round(stddev, 3),
                        "peak_ax": round(ax, 3),
                        "peak_ay": round(ay, 3),
                        "peak_az": round(az, 3),
                        "sample_count": len(az_window),
                    })
                    last_rough_event_time = epoch

    # Close any still-active events at end of data
    if rows:
        last_row = rows[-1]
        for event_type, min_dur in [
            ("HARD_BRAKE", HARD_BRAKE_MIN_DURATION_S),
            ("BIG_CORNER", BIG_CORNER_MIN_DURATION_S),
            ("HIGH_G", HIGH_G_MIN_DURATION_S),
        ]:
            end_active(event_type, last_row, min_dur)

    events.sort(key=lambda e: e["start_ts"])
    return events


def print_report(
    target_date: date,
    rows: list[dict],
    events: list[dict],
    offsets: tuple[float, float, float],
) -> None:
    ox, oy, oz = offsets
    print(f"\nIMU Replay — {target_date.isoformat()}")
    print(f"  {len(rows)} readings  |  sample rate: 1 Hz (low-rate path)")
    print(f"  NOTE: live detector uses 100 Hz — brief events may not appear here")
    if ox != 0.0 or oy != 0.0 or oz != 0.0:
        print(f"  Calibration offsets applied: ax{ox:+.4f}  ay{oy:+.4f}  az{oz:+.4f}")
    else:
        print(f"  No calibration offsets — using raw DB values")
    print()

    if not rows:
        print("  No IMU data for this date.")
        return

    # Summary stats
    ax_vals = [r["ax"] for r in rows]
    ay_vals = [r["ay"] for r in rows]
    az_vals = [r["az"] for r in rows]
    print(f"  ax: min={min(ax_vals):+.3f}g  max={max(ax_vals):+.3f}g")
    print(f"  ay: min={min(ay_vals):+.3f}g  max={max(ay_vals):+.3f}g")
    print(f"  az: min={min(az_vals):+.3f}g  max={max(az_vals):+.3f}g")
    print()

    if not events:
        print("  No events detected above thresholds.")
        return

    print(f"  {len(events)} event(s) detected:\n")

    type_label = {
        "HARD_BRAKE":  "HARD_BRAKE  ",
        "BIG_CORNER":  "BIG_CORNER  ",
        "HIGH_G":      "HIGH_G      ",
        "ROUGH_ROAD":  "ROUGH_ROAD  ",
    }
    type_detail = {
        "HARD_BRAKE":  lambda e: f"ax={e['peak_ax']:+.3f}g",
        "BIG_CORNER":  lambda e: f"ay={e['peak_ay']:+.3f}g",
        "HIGH_G":      lambda e: f"peak={e['peak_value']:.3f}g  ax={e['peak_ax']:+.3f}  ay={e['peak_ay']:+.3f}",
        "ROUGH_ROAD":  lambda e: f"stddev={e['peak_value']:.3f}g",
    }

    for ev in events:
        label = type_label.get(ev["type"], ev["type"])
        detail = type_detail.get(ev["type"], lambda e: "")(ev)
        start = ev["start_ts"] if isinstance(ev["start_ts"], str) else datetime.fromtimestamp(ev["start_ts"], tz=timezone.utc).isoformat()
        dur = f"{ev['duration_s']:.1f}s" if ev["duration_s"] else "?"
        print(f"  {label}  {start[11:19]}  dur={dur:>6}  {detail}")

    print()

    # Threshold reminder
    print("  Thresholds used:")
    print(f"    HARD_BRAKE : ax < {HARD_BRAKE_THRESHOLD_G:+.2f}g  for ≥{HARD_BRAKE_MIN_DURATION_S*1000:.0f}ms")
    print(f"    BIG_CORNER : |ay| > {BIG_CORNER_THRESHOLD_G:.2f}g  for ≥{BIG_CORNER_MIN_DURATION_S*1000:.0f}ms")
    print(f"    HIGH_G     : √(ax²+ay²) > {HIGH_G_THRESHOLD:.2f}g  for ≥{HIGH_G_MIN_DURATION_S*1000:.0f}ms")
    print(f"    ROUGH_ROAD : stddev(az,1s) > {ROUGH_ROAD_STDDEV_THRESHOLD:.2f}g")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay IMU data and check for missed events")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"Path to SQLite DB (default: {DEFAULT_DB})")
    parser.add_argument("--date", default=date.today().isoformat(), help="Date to analyse (YYYY-MM-DD, default: today)")
    parser.add_argument("--no-offsets", action="store_true", help="Skip calibration offsets, use raw DB values")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        print("Run on the Pi, or copy the DB with:", file=sys.stderr)
        print(f"  rsync laser:{db_path} /tmp/telemetry.db && python scripts/replay_events.py --db /tmp/telemetry.db", file=sys.stderr)
        sys.exit(1)

    try:
        target_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}  (use YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)

    offsets = (0.0, 0.0, 0.0) if args.no_offsets else load_offsets()

    conn = sqlite3.connect(str(db_path))
    try:
        rows = query_imu_today(conn, target_date)
        calibrated_rows = apply_offsets(rows, *offsets)
        events = detect_events(calibrated_rows)
        print_report(target_date, rows, events, offsets)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
