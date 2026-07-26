from __future__ import annotations

from sqlalchemy import inspect

from mbi_api.database import create_database_engine, migrate, session_factory, transaction
from mbi_api.models import JobRecord


def test_sqlite_migration_and_transaction(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'mbi.db'}")
    migrate(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"jobs", "builds", "build_versions", "chunk_blobs", "patches"} <= tables
    factory = session_factory(engine)
    with transaction(factory) as session:
        session.add(JobRecord(id="job_test", type="import"))
    with transaction(factory) as session:
        assert session.get(JobRecord, "job_test") is not None
    engine.dispose()
