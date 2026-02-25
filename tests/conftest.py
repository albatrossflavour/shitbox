"""Shared pytest fixtures for shitbox tests."""

import pytest

from shitbox.events.storage import EventStorage
from shitbox.storage.database import Database


@pytest.fixture
def tmp_db_path(tmp_path):
    """Return a Path to a temporary SQLite file."""
    return tmp_path / "test.db"


@pytest.fixture
def db(tmp_db_path):
    """Create a connected Database instance, yield it, then close."""
    database = Database(tmp_db_path)
    database.connect()
    yield database
    database.close()


@pytest.fixture
def event_storage_dir(tmp_path):
    """Return a Path for event JSON files."""
    return tmp_path / "events"


@pytest.fixture
def event_storage(event_storage_dir):
    """Create an EventStorage instance with a temporary base directory."""
    return EventStorage(base_dir=str(event_storage_dir))
