# Mandatory Snowflake / CoCo Sandbox Profile

## Runtime boundary

The mandatory profile is a single installable Python process. Its dependency graph is:

```text
CLI / Python API
  ├── format detection + bounded NBT reader
  ├── canonical document + content-addressed chunks
  ├── local analyses
  ├── NumPy/Pillow CPU renderer
  ├── semantic-map encoder
  ├── transactional patch/version engine
  ├── deterministic exporters + verifier
  └── optional multimodal provider adapters
```

Core execution uses no Node.js, browser, GL context, GPU, Docker, database, queue, remote object store or external executable.

## Job state

```text
pending → running → succeeded
                  ↘ failed
                  ↘ cancelled
```

Jobs are synchronous but persisted as deterministic records so a future queue adapter can reuse the domain model.

## Patch state

```text
draft → validated → previewed → committed → rolled_back
                  ↘ rejected
                  ↘ superseded
```

A committed version is immutable. Rollback selects an exact immutable parent rather than recomputing procedural inverses.

## AI workflow

```text
perceive PNG + semantic maps + summary
  → query exact coordinates
  → analyze rooms/components/navigation/facades
  → propose bounded patch with evidence references
  → validate
  → render before/after preview
  → approve/commit
  → render changed crop
  → visually critique
  → repeat
  → export and exact re-import verification
```

## Artifact recovery

Every run is self-describing. Copying the `run/` directory to another machine preserves canonical data, chunks, versions, evidence, patches and exports without an external service.
