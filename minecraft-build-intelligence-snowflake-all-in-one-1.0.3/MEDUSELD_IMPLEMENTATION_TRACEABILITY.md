# Meduseld implementation traceability

This document maps every actionable item in `MEDUSELD_ANALYSIS_ISSUES.md` to
the 1.1.0 implementation. “Implemented” means the behavior exists in the
runtime; it does not mean that every heuristic verdict is ground truth.
Analysis and render manifests continue to label heuristic, sampled, fast, and
exact evidence explicitly.

## Acceptance fixture

- Source SHA-256:
  `406cc8accfaa0dea76d4fa48473b04080afc67202b9d537563b182f072383021`
- Canonical content hash:
  `248d2831ea3059bfbb4c3eda353aff8b97cabb97f771a968ff1418716593f273`
- Imported content: 108,917 placed blocks, 1,495 block entities, 454 palette
  entries, bounds `(1070,105,-1902)..(1213,225,-1663)`.
- The acceptance run is external to the source tree so release manifests never
  absorb generated evidence.

## A, B, and C: blockers, defects, and render ceiling

| ID | Status | Implementation and evidence |
|---|---|---|
| A1 | Implemented | `mbi.hashing.nonsecurity_blake2b/nonsecurity_blake2s` centralize FIPS-safe non-security hashing. Raster colors, content hashes, caches, and patch IDs use the helper. `services/core/tests/test_hashing.py` exercises a hardened-provider simulation. |
| A2 | Implemented | `BOOTSTRAP_SNOWFLAKE.py` compares installed versions against declared bounds, reports mismatches, installs missing/out-of-range requirements, and uses the same Pillow range as `pyproject.toml`. `tests/unit/test_bootstrap_versions.py` covers the checks. |
| B1 | Fixed | Litematic export re-imports and verifies successfully. The Meduseld structure extract passed exact verification with zero coordinate, state, or block-entity mismatches. |
| B2 | Fixed | `mbi.export.litematic` writes block-entity `Pos` in region-local coordinates. Round-trip regression coverage is in `services/core/tests/test_export_roundtrip.py`. |
| B3 | Fixed | `mbi.formats.litematic` preserves the source `Id`/`id` representation instead of injecting a duplicate lowercase key. |
| B4 | Fixed | `mbi.export.verify` independently reports coordinate, state, block-entity, entity, tick, region, and extension mismatch classes. A block-entity mismatch can no longer increment coordinate/state counts. |
| B5 | Fixed | `app/assets/legacy_ids.py` supplies versioned asset-only migrations including `grass -> short_grass` and `chain -> iron_chain`; diagnostics distinguish migrated and unmapped legacy IDs. Meduseld texture audit reached 100% total coverage. |
| B6 | Fixed | Lighting accepts configurable or removable caps, bounded/structure scopes, and room scopes. A skip is explicit. Meduseld structure analysis processed 44 rooms and 239 emitters with `analysisSkipped=false`. |
| B7 | Fixed | Manual seed-and-clip rooms seal requested bounds and report sealed openings and leak paths. Structure analysis also runs a conservative constructed-envelope recovery pass before room reporting. Tests cover both an open doorway and a clipped leak. |
| B8 | Fixed | Interior/exterior consistency excludes decorative trapdoors without navigable approaches and reports the exclusion count. The Meduseld false-door result fell from 2,515 to 6, with 5,015 decorative trapdoors excluded. |
| B9 | Fixed | Balcony findings carry `navigabilityWeight`; the report publishes both raw and weighted totals and excludes non-navigable fence/decorative candidates. |
| B10 | Fixed | Appendix B in both autonomous manuals and the README document current interior, perspective, render, structure, authoring, comprehension, analysis, and quality surfaces. Runtime `--help` remains authoritative. |
| B11 | Fixed | Nested output paths raise the typed `OUTPUT_NESTED_IN_SOURCE` validation error with a suggested sibling path instead of `UNEXPECTED_ERROR`. |
| B12 | Fixed | Slice renders honor `--name`; the default remains an axis/index descriptive name. |
| B13 | Fixed | The `test` extra declares `pytest-asyncio`, asyncio mode/marker configuration is checked in, and async integration tests execute rather than silently skip. |
| B14 | Fixed | Interior render rejects dominant-plane and other degenerate frames. `--fail-on-reject` is enabled by default and produces a typed non-zero error with rejection reasons; `--no-fail-on-reject` is explicit opt-out. |
| B15 | Fixed | Camera fitting is on by default. `--fit/--no-fit`, `--zoom`, and `--margin` have runtime help and are documented. |
| C1 | Implemented | The software renderer creates entity-texture proxy geometry for banners (including pattern layers), skulls/heads, signs, beds, and shulker boxes. Diagnostics label `ENTITY_RENDERED` separately from fallback. The Meduseld audit resolved all 36 entity-rendered blocks and reached 100% combined coverage. |

## D: verification statements

| ID | Status | Implementation and evidence |
|---|---|---|
| D1 | Re-executed | The complete Python suite is run after the 1.1.0 changes; the final count is recorded in `RELEASE_MANIFEST.json` and `RELEASE_FILE_MANIFEST_PATCH.json`. |
| D2 | Resolved for this revision | Work is in a real Git checkout on `feature/meduseld-quality-map-maker`; the final commit and hosted check status provide provenance. |
| D3 | Preserved | Deterministic snapshot IDs and byte-stable same-runtime rendering remain covered by renderer tests. The exact Meduseld tiled render resumed from finalized output with an unchanged PNG SHA-256 of `96b37b0823bc341f945c3a2f29099fc9e468a332c17a8b850f6adc672a693300`. |

## E: Snowflake/CoCo environment hardening

| ID | Status | Implementation and evidence |
|---|---|---|
| E1 | Implemented | Bootstrap mirrors source to writable local scratch and documents why stage execution is slow. |
| E2 | Implemented | Virtual environments are created under configurable local scratch, never assumed to be repository-local or symlink-capable. |
| E3 | Implemented | Wheel/editable builds execute from the local source mirror rather than the mounted stage. |
| E4 | Implemented | `build_backend.py` supplies PEP 660 `build_editable`, metadata, and editable-wheel hooks; backend tests install the result. |
| E5 | Implemented | Bootstrap accepts an authenticated/custom `--index-url`; the empty wheelhouse is documented honestly and never claimed as a complete offline dependency source. |
| E6 | Implemented | `--warm-cache` stores the reconstructed asset and compact source archive; `--cache-venv` also stores/restores the environment archive. Cache entries are content-addressed and verified. |

## F: build-quality findings

The reported floating components, unsupported/gravity blocks, cantilevers,
navigation dead ends, blocked approaches, and flat patches were build findings,
not software defects. They remain visible in per-structure support,
circulation, facade, critique, map, and composite quality reports. Exact
symmetry is now available, so symmetry evidence is no longer forced to be a
sampled lower bound. No automatic geometry mutation is performed merely
because a heuristic flags a finding.

## G: comprehension improvements

| ID | Status | Implementation and evidence |
|---|---|---|
| G1 | Implemented | `export-map` emits CSV, JSONL, or optional Parquet with coordinate, state, texture, model, status, region, component, room, and classification fields. Meduseld CSV contains exactly 108,917 rows. |
| G2 | Implemented | `texture-audit --fail-under` reports state/block/static/entity/combined coverage and every unresolved reason; the threshold is a typed CI gate. |
| G3 | Implemented | `annotated-render` adds coordinate gridlines, axis ticks, compass, and optional common-material labels. |
| G4 | Implemented | Slice `--name` is honored and default filenames encode axis/index. |
| G5 | Implemented | `contact-sheet` creates a baked-label montage across selected views/slices. |
| G6 | Implemented | `slice-sweep --slice AXIS:MIN..MAX --step N --montage` emits resumable sections and a labelled montage. |
| G7 | Implemented | `--accuracy fast` uses the cheap flat preview path and records a non-texture-exact accuracy contract in the manifest. |
| G8 | Implemented | Batch comprehension, structure, and exact tiled render paths support `--resume` with durable artifact/checkpoint validation. |
| G9 | Implemented | `analyze` supports bounds, detected structures, manual room bounds/seeds, envelope sealing, lighting caps, and full room-scoped navigation/lighting. |
| G10 | Implemented | Reflection symmetry is exact and uncapped. |
| G11 | Implemented | `palette-atlas` produces labelled state swatches and texture/model resolution metadata. |
| G12 | Implemented | Entity-texture proxy rendering and explicit entity diagnostics cover the C1 states. |

## H: map-maker-grade authoring roadmap

| ID | Status | Implementation and evidence |
|---|---|---|
| H1.1 | Implemented | Default fit-to-subject framing plus documented fit/zoom/margin controls. |
| H1.2 | Implemented | Reject-by-default CLI behavior and dominant-plane gates. |
| H1.3 | Implemented | Whole-volume `export-map`. |
| H1.4 | Implemented | Gated `texture-audit`. |
| H1.5 | Implemented | Labelled `contact-sheet`. |
| H1.6 | Implemented | Resumable `slice-sweep`. |
| H1.7 | Implemented | Grid/axis/compass/material `annotated-render`. |
| H1.8 | Implemented | Labelled `palette-atlas`. |
| H1.9 | Implemented | Entity-texture proxy geometry and composited banner patterns. |
| H2.1 | Implemented | Manual watertight seed-and-clip plus conservative automatic structure-envelope pass, sealed-opening count, and explicit leak path. |
| H2.2 | Implemented | Lighting executes per room/structure/bounds with configurable/removable cap. |
| H2.3 | Implemented | Coverage candidates are greedily selected by marginal union gain; packets report and gate cumulative coordinate coverage. |
| H2.4 | Implemented | `interior walkthrough` follows an ordered navigation path and emits grounded frames. |
| H2.5 | Implemented | Every room carries furnishing density, functional/decorative counts, vertical-detail occupancy, dead-volume ratio, and `is_hollow`. |
| H2.6 | Implemented | `interior sightline` samples entry-to-feature voxel rays and exact blockers. |
| H3.1 | Implemented | `author style-extract` records palette ratios, proportions, bay rhythm, roof pitch, trim, symmetry, facade baseline, and fixture vocabulary. |
| H3.2 | Implemented | Named parametric `draw_truss`, `draw_dormer`, `draw_arcade`, and `draw_bellcast_eave` compound patch operations. |
| H3.3 | Implemented | `symmetry_edit` mirrors nested bounded operations across an exact axis. |
| H3.4 | Implemented | Seeded deterministic `greeble_surface` supports protrude, recess, and mixed depth passes. |
| H3.5 | Implemented | `author critique` joins facade monotony, support, circulation, furnishing, roofline, palette, and style-profile divergence into bounded patch targets. |
| H3.6 | Implemented | Exact uncapped reflection symmetry. |
| H3.7 | Implemented | Fixture kit includes bench, table, hearth, brazier, and banner arrangement assemblies. |
| H3.8 | Implemented | Durable absolute, room-face, and structure-bay anchors; authoring operations resolve relative offsets from named anchors. |
| H3.9 | Implemented | `repeat_module` repeats a nested operation with automatic spacing and seeded controlled variation. |
| H4.1 | Implemented | Explicit non-texture-exact fast preview. |
| H4.2 | Implemented | Resumable batch rendering and artifact skipping. |
| H4.3 | Implemented | Local-scratch mirroring in bootstrap and manuals. |
| H4.4 | Implemented | Warm asset/source/environment caches. |
| H4.5 | Implemented | PEP 660 editable backend hooks. |
| H4.6 | Implemented | Exact screen-space tiled renderer uses durable per-tile markers and disk-backed semantic buffers. Finalized-output resume records every tile as resumed and preserves the image hash. |
| H5 | Closed | The suggested order was used as dependency guidance: comprehension/rejection and environment foundations precede interior coverage, assemblies, quality scoring, and tiled rendering. |

## I: map-scale analysis and composition

| ID | Status | Implementation and evidence |
|---|---|---|
| I1.1 | Implemented | Streamed state classification plus built-column density/enclosure/separation clustering produces durable structure IDs. Meduseld resolves two structures. |
| I1.2 | Implemented | Every non-air state/coordinate is classified as terrain, built, vegetation, or prop with crafted-form precedence. |
| I1.3 | Implemented | `analyze --bounds` and `analyze --structure` produce independent scoped reports; the latter resolves bounds before cloning output. |
| I1.4 | Implemented | `structure inventory` records IDs, bounds, volume, block counts, palette, rooms, storeys, style, proportions, roof pitch, trim, and terrain contact. |
| I1.5 | Implemented | Structures can be durably named; all later structure commands resolve ID or name. Author anchors provide named landmarks. |
| I1.6 | Implemented | `structure extract` creates an independent run and verified `.schem` or `.litematic`. Both formats passed exact Meduseld extraction. |
| I2.1 | Implemented | Structure detection is a single streamed coordinate pass aggregated by bounded spatial windows; the manifest records peak window occupancy and proves no document-sized coordinate label map was retained. |
| I2.2 | Implemented | Detected structures automatically run conservative envelope recovery before room reporting; manual bounds can opt in with `--seal-structure-envelope`. Broad exterior connections and micro-voids are rejected. |
| I2.3 | Implemented | Lighting and room caps are configurable/removable; skip reasons, limits, structure IDs, progress, and configuration are explicit. |
| I2.4 | Implemented | `structure analyze-all --resume` writes versioned per-structure checkpoints keyed by parent hash, bounds, cap, and algorithm version. |
| I2.5 | Implemented | One map report contains aggregate comparison and complete per-structure analyses/programs/scorecards. |
| I3.1 | Implemented | `structure interiors` sweeps rooms per structure, applies normal rejection gates, and supports resume. |
| I3.2 | Implemented | Each structure receives a labelled packet index linking plans, sections, accepted perspectives, rejects, and coverage evidence. |
| I3.3 | Implemented | Per-structure room programs assign stable structure-prefixed names and shared architectural type labels. |
| I3.4 | Implemented | Per-structure completeness reports furnished/hollow, lit/dark, reachable/sealed counts and a normalized score. |
| I3.5 | Implemented | Structure comparison/map reports calculate palette, proportion, roof-pitch, trim, and style divergence. |
| I4.1 | Implemented | `structure site-plan` draws top-down terrain, structure outlines, IDs, and names. |
| I4.2 | Implemented | Foundation contact, buried ratio, floating bottom columns, support findings, and terrain seams are reported per structure. |
| I4.3 | Implemented | Map report builds a terrain-surface A* graph and reports inter-structure route reachability, path length, elevation change, visited nodes, and coordinates. |
| I4.4 | Implemented | Approach sightlines use voxel rays and name exact blocking coordinates per structure/approach. |
| I4.5 | Implemented | `structure render-all` emits a fast whole-map overview plus consistent per-structure detail views and supports resume. |
| I4.6 | Implemented | `structure compare` performs structure-granularity geometry, palette, proportion, roof, trim, terrain, and style comparison. |
| I5 | Closed | The suggested map-scale order is reflected in scoped/checkpointed analysis first, classification/sealing second, manifests/scorecards next, then segmentation, batch interiors/composition, and heavy sightline/LOD work. |
| I6 | Implemented | The near-term path is directly available: `analyze --bounds ... --seal-structure-envelope` yields independent room, lighting, navigation, consistency, facade, and quality evidence without requiring automatic segmentation. |

## J: quality feedback loop

| ID | Status | Implementation and evidence |
|---|---|---|
| J1 | Implemented | Bounds/structure/room lighting yields emitter states, per-room distributions, dark cells/ratios, and explicit caps. The Meduseld main structure analyzed 239 sources without skipping. |
| J2 | Implemented | Packets optimize cumulative union coverage and `--min-cumulative-coverage` fails with achieved/required values when unmet. |
| J3 | Implemented | Room furnishing blocks contain density, vertical occupancy, dead volume, and `is_hollow`; structure reports aggregate completeness. |
| J4 | Implemented | Each elevation reports normalized flat area, depth variance, silhouette variation, monotony score, and ranked bounded worst regions. |
| J5 | Implemented | Degenerate render rejection is default and typed/non-zero with stderr reasons. |
| J6 | Implemented | `quality-report` normalizes lighting, coverage, furnishing, facade, structural, circulation, palette, and symmetry dimensions; supports `--fail-under`, structure/bounds scopes, and version diffs. |
| J7 | Closed | The missing “judge whether it is good” link is now represented by the composite scorecard, per-dimension evidence, critique findings, and patch-ready coordinates. These remain transparent heuristics, not an unsupported claim of aesthetic truth. |
| J8 | Closed | The requested order is reflected in the implementation: rejection/furnishing, then lighting/coverage, facade scoring, and finally the composite gate/diff. |

## Real-schematic evidence summary

- Both `.schem` and `.litematic` main-structure extracts re-imported with every
  mismatch class equal to zero.
- Texture audit: 447 static states plus 6 entity-rendered states, zero failed
  states/blocks, 100% combined block coverage.
- Exact tiled render: 512x320, 12 tiles, zero fallbacks; resume reported all 12
  tiles resumed and retained the same PNG digest.
- Structure inventory: two structures; the main structure contains 56,706
  built/prop classification points and the small structure contains 56.
- Main structure analysis: 44 interior volumes, 44 navigation rows, 44 lighting
  rows, 239 light sources, no lighting skip.
- Whole-volume export: 108,917 CSV rows with coordinate, state, asset, region,
  component, room, and classification columns.
- Walkthrough and sightline artifacts contain grounded navigation paths, exact
  voxel blockers, and rendered frames.
- Packet coverage records greedy marginal-union selection, achieved and
  required coverage, accepted/rejected renders, and the exact source hash.
