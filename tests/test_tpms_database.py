"""Integration tests for tpms_readings table + Prometheus cursor.

SPEC-4 (SQLite persistence), SPEC-5 (Prometheus exposition cursor).
Wave 0 stubs — bodies activate when Plan 28-02 lands schema v11.
"""
from __future__ import annotations

import pytest

from shitbox.storage.database import SCHEMA_VERSION, Database


def test_migrate_v11(db):
    """SPEC-4: connecting bumps SCHEMA_VERSION to 11 and creates tpms_readings."""
    if SCHEMA_VERSION < 11:
        pytest.skip(
            f"Plan 28-02 — SCHEMA_VERSION still {SCHEMA_VERSION}; "
            "bump to 11 lands with the migration"
        )
    conn = db._get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tpms_readings'"
    ).fetchone()
    assert row is not None, "tpms_readings table missing after connect()"


def test_insert_retrieve(db):
    """SPEC-4: insert_tpms_reading persists every parsed frame; one row per frame."""
    if not hasattr(db, "insert_tpms_reading"):
        pytest.skip("Plan 28-02 — Database.insert_tpms_reading not yet implemented")
    row_id = db.insert_tpms_reading(
        timestamp_utc="2026-04-28T12:34:56Z",
        sensor_id="550b57d9",
        wheel="front-driver",
        pressure_psi=31.1,
        temperature_c=22.5,
        status=19,
        raw_pressure_kpa=87.6,
    )
    assert row_id > 0
    conn = db._get_connection()
    row = conn.execute(
        "SELECT * FROM tpms_readings WHERE id = ?", (row_id,)
    ).fetchone()
    assert row["wheel"] == "front-driver"
    assert row["pressure_psi"] == pytest.approx(31.1, abs=0.01)


def test_prometheus_metric_shape():
    """SPEC-5: Prometheus metric tuple uses shitbox_tpms_pressure_psi + wheel label."""
    if not hasattr(Database, "insert_tpms_reading"):
        pytest.skip("Plan 28-02 — TPMS persistence not yet implemented")
    # Real assertion lands when Plan 28-05 wires the batch_sync TPMS branch.
    pytest.skip("Plan 28-05 — batch_sync TPMS metric encoder not yet implemented")


def test_cursor_advance(db):
    """SPEC-5: prometheus_tpms cursor advances on each batch."""
    if not hasattr(db, "get_unsynced_tpms_readings"):
        pytest.skip("Plan 28-02 — Database.get_unsynced_tpms_readings not yet implemented")
    db.insert_tpms_reading(
        timestamp_utc="2026-04-28T12:34:56Z",
        sensor_id="550b57d9",
        wheel="front-driver",
        pressure_psi=31.1,
        temperature_c=22.5,
        status=19,
        raw_pressure_kpa=87.6,
    )
    rows_before = db.get_unsynced_tpms_readings(batch_size=10)
    assert len(rows_before) == 1
    db.update_sync_cursor("prometheus_tpms", rows_before[-1]["id"])
    rows_after = db.get_unsynced_tpms_readings(batch_size=10)
    assert rows_after == []
