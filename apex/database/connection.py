"""Database connection management.

Simple SQLite connection handling with schema initialization.
"""

import logging
import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from apex.database.migrations import _run_migrations, run_pre_migrations

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "apex.db"

# Schema file location
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Database filenames from before the project's renames (teamarr -> vroomarr ->
# apex). Checked once at startup (see _migrate_legacy_db_file) so an existing
# install's real data isn't silently orphaned by init_db() creating a fresh
# empty database at the new default path.
_LEGACY_DB_NAMES = ("teamarr.db", "vroomarr.db")


def _migrate_legacy_db_file(path: Path) -> None:
    """Rename a pre-rebrand database file to the current default path.

    One-time migration: if nothing exists yet at `path` but a legacy-named
    database sits alongside it, rename it (plus WAL/SHM sidecars) into place.
    Without this, upgrading to a build with a renamed DEFAULT_DB_PATH would
    silently start every existing install with a brand-new empty database.
    """
    if path.exists():
        return
    for legacy_name in _LEGACY_DB_NAMES:
        legacy_path = path.parent / legacy_name
        if not legacy_path.exists():
            continue
        logger.warning(
            "[MIGRATE] Found pre-rebrand database '%s'; renaming to '%s'",
            legacy_path,
            path,
        )
        legacy_path.rename(path)
        for suffix in ("-wal", "-shm"):
            sidecar = legacy_path.with_name(legacy_path.name + suffix)
            if sidecar.exists():
                sidecar.rename(path.with_name(path.name + suffix))
        return


def resolve_db_path(db_path: Path | str | None) -> Path:
    """Explicit argument > DATABASE_PATH env var > repo default.

    Read at call time (not import time) so tests can redirect the database
    with monkeypatch.setenv before touching any connection helper.
    """
    if db_path:
        return Path(db_path)
    env_path = os.environ.get("DATABASE_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get a database connection.

    Args:
        db_path: Path to database file. Uses DATABASE_PATH env var or
            DEFAULT_DB_PATH if not specified.

    Returns:
        SQLite connection with row factory set to sqlite3.Row
    """
    path = resolve_db_path(db_path)

    # timeout=30: Wait up to 30 seconds if database is locked by another connection
    # check_same_thread=False: Allow connection to be used across threads (required for FastAPI)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Enable Write-Ahead Logging for better concurrent access
    # WAL allows readers to not block writers and vice versa
    conn.execute("PRAGMA journal_mode=WAL")

    # Wait up to 30 seconds if a table is locked (milliseconds)
    conn.execute("PRAGMA busy_timeout=30000")

    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


@contextmanager
def get_db(db_path: Path | str | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections.

    Usage:
        with get_db() as conn:
            cursor = conn.execute("SELECT * FROM teams")
            teams = cursor.fetchall()
    """
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | str | None = None) -> None:
    """Initialize database with schema.

    Creates tables if they don't exist. Safe to call multiple times.
    Also seeds TSDB cache from distributed seed file if needed.

    Args:
        db_path: Path to database file. Uses DEFAULT_DB_PATH if not specified.

    Raises:
        RuntimeError: If database file exists but is not a valid V2 database
    """
    path = resolve_db_path(db_path)
    _migrate_legacy_db_file(path)
    schema_sql = SCHEMA_PATH.read_text()

    try:
        with get_db(db_path) as conn:
            # First, verify this is a valid V2-compatible database by checking integrity
            # and querying a core table. This catches both corruption AND V1 databases.
            _verify_database_integrity(conn, path)

            # Structural pre-migrations (renames, table rebuilds) — these
            # can't be handled by reconciliation; see database/migrations/pre.py
            run_pre_migrations(conn)

            # ================================================================
            # Schema reconciliation — ensures ALL columns match schema.sql.
            # Replaces all individual _add_*_column_if_needed functions.
            # Adding a new column is now: just add it to schema.sql.
            # ================================================================
            from apex.database.reconciliation import reconcile_schema

            result = reconcile_schema(conn, schema_sql)
            if result.columns_added > 0:
                logger.info(
                    "[RECONCILE] Added %d missing columns across %d tables",
                    result.columns_added,
                    len(result.columns_by_table),
                )
            if result.errors:
                for err in result.errors:
                    logger.warning("[RECONCILE] %s", err)

            # Apply schema (creates tables if missing, INSERT OR REPLACE updates seed data)
            conn.executescript(schema_sql)
            # Run data migrations for existing databases
            _run_migrations(conn)
            # Seed TSDB cache if empty or incomplete
            _seed_tsdb_cache_if_needed(conn)

            # Final verification: ensure settings table exists and is queryable
            conn.execute("SELECT id FROM settings LIMIT 1")
    except sqlite3.DatabaseError as e:
        if "file is not a database" in str(e):
            logger.error(
                f"Database file '{path}' exists but is not compatible with Apex V2. "
                "This usually means you're trying to use a V1 database. "
                "V2 requires a fresh database - please either:\n"
                "  1. Use a different data directory for V2, or\n"
                "  2. Backup and delete the existing database file"
            )
            raise RuntimeError(
                f"Incompatible database file at '{path}'. "
                "V2 is not compatible with V1 databases. "
                "Please use a fresh data directory or delete the existing database."
            ) from e
        raise


def _verify_database_integrity(conn: sqlite3.Connection, path: Path) -> None:
    """Verify database is valid and compatible with V2.

    Catches:
    1. Corrupt database files ("file is not a database")
    2. V1 databases — V1 is no longer supported. The presence of V1-specific
       tables raises immediately with instructions to delete or relocate.

    Raises:
        RuntimeError: If database is a V1 database
        sqlite3.DatabaseError: If database file is corrupt
    """
    try:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 100")
        existing_tables = {row["name"] for row in cursor.fetchall()}
    except sqlite3.DatabaseError:
        raise

    v1_indicators = {
        "schedule_cache",
        "league_config",
        "h2h_cache",
        "error_log",
        "soccer_cache_meta",
        "team_stats_cache",
    }
    v1_tables_found = v1_indicators & existing_tables

    if v1_tables_found:
        raise RuntimeError(
            f"Database file '{path}' is a V1 (Apex 1.x) database "
            f"(found V1-specific tables: {sorted(v1_tables_found)}). "
            "V1 is no longer supported. Move or delete the database file and "
            "restart Apex to initialize a fresh V2 database."
        )


def _seed_tsdb_cache_if_needed(conn: sqlite3.Connection) -> None:
    """Seed TSDB cache from distributed seed file if needed."""
    from apex.database.seed import seed_if_needed

    result = seed_if_needed(conn)
    if result and result.get("seeded"):
        logger.info(
            f"Seeded TSDB cache: {result.get('teams_added', 0)} teams, "
            f"{result.get('leagues_added', 0)} leagues"
        )




def reset_db(db_path: Path | str | None = None) -> None:
    """Reset database - drops all tables and reinitializes.

    WARNING: This deletes all data!

    Args:
        db_path: Path to database file. Uses DATABASE_PATH env var or
            DEFAULT_DB_PATH if not specified.
    """
    path = resolve_db_path(db_path)

    if path.exists():
        path.unlink()

    init_db(path)
