"""Tests for the BME680 air-quality score (schema v13).

Covers the pure scoring function, the v12->v13 migration mechanics, the full
store/read round-trip through both insert paths, and the Prometheus emit.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

from shitbox.collectors.environment import compute_air_quality_score
from shitbox.storage.database import SCHEMA_VERSION, Database
from shitbox.storage.models import Reading, SensorType
from shitbox.sync.batch_sync import BatchSyncService


def _ts() -> datetime:
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


# --- scoring function -------------------------------------------------------

def test_score_clean_air_near_100() -> None:
    """Gas at baseline and ideal 40% humidity scores at the top of the range."""
    score = compute_air_quality_score(gas_ohms=50000, humidity_pct=40.0, gas_baseline_ohms=50000)
    assert 99.0 <= score <= 100.0


def test_score_drops_when_gas_below_baseline() -> None:
    """Resistance well below baseline (VOCs present) tanks the gas component."""
    clean = compute_air_quality_score(50000, 40.0, 50000)
    dirty = compute_air_quality_score(10000, 40.0, 50000)
    assert dirty < clean
    # gas at 20% of baseline -> gas component ~15/75, humidity full 25 -> ~40
    assert 35.0 <= dirty <= 45.0


def test_score_humidity_penalty() -> None:
    """Straying from 40% humidity costs marks even with clean gas."""
    ideal = compute_air_quality_score(50000, 40.0, 50000)
    humid = compute_air_quality_score(50000, 90.0, 50000)
    assert humid < ideal


def test_score_gas_above_baseline_caps() -> None:
    """Cleaner-than-baseline air doesn't score above the gas weighting."""
    score = compute_air_quality_score(80000, 40.0, 50000)
    assert 99.0 <= score <= 100.0


def test_score_zero_baseline_safe() -> None:
    """A zero/unset baseline must not divide by zero."""
    score = compute_air_quality_score(50000, 40.0, 0.0)
    assert 99.0 <= score <= 100.0


# --- migration --------------------------------------------------------------

def test_v13_migration_adds_column(tmp_path) -> None:
    """An existing v12 database gains air_quality_score and lands at v13.

    Builds a faithful v12 DB from the real current schema, then strips the v13
    column and resets the version — so connect() re-runs _migrate_to_v13 against
    a fully-shaped readings table that genuinely lacks the column.
    """
    db_path = tmp_path / "v12.db"
    db = Database(db_path)
    db.connect()
    db.close()

    raw = sqlite3.connect(str(db_path))
    raw.execute("ALTER TABLE readings DROP COLUMN air_quality_score")
    raw.execute("DELETE FROM schema_version")
    raw.execute("INSERT INTO schema_version (version) VALUES (12)")
    raw.commit()
    pre_cols = [r[1] for r in raw.execute("PRAGMA table_info(readings)").fetchall()]
    raw.close()
    assert "air_quality_score" not in pre_cols  # precondition: genuinely v12-shaped

    db = Database(db_path)
    db.connect()
    try:
        conn = db._get_connection()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(readings)").fetchall()]
        assert "air_quality_score" in cols
        version = conn.execute(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ).fetchone()[0]
        assert version == SCHEMA_VERSION == 13
    finally:
        db.close()


def test_v13_migration_idempotent_on_fresh_db(tmp_path) -> None:
    """A fresh database already has the column and is at v13 — no migration run."""
    db = Database(tmp_path / "fresh.db")
    db.connect()
    try:
        conn = db._get_connection()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(readings)").fetchall()]
        assert "air_quality_score" in cols
    finally:
        db.close()


# --- store/read round-trip (both insert paths) ------------------------------

def _env_reading(score: float) -> Reading:
    return Reading(
        sensor_type=SensorType.ENVIRONMENT,
        timestamp_utc=_ts(),
        pressure_hpa=1013.0,
        humidity_pct=40.0,
        env_temp_celsius=22.0,
        gas_resistance_ohms=50000.0,
        air_quality_score=score,
    )


def test_round_trip_single_insert(tmp_path) -> None:
    db = Database(tmp_path / "single.db")
    db.connect()
    try:
        db.insert_reading(_env_reading(87.5))
        rows = db.get_unsynced_readings("prometheus", batch_size=10)
        assert any(r.air_quality_score == 87.5 for r in rows)
    finally:
        db.close()


def test_round_trip_batch_insert(tmp_path) -> None:
    db = Database(tmp_path / "batch.db")
    db.connect()
    try:
        db.insert_readings_batch([_env_reading(73.2)])
        rows = db.get_unsynced_readings("prometheus", batch_size=10)
        assert any(r.air_quality_score == 73.2 for r in rows)
    finally:
        db.close()


# --- Prometheus emit --------------------------------------------------------

def _make_service() -> BatchSyncService:
    config = MagicMock()
    config.remote_write_url = "http://localhost:9090/api/v1/write"
    config.batch_size = 100
    config.batch_interval_seconds = 15
    return BatchSyncService(
        config=config, database=MagicMock(), connection_monitor=MagicMock()
    )


def test_air_quality_metric_emitted() -> None:
    svc = _make_service()
    metrics = svc._readings_to_metrics([_env_reading(64.0)])
    aq = [m for m in metrics if m[0] == "shitbox_air_quality"]
    assert len(aq) == 1
    assert aq[0][2] == 64.0


def test_air_quality_none_produces_no_metric() -> None:
    svc = _make_service()
    reading = _env_reading(64.0)
    reading.air_quality_score = None
    metrics = svc._readings_to_metrics([reading])
    assert not any(m[0] == "shitbox_air_quality" for m in metrics)
