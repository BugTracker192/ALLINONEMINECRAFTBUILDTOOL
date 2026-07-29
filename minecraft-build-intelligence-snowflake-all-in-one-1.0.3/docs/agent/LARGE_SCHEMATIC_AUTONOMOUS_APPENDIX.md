# Large-schematic autonomous appendix (version 1.2.0)

This is the normative detailed appendix to both autonomous operating manuals.
It supersedes older command summaries wherever scale, classification,
rendering, verification or schemas differ. The requirement/evidence index is
`TREE_OF_DREAMS_IMPLEMENTATION_TRACEABILITY.md`.

## Scope and truth rules

Supported inputs are Sponge `.schem` v1-v3, Litematic `.litematic` and
conservative legacy `.schematic`. Anvil `.mca` files/world directories are
outside the 1.2.0 scope and return `ANVIL_WORLD_UNSUPPORTED` with
`scopeDecision: schematic-files-only`. Never claim world-save support.

Never turn an unavailable fixture into a pass. `Tree_of_dreams.schem` must be
run unmodified before reporting its named acceptance gate complete. Generated
scale fixtures prove architecture, not the exact contents/timings of a missing
file.

Preserve these invariants:

1. Canonical/version JSON retains the established byte encoding.
2. Content hashes retain the established canonical payload.
3. Streamed loads consume and validate the complete source and stored hash.
4. Typed error codes and detail keys remain API contracts.
5. Coordinate/output iteration remains deterministic.
6. Rendering, analysis and export never mutate canonical truth.
7. Exact and LOD/non-exact evidence are never conflated.

## Scale envelope and controls

Default guards: 100,000,000 volume cells; 65,536 palette states; 65,535
blocks/axis; 2 GiB decompressed NBT; 512 MiB compressed NBT. They are parser
ceilings, not a promise that every accepted file fits every computer.

The chunk store uses 4 bytes per allocated voxel slot plus a small chunk index.
The release gate stores 16,777,216 placed voxels in 67,108,864 array bytes,
exceeding five million placed blocks/GiB. Sparse edge chunks still occupy full
16 KiB arrays. NBT bytes, palettes, block entities, analysis arrays, asset
caches and output buffers are additional.

| Path | Memory/time shape | Required policy |
|---|---|---|
| Sponge import | compressed + decompressed bytes + voxel chunks | Stream varints; never list-decode large cell streams. |
| Litematic import/export | packed words + voxel chunks | Use `iter_block_states` and iterable `pack_block_states`. |
| Canonical save/load | mmap + chunks; streamed JSON | Use project APIs; never `json.loads` a multi-million-row canonical file. |
| CSV/JSONL `export-map` | voxel/chunk model + bounded labels | Stream rows directly to the output. |
| Structure inventory | voxels + dense label arrays | Persist and reuse durable IDs. |
| Scoped analysis/extract | parent validation + scoped result | Pass bounds/structure into loading. |
| Exact render | one tile geometry/raster + disk-backed semantic maps; scans source per tile | Use 256-1024 tiles and `--resume`; prefer 512. |
| Fast overview | output pixels + semantic maps; one source scan | Use `--accuracy fast`; require an LOD/non-exact manifest. |
| Block entities | entity count + nested NBT | Preserve nested NBT and verify round-trip. |

Controls:

- `MBI_MAX_VISIBLE_BLOCKS`: emitted-geometry limit per tile/frame; default
  250,000. Buried/culled blocks do not consume it.
- `MBI_MAX_RENDER_SIZE`: max width/height; default 4096.
- `MBI_MAX_TOTAL_TILE_WORK`: `width * height * tile_count` ceiling; default
  2,147,483,648.
- `render --max-visible-blocks N`: one-run override.

Exact large scenes auto-enable 512-pixel tiles when no explicit size is given.
`--tile-size 0` requests automatic behavior. Reduce output/crop/scope, choose a
larger tile if RAM permits, or use honest LOD before raising safety ceilings.

## Complete 1.1/1.2 command extension schema

All commands accept `--json-errors`, `--quiet`, `--verbose`, `--log-json`.
`RUN` is an initialized run. Vectors are document-space `x,y,z`; bounds are
inclusive `x1,y1,z1,x2,y2,z2`; image sizes are `WIDTHxHEIGHT`.

Core extensions:

| Command | Parameters and behavior |
|---|---|
| `analyze RUN` | `--bounds BOX`; `--structure ID_OR_NAME`; `--lighting-max-cells N` (0 disables); `--dark-threshold N`; `--room-max-cells N`; repeatable `--room-bounds BOX` and optional repeatable `--room-seed X,Y,Z`; `--seal-structure-envelope`; `--out`. |
| `render RUN` | Existing camera/view/material/region flags plus `--projection auto|orthographic|perspective`; `--camera-position`; `--camera-target` or yaw/pitch; FOV/near/far; repeatable `--hide-coordinate`; `--accuracy exact|fast`; `--tile-size`; `--max-visible-blocks`; `--resume`; `--crop x,y,z,w,h,l`; `--size`; `--mode`; `--out`. Perspective requires a position. |
| `export RUN` | Required `--format schem|litematic`; verification defaults on; `--no-verify` returns `passed:"skipped"`; optional `--out`. Verification mismatch raises exit 51. |
| `quality-report RUN` | Optional `--bounds` or `--structure`; `--seal-structure-envelope`; `--fail-under`; version diff via `--from`/`--to`. Uncomputed dimensions are unavailable/null and unweighted. |
| `export-map RUN` | Required `--out`; `--format csv|jsonl|parquet`; optional `--resource-pack`. CSV/JSONL stream; Parquet is optional-dependency backed. |
| `texture-audit RUN` | `--resource-pack`; `--fail-under`. Entity/fluid coverage requires actual renderer support. |
| `palette-atlas RUN` | Required `--out`; `--resource-pack`; `--columns`; `--swatch-size`. Maximum 250 states/page. |
| `contact-sheet RUN` | `--views`; `--slices`; required `--out`; pack/size; `--accuracy`; `--resume`; `--columns`. |
| `slice-sweep RUN` | Required `--slice AXIS:MIN..MAX` and `--out`; `--step`; pack; `--resume`; `--montage`/`--no-montage`. |
| `annotated-render RUN` | Required `--out`; `--view`; pack/size; `--annotate-materials`. |

`author`:

| Command | Parameters |
|---|---|
| `author anchor-set RUN NAME` | Required `--position X,Y,Z`. |
| `author anchor-room RUN NAME` | Required `--room ID`, `--face north|south|east|west|floor|ceiling`. |
| `author anchor-bay RUN NAME` | Required `--structure`, cardinal `--face`, `--bay-index`, `--bay-count`. |
| `author anchors RUN` | Lists anchors. |
| `author style-extract RUN` | Optional `--name` (`reference`). |
| `author critique RUN` | Optional `--style-profile`. |
| `author fixture-catalog` | Returns fixture/assembly schemas; no run required. |

`structure`:

| Command | Parameters |
|---|---|
| `structure inventory RUN` | `--separation` (2); `--minimum-blocks` (24); `--window-edge` (64); `--classification-config FILE`. Emits thresholds and geometric evidence. |
| `structure name RUN IDENTIFIER NAME` | Registers a durable name. |
| `structure extract RUN IDENTIFIER` | Required `--out`; `--format schem|litematic`. |
| `structure analyze-all RUN` | `--resume`; `--lighting-max-cells`. |
| `structure compare RUN FIRST SECOND` | Compares two IDs/names. |
| `structure site-plan RUN` | `--out`; `--pixels-per-block`. |
| `structure map-report RUN` | Whole-map summary. |
| `structure render-all RUN` | `--out`; pack; `--accuracy fast|exact`; `--resume`; `--size`. |
| `structure interiors RUN` | `--out`; pack; `--resume`; `--max-rooms-per-structure`; `--min-cumulative-coverage`; `--size`. |

`interior`:

| Command | Parameters |
|---|---|
| `interior inspect RUN --room ID` | Canonical room geometry/features/classification. |
| `interior diagnose RUN --room ID` | Camera/reachability/occlusion/quality diagnostics. |
| `interior render RUN --room ID` | `--shot auto|doorway|corner|center|feature|low|upper|coverage|walkthrough`; pack/size/FOV/near/far/eye-height/lighting; camera mode; physical/cutaway/hybrid/roof-off/wall-off occlusion; minimal-ray/roof/wall cutaway; quality profile/coverage/obstruction/attempt controls; fail-on-reject toggle; name/out. |
| `interior gallery RUN` | `--rooms`; `--shots`; pack/size/FOV/near/far/eye-height/lighting; occlusion; `--include-non-rooms`; `--out`. |
| `interior walkthrough RUN --room ID` | `--spacing`; `--render`; pack/size; `--resume`; `--out`. |
| `interior sightline RUN --room ID` | Optional `--out`. |
| `interior packet RUN --room ID` | shots; pack/size/camera; fallback stages; occlusion/cutaway; slice fallback; quality/coverage/attempt controls; cumulative coverage; out. |

The runtime parser remains authoritative:
`python -m app.cli GROUP SUBCOMMAND --help`. Never invent flags.

## Complete patch schema

Patch envelope:

```json
{
  "reason": "why",
  "author": "agent-id",
  "bounds": {"min": [0, 0, 0], "max": [15, 15, 15]},
  "maxAffectedBlocks": 100000,
  "coordinateSpace": "document",
  "expectedParentHash": "canonical-hash",
  "targetRegion": null,
  "evidenceRefs": [],
  "preconditions": [],
  "operations": []
}
```

`coordinateSpace` must be `document`. Bounds are inclusive and contain every
change. Preconditions:

- `{"type":"block_state","position":[x,y,z],"state":"namespace:block[...]"}`
- `{"type":"chunk_hash","chunk":[cx,cy,cz],"hash":"..."}`
- `{"type":"version","versionId":"..."}`

Supply the expected parent hash, tight bounds and realistic effect cap.

| Operation `type` | Accepted fields |
|---|---|
| `set_block` | `position`, `state`. |
| `set_blocks` | `blocks:[{position,state}]`, optional `offset`. |
| `paste_template` | Same as `set_blocks`. |
| `fill_cuboid`; `hollow_cuboid` | `min`, `max`, `state`. |
| `clear_region` | `min`, `max`. |
| `replace_blocks` | `from:[states]`, `to`, optional `min`/`max`, optional `mask:{type:"surface_noise",seed,probability}`. |
| `draw_line` | `start`, `end`, `state`. |
| `draw_polyline` | `points`, `state`. |
| `draw_wall` | `start`, `end`, `height`, `thickness`, `state`. |
| `draw_floor` | `min`, `max`, optional `y`, `state`. |
| `draw_roof` | `min`, `max`, `style:flat|gable`, optional `axis`, `y`, `state`. |
| `draw_circle`; `draw_ellipse` | `center`, `radius` or `radiusA`/`radiusB`, `plane`, `filled`, `state`. |
| `draw_cylinder` | `center`, `radius` or `radiusX`/`radiusZ`, `height`, `hollow`, `state`. |
| `draw_sphere`; `draw_dome` | `center`, `radius`, `hollow`, `state`. |
| `draw_arch` | `start`, `end`, `height`, `thickness`, `state`. |
| `draw_bezier` | `controlPoints` (alias `points`), optional `samples`, `state`. |
| `extrude_profile` | `profile`, `offset`, `steps`, `state`. |
| `loft_profiles` | `profiles`, `stepsPerPair`, `state`. |
| `copy_region`; `move_region` | `sourceMin`/`sourceMax` (aliases `min`/`max`), `offset`; move clears source. |
| `rotate_region` | Source bounds, optional `origin`, `quarterTurns`, `clearSource`; transforms directional state. |
| `mirror_region` | Source bounds, optional `origin`, `axis`, `clearSource`; transforms directional state. |
| `scale_pattern_integer` | Source bounds, optional `origin`, positive integer `factor:[x,y,z]`. |
| `apply_noise_mask` | `min`, `max`, `state`, `probability`, `seed`, optional `from`. |
| `apply_gradient_palette` | `min`, `max`, non-empty `palette`, `axis`. |
| `greeble_surface` | `min`, `max`, `detailState`/`state`, `probability`, `seed`, `mode:mixed|protrude|recess`, `depth` 1-4. |
| `symmetry_edit` | `origin`, `axis`, `operations:[nested operations]`. |
| `repeat_module` | `operation`, `count` 1-256, `spacing`, optional `variation`, `seed`. |
| `set_block_entity` | `position`, nested `data`, optional `id`, `region`. |
| `remove_block_entity` | `position`. |
| `draw_truss` | `origin`, `width`, `height`, `axis`, `state`, optional `accentState`, `thickness`. |
| `draw_dormer` | `origin`, `width`, `depth`, `height`, `axis`, `state`, `roofState`, optional `trimState`. |
| `draw_arcade` | `origin`, `bayCount`, `bayWidth`, `height`, `axis`, `state`, optional `thickness`. |
| `draw_bellcast_eave` | `origin`, `length`, `overhang`, `drop`, `axis`, `state`, optional `trimState`. |
| `place_fixture` | `origin`, fixture `bench|table|hearth|brazier|banner_arrangement`, `facing`, `length`, fixture-specific state fields. |

Anchored operations may be resolved through authoring anchors. Inspect the
resolved preview after any parent-version change.

Lifecycle:

```bash
python -m app.cli patch validate RUN patch.json
python -m app.cli patch preview RUN patch.json --out PREVIEW
python -m app.cli patch commit RUN patch.json --out RESULT
python -m app.cli patch reject RUN patch.json
python -m app.cli patch rollback RUN --patch-id PATCH_ID
```

Inspect effect count, bounds, preconditions, evidence, analysis delta and
protected content before commit.

## Large-schematic autonomous sequence

1. Hash/preserve the untouched input.
2. Import once; record dimensions, placed/palette/entity counts, canonical
   hash and diagnostics.
3. Texture-audit at the required threshold; require real entity/fluid support.
4. Stream export-map; CSV rows must equal placed blocks plus header.
5. Inventory structures; inspect kind, bounds and geometric evidence.
6. Name durable structures.
7. Analyze/extract/render through scopes.
8. Use exact tiled/resumable evidence where exact pixels matter; LOD only for
   labelled overviews.
9. Treat missing/capped lighting as unknown.
10. Export requested formats with verification on and all mismatches zero.
11. Repeat and resume exact render; compare PNG and eight semantic layers.
12. Run the full Python suite and release verifier; record actual counts.

Tree gate when the untouched source exists:

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

If absent, report `named-fixture gate pending: source unavailable`; never
substitute another file.

## Exact, LOD and acceptance

Exact tiled output is accepted only when clean repeat and resumed repeat match
for the PNG and palette, coordinate, depth, normal, region, occupancy, changed
and issue maps. A tile marker is valid only after its PNG and semantic slices
are durable, and resume validates marker hashes.

LOD uses nearest-depth sampling and disk-backed maps. Its manifest must contain
`lod.enabled:true`, `accuracy.exact:false` and source block count. LOD is not
proof of exact block visibility or export correctness.

Acceptance also requires classification counts sum to placed blocks; terrain
is not one building; castle/bridge/dungeon guards remain buildings; fluid and
entity coverage is real; scopes cite the parent hash; uncomputed lighting is
unavailable; export verifies by default; canonical truth is unchanged; and
fixture name/size/evidence boundary are stated.

## Warm cache and hostile environments

`BOOTSTRAP_SNOWFLAKE.py --warm-cache` includes every
`app/bundled_assets/parts/` file and validates the part manifest before cache
creation. An incomplete payload is a hard error.

In recycle-prone/low-memory environments, use the verified persistent
workspace, keep stages idempotent, retain checkpoints, validate the resolved
path before writes and re-hash cache files. Clear hostile `PYTHONPATH` or
`PYTHONSAFEPATH` only for controlled invocations. Never weaken integrity or
verification as an environment workaround.

