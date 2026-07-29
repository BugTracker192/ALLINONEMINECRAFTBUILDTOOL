# Verification record — Offline Snowflake/CoCo profile

Run the complete release matrix:

```bash
python scripts/verify_snowflake_release.py \
  --resource-pack /path/to/minecraft-or-resource-pack.zip \
  --output ./verification
```

The verifier records commands, return codes, durations, logs, representative evidence and machine-readable reports.

## Current release gates

- Version 1.2.0 full suite: `pytest -q` -> **129 passed, zero skipped** on
  Python 3.12.13/Windows. A direct run completed in 303.89 seconds and the
  independent release-verifier run completed in 277.04 seconds.
- Current production-interior branch full suite: `pytest -q` → **81 passed, zero skipped** on Python 3.12.13/Windows.
- Focused static gates: Ruff passes for the new interior/classification modules; strict mypy passes for those modules.
- Interior gates include exact component membership, architectural classification, deterministic voxel rays, collision/visibility camera diagnostics, semantic frame metrics, protected cutaways, room-bounded slice hashes, exact packet layout, and CLI contract parsing.
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

## Large-schematic 1.2.0 release gate

The uninterrupted 1.2.0 verifier passed every local gate:

- 129 tests with zero failures/skips;
- offline Python 3.12 grammar/import-closure and source-security audits;
- textured Snowflake E2E, multimodal loop/HTTP, and AI construction from
  blank;
- CPU model coverage and 5,000 malformed-input mutations;
- flat/textured benchmarks and two 195-artifact byte-identical pipeline trees;
- isolated `minecraft_build_intelligence-1.2.0-py3-none-any.whl` execution with
  exact export/re-import verification;
- 8,092 indexed resource assets and zero audit failures.

The generated scale matrix includes 16,777,216 chunk-array voxels,
4,194,304 streamed Litematic states, 50,000 nested-NBT block entities and a
2,097,152-block exact tiled/resume render. The latter passed PNG byte identity
and equality for all eight semantic maps in 231.05 seconds. A live process
sample after the cache correction observed roughly 78 MB working set and
449 MiB private allocation, versus the rejected pre-correction coordinate
cache run that exceeded 2.7 GB working set.

The dependency mirror supplied no NumPy/Pillow distributions during the clean
wheel check, so the verifier recorded
`tested-runtime-mounted-after-index-unavailable`; the isolated 1.2.0 wheel
pipeline itself passed. The exact `Tree_of_dreams.schem` was absent, so its
named gate remains explicitly unexecuted.

## Installation hardening found by the final audit

The original build-system declaration required downloading `setuptools>=75`, which failed in the constrained package mirror. The repository now uses `build_backend.py`, a deterministic standard-library PEP 517 backend with an empty build requirement list. Consequently, project wheel construction itself requires no network-fetched build backend.

## Exact Python 3.12 boundary

The production-interior release matrix executed on Python 3.12.13. The clean wheel was installed and executed from an isolated virtual environment outside the source tree. The dependency index was unavailable during that step, so the verifier mounted the already-tested local runtime dependencies and records that qualification in its machine-readable report. Hosted Linux/Python 3.12 CI remains the independent clean-install gate.

No paid provider credentials or Minecraft client executable were available. Provider wire formats were exercised against local HTTP/SSE servers and exports were verified through exact normal re-import. Those facts are stated rather than replaced with unsupported universal claims.


## Private all-in-one 1.0.3 update

The exact user-supplied Minecraft asset archive is embedded inside the installable package and auto-selected without configuration. `BOOTSTRAP_SNOWFLAKE.py --smoke` verifies installation, asset integrity, Tier 2 textured rendering, and the reference pipeline. The current suite passes 82/82 tests, and the installed-wheel pipeline passes exact export/re-import verification.

## Production interior-vision release gate

The uninterrupted release verifier at `work/verification-p2/full-release-3/release-verification.json` passed every local gate on Python 3.12.13:

- 81 tests, zero failures or skips.
- Offline import-closure and source-security audits.
- Flat and textured end-to-end pipelines.
- Literal multimodal protocol loops and blank-document AI construction.
- CPU block-model coverage and 5,000 malformed-input mutations with zero unexpected failures.
- Flat and textured benchmarks.
- Two byte-identical pipeline trees containing 195 artifacts.
- Isolated installed-wheel pipeline and exact export/re-import verification.
- Resource-pack index of 8,092 assets with zero audit failures.

The built wheel is `minecraft_build_intelligence-1.0.3-py3-none-any.whl`, 408,248,329 bytes, SHA-256 `86c84e11fea4c535fa6a1390808d2dfb7a9c9befd313caa9293fe4ef27dde2a3`.

The Japan lobby benchmark source page was identified, but the static `.schem` download is blocked by the current browser/CDN environment; no benchmark file is committed or redistributed. A deterministic synthetic regression reproduces the same external-feature/terrain-obstruction mechanism and is covered by exact membership, line-of-sight, dominant-surface, retry, cutaway, and slice tests. The legally acquired Japan benchmark remains an explicit unexecuted gate rather than being represented as locally tested.
