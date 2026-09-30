"""Unit tests for database repository contracts and connection handling."""

from unittest.mock import MagicMock
import pytest
import psycopg.errors

from app.core.config import Settings
from app.database.connection import DatabaseManager
from app.database.repository import (
    DuplicateShortCodeError,
    PostgresURLRepository,
    get_repository,
)


def test_get_repository_raises_runtime_error_when_db_missing_in_production(monkeypatch):
    """Verify get_repository() raises RuntimeError when DATABASE_URL is missing in non-test runtime."""
    monkeypatch.setattr(
        "app.database.repository.get_settings",
        lambda: Settings(app_env="production", database_url=None),
    )
    monkeypatch.setattr("app.database.repository.get_db_pool", lambda: None)

    with pytest.raises(RuntimeError, match="PostgreSQL is required for application runtime"):
        get_repository()


def test_get_repository_raises_runtime_error_when_db_missing_in_development(monkeypatch):
    """Verify get_repository() raises RuntimeError when DATABASE_URL is missing in development."""
    monkeypatch.setattr(
        "app.database.repository.get_settings",
        lambda: Settings(app_env="development", database_url=None),
    )
    monkeypatch.setattr("app.database.repository.get_db_pool", lambda: None)

    with pytest.raises(RuntimeError, match="PostgreSQL is required for application runtime"):
        get_repository()


def test_postgres_repository_maps_unique_violation_to_domain_error():
    """Verify PostgresURLRepository maps psycopg UniqueViolation to DuplicateShortCodeError."""
    mock_pool = MagicMock()
    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    # Simulate psycopg UniqueViolation exception on execute
    mock_pool.connection.return_value.__enter__.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    mock_cursor.execute.side_effect = psycopg.errors.UniqueViolation("duplicate key value violates unique constraint")

    repo = PostgresURLRepository(pool=mock_pool)

    with pytest.raises(DuplicateShortCodeError, match="already exists in database"):
        repo.create_url(short_code="COLLIDE", original_url="https://example.com")


def test_database_manager_health_check_returns_false_when_uninitialized():
    """Verify DatabaseManager.check_health() returns False cleanly without crashing when pool is None."""
    DatabaseManager.close_pool()
    assert DatabaseManager.check_health() is False


def test_database_pool_disables_prepared_statements(monkeypatch):
    """Verify DatabaseManager.initialize_pool passes prepare_threshold=None for transaction poolers."""
    DatabaseManager.close_pool()

    captured_kwargs = {}

    class MockPool:
        def __init__(self, conninfo, **kwargs):
            self.conninfo = conninfo
            self.kwargs = kwargs
            self.closed = False
            captured_kwargs.update(kwargs)

    monkeypatch.setattr("app.database.connection.ConnectionPool", MockPool)

    pool = DatabaseManager.initialize_pool("postgresql://postgres:pass@localhost:5432/postgres")
    assert pool is not None
    assert "kwargs" in captured_kwargs
    assert captured_kwargs["kwargs"] == {"prepare_threshold": None}

    DatabaseManager.close_pool()

