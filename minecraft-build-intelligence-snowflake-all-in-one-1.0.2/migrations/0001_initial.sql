-- PostgreSQL 15+ baseline. SQLAlchemy models remain the executable source of truth.
CREATE TABLE IF NOT EXISTS jobs (
  id varchar(64) PRIMARY KEY, type varchar(40) NOT NULL, status varchar(30) NOT NULL,
  stage varchar(80) NOT NULL, progress double precision NOT NULL, message text NOT NULL,
  payload jsonb NOT NULL, result jsonb, error jsonb, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS builds (
  id varchar(64) PRIMARY KEY, source_filename varchar(512) NOT NULL,
  source_hash varchar(64) NOT NULL UNIQUE, active_version_id varchar(64) NOT NULL,
  summary jsonb NOT NULL, storage_key varchar(1024) NOT NULL, created_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS build_versions (
  id varchar(64) PRIMARY KEY, build_id varchar(64) NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
  parent_version_id varchar(64), patch_id varchar(64), manifest_key varchar(1024) NOT NULL,
  content_hash varchar(64) NOT NULL, created_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_build_versions_build_id ON build_versions(build_id);
CREATE INDEX IF NOT EXISTS ix_build_versions_content_hash ON build_versions(content_hash);
CREATE TABLE IF NOT EXISTS chunk_blobs (
  hash varchar(64) PRIMARY KEY, compression varchar(20) NOT NULL, encoding varchar(20) NOT NULL,
  size_bytes bigint NOT NULL, storage_key varchar(1024) NOT NULL
);
CREATE TABLE IF NOT EXISTS patches (
  id varchar(64) PRIMARY KEY, build_id varchar(64) NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
  parent_version_id varchar(64) NOT NULL, new_version_id varchar(64), status varchar(30) NOT NULL,
  author varchar(255) NOT NULL, reason text NOT NULL, operations jsonb NOT NULL, validation jsonb NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_patches_build_id ON patches(build_id);
