"""Tests for legacy database-file migration (apex/database/connection.py).

DEFAULT_DB_PATH's filename changed (teamarr.db -> apex.db) as part of the
project's renames. Without _migrate_legacy_db_file, init_db() would silently
create a brand-new empty database at the new path on every existing install,
while the real data sat untouched alongside it under the old name — this
happened for real on a live instance before the fix.
"""

from apex.database.connection import _migrate_legacy_db_file


def test_migrates_legacy_teamarr_db(tmp_path):
    target = tmp_path / "apex.db"
    legacy = tmp_path / "teamarr.db"
    legacy.write_bytes(b"real data")

    _migrate_legacy_db_file(target)

    assert target.read_bytes() == b"real data"
    assert not legacy.exists()


def test_migrates_legacy_vroomarr_db(tmp_path):
    target = tmp_path / "apex.db"
    legacy = tmp_path / "vroomarr.db"
    legacy.write_bytes(b"real data")

    _migrate_legacy_db_file(target)

    assert target.read_bytes() == b"real data"
    assert not legacy.exists()


def test_moves_wal_and_shm_sidecars(tmp_path):
    target = tmp_path / "apex.db"
    legacy = tmp_path / "teamarr.db"
    legacy.write_bytes(b"real data")
    (tmp_path / "teamarr.db-wal").write_bytes(b"wal")
    (tmp_path / "teamarr.db-shm").write_bytes(b"shm")

    _migrate_legacy_db_file(target)

    assert (tmp_path / "apex.db-wal").read_bytes() == b"wal"
    assert (tmp_path / "apex.db-shm").read_bytes() == b"shm"
    assert not (tmp_path / "teamarr.db-wal").exists()
    assert not (tmp_path / "teamarr.db-shm").exists()


def test_noop_when_target_already_exists(tmp_path):
    target = tmp_path / "apex.db"
    target.write_bytes(b"current data")
    legacy = tmp_path / "teamarr.db"
    legacy.write_bytes(b"stale data")

    _migrate_legacy_db_file(target)

    # A real current database must never be clobbered by a stale legacy one.
    assert target.read_bytes() == b"current data"
    assert legacy.read_bytes() == b"stale data"


def test_noop_when_neither_file_exists(tmp_path):
    target = tmp_path / "apex.db"

    _migrate_legacy_db_file(target)

    assert not target.exists()
