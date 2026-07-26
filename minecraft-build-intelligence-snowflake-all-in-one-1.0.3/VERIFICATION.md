# Verification record — Offline Snowflake/CoCo profile

Run the complete release matrix:

```bash
python scripts/verify_snowflake_release.py \
  --resource-pack /path/to/minecraft-or-resource-pack.zip \
  --output ./verification
```

The verifier records commands, return codes, durations, logs, representative evidence and machine-readable reports.

## Current release gates

- `pytest -q`: **80 passed, zero skipped**.
- Python 3.12 grammar and mandatory import-closure audit.
- Source-security scan for secrets, unsafe deserialization, shell execution and mandatory dependency leakage.
- Complete flat and textured Snowflake E2E pipelines.
- Exact coordinate, chunk, block-entity and pixel-hit queries.
- Pure CPU Tier-2 block-model rendering.
- Patch validation, preview, commit, rejection and rollback.
- Literal PNG + exact-tool multimodal loops across all three provider protocols.
- AI construction from an all-air document followed by visual critique and exact export.
- 5,000 malformed format mutations.
- Flat/textured CPU benchmarks.
- Two complete byte-identical pipeline trees.
- Built-wheel execution outside the source tree.
- Full resource-pack index and model-parent audit.
- Exact Sponge and Litematic export/re-import comparisons.

## Installation hardening found by the final audit

The original build-system declaration required downloading `setuptools>=75`, which failed in the constrained package mirror. The repository now uses `build_backend.py`, a deterministic standard-library PEP 517 backend with an empty build requirement list. Consequently, project wheel construction itself requires no network-fetched build backend.

## Exact Python 3.12 boundary

The current container exposes Python 3.13.5 but no Python 3.12 executable. Outbound runtime download was unavailable. All mandatory files parse under Python 3.12 grammar and CI declares an exact Python 3.12 clean-install/pipeline/test job, but this local report does not mislabel 3.13 execution as the exact 3.12 gate.

The package mirror also exposed no downloadable NumPy/Pillow distributions during the clean-environment attempt. The clean wheel was therefore installed exactly and executed in a fresh venv with the already-tested binary dependencies made available locally. This proves project packaging and isolated execution, while the live dependency-download portion remains an external environment check.

No paid provider credentials or Minecraft client executable were available. Provider wire formats were exercised against local HTTP/SSE servers and exports were verified through exact normal re-import. Those facts are stated rather than replaced with unsupported universal claims.


## Private all-in-one 1.0.3 update

The exact user-supplied Minecraft asset archive is embedded inside the installable package and auto-selected without configuration. `BOOTSTRAP_SNOWFLAKE.py --smoke` verifies installation, asset integrity, Tier 2 textured rendering, and the reference pipeline. The current suite passes 82/82 tests, and the installed-wheel pipeline passes exact export/re-import verification.
