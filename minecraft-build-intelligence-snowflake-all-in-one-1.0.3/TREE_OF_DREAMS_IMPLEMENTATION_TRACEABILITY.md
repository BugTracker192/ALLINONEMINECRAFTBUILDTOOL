# Tree of Dreams whole-map implementation traceability

This document maps every requirement in `TREE_OF_DREAMS_FIX_PLAN.md` to the
1.2.0 implementation and its evidence. It distinguishes implementation
evidence from fixture evidence; absence of the named source schematic is never
converted into a passing claim.

## Status vocabulary and evidence boundary

- **Implemented and tested**: code exists and an automated local test exercises
  the behavior.
- **Implemented; named-fixture gate pending**: the path is implemented and
  covered by generated scale fixtures, but the exact
  `Tree_of_dreams.schem` file was not present in this checkout or Downloads.
- **Explicitly out of scope**: the plan required a scope decision rather than
  necessarily an implementation. The decision and typed failure are recorded.
- **Environment note**: operational advice from the report, not a product
  feature.

The supplied plan describes a 413 x 213 x 413 Sponge v2 schematic with
36,331,197 cells and 4,245,699 placed blocks. That file is not in the current
workspace. The checked-in regression matrix therefore uses deterministic
generated fixtures, including 16,777,216 placed voxels, 4,194,304 Litematic
states, 2,097,152-block exact tiled rendering, 50,000 rich block entities,
2,000 palette states, negative Y through modern height, terrain-only and
material-independent architectural subjects. The exact real-file command
sequence in section G remains a mandatory release gate when the file is
available.

## Executed local release evidence

- Full suite: 129 passed, zero failures/skips, Python 3.12.13.
- Dense exact scale render: 2,097,152 blocks; PNG byte-identical after
  checkpoint reconstruction; all eight semantic maps equal; 231.05 seconds.
- Renderer cache correction: live sampling fell from a rejected 2.7 GB
  working-set coordinate cache to roughly 78 MB working set/449 MiB private
  allocation on the same running gate.
- Complete release verifier: passed offline/import closure, source security,
  Snowflake E2E, multimodal provider loops, autonomous construction, CPU model
  coverage, 5,000 mutations, flat/textured benchmarks, 195-artifact
  determinism, isolated 1.2.0 wheel execution and the 8,092-entry asset audit.
- Release overlay: `1.2.0-tree-of-dreams-large-schematic`, self-check passed.

## A. Memory-streaming requirements

| ID | Status | Implementation and evidence |
|---|---|---|
| A1 | Implemented and tested | `mbi.formats.varint.iter_unsigned_varints` streams values and preserves excess, overflow, unterminated and final-length typed errors. The list API wraps the iterator for compatibility. Randomized equality and bounded-memory tests are in `services/core/tests/test_map_scale_streaming.py`. |
| A2 | Implemented and tested | Sponge decoding consumes the varint stream once, validates the first bad source palette ID in index order and writes directly to `ChunkedVoxelMap`; there is no decoded cell list or separate membership pass. |
| A3 | Implemented and tested | `BuildDocument.compute_content_hash` incrementally emits the exact legacy sorted/minified JSON byte sequence. A legacy materializing oracle proves hash identity. |
| A4 | Implemented and tested | Serialization supports deferred `blocks`/`regionBlocks` rows and accepts supplied streamed maps during reconstruction without changing the canonical schema. |
| A5 | Implemented and tested | `mbi.canonical_reader` scans canonical JSON with `mmap`, string/escape/depth awareness and streams block rows into chunk arrays. Negative integers, nested decoy keys, bounds filtering and hash validation are covered. |
| A6 | Implemented and tested | Project save streams canonical JSON, copies immutable versions byte-for-byte and loads through the streaming reader. Bounded loads retain integrity validation while returning only scoped voxels. |
| A7 | Implemented and tested | `atomic_write_json` uses `JSONEncoder.iterencode`, newline, flush/fsync and atomic replacement rather than building one giant byte string. |
| A8 | Implemented and tested | `export-map` streams CSV/JSONL to a temporary output and atomically replaces it. Component labels use dense relative `uint32` storage and queue arrays; repeated `min(unseen)` scans and per-voxel Python label dictionaries are gone. |
| A9 | Implemented and tested | The map-scale test module covers byte equality, content-hash identity, all typed stream errors, first invalid palette ID, canonical reader decoys/negative coordinates, tamper rejection, version copies and memory scaling. |

All five global invariants are retained: canonical bytes, content hashes, full
integrity checking, typed errors and deterministic iteration.

## B. Whole-map blockers

| ID | Status | Implementation and evidence |
|---|---|---|
| B1 | Implemented; named-fixture gate pending | `MBI_MAX_VISIBLE_BLOCKS` and `--max-visible-blocks` configure a per-tile emitted-geometry budget. Exact large scenes auto-enable 512-pixel tiling. Each tile builds and releases its own geometry; buried/culled blocks do not consume the visible budget. Total pixel-by-tile work has its own safety ceiling. Checkpoints and `--resume` are deterministic. |
| B2 | Implemented and tested | Block-map rows are produced one at a time. CSV and JSONL do not materialize the map; optional Parquet is explicitly dependency-backed. Component and classification lookup use bounded array/chunk structures. |
| B3 | Implemented and tested | Structure extraction resolves the durable structure bounds, loads only that scope and streams Sponge/Litematic export input. It does not clone the parent map into a Python dictionary. |
| B4 | Implemented and tested | `analyze --bounds`, `analyze --structure`, orthographic crop and perspective crop push the bounds into project loading. Scoped reports preserve the parent hash and scope metadata. |

## C. Architectural voxel model

| ID | Status | Implementation and evidence |
|---|---|---|
| C1 | Implemented and tested | `ChunkedVoxelMap` stores sparse 16-cubed chunks as `uint32` arrays with O(1) lookup/mutation and deterministic heap-merged iteration. `RegionOverlayVoxelMap` supplies a lazy flattened multi-region view. The 16,777,216-voxel fixture occupies 67,108,864 array bytes, over the declared five-million placed blocks/GiB target. |

Chunk arrays are now used by Sponge, Litematic, legacy import, canonical load,
scoping and analysis labels. Python objects remain only at API iteration
boundaries.

## D. Correctness defects

| ID | Status | Implementation and evidence |
|---|---|---|
| D1 | Implemented and tested | Structure inventory v2 derives local terrain surfaces, identifies above-terrain/cavity candidates, prevents terrain skins from bridging structures, and emits separate building, rock-formation and vegetation kinds. Window aggregation avoids a single map-wide adjacency collapse. |
| D2 | Implemented and tested | Flowers/plants are vegetation. Crafted material is only a candidate: verticality, enclosure, regularity, surface embedding and crafted-material ratio determine structure promotion. Thin backed ground skins remain terrain detail. Cobblestone castle, stone-brick bridge and mossy dungeon negative guards all classify as buildings. Thresholds and evidence are emitted; `--classification-config` overrides them per run. |
| D3 | Implemented and tested | Texture audit emits `fluid-rendered` only when the real renderer path and required still/flowing water or lava assets resolve. Waterlogged states report overlay support. Still/flowing water, lava and waterlogged geometry plus all five entity-rendered families are covered by a strict render fixture. |
| D4 | Implemented and tested | Export verification defaults on. `--no-verify` is the deliberate fast path and reports `passed: "skipped"` plus `verification: "skipped"` rather than null. Verification mismatch still raises exit 51. |
| D5 | Implemented and tested | Missing or capped lighting is `available: false`, `score: null`, and excluded from `available_weight`. A genuine evaluated zero remains distinguishable. |
| D6 | Implemented and tested | Exact tiled semantic layers are disk-backed and copied tile-by-tile; LOD semantic layers are disk-backed too. Full-resolution eight-layer arrays are not simultaneously held as Python objects. |
| D7 | Implemented and tested | Component, facade, navigation and structure scans use one deterministic sorted pass with membership skips, not `min()` once per component. |

## E. Documentation and packaging

| ID | Status | Implementation and evidence |
|---|---|---|
| E1 | Implemented | Appendix C of both autonomous manuals documents every 1.1/1.2 command extension and every patch operation with its accepted fields. |
| E2 | Implemented | Both manuals and this trace record the measured scale envelope, O(N) behavior, render modes and environment overrides. Default maximum volume is 100,000,000 cells and palette limit is 65,536, replacing misleading billion/million defaults. |
| E3 | Implemented | `MEDUSELD_IMPLEMENTATION_TRACEABILITY.md` and `IMPLEMENTATION_STATUS.md` now label 108,917 blocks/1,495 block entities as Meduseld-specific evidence and separate it from the generated large-map matrix and pending Tree gate. |
| E4 | Implemented and tested | Warm-cache source archives include `app/bundled_assets/parts/`. Bootstrap validates every required part before archive creation and fails loudly on an incomplete source payload. |

## F. Environment realities

F1-F7 are retained in the manuals as execution guidance: use streaming/chunk
arrays under low RAM, persist resumable checkpoints, avoid symlink-dependent
staging, mirror slow filesystems locally when permitted, clear hostile Python
path injection, verify the resolved workspace before writes and hash-check
cache artifacts after creation. These constraints do not weaken data integrity
or exactness requirements.

## G. Named Tree of Dreams acceptance gate

**Status: implemented; named-fixture execution pending because
`Tree_of_dreams.schem` is absent.**

When the untouched file is supplied, run all of the following without changing
the source:

```bash
python -m app.cli import Tree_of_dreams.schem --out ./tod
python -m app.cli texture-audit ./tod --fail-under 100
python -m app.cli export-map ./tod --format csv --out ./map.csv
python -m app.cli structure inventory ./tod
python -m app.cli structure extract ./tod HOUSE_ID --format schem --out ./house.schem
python -m app.cli analyze ./tod --structure HOUSE_ID --out ./house-analysis
python -m app.cli render ./tod --view isometric_ne --size 4096x4096 --accuracy exact --tile-size 512 --resume
python -m app.cli quality-report ./tod --structure HOUSE_ID
python -m app.cli export ./tod --format schem
python -m app.cli export ./tod --format litematic
```

Required evidence: all commands exit 0; CSV has 4,245,700 lines; fluid/entity
coverage is genuinely rendered; both exports report every mismatch class zero;
repeat and resumed exact PNG/semantic outputs are byte/array identical; peak
memory remains within the declared machine budget.

## H-I. Prior evidence handling

The plan's measurements are treated as upstream observations, not as evidence
generated by this checkout. No referenced Snowflake workspace or hidden
`.mbi-evidence` directory is claimed to exist locally. Current local evidence is
the test suite, release verifier and generated fixtures recorded in the release
manifest.

## J. Universality matrix

| ID | Status | Implementation and evidence |
|---|---|---|
| J1 | Implemented and tested | Litematic has streaming bit-state iteration and iterable packing with exact count checks. A 4,194,304-state stream is exercised without a cell list. Legacy import writes directly to chunk arrays. |
| J2 | Implemented and tested | Multi-region Litematic retains independent chunk maps and uses `RegionOverlayVoxelMap` for the deterministic flattened view, eliminating the second full flattened allocation. |
| J3 | Explicitly out of scope | Product scope is schematic files: Sponge `.schem`, `.litematic`, legacy `.schematic`. Anvil `.mca` files and world directories fail with typed `ANVIL_WORLD_UNSUPPORTED`, supported inputs and `scopeDecision: schematic-files-only`. No universal world-save claim is made. |
| J4 | Implemented and tested | A 50,000-block-entity fixture carries nested compound/list data and verifies Sponge export/re-import with coordinate, state and block-entity mismatches all zero. |
| J5 | Implemented and tested | Banner, skull, sign, bed and shulker families are simultaneously audited and rendered with their proxy geometry. |
| J6 | Implemented and tested | Still/flowing water, lava levels and a waterlogged stair are audited; fluid coverage is conditional on genuine render asset/path support. |
| J7 | Implemented and tested | A -64 through 320 fixture renders all eight semantic layers and passes export/re-import. The rich block-entity fixture also uses negative Y. |
| J8 | Implemented and tested | The declared array budget is at least five million placed blocks/GiB. The 16,777,216-voxel storage gate is four times the Tree placed-block magnitude. |
| J9 | Implemented and tested | `render_lod` writes a nearest-depth sampled overview and semantic maps with bounded buffers. Its manifest says `lod.enabled: true` and `accuracy.exact: false`; it never masquerades as exact. |
| J10 | Implemented and tested | Small-fixture monolithic/exact-tiled equivalence and 12-tile resume are retained. A dense 2,097,152-block exact one-tile render is deleted, resumed from its checkpoint and compared byte-for-byte for PNG plus equality for all semantic layers. |
| J11 | Implemented and tested | Palette atlas output paginates at 250 states/page. The 2,000-state fixture produces eight bounded, legible pages rather than one unbounded image. |
| J12 | Implemented and tested, plus named fixture pending | `test_tree_of_dreams_universality.py` covers scale arrays, Litematic streaming, terrain-only behavior, three material-independent buildings, entity/fluid rendering, 50,000 rich block entities, modern height, exact scale determinism, honest LOD, lighting/skip semantics and 2,000-state pagination. The actual Tree Sponge row remains pending solely because its file is absent. |

## Release claim

The accurate release claim is:

> Version 1.2.0 implements bounded large-schematic processing for Sponge,
> Litematic and legacy schematic files using chunk-array storage, streamed
> canonical I/O/export, scoped analysis, exact resumable tiling and honest LOD.
> A generated universality matrix covers up to 16.8 million placed voxels and
> the listed correctness edge cases. Anvil worlds are explicitly unsupported.
> The named Tree of Dreams end-to-end gate must still be executed when the
> unmodified source fixture is available.
