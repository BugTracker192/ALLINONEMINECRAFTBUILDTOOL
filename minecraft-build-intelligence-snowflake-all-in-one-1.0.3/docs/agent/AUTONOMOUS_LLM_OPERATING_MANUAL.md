# AUTONOMOUS LLM OPERATING MANUAL — MINECRAFT BUILD INTELLIGENCE
## Mandatory Offline Python 3.12 / Snowflake–CoCo Profile

> **Audience:** an LLM/coding agent operating a writable Snowflake/CoCo-style Python sandbox with shell and file access. This document is not a human tutorial. Treat it as the authoritative runbook for autonomous operation of this repository.

---

## 0. EXECUTION DIRECTIVE

You are operating a Minecraft Java build-intelligence system. Your job is to complete the requested build task without routine human assistance. You must discover the environment, install or activate the package, locate the input structure and resource pack, create a self-contained run directory, inspect exact symbolic voxel data and literal rendered images together, plan bounded changes, preview them, re-render them, critique them, commit only validated changes, verify final quality, export, re-import, and prove exact coordinate/state preservation.

Never treat a render as the source of exact block identity. Never treat raw block data as sufficient visual proof. Every architectural conclusion must be grounded in one or more of:

- a deterministic PNG evidence ID;
- a semantic map and pixel-to-block lookup;
- an exact coordinate/state query;
- a room/component/navigation/facade/lighting/consistency analysis result;
- a version comparison or patch diff;
- an export verification report.

Never execute model-generated Python, shell, or arbitrary paths. Use only the validated CLI, JSON tool bridge, or built-in provider tool interface.

### Completion condition

Do not declare success until this chain has completed:

```text
Import or create blank build
→ canonicalize exact voxel data
→ analyze
→ render global views and relevant slices/crops
→ inspect images and exact data
→ plan
→ create bounded transaction
→ validate
→ preview with before/after images
→ critique
→ commit or reject
→ re-render changed areas
→ repeat as needed
→ run final quality gates
→ export .schem and/or .litematic
→ re-import export
→ verify zero unacceptable coordinate/state loss
```

---

## 1. ENVIRONMENT CONTRACT

The mandatory profile assumes:

- Python 3.12;
- `pip` access to PyPI during installation;
- a writable local directory;
- no Node.js requirement;
- no browser requirement;
- no Docker requirement;
- no database, Redis, S3, Celery, GPU, OpenGL, Chromium, or external executable requirement.

Mandatory runtime dependencies are only:

```text
numpy >=2.0,<3
Pillow >=12.3,<13
```

Optional live-provider dependency:

```text
httpx >=0.27,<1
```

Optional test dependencies:

```text
pytest >=8,<10
hypothesis >=6.100,<7
pytest-asyncio >=1,<2
```

The repository uses a self-contained standard-library PEP 517 wheel backend. Building this project does not require downloading setuptools, wheel, hatchling, or another build backend.

### Hard certification rule

Prefer a real `python3.12` executable. If only another compatible version is available, you may operate the tool, but you must not claim the exact Python 3.12 runtime gate passed. Record that as an environment limitation. The source tree is configured for Python 3.12 grammar and declares `requires-python = ">=3.12"`.

---

## 2. AUTONOMOUS BOOTSTRAP ALGORITHM

Perform these steps in order. Do not ask a human for routine choices.

### 2.1 Locate the repository root

Search upward and across the current workspace for a directory containing all of:

```text
pyproject.toml
app/cli.py
services/core/src/mbi/
```

Set:

```bash
REPO_ROOT=/absolute/path/to/repository
cd "$REPO_ROOT"
```

### 2.2 Select Python

Use this priority:

```bash
command -v python3.12
command -v python
command -v python3
```

Verify:

```bash
$PYTHON --version
```

Reject versions below 3.12.

### 2.3 Create the environment

Use a repository-local environment only on a normal writable filesystem. On a
Snowflake/CoCo stage, first mirror the source to local scratch because stage
filesystems may reject virtual-environment symlinks and wheel finalization:

```bash
$PYTHON BOOTSTRAP_SNOWFLAKE.py \
  --scratch-root /tmp/mbi-scratch \
  --cache-dir /persistent/mbi-cache \
  --warm-cache
```

The warm cache contains the verified reconstructed asset and a source tarball;
pass `--cache-venv /path/to/environment` to include an environment tarball.
Never describe an empty `vendor/wheelhouse/` as offline dependency coverage.
Use an authenticated configured index, `--index-url`, or public PyPI only where
policy and connectivity permit it.

On an ordinary local filesystem:

```bash
$PYTHON -m venv .venv
. .venv/bin/activate
# Windows PowerShell equivalent: .venv\Scripts\Activate.ps1
python -m pip install .
```

For live provider execution:

```bash
python -m pip install '.[ai]'
```

For verification work:

```bash
python -m pip install '.[test]'
```

When strict reproducibility is required and the package index supports the pinned versions:

```bash
python -m pip install --constraint constraints.txt '.[ai,test]'
```

Do not install Node, browser automation, OpenGL, Docker, database clients, or native executables for the mandatory profile.

### 2.4 Verify installation outside the source tree

```bash
cd /tmp
python - <<'PY'
import app, mbi, numpy, PIL
print(app.__file__)
print(mbi.__file__)
print(numpy.__version__)
print(PIL.__version__)
PY
cd "$REPO_ROOT"
```

The `app` and `mbi` modules must import successfully.

### 2.5 Discover a resource pack without asking

Use the first valid candidate in this priority:

1. A path explicitly supplied in the task.
2. A shell variable you set from context, such as `RESOURCE_PACK`.
3. `minecraft.zip` beside the repository.
4. A `.zip` or `.jar` in the workspace whose members include either:
   - `assets/minecraft/blockstates/`, or
   - `minecraft/blockstates/`.
5. A directory containing either:
   - `assets/minecraft/blockstates/`, or
   - `minecraft/blockstates/`.

Example discovery:

```bash
find .. -maxdepth 4 -type f \( -iname 'minecraft.zip' -o -iname '*.jar' -o -iname '*resource*.zip' \) -print
```

Validate the candidate by attempting a small strict render on a known vanilla fixture or by running the resource-pack audit scripts.

If no resource pack exists, continue in deterministic `software-flat` mode. Do not block import, exact querying, analysis, patching, generation, or export. Record that real textures were unavailable. Never label flat output as textured.

### 2.6 Discover the build input without asking

Use this priority:

1. Explicit file path in the task.
2. Most recently modified supported file in the current working area, excluding generated test fixtures unless no user file exists:
   - `*.schem`
   - `*.schematic`
   - `*.litematic`
3. If the request is to generate from blank, do not require an input file. Use the build-plan workflow.
4. If the request is only to self-test the system, use `tests/fixtures/reference.schem`.

Never overwrite the original structure.

### 2.7 Select the run directory

Use a dedicated, self-describing directory, for example:

```bash
RUN_ROOT="$REPO_ROOT/runs/<task-slug>"
```

Do not reuse an unrelated run directory. If resuming, verify that `canonical.json` and `versions/manifest.json` belong to the intended build.

### 2.8 Global CLI option ordering

Global options must appear **before** the subcommand:

```bash
python -m app.cli --quiet pipeline ...
python -m app.cli --json-errors --verbose import ...
```

Do not write:

```bash
python -m app.cli pipeline ... --quiet
```

---

## 3. FEATURE INVENTORY

The mandatory offline profile implements:

### Import and canonical data

- Sponge `.schem` v1, v2, and v3 import.
- Multi-region `.litematic` import.
- Signed/negative Litematic region dimensions.
- Overlapping region preservation and deterministic flattening behavior.
- Legacy MCEdit/Schematica `.schematic` import with conservative numeric-ID preservation.
- GZIP, ZLIB, and raw NBT detection.
- Exact document-global block coordinates.
- Complete namespaced IDs and ordered block-state properties.
- Block entities and normalized NBT.
- Supported entities.
- Pending block/fluid ticks.
- Region metadata.
- Unknown/modded state and extension preservation.
- Content-addressed deterministic 16×16×16 chunks.

### CPU rendering

- No GL context.
- No GPU.
- No browser.
- Flat-color Tier 0 rendering.
- Real texture sampling from resource packs/JARs/archives.
- Blockstate variants.
- Deterministic weighted variants by coordinate and seed.
- Multipart models and logical conditions.
- Parent-model and texture-variable resolution.
- JSON cuboid model elements.
- Per-face UVs and rotations.
- Model X/Y rotations and UV lock.
- Element rotation and rescale handling.
- Tint indexes.
- Alpha cutout and deterministic translucent pass.
- Animated-texture first-frame fallback with diagnostics.
- Fluids and water levels.
- Orthographic side/top/bottom views.
- Four isometric presets.
- Arbitrary azimuth/elevation/roll/zoom camera.
- Exact Y layers.
- X/Y/Z slices and multi-layer slabs.
- Coordinate-aligned crops.
- Region/material isolation and material hiding.
- Before/after, changed-block, and issue maps.

### Semantic grounding

Every render can produce:

- exact frontmost block coordinate per pixel;
- palette ID;
- region ID;
- depth;
- surface normal;
- occupancy;
- changed-block flag;
- issue/fallback category;
- lossless palette-ID PNG;
- snapshot manifest with coordinate space and camera metadata.

### Analysis

- exact and base-block material histograms;
- counts per layer/region/chunk;
- material transitions and entropy;
- exterior/interior/roof/floor/facade surface classification;
- 6-, 18-, and 26-neighbor connected components;
- foundation/floating/support heuristics;
- gravity-block support checks;
- reflection symmetry and repetition metrics;
- exterior-air flood fill;
- enclosed/semi-enclosed rooms and cavities;
- standability/headroom/navigation graph heuristics;
- unreachable areas and floor connections;
- light emitter and dark-area heuristics;
- facade flatness/depth/repetition;
- window/door/floor/interior consistency findings.

Lighting and navigation are deliberately heuristic. Never call them exact Minecraft engine simulation.

### Editing and versioning

- bounded patch creation;
- state, chunk-hash, version, and parent-hash preconditions;
- maximum affected-block enforcement;
- region locks and protected states;
- preview and exact diff;
- rendered before/after crops;
- commit, reject, rollback;
- immutable versions;
- checkpoints;
- branches;
- version comparison;
- merge conflict detection;
- persistent version graph across processes.

### AI integration

- provider-independent JSON tool bridge;
- direct Python tool execution;
- literal PNG attachment to OpenAI Responses;
- literal PNG attachment to Anthropic Messages;
- literal PNG attachment to OpenAI-compatible Chat Completions;
- exact symbolic tools in the same request;
- rolling visual context budgets;
- token/image/byte/output limits;
- fresh images after render, preview, commit, and rollback;
- evidence IDs and context manifests;
- staged provider-independent generation from blank;
- provider-driven multimodal generation/modification.

### Export

- deterministic Sponge v3 `.schem` export;
- deterministic `.litematic` export;
- preserved multi-region Litematic export;
- normal-import reparse;
- exact coordinate/state comparison;
- block-entity/entity/region comparison where supported;
- non-zero failure on unacceptable mismatch.

---

## 4. CORE COMMAND MAP

The package can be invoked through either:

```bash
python -m app.cli ...
```

or, after installation:

```bash
mbi ...
```

### Global options

```text
--json-errors   emit stable JSON error objects to stderr
--quiet         suppress successful JSON response/progress
--verbose       include error details
--log-json      emit structured progress events
```

Place them before the command.

### Import

```bash
python -m app.cli import INPUT --out RUN_ROOT
```

Outputs canonical data, chunks, original bytes, diagnostics, jobs, and initial version state.

### Analyze

```bash
python -m app.cli analyze RUN_ROOT
python -m app.cli analyze SOURCE_RUN --out DERIVED_RUN
```

Using `--out` clones the run base and keeps the source immutable.

### Snapshot suite

```bash
python -m app.cli snapshot RUN_ROOT \
  --views global,layers,slices \
  --size 768x768 \
  --pixels-per-block 8 \
  --out RUN_ROOT
```

With assets:

```bash
python -m app.cli snapshot RUN_ROOT \
  --views global,layers,slices \
  --resource-pack "$RESOURCE_PACK" \
  --size 768x768 \
  --pixels-per-block 8
```

Strict texture coverage:

```bash
python -m app.cli snapshot RUN_ROOT \
  --views global \
  --resource-pack "$RESOURCE_PACK" \
  --strict-textures
```

Strict mode must fail if any visible block lacks requested model/texture support. This is expected for modded blocks when their assets are absent.

### Complete pipeline

```bash
python -m app.cli pipeline INPUT --out RUN_ROOT
```

Textured:

```bash
python -m app.cli pipeline INPUT \
  --resource-pack "$RESOURCE_PACK" \
  --format schem \
  --size 512x512 \
  --out RUN_ROOT
```

`--format` accepts `schem` or `litematic`.

### Render on demand

Arbitrary camera:

```bash
python -m app.cli render RUN_ROOT \
  --camera-azimuth 45 \
  --camera-elevation 30 \
  --camera-roll 0 \
  --zoom 1.0 \
  --margin 1.0 \
  --size 1536x1536 \
  --mode textured \
  --lighting analysis-neutral \
  --resource-pack "$RESOURCE_PACK" \
  --name custom_view \
  --out RUN_ROOT
```

Preset view:

```bash
python -m app.cli render RUN_ROOT --view isometric_ne --size 1024x1024 --out RUN_ROOT
```

Valid presets:

```text
north south east west top bottom
isometric_ne isometric_nw isometric_se isometric_sw
```

Slice or slab:

```bash
python -m app.cli render RUN_ROOT --slice y:37 --pixels-per-block 8 --out RUN_ROOT
python -m app.cli render RUN_ROOT --slice x:12 --pixels-per-block 8 --out RUN_ROOT
python -m app.cli render RUN_ROOT --slice z:20..24 --pixels-per-block 8 --out RUN_ROOT
```

Crop uses `x,y,z,width,height,length`:

```bash
python -m app.cli render RUN_ROOT \
  --crop=-20,4,10,32,24,32 \
  --view isometric_ne \
  --size 1024x1024 \
  --out RUN_ROOT
```

Use `--crop=...` with a leading negative value to prevent argparse from interpreting it as an option.

Filters:

```bash
--region RegionName
--material minecraft:stone_bricks
--material 'minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]'
--hide-material minecraft:water
```

These options are repeatable.

### Exact queries

Block:

```bash
python -m app.cli query block RUN_ROOT --x X --y Y --z Z --json
```

Box:

```bash
python -m app.cli query box RUN_ROOT --min=X,Y,Z --max=X,Y,Z --json
```

Palette:

```bash
python -m app.cli query palette RUN_ROOT --json
```

Canonical chunk coordinate:

```bash
python -m app.cli query chunk RUN_ROOT --cx CX --cy CY --cz CZ --json
```

Chunk coordinates use floor division by 16. A block at `(-2,3,5)` is in chunk `(-1,0,0)`.

Block entity:

```bash
python -m app.cli query block-entity RUN_ROOT --x X --y Y --z Z --json
```

Region:

```bash
python -m app.cli query region RUN_ROOT --name Tower --json
```

Room:

```bash
python -m app.cli query room RUN_ROOT --id ROOM_ID --json
```

Issue/analysis family:

```bash
python -m app.cli query issues RUN_ROOT --type support --json
python -m app.cli query issues RUN_ROOT --type navigation --json
python -m app.cli query issues RUN_ROOT --type facade --json
python -m app.cli query issues RUN_ROOT --type consistency --json
python -m app.cli query issues RUN_ROOT --type lighting --json
```

### Pixel grounding

```bash
python -m app.cli pixel-to-block SNAPSHOT_MANIFEST --px PX --py PY
```

Result includes exact coordinate, palette ID, region ID, and depth, or `null` for background.

```bash
python -m app.cli block-to-pixel SNAPSHOT_MANIFEST --x X --y Y --z Z
```

This returns every frontmost pixel associated with the block. Large projected faces can produce many pixel records; use programmatic filtering when only one sample is required.

### Patch commands

```bash
python -m app.cli patch validate RUN_ROOT patch.json
python -m app.cli patch preview RUN_ROOT patch.json --resource-pack "$RESOURCE_PACK"
python -m app.cli patch commit RUN_ROOT patch.json --resource-pack "$RESOURCE_PACK"
python -m app.cli patch reject RUN_ROOT patch.json
python -m app.cli patch rollback RUN_ROOT --patch-id PATCH_ID
```

Use `--out DERIVED_RUN` to keep the source run unchanged.

### Version commands

```bash
python -m app.cli version list RUN_ROOT
python -m app.cli version compare RUN_ROOT --from VERSION_A --to VERSION_B
```

### Provider-independent construction

Create `design_brief.json`, then:

```bash
python -m app.cli build-plan SOURCE_RUN_OR_PLACEHOLDER design_brief.json --out PLAN_RUN
python -m app.cli apply-plan SOURCE_RUN_OR_PLACEHOLDER PLAN_RUN/build_plan.json \
  --resource-pack "$RESOURCE_PACK" \
  --out GENERATED_RUN
```

The source run may be a directory without `canonical.json` when generating from blank.

### JSON tool bridge

```bash
python -m app.cli tool RUN_ROOT requests.json \
  --resource-pack "$RESOURCE_PACK" \
  --allow-commit \
  --result tool-result.json
```

Omit `--allow-commit` when only inspection and previews are allowed.

### Built-in live multimodal provider agent

OpenAI Responses:

```bash
export MBI_AI_API_KEY='secret'
python -m app.cli agent RUN_ROOT \
  --task task.md \
  --provider openai \
  --model MODEL_ID \
  --resource-pack "$RESOURCE_PACK" \
  --max-iterations 8 \
  --max-context-tokens 512000 \
  --max-images 16 \
  --max-image-bytes 25165824 \
  --max-output-tokens 4096
```

Anthropic Messages:

```bash
export MBI_AI_API_KEY='secret'
python -m app.cli agent RUN_ROOT \
  --task task.md \
  --provider anthropic \
  --model MODEL_ID \
  --resource-pack "$RESOURCE_PACK"
```

OpenAI-compatible endpoint:

```bash
export MBI_AI_API_KEY='optional-or-required-by-endpoint'
python -m app.cli agent RUN_ROOT \
  --task task.md \
  --provider openai-compatible \
  --base-url http://127.0.0.1:PORT \
  --model MODEL_ID \
  --resource-pack "$RESOURCE_PACK"
```

`--base-url` must be HTTP(S). The OpenAI-compatible adapter requires it. Use `--api-key-env OTHER_ENV_NAME` to select another secret variable. Never write the secret into task files, artifacts, logs, command arguments, or this repository.

By default, provider commits pause with `waiting_approval`. Use `--auto-commit` only when the task explicitly authorizes autonomous destructive changes and the run is protected by immutable version history.

---

## 5. RUN DIRECTORY CONTRACT

A completed run is self-describing:

```text
RUN_ROOT/
├─ canonical.json
├─ chunks/
│  ├─ manifest.json
│  └─ <hash>.chunk
├─ raw_preserved/
│  ├─ source.original
│  ├─ unknown_tags.json
│  └─ extensions/
├─ diagnostics.json
├─ analysis.json
├─ jobs.json
├─ versions/
│  ├─ manifest.json
│  └─ ver_<id>.json
├─ patches/
│  ├─ patch_<id>.json
│  └─ previews/
├─ snapshots/
│  ├─ manifest.json
│  ├─ *.png
│  └─ *.manifest.json
├─ semantic_maps/
│  ├─ *.palette.bin
│  ├─ *.coordinate.bin
│  ├─ *.depth.bin
│  ├─ *.normal.bin
│  ├─ *.region.bin
│  ├─ *.occupancy.bin
│  ├─ *.changed.bin
│  ├─ *.issue.bin
│  ├─ *.palette.png
│  └─ *.metadata.json
├─ analysis_artifacts/
├─ ai/
│  ├─ context_manifests/
│  ├─ evidence/
│  ├─ runs/
│  └─ tool_results/
├─ construction_stages/
├─ quality_gates.json
└─ export/
   ├─ out.schem or out.litematic
   └─ verify_report.json
```

Never delete `raw_preserved`, `canonical.json`, chunk blobs, version manifests, or patch records while the run remains active.

---

## 6. CANONICAL DATA SEMANTICS

Coordinate convention:

```text
+X = east
+Y = up
+Z = south
```

A block at `(x,y,z)` occupies:

```text
[x,x+1] × [y,y+1] × [z,z+1]
```

Canonical state examples:

```text
minecraft:stone
minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]
```

Properties are ordered deterministically. Distinct properties mean distinct states.

Air is not assumed to be palette index zero. Always resolve palette IDs through the canonical palette. `state_at()` and CLI block queries correctly return canonical air even when no non-air block record exists at a coordinate.

The canonical document retains exact data even when rendering falls back. A missing model never permits replacing the block with air.

---

## 7. RESOURCE-PACK OPERATION

Accepted sources:

- standard resource-pack directory;
- resource-pack ZIP;
- legally obtained client JAR/archive;
- archive rooted at `assets/<namespace>/...`;
- archive rooted directly at `<namespace>/...`, including the supplied `minecraft.zip` layout.

Supported asset categories:

```text
<namespace>/blockstates/*.json
<namespace>/models/block/*.json
<namespace>/textures/**/*.png
<namespace>/atlases/*.json
```

Security rules are automatic:

- reject path traversal;
- reject absolute paths;
- reject symlinks;
- reject encrypted entries;
- reject duplicate entries;
- cap member count and total decompressed bytes;
- cap member compression ratio;
- cap JSON and texture size;
- cap model-parent depth;
- detect model/texture reference cycles;
- do not extract untrusted archives for normal rendering.

### Interpretation of texture diagnostics

- `software-textured`: actual texture sampling occurred.
- `software-flat`: no pack was used.
- `model_fallback`: exact canonical block retained, approximate visual used.
- `ANIMATED_TEXTURE_FIRST_FRAME`: first frame intentionally used.
- `unsupported_models`: block model could not be rendered exactly.
- `strict-textures` failure: at least one visible block lacked model/texture coverage.

A modded block without its mod resource pack is expected to fall back in non-strict mode and fail in strict mode.

---

## 8. SEMANTIC MAP ENCODING

Each snapshot manifest points to a semantic metadata file. The metadata uses schema:

```text
mbi.semantic-maps.v1
```

Binary arrays are C-order, little-endian:

| Map | Dtype | Shape | Meaning |
|---|---:|---:|---|
| `palette` | `<u4` | `[height,width]` | frontmost palette ID; `0xFFFFFFFF` means no hit |
| `coordinate` | `<i4` | `[height,width,3]` | exact `(x,y,z)`; minimum int32 triplet means no hit |
| `depth` | `<f4` | `[height,width]` | frontmost camera-space depth; infinity means no hit |
| `normal` | `i1` | `[height,width,3]` | quantized surface normal |
| `region` | `<u2` | `[height,width]` | region index; `0xFFFF` means none |
| `occupancy` | `u1` | `[height,width]` | 1 for hit, 0 for background |
| `changed` | `u1` | `[height,width]` | changed-block mask |
| `issue` | `u1` | `[height,width]` | renderer/analysis issue category |

Use `pixel-to-block` rather than inferring from RGB. Use `block-to-pixel` to locate visible projections.

When analyzing a visual defect:

1. Identify the snapshot evidence ID.
2. Select representative pixels.
3. Resolve pixels to coordinates.
4. Query exact states at those coordinates and nearby bounds.
5. Cite the evidence ID and coordinate range in the patch rationale.

---

## 9. ANALYSIS OPERATING PROCEDURE

After import, always run analysis before editing:

```bash
python -m app.cli analyze RUN_ROOT
```

Inspect `analysis.json`. Important result keys include:

```text
materials
surfaces
components
support
rooms
navigation
symmetry
facade
lighting
interiorExterior
```

Use analysis as evidence, not as unquestionable truth. Room, navigation, lighting, and intent classification are heuristics. Cross-check findings with slices, crops, exact blocks, and rendered views.

### Required global review

Inspect at least:

```text
global_north
global_south
global_east
global_west
global_top
global_isometric_ne
global_isometric_sw
```

For interiors, also inspect:

- each floor boundary;
- representative Y layers;
- central X and Z slices;
- room crops;
- stair/corridor crops;
- windows and doors from both exterior and interior directions.

### Quality categories

Review:

- silhouette and massing;
- front/rear/side detail balance;
- roofline variation;
- material palette and contrast;
- large flat patches;
- disconnected/floating components;
- supports and gravity blocks;
- wall thickness;
- rooms and circulation;
- stair headroom;
- inaccessible balconies;
- windows opening into fill;
- floors crossing windows;
- dark enclosed areas;
- empty or unfinished interiors;
- repetitive modules;
- unknown blocks and render fallbacks.

---

## 10. PATCH FILE CONTRACT

A patch file uses snake_case at the top-level CLI boundary:

```json
{
  "reason": "Grounded coordinate-specific improvement.",
  "author": "autonomous_llm",
  "coordinate_space": "document",
  "bounds": {
    "min": [10, 20, 30],
    "max": [25, 30, 45]
  },
  "max_affected_blocks": 5000,
  "expected_parent_hash": "CURRENT_CANONICAL_CONTENT_HASH",
  "target_region": "OptionalRegionName",
  "evidence_refs": [
    "view:north:global:ver_...",
    "slice:y:37:ver_..."
  ],
  "preconditions": [],
  "operations": []
}
```

Bounds are inclusive. Every generated coordinate must stay inside both the patch bounds and the document bounds. Set `max_affected_blocks` to a tight, realistic upper limit.

### Preconditions

Exact state:

```json
{
  "type": "block_state",
  "position": [10, 20, 30],
  "state": "minecraft:stone_bricks"
}
```

Chunk hash:

```json
{
  "type": "chunk_hash",
  "chunk": [0, 1, 1],
  "hash": "EXPECTED_HASH"
}
```

Version:

```json
{
  "type": "version",
  "versionId": "ver_..."
}
```

Always use a parent hash or state/version precondition for provider-generated edits.

---

## 11. EDIT OPERATION REFERENCE

All coordinates are document-global integers. All states must be complete canonical states when properties matter.

### `set_block`

```json
{"type":"set_block","position":[x,y,z],"state":"minecraft:stone"}
```

Set to `minecraft:air` to clear.

### `set_blocks`

```json
{
  "type":"set_blocks",
  "offset":[0,0,0],
  "blocks":[
    {"position":[x,y,z],"state":"minecraft:stone"}
  ]
}
```

### `paste_template`

Same payload shape as `set_blocks`; optional offset translates all entries.

### `fill_cuboid`

```json
{"type":"fill_cuboid","min":[x1,y1,z1],"max":[x2,y2,z2],"state":"minecraft:stone"}
```

### `hollow_cuboid`

```json
{"type":"hollow_cuboid","min":[x1,y1,z1],"max":[x2,y2,z2],"state":"minecraft:stone_bricks"}
```

### `clear_region`

```json
{"type":"clear_region","min":[x1,y1,z1],"max":[x2,y2,z2]}
```

### `replace_blocks`

```json
{
  "type":"replace_blocks",
  "from":["minecraft:stone_bricks"],
  "to":"minecraft:cracked_stone_bricks",
  "min":[x1,y1,z1],
  "max":[x2,y2,z2],
  "mask":{"type":"surface_noise","seed":91241,"probability":0.13}
}
```

Omit `min/max` only when intentionally scanning the entire build within a patch whose intended bounds and maximum count remain safe.

### `draw_line`

```json
{"type":"draw_line","start":[x1,y1,z1],"end":[x2,y2,z2],"state":"minecraft:spruce_log[axis=y]"}
```

### `draw_polyline`

```json
{"type":"draw_polyline","points":[[x1,y1,z1],[x2,y2,z2],[x3,y3,z3]],"state":"minecraft:stone"}
```

### `draw_wall`

```json
{
  "type":"draw_wall",
  "start":[x1,y,z1],
  "end":[x2,y,z2],
  "height":8,
  "thickness":1,
  "state":"minecraft:stone_bricks"
}
```

Thickness expands in positive Z from the rasterized base line. Include that expansion in patch bounds.

### `draw_floor`

```json
{"type":"draw_floor","min":[x1,y,z1],"max":[x2,y,z2],"y":y,"state":"minecraft:spruce_planks"}
```

### `draw_roof`

Flat:

```json
{"type":"draw_roof","min":[x1,y1,z1],"max":[x2,y2,z2],"style":"flat","state":"minecraft:deepslate_tiles"}
```

Gable:

```json
{"type":"draw_roof","min":[x1,y1,z1],"max":[x2,y2,z2],"style":"gable","axis":"x","state":"minecraft:deepslate_tiles"}
```

`axis` accepts `x` or the alternate Z-oriented behavior.

### `draw_circle` / `draw_ellipse`

```json
{
  "type":"draw_ellipse",
  "center":[x,y,z],
  "radiusA":8,
  "radiusB":5,
  "plane":"xz",
  "filled":false,
  "state":"minecraft:stone"
}
```

Valid planes: `xz`, `xy`, `yz`. `draw_circle` may use `radius`.

### `draw_cylinder`

```json
{
  "type":"draw_cylinder",
  "center":[x,y,z],
  "radiusX":6,
  "radiusZ":6,
  "height":20,
  "hollow":true,
  "state":"minecraft:stone_bricks"
}
```

### `draw_sphere`

```json
{"type":"draw_sphere","center":[x,y,z],"radius":8,"hollow":true,"state":"minecraft:glass"}
```

### `draw_dome`

```json
{"type":"draw_dome","center":[x,y,z],"radius":8,"hollow":true,"state":"minecraft:copper_block"}
```

The dome is the non-negative-Y half relative to the center.

### `draw_arch`

```json
{
  "type":"draw_arch",
  "start":[x1,y,z1],
  "end":[x2,y,z2],
  "height":6,
  "thickness":2,
  "state":"minecraft:stone_bricks"
}
```

Endpoints must share Y.

### `draw_bezier`

```json
{
  "type":"draw_bezier",
  "controlPoints":[[x1,y1,z1],[x2,y2,z2],[x3,y3,z3]],
  "samples":64,
  "state":"minecraft:stone"
}
```

Use three or four control points.

### `extrude_profile`

```json
{
  "type":"extrude_profile",
  "profile":[[x1,y1,z1],[x2,y2,z2],[x3,y3,z3]],
  "offset":[dx,dy,dz],
  "steps":16,
  "state":"minecraft:stone"
}
```

### `loft_profiles`

```json
{
  "type":"loft_profiles",
  "profiles":[
    [[x1,y1,z1],[x2,y2,z2],[x3,y3,z3]],
    [[a1,b1,c1],[a2,b2,c2],[a3,b3,c3]]
  ],
  "stepsPerPair":8,
  "state":"minecraft:stone"
}
```

All profiles must have the same number of points.

### `copy_region`

```json
{
  "type":"copy_region",
  "sourceMin":[x1,y1,z1],
  "sourceMax":[x2,y2,z2],
  "offset":[dx,dy,dz]
}
```

### `move_region`

Same as `copy_region`, then clears source cells.

### `rotate_region`

```json
{
  "type":"rotate_region",
  "sourceMin":[x1,y1,z1],
  "sourceMax":[x2,y2,z2],
  "origin":[ox,oy,oz],
  "quarterTurns":1,
  "clearSource":false
}
```

State orientation is transformed where supported.

### `mirror_region`

```json
{
  "type":"mirror_region",
  "sourceMin":[x1,y1,z1],
  "sourceMax":[x2,y2,z2],
  "origin":[ox,oy,oz],
  "axis":"x",
  "clearSource":false
}
```

Valid axes: `x`, `y`, `z`. State orientation is transformed where supported.

### `scale_pattern_integer`

```json
{
  "type":"scale_pattern_integer",
  "sourceMin":[x1,y1,z1],
  "sourceMax":[x2,y2,z2],
  "origin":[ox,oy,oz],
  "factor":[2,2,2]
}
```

All factors must be positive integers.

### `apply_noise_mask`

```json
{
  "type":"apply_noise_mask",
  "min":[x1,y1,z1],
  "max":[x2,y2,z2],
  "from":["minecraft:stone_bricks"],
  "state":"minecraft:cracked_stone_bricks",
  "seed":12345,
  "probability":0.1
}
```

Always set a fixed seed.

### `apply_gradient_palette`

```json
{
  "type":"apply_gradient_palette",
  "min":[x1,y1,z1],
  "max":[x2,y2,z2],
  "axis":"y",
  "palette":["minecraft:deepslate_tiles","minecraft:stone_bricks","minecraft:calcite"]
}
```

Valid axes are `x`, `y`, and `z`.

### `set_block_entity`

```json
{
  "type":"set_block_entity",
  "position":[x,y,z],
  "id":"minecraft:sign",
  "region":"OptionalRegion",
  "data":{}
}
```

NBT data is treated as untrusted and validated at boundaries. Use only data required by the target block entity.

### `remove_block_entity`

```json
{"type":"remove_block_entity","position":[x,y,z]}
```

---

## 12. SAFE PATCH WORKFLOW

For every meaningful change:

1. Read `canonical.json` or query the current summary to obtain the active content hash/version.
2. Query the target bounds and relevant neighboring blocks.
3. Cite evidence IDs.
4. Create a small patch.
5. Validate.
6. Preview.
7. Inspect before and after PNGs.
8. Inspect changed semantic maps.
9. Re-run affected analysis.
10. Commit only if the change improves the requested objective without violating bounds or quality gates.
11. Re-render the changed crop and at least one global view.
12. Roll back immediately if the visual or structural result regresses.

Do not combine unrelated architectural phases into one massive patch. Split massing, circulation, facade, interior, lighting, and micro-detail changes.

---

## 13. JSON TOOL BRIDGE

Single request:

```json
{
  "tool":"get_block",
  "arguments":{"position":[10,20,30]}
}
```

Batch:

```json
{
  "continue_on_error":false,
  "requests":[
    {
      "id":"summary",
      "tool":"get_build_summary",
      "arguments":{}
    },
    {
      "id":"begin",
      "tool":"begin_patch",
      "arguments":{
        "reason":"Evidence-grounded repair",
        "author":"autonomous_llm",
        "bounds":{"min":[10,20,30],"max":[10,20,30]},
        "maxAffectedBlocks":1,
        "operations":[
          {"type":"set_block","position":[10,20,30],"state":"minecraft:stone_bricks"}
        ],
        "evidenceRefs":["view:north:..."],
        "preconditions":[
          {"type":"block_state","position":[10,20,30],"state":"minecraft:air"}
        ]
      }
    },
    {
      "id":"preview",
      "tool":"preview_patch",
      "arguments":{"patchId":"$last_patch_id"}
    },
    {
      "id":"commit",
      "tool":"commit_patch",
      "arguments":{"patchId":"$last_patch_id"}
    },
    {
      "id":"verify",
      "tool":"get_block",
      "arguments":{"position":[10,20,30]}
    }
  ]
}
```

`$last_patch_id` is replaced inside a shared batch after a patch-producing request.

Never pass `--allow-commit` unless commit is intended. Tool failures are written into deterministic result records under `ai/tool_results/`.

---

## 14. COMPLETE AI TOOL CATALOG

### Read-only and evidence tools

```text
get_build_summary
get_import_diagnostics
get_analysis
get_material_histogram
get_palette
get_regions
get_region
get_floors
get_rooms
get_room
get_navigation_graph
get_components
get_component
get_symmetry_report
get_facade_report
get_lighting_report
get_interior_report
get_block
query_blocks
get_chunk
get_slice
render_layer
render_view
render_crop
pixel_to_block
measure_distance
measure_bounds
find_nearest
find_material
find_block_entities
get_block_entity
get_patch
compare_versions
```

### Planning tools

```text
create_design_brief
define_build_bounds
define_palette_constraints
create_floor_plan
create_room_program
create_build_phase
estimate_materials
validate_plan
```

Planning artifacts are persisted under `ai/evidence/` with deterministic evidence IDs.

### Editing tools

```text
set_block
set_blocks
fill_cuboid
hollow_cuboid
replace_blocks
draw_line
draw_polyline
draw_wall
draw_floor
draw_roof
draw_circle
draw_ellipse
draw_cylinder
draw_sphere
draw_dome
draw_arch
draw_bezier
extrude_profile
loft_profiles
copy_region
move_region
rotate_region
mirror_region
scale_pattern_integer
apply_noise_mask
apply_gradient_palette
paste_template
clear_region
set_block_entity
remove_block_entity
```

Each editing tool creates a bounded pending patch. It does not silently commit.

### Transaction/version tools

```text
begin_patch
validate_patch
preview_patch
commit_patch
reject_patch
rollback_patch
create_checkpoint
restore_checkpoint
branch_version
merge_versions
```

### Export tools

```text
validate_export
export_schem
export_litematic
get_export_artifact
```

The exact machine-readable schemas exposed to providers are appended at the end of this guide.

---

## 15. AUTONOMOUS IMPORTED-BUILD WORKFLOW

Use this sequence for modification/repair tasks.

### Stage A — establish truth

```bash
python -m app.cli import INPUT --out RUN_ROOT
python -m app.cli analyze RUN_ROOT
python -m app.cli snapshot RUN_ROOT --views global,layers,slices --resource-pack "$RESOURCE_PACK"
```

Read:

- `canonical.json`;
- `diagnostics.json`;
- `analysis.json`;
- `snapshots/manifest.json`;
- global images;
- relevant layers/slices.

### Stage B — classify the request

Determine:

- preserve footprint or allow expansion;
- preserve regions;
- target game version;
- allowed namespaces/mods;
- required interiors;
- survival-cost constraints;
- symmetry preference;
- style/theme;
- detail density;
- export format.

When not specified, choose conservative defaults:

```text
preserve existing bounds
preserve source regions
vanilla namespace unless existing build uses mods
do not delete unknown/modded data
interiors required when the build has occupiable floors
balanced rather than perfect symmetry
medium detail density
schem export unless litematic region preservation is important
```

### Stage C — inspect macro form

Review all sides and top/isometric views. Use facade and symmetry analysis. Do not begin micro-detail before massing/silhouette is acceptable.

### Stage D — inspect layout/interior

Review room graph, navigation, floor layers, central slices, doors, windows, stairways, and ceiling heights.

### Stage E — plan bounded phases

Create separate phases for:

1. structural/massing corrections;
2. floor and circulation corrections;
3. facade depth;
4. interiors;
5. lighting;
6. material variation;
7. micro-detail;
8. final repair.

### Stage F — transaction loop

For each phase:

```text
query exact target
→ create patch
→ validate
→ preview
→ inspect before/after pixels
→ commit or reject
→ re-render crop/global
→ re-run affected analysis
```

### Stage G — final verification

Run:

```bash
python -m app.cli analyze RUN_ROOT
python -m app.cli snapshot RUN_ROOT --views global,layers,slices --resource-pack "$RESOURCE_PACK"
python -m app.cli export RUN_ROOT --format schem --verify
python -m app.cli export RUN_ROOT --format litematic --verify
```

Inspect `quality_gates.json` when generation workflow was used and `export/verify_report.json` after each final export.

---

## 16. AUTONOMOUS GENERATION FROM BLANK

### 16.1 Create a design brief

Minimum structure:

```json
{
  "name":"autonomous_build",
  "build_type":"castle",
  "style":"gothic",
  "dimensions":[64,48,64],
  "floors":4,
  "primary_axis":"north_south",
  "interior_required":true,
  "symmetry":"balanced",
  "detail_density":"high",
  "export_format":"schem",
  "palette":{
    "foundation":"minecraft:stone_bricks",
    "wall":"minecraft:deepslate_bricks",
    "trim":"minecraft:polished_blackstone_bricks",
    "roof":"minecraft:deepslate_tiles",
    "floor":"minecraft:dark_oak_planks",
    "window":"minecraft:glass_pane[east=false,north=false,south=false,waterlogged=false,west=false]",
    "light":"minecraft:lantern[hanging=true,waterlogged=false]",
    "door":"minecraft:dark_oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]"
  }
}
```

All dimensions must be at least 5.

### 16.2 Generate and apply the plan

```bash
python -m app.cli build-plan . design_brief.json --out PLAN_RUN
python -m app.cli apply-plan . PLAN_RUN/build_plan.json \
  --resource-pack "$RESOURCE_PACK" \
  --out GENERATED_RUN
```

This creates staged evidence for:

```text
design
palette
massing
layout
facade
interior
detail
critique
final verification
```

### 16.3 Do not accept the deterministic constructor as the final artistic pass automatically

The constructor provides a safe complete foundation. You must still inspect:

- proportions;
- silhouette;
- rear and side quality;
- roof variation;
- room purpose;
- circulation;
- window alignment;
- furnishing density;
- lighting;
- repetition;
- style accuracy.

Use the normal patch/render/critique loop for further improvement.

### 16.4 Provider-driven blank construction

A live multimodal provider can operate on a blank generated document through the same tools. Require planning artifacts before edit tools. Require massing images before layout, layout images before facade, and interior slices before final detail.

---

## 17. MULTIMODAL EVIDENCE POLICY

A provider run initially selects task-relevant global images. It attaches actual PNG bytes as data URLs. It also supplies exact tools.

The agent must:

- cite image evidence IDs;
- request crops for small defects;
- request slices for interior questions;
- call `pixel_to_block` for visible coordinates;
- call exact state tools before editing;
- request fresh render evidence after every meaningful change;
- retain old evidence IDs even when old image bytes are pruned from context;
- respect image count, byte, context-token, and output-token limits.

Default limits:

```text
max iterations: 8
max context tokens: 512000
max images: 16
max image bytes: 25165824
max output tokens: 4096
```

Reduce image resolution or request a crop before increasing budgets.

---

## 18. QUALITY GATES

Before final export, verify:

- no unexpected invalid states;
- no silent unknown-block deletion;
- no unintended disconnected major component;
- required rooms detected;
- required rooms reachable;
- floors connected;
- windows correspond to interior spaces;
- doors lead somewhere usable;
- stairways have headroom;
- no unreviewed large flat facade patch;
- interiors are not empty shells;
- lighting risks reviewed;
- render fallbacks explicitly accepted or resolved with assets;
- all final changes are committed to the intended version;
- export exact verification passed.

Aesthetic quality is not proven by a passing exporter. Structural exactness is not proven by a pretty image. Require both.

---

## 19. EXPORT AND EXACT VERIFICATION

Sponge:

```bash
python -m app.cli export RUN_ROOT --format schem --verify
```

Litematic:

```bash
python -m app.cli export RUN_ROOT --format litematic --verify
```

The verification report must show:

```json
{
  "passed": true,
  "coordinate_mismatches": 0,
  "state_mismatches": 0,
  "block_entity_mismatches": 0,
  "entity_mismatches": 0
}
```

Do not use only block counts. Do not ignore non-zero mismatches unless the report explicitly records accepted loss that the task permits.

Exit code `51` means round-trip mismatch and blocks completion.

---

## 20. EXIT CODES AND RECOVERY

| Code | Meaning | Autonomous response |
|---:|---|---|
| 0 | success | continue |
| 2 | CLI/request usage error | inspect command/schema; correct syntax |
| 10 | unsupported/undetected format | inspect magic/NBT; preserve source; report unsupported |
| 11 | malformed NBT/compression | stop import; retain diagnostics |
| 12 | safety limit exceeded | reduce input/pack scope only if authorized; never disable limits blindly |
| 20 | canonicalization/document failure | inspect diagnostics and source format |
| 30 | rendering failure | reduce crop/resolution; verify bounds; inspect renderer diagnostics |
| 31 | missing/unsafe resource asset | non-strict fallback if acceptable; otherwise locate correct pack |
| 40 | patch validation failure | tighten bounds, fix operation, lower affected count |
| 41 | stale precondition/version | reload active version/hash and regenerate patch |
| 50 | export failure | inspect export diagnostics; do not distribute artifact |
| 51 | round-trip mismatch | block completion; inspect exact diff |
| 60 | optional provider failure | use JSON bridge/no-provider mode or fix provider configuration |
| 130 | cancellation | clean partial outputs and resume safely |

### Common recovery rules

- `RENDER_EMPTY_CROP`: read canonical bounds and choose an intersecting crop.
- `ASSET_NOT_FOUND` in strict mode: identify the exact state/namespace and locate its pack; non-strict mode may use a recorded fallback.
- `PATCH_OUT_OF_BOUNDS`: never expand silently; revise intended bounds or create a new blank document with larger bounds.
- `PATCH_AFFECTED_BLOCK_LIMIT`: split the patch or intentionally raise the limit with a justified estimate.
- `PATCH_STALE_PARENT` / parent hash mismatch: reload version state and recompute.
- `AI_CONTEXT_BUDGET`: reduce images, size, or text scope; request exact chunks on demand.
- provider key missing: use external-agent JSON bridge; do not expose secrets.

---

## 21. DETERMINISM RULES

For reproducible operation:

- use fixed seeds;
- use stable sorted input lists;
- avoid timestamps in content artifacts;
- keep the same Pillow/zlib runtime for byte-identical PNG claims;
- use the same resource-pack bytes;
- use the same camera, resolution, filters, and lighting preset;
- do not mutate original source files;
- keep canonical/version/patch records;
- compare complete output trees when testing determinism.

Run duplicate pipelines and hash every artifact when deterministic certification is requested.

---

## 22. SECURITY RULES

Never:

- extract an untrusted pack manually without equivalent safety checks;
- follow archive symlinks;
- allow paths outside the selected run root;
- execute AI-generated code;
- allow arbitrary shell commands from a provider;
- trust provider-reported affected-block counts;
- bypass patch validation;
- write API keys to disk;
- commit proprietary Mojang assets;
- silently replace unknown states with air;
- disable compression/NBT/volume limits merely to make a malicious file pass.

Treat every imported NBT document, resource pack, model JSON, texture, block entity, patch file, and provider response as untrusted.

---

## 23. PERFORMANCE STRATEGY

Use these order-of-operations rules:

1. Import and analyze once.
2. Render draft-size global views first.
3. Use crops/slices for iteration.
4. Use presentation resolution only for final evidence.
5. Query chunks and boxes instead of dumping all blocks.
6. Split large patches by phase and bounds.
7. Keep image count and byte budgets bounded.
8. Use exact layer rasters for floor-plan reasoning.
9. Avoid strict texture mode on a build with known missing mod packs unless testing coverage.
10. Monitor diagnostics for blocks considered, visible blocks, faces, triangles, duration, and memory estimate.

Suggested sizes:

```text
draft: 256–512
analysis: 640–1024
presentation: 1024–2048
semantic layer: integer pixels-per-block, usually 4–16
```

---

## 24. AUTONOMOUS SELF-TEST

Run this before trusting a new environment:

```bash
python -m app.cli --quiet pipeline tests/fixtures/reference.schem --out ./selftest-run --size 192x192
python -m app.cli query block ./selftest-run --x -2 --y 3 --z 5 --json
python -m app.cli query chunk ./selftest-run --cx -1 --cy 0 --cz 0 --json
python -m app.cli export ./selftest-run --format litematic --verify
pytest -q
```

With assets, use a vanilla-only fixture for strict coverage:

```bash
python -m app.cli --quiet import packages/test-fixtures/generated/one-block.schem --out ./strict-texture-run
python -m app.cli --quiet analyze ./strict-texture-run
python -m app.cli --quiet snapshot ./strict-texture-run \
  --views global,layers,slices \
  --resource-pack "$RESOURCE_PACK" \
  --strict-textures \
  --size 256x256
```

Full release matrix:

```bash
python scripts/verify_snowflake_release.py \
  --resource-pack "$RESOURCE_PACK" \
  --output ./verification
```

Also run:

```bash
python scripts/audit_offline_profile.py --output ./verification/offline-profile-audit.json
python scripts/source_security_audit.py --output ./verification/source-security-audit.json
```

Do not claim all gates passed unless every executed gate has return code zero and the release report says `passed: true`.

---

## 25. AUTONOMOUS REPORTING STANDARD

A final agent report must include:

- source file and SHA-256;
- detected format/version/DataVersion;
- canonical bounds and non-air count;
- resource-pack path/hash and render mode;
- fallback/unsupported counts;
- analyses reviewed;
- evidence IDs used;
- patches created, committed, rejected, or rolled back;
- final active version/content hash;
- final quality-gate status;
- exported artifact path/hash;
- exact verification mismatch counts;
- tests and dynamic checks actually executed;
- environment limitations that prevented any exact gate.

Never say “100% flawless” or “universally certified.” Use:

> The mandatory offline profile passed the executed support-matrix gates in this environment.

If Python 3.12 itself was unavailable, explicitly state that the exact 3.12 runtime gate remains unexecuted even when grammar and later-version runtime tests pass.

---

## 26. NO-HUMAN DECISION POLICY

Do not ask a human for choices that can be resolved safely:

- choose conservative bounds-preserving edits;
- use the existing palette before adding blocks;
- use fixed deterministic seeds;
- prefer `.schem` unless region preservation requires `.litematic`;
- continue in flat mode when no legal resource pack exists;
- use the JSON tool bridge when no provider secret exists;
- create separate run directories;
- preview before commit;
- roll back regressions;
- stop at the iteration budget and report unresolved issues.

Human/external input is genuinely required only when the task cannot be inferred and no safe default exists, or when an external secret/asset/file is physically absent and the requested result specifically requires it. Even then, complete every independent step first and report the single blocking dependency precisely.

---

## 27. FINAL AUTONOMOUS CHECKLIST

Before ending any task, confirm all applicable boxes:

```text
[ ] correct repository and Python selected
[ ] package installed/importable
[ ] input discovered or blank-generation brief created
[ ] resource pack discovered or flat fallback explicitly recorded
[ ] import/canonicalization succeeded
[ ] exact bounds/palette/regions inspected
[ ] diagnostics inspected
[ ] analysis completed
[ ] global images inspected
[ ] relevant layers/slices/crops inspected
[ ] pixels grounded to exact coordinates where visual claims were made
[ ] plan separated into phases
[ ] every edit bounded and evidence-linked
[ ] every patch validated and previewed
[ ] before/after images inspected
[ ] commits re-rendered
[ ] regressions rolled back
[ ] final analyses and quality gates reviewed
[ ] .schem export verified when required
[ ] .litematic export verified when required
[ ] exact mismatch counts are zero or explicitly accepted
[ ] final artifact/hash reported
[ ] no secret/proprietary asset committed
[ ] no unsupported certainty claim made
```

---

# APPENDIX A — MACHINE TOOL SCHEMAS

The following schemas are generated from the installed implementation. Treat them as the provider-facing source of truth.


## `get_build_summary`

```json
{
  "description": "Return the canonical build summary.",
  "name": "get_build_summary",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "required": [],
    "type": "object"
  },
  "type": "function"
}
```

## `get_analysis`

```json
{
  "description": "Return deterministic structural analyses.",
  "name": "get_analysis",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "required": [],
    "type": "object"
  },
  "type": "function"
}
```

## `get_material_histogram`

```json
{
  "description": "Return exact canonical-state and base-block material histograms.",
  "name": "get_material_histogram",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "required": [],
    "type": "object"
  },
  "type": "function"
}
```

## `get_palette`

```json
{
  "description": "Return exact canonical palette states.",
  "name": "get_palette",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "required": [],
    "type": "object"
  },
  "type": "function"
}
```

## `get_block`

```json
{
  "description": "Return the exact block state and block entity at a coordinate.",
  "name": "get_block",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "position": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      }
    },
    "required": [
      "position"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `query_blocks`

```json
{
  "description": "Return exact non-air blocks inside a bounding box.",
  "name": "query_blocks",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "limit": {
        "maximum": 100000,
        "minimum": 1,
        "type": "integer"
      }
    },
    "required": [
      "bounds"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_chunk`

```json
{
  "description": "Return exact non-air blocks and deterministic metadata for a 16x16x16 canonical chunk.",
  "name": "get_chunk",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "chunk": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      }
    },
    "required": [
      "chunk"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_slice`

```json
{
  "description": "Return exact blocks for an X, Y, or Z slice; Y slices also include run-length rows.",
  "name": "get_slice",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "axis": {
        "enum": [
          "x",
          "y",
          "z"
        ],
        "type": "string"
      },
      "index": {
        "type": "integer"
      },
      "limit": {
        "maximum": 100000,
        "minimum": 1,
        "type": "integer"
      },
      "y": {
        "type": "integer"
      }
    },
    "required": [],
    "type": "object"
  },
  "type": "function"
}
```

## `render_layer`

```json
{
  "description": "Generate a deterministic semantic layer PNG manifest.",
  "name": "render_layer",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "pixelsPerBlock": {
        "maximum": 32,
        "minimum": 1,
        "type": "integer"
      },
      "y": {
        "type": "integer"
      }
    },
    "required": [
      "y"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `begin_patch`

```json
{
  "description": "Create and validate a bounded transactional patch.",
  "name": "begin_patch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "author": {
        "type": "string"
      },
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "expectedParentHash": {
        "type": "string"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operations": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      },
      "targetRegion": {
        "type": "string"
      }
    },
    "required": [
      "reason",
      "bounds",
      "maxAffectedBlocks",
      "operations"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `preview_patch`

```json
{
  "description": "Preview a previously created patch.",
  "name": "preview_patch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "required": [
      "patchId"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `commit_patch`

```json
{
  "description": "Commit a previously validated patch when automatic commit is permitted.",
  "name": "commit_patch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "required": [
      "patchId"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `rollback_patch`

```json
{
  "description": "Rollback the active committed patch.",
  "name": "rollback_patch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "required": [
      "patchId"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `reject_patch`

```json
{
  "description": "Reject a pending patch without applying it.",
  "name": "reject_patch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "patchId"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `compare_versions`

```json
{
  "description": "Compare exact canonical states between two versions.",
  "name": "compare_versions",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "a": {
        "type": "string"
      },
      "b": {
        "type": "string"
      }
    },
    "required": [
      "a",
      "b"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `render_view`

```json
{
  "description": "Render a new textured or flat orthographic/isometric view and return its evidence manifest.",
  "name": "render_view",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "hideMaterials": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "materials": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "regions": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "size": {
        "maximum": 2048,
        "minimum": 128,
        "type": "integer"
      },
      "view": {
        "enum": [
          "north",
          "south",
          "east",
          "west",
          "top",
          "bottom",
          "isometric_ne",
          "isometric_nw",
          "isometric_se",
          "isometric_sw"
        ],
        "type": "string"
      }
    },
    "required": [
      "view"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `render_crop`

```json
{
  "description": "Render a coordinate-bounded crop and return a grounded visual evidence manifest.",
  "name": "render_crop",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "hideMaterials": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "materials": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "regions": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "size": {
        "maximum": 2048,
        "minimum": 128,
        "type": "integer"
      },
      "view": {
        "type": "string"
      }
    },
    "required": [
      "bounds"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `pixel_to_block`

```json
{
  "description": "Resolve an exact visible pixel from a snapshot manifest to its canonical coordinate and palette ID.",
  "name": "pixel_to_block",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "manifest": {
        "type": "string"
      },
      "px": {
        "type": "integer"
      },
      "py": {
        "type": "integer"
      }
    },
    "required": [
      "manifest",
      "px",
      "py"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_rooms`

```json
{
  "description": "Return grounded room and air-volume analysis.",
  "name": "get_rooms",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_navigation_graph`

```json
{
  "description": "Return approximate player navigation analysis.",
  "name": "get_navigation_graph",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_components`

```json
{
  "description": "Return connected-component and floating-cluster analysis.",
  "name": "get_components",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_facade_report`

```json
{
  "description": "Return facade flatness and depth analysis.",
  "name": "get_facade_report",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_lighting_report`

```json
{
  "description": "Return heuristic lighting coverage analysis.",
  "name": "get_lighting_report",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_interior_report`

```json
{
  "description": "Return interior/exterior consistency findings.",
  "name": "get_interior_report",
  "parameters": {
    "additionalProperties": false,
    "properties": {},
    "type": "object"
  },
  "type": "function"
}
```

## `get_import_diagnostics`

```json
{
  "description": "Return structured import diagnostics.",
  "name": "get_import_diagnostics",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_regions`

```json
{
  "description": "Return all source regions and exact bounds.",
  "name": "get_regions",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_floors`

```json
{
  "description": "Return detected floor-level summaries.",
  "name": "get_floors",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_symmetry_report`

```json
{
  "description": "Return grounded reflection symmetry metrics.",
  "name": "get_symmetry_report",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `find_block_entities`

```json
{
  "description": "Find block entities, optionally bounded.",
  "name": "find_block_entities",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_patch`

```json
{
  "description": "Return a pending transactional patch record.",
  "name": "get_patch",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "patchId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_region`

```json
{
  "description": "Return one named region.",
  "name": "get_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "name": {
        "type": "string"
      }
    },
    "required": [
      "name"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_room`

```json
{
  "description": "Return one room by ID.",
  "name": "get_room",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "id": {
        "type": "string"
      }
    },
    "required": [
      "id"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_component`

```json
{
  "description": "Return one component by ID/index.",
  "name": "get_component",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "id": {
        "type": [
          "string",
          "integer"
        ]
      }
    },
    "required": [
      "id"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `measure_distance`

```json
{
  "description": "Measure Euclidean and Manhattan distance between exact coordinates.",
  "name": "measure_distance",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "a": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      },
      "b": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      }
    },
    "required": [
      "a",
      "b"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `measure_bounds`

```json
{
  "description": "Measure dimensions, area, and volume of bounds.",
  "name": "measure_bounds",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      }
    },
    "required": [
      "bounds"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `find_material`

```json
{
  "description": "Find exact coordinates using a canonical state or base block.",
  "name": "find_material",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "limit": {
        "maximum": 100000,
        "minimum": 1,
        "type": "integer"
      },
      "state": {
        "type": "string"
      }
    },
    "required": [
      "state"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `find_nearest`

```json
{
  "description": "Find nearest block matching a state from a coordinate.",
  "name": "find_nearest",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "position": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      },
      "state": {
        "type": "string"
      }
    },
    "required": [
      "position",
      "state"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `get_block_entity`

```json
{
  "description": "Return exact block-entity NBT at a coordinate.",
  "name": "get_block_entity",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "position": {
        "items": {
          "type": "integer"
        },
        "maxItems": 3,
        "minItems": 3,
        "type": "array"
      }
    },
    "required": [
      "position"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `create_design_brief`

```json
{
  "description": "Structured planning operation: create_design_brief.",
  "name": "create_design_brief",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `define_build_bounds`

```json
{
  "description": "Structured planning operation: define_build_bounds.",
  "name": "define_build_bounds",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `define_palette_constraints`

```json
{
  "description": "Structured planning operation: define_palette_constraints.",
  "name": "define_palette_constraints",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `create_floor_plan`

```json
{
  "description": "Structured planning operation: create_floor_plan.",
  "name": "create_floor_plan",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `create_room_program`

```json
{
  "description": "Structured planning operation: create_room_program.",
  "name": "create_room_program",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `create_build_phase`

```json
{
  "description": "Structured planning operation: create_build_phase.",
  "name": "create_build_phase",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `estimate_materials`

```json
{
  "description": "Structured planning operation: estimate_materials.",
  "name": "estimate_materials",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `validate_plan`

```json
{
  "description": "Structured planning operation: validate_plan.",
  "name": "validate_plan",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "artifact": {
        "type": "object"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `set_block`

```json
{
  "description": "Create a bounded transactional set_block patch; does not commit automatically.",
  "name": "set_block",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `set_blocks`

```json
{
  "description": "Create a bounded transactional set_blocks patch; does not commit automatically.",
  "name": "set_blocks",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `fill_cuboid`

```json
{
  "description": "Create a bounded transactional fill_cuboid patch; does not commit automatically.",
  "name": "fill_cuboid",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `hollow_cuboid`

```json
{
  "description": "Create a bounded transactional hollow_cuboid patch; does not commit automatically.",
  "name": "hollow_cuboid",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `replace_blocks`

```json
{
  "description": "Create a bounded transactional replace_blocks patch; does not commit automatically.",
  "name": "replace_blocks",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_line`

```json
{
  "description": "Create a bounded transactional draw_line patch; does not commit automatically.",
  "name": "draw_line",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_polyline`

```json
{
  "description": "Create a bounded transactional draw_polyline patch; does not commit automatically.",
  "name": "draw_polyline",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_wall`

```json
{
  "description": "Create a bounded transactional draw_wall patch; does not commit automatically.",
  "name": "draw_wall",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_floor`

```json
{
  "description": "Create a bounded transactional draw_floor patch; does not commit automatically.",
  "name": "draw_floor",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_roof`

```json
{
  "description": "Create a bounded transactional draw_roof patch; does not commit automatically.",
  "name": "draw_roof",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_circle`

```json
{
  "description": "Create a bounded transactional draw_circle patch; does not commit automatically.",
  "name": "draw_circle",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_ellipse`

```json
{
  "description": "Create a bounded transactional draw_ellipse patch; does not commit automatically.",
  "name": "draw_ellipse",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_cylinder`

```json
{
  "description": "Create a bounded transactional draw_cylinder patch; does not commit automatically.",
  "name": "draw_cylinder",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_sphere`

```json
{
  "description": "Create a bounded transactional draw_sphere patch; does not commit automatically.",
  "name": "draw_sphere",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_dome`

```json
{
  "description": "Create a bounded transactional draw_dome patch; does not commit automatically.",
  "name": "draw_dome",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_arch`

```json
{
  "description": "Create a bounded transactional draw_arch patch; does not commit automatically.",
  "name": "draw_arch",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `draw_bezier`

```json
{
  "description": "Create a bounded transactional draw_bezier patch; does not commit automatically.",
  "name": "draw_bezier",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `extrude_profile`

```json
{
  "description": "Create a bounded transactional extrude_profile patch; does not commit automatically.",
  "name": "extrude_profile",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `loft_profiles`

```json
{
  "description": "Create a bounded transactional loft_profiles patch; does not commit automatically.",
  "name": "loft_profiles",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `copy_region`

```json
{
  "description": "Create a bounded transactional copy_region patch; does not commit automatically.",
  "name": "copy_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `move_region`

```json
{
  "description": "Create a bounded transactional move_region patch; does not commit automatically.",
  "name": "move_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `rotate_region`

```json
{
  "description": "Create a bounded transactional rotate_region patch; does not commit automatically.",
  "name": "rotate_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `mirror_region`

```json
{
  "description": "Create a bounded transactional mirror_region patch; does not commit automatically.",
  "name": "mirror_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `scale_pattern_integer`

```json
{
  "description": "Create a bounded transactional scale_pattern_integer patch; does not commit automatically.",
  "name": "scale_pattern_integer",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `apply_noise_mask`

```json
{
  "description": "Create a bounded transactional apply_noise_mask patch; does not commit automatically.",
  "name": "apply_noise_mask",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `apply_gradient_palette`

```json
{
  "description": "Create a bounded transactional apply_gradient_palette patch; does not commit automatically.",
  "name": "apply_gradient_palette",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `paste_template`

```json
{
  "description": "Create a bounded transactional paste_template patch; does not commit automatically.",
  "name": "paste_template",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `clear_region`

```json
{
  "description": "Create a bounded transactional clear_region patch; does not commit automatically.",
  "name": "clear_region",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `set_block_entity`

```json
{
  "description": "Create a bounded transactional set_block_entity patch; does not commit automatically.",
  "name": "set_block_entity",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `remove_block_entity`

```json
{
  "description": "Create a bounded transactional remove_block_entity patch; does not commit automatically.",
  "name": "remove_block_entity",
  "parameters": {
    "additionalProperties": false,
    "properties": {
      "bounds": {
        "additionalProperties": false,
        "properties": {
          "max": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          },
          "min": {
            "items": {
              "type": "integer"
            },
            "maxItems": 3,
            "minItems": 3,
            "type": "array"
          }
        },
        "required": [
          "min",
          "max"
        ],
        "type": "object"
      },
      "evidenceRefs": {
        "items": {
          "type": "string"
        },
        "type": "array"
      },
      "maxAffectedBlocks": {
        "maximum": 10000000,
        "minimum": 1,
        "type": "integer"
      },
      "operation": {
        "type": "object"
      },
      "preconditions": {
        "items": {
          "type": "object"
        },
        "type": "array"
      },
      "reason": {
        "type": "string"
      }
    },
    "required": [
      "bounds",
      "maxAffectedBlocks",
      "reason",
      "operation"
    ],
    "type": "object"
  },
  "type": "function"
}
```

## `validate_patch`

```json
{
  "description": "Version/transaction operation: validate_patch.",
  "name": "validate_patch",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "name": {
        "type": "string"
      },
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "sourceVersionId": {
        "type": "string"
      },
      "versionId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `create_checkpoint`

```json
{
  "description": "Version/transaction operation: create_checkpoint.",
  "name": "create_checkpoint",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "name": {
        "type": "string"
      },
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "sourceVersionId": {
        "type": "string"
      },
      "versionId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `restore_checkpoint`

```json
{
  "description": "Version/transaction operation: restore_checkpoint.",
  "name": "restore_checkpoint",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "name": {
        "type": "string"
      },
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "sourceVersionId": {
        "type": "string"
      },
      "versionId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `branch_version`

```json
{
  "description": "Version/transaction operation: branch_version.",
  "name": "branch_version",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "name": {
        "type": "string"
      },
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "sourceVersionId": {
        "type": "string"
      },
      "versionId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `merge_versions`

```json
{
  "description": "Version/transaction operation: merge_versions.",
  "name": "merge_versions",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "name": {
        "type": "string"
      },
      "patchId": {
        "type": "string"
      },
      "reason": {
        "type": "string"
      },
      "sourceVersionId": {
        "type": "string"
      },
      "versionId": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `validate_export`

```json
{
  "description": "Export operation: validate_export.",
  "name": "validate_export",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "format": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `export_schem`

```json
{
  "description": "Export operation: export_schem.",
  "name": "export_schem",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "format": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `export_litematic`

```json
{
  "description": "Export operation: export_litematic.",
  "name": "export_litematic",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "format": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

## `get_export_artifact`

```json
{
  "description": "Export operation: get_export_artifact.",
  "name": "get_export_artifact",
  "parameters": {
    "additionalProperties": true,
    "properties": {
      "format": {
        "type": "string"
      }
    },
    "type": "object"
  },
  "type": "function"
}
```

---

# APPENDIX B — CURRENT CLI HELP


## `root`

```text
usage: python -m app.cli [-h] [--json-errors] [--quiet] [--verbose]
                         [--log-json]
                         {import,analyze,snapshot,export,pipeline,render,query,patch,version,build-plan,apply-plan,pixel-to-block,block-to-pixel,tool,agent,quality-report,export-map,texture-audit,palette-atlas,contact-sheet,slice-sweep,annotated-render,structure,author,interior} ...
python -m app.cli: error: the following arguments are required: command
```

## `import`

```text
usage: python -m app.cli import [-h] --out OUT file

positional arguments:
  file

options:
  -h, --help  show this help message and exit
  --out OUT
```

## `analyze`

```text
usage: python -m app.cli analyze [-h] [--out OUT] run

positional arguments:
  run

options:
  -h, --help  show this help message and exit
  --out OUT
```

## `snapshot`

```text
usage: python -m app.cli snapshot [-h] [--views VIEWS]
                                  [--resource-pack RESOURCE_PACK]
                                  [--strict-textures] [--size SIZE]
                                  [--pixels-per-block PIXELS_PER_BLOCK]
                                  [--out OUT]
                                  run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --views VIEWS
  --resource-pack RESOURCE_PACK
  --strict-textures
  --size SIZE
  --pixels-per-block PIXELS_PER_BLOCK
  --out OUT
```

## `export`

```text
usage: python -m app.cli export [-h] --format {schem,litematic} [--verify]
                                [--out OUT]
                                run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --format {schem,litematic}
  --verify
  --out OUT
```

## `pipeline`

```text
usage: python -m app.cli pipeline [-h] --out OUT
                                  [--resource-pack RESOURCE_PACK]
                                  [--format {schem,litematic}] [--size SIZE]
                                  file

positional arguments:
  file

options:
  -h, --help            show this help message and exit
  --out OUT
  --resource-pack RESOURCE_PACK
  --format {schem,litematic}
  --size SIZE
```

## `render`

```text
usage: python -m app.cli render [-h] [--camera-azimuth CAMERA_AZIMUTH]
                                [--camera-elevation CAMERA_ELEVATION]
                                [--camera-roll CAMERA_ROLL] [--zoom ZOOM]
                                [--margin MARGIN] [--size SIZE]
                                [--mode {flat,textured}] [--lighting LIGHTING]
                                [--resource-pack RESOURCE_PACK]
                                [--strict-textures] [--slice SLICE]
                                [--pixels-per-block PIXELS_PER_BLOCK]
                                [--crop CROP]
                                [--view {north,south,east,west,top,bottom,isometric_ne,isometric_nw,isometric_se,isometric_sw}]
                                [--seed SEED] [--region REGION]
                                [--material MATERIAL]
                                [--hide-material HIDE_MATERIAL] [--name NAME]
                                [--out OUT]
                                run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --camera-azimuth CAMERA_AZIMUTH
  --camera-elevation CAMERA_ELEVATION
  --camera-roll CAMERA_ROLL
  --zoom ZOOM
  --margin MARGIN
  --size SIZE
  --mode {flat,textured}
  --lighting LIGHTING
  --resource-pack RESOURCE_PACK
  --strict-textures
  --slice SLICE
  --pixels-per-block PIXELS_PER_BLOCK
  --crop CROP
  --view {north,south,east,west,top,bottom,isometric_ne,isometric_nw,isometric_se,isometric_sw}
  --seed SEED
  --region REGION       Render only the named region; repeatable.
  --material MATERIAL   Render only this exact state or base block ID;
                        repeatable.
  --hide-material HIDE_MATERIAL
                        Hide this exact state or base block ID; repeatable.
  --name NAME
  --out OUT
```

## `query`

```text
usage: python -m app.cli query [-h]
                               {block,box,palette,chunk,block-entity,region,room,issues} ...

positional arguments:
  {block,box,palette,chunk,block-entity,region,room,issues}

options:
  -h, --help            show this help message and exit
```

## `patch`

```text
usage: python -m app.cli patch [-h]
                               {validate,preview,commit,reject,rollback} ...

positional arguments:
  {validate,preview,commit,reject,rollback}

options:
  -h, --help            show this help message and exit
```

## `version`

```text
usage: python -m app.cli version [-h] {list,compare} ...

positional arguments:
  {list,compare}

options:
  -h, --help      show this help message and exit
```

## `build-plan`

```text
usage: python -m app.cli build-plan [-h] --out OUT run design_brief

positional arguments:
  run
  design_brief

options:
  -h, --help    show this help message and exit
  --out OUT
```

## `apply-plan`

```text
usage: python -m app.cli apply-plan [-h] [--resource-pack RESOURCE_PACK]
                                    --out OUT
                                    run build_plan

positional arguments:
  run
  build_plan

options:
  -h, --help            show this help message and exit
  --resource-pack RESOURCE_PACK
  --out OUT
```

## `pixel-to-block`

```text
usage: python -m app.cli pixel-to-block [-h] --px PX --py PY manifest

positional arguments:
  manifest

options:
  -h, --help  show this help message and exit
  --px PX
  --py PY
```

## `block-to-pixel`

```text
usage: python -m app.cli block-to-pixel [-h] --x X --y Y --z Z manifest

positional arguments:
  manifest

options:
  -h, --help  show this help message and exit
  --x X
  --y Y
  --z Z
```

## `tool`

```text
usage: python -m app.cli tool [-h] [--resource-pack RESOURCE_PACK]
                              [--allow-commit] [--result RESULT]
                              run request_file

positional arguments:
  run
  request_file

options:
  -h, --help            show this help message and exit
  --resource-pack RESOURCE_PACK
  --allow-commit
  --result RESULT
```

## `agent`

```text
usage: python -m app.cli agent [-h] --task TASK
                               --provider {openai,anthropic,openai-compatible}
                               --model MODEL [--base-url BASE_URL]
                               [--api-key-env API_KEY_ENV]
                               [--resource-pack RESOURCE_PACK] [--auto-commit]
                               [--max-iterations MAX_ITERATIONS]
                               [--max-context-tokens MAX_CONTEXT_TOKENS]
                               [--max-images MAX_IMAGES]
                               [--max-image-bytes MAX_IMAGE_BYTES]
                               [--max-output-tokens MAX_OUTPUT_TOKENS]
                               [--out OUT]
                               run

positional arguments:
  run

options:
  -h, --help            show this help message and exit
  --task TASK
  --provider {openai,anthropic,openai-compatible}
  --model MODEL
  --base-url BASE_URL
  --api-key-env API_KEY_ENV
  --resource-pack RESOURCE_PACK
  --auto-commit
  --max-iterations MAX_ITERATIONS
  --max-context-tokens MAX_CONTEXT_TOKENS
  --max-images MAX_IMAGES
  --max-image-bytes MAX_IMAGE_BYTES
  --max-output-tokens MAX_OUTPUT_TOKENS
  --out OUT
```

---

## Appendix B runtime additions (1.1.0 Meduseld quality/map-maker revision)

Appendix B is a checked-in snapshot. The runtime `--help` output is
authoritative. This revision additionally exposes:

```text
render:
  --projection {auto,orthographic,perspective}
  --camera-position X,Y,Z
  --camera-target X,Y,Z
  --camera-yaw DEGREES
  --camera-pitch DEGREES
  --fov DEGREES
  --near DISTANCE
  --far DISTANCE
  --hide-coordinate X,Y,Z
  --fit / --no-fit
  --zoom SCALE
  --margin BLOCKS
  --accuracy {exact,fast}
  --tile-size PIXELS
  --resume

analyze:
  --bounds X1,Y1,Z1,X2,Y2,Z2
  --structure ID_OR_NAME
  --seal-structure-envelope
  --room-bounds X1,Y1,Z1,X2,Y2,Z2
  --room-seed X,Y,Z
  --lighting-max-cells N       0 removes the cap
  --room-max-cells N

interior:
  render, gallery, inspect, diagnose, packet, walkthrough, sightline
  render defaults to --fail-on-reject and accepts --no-fail-on-reject
  packet accepts --min-cumulative-coverage FRACTION

comprehension:
  export-map, texture-audit, palette-atlas, contact-sheet, slice-sweep,
  annotated-render

quality-report:
  --bounds, --structure, --seal-structure-envelope, --fail-under,
  --from, --to

structure:
  inventory, name, extract, analyze-all, compare, site-plan, map-report,
  render-all, interiors

author:
  anchor-set, anchor-room, anchor-bay, anchors, style-extract, critique,
  fixture-catalog
```

Run `python -m app.cli COMMAND --help` for the complete current option set.
See `MEDUSELD_IMPLEMENTATION_TRACEABILITY.md` for the exhaustive report map and
real-schematic acceptance evidence.

# APPENDIX C — AUTHORITATIVE INTERNAL REFERENCES

- `README.md`
- `CAPABILITY_MATRIX.md`
- `IMPLEMENTATION_STATUS.md`
- `VERIFICATION.md`
- `FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.md`
- `FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.json`
- `docs/MASTER_SPEC_SNOWFLAKE.md`
- `docs/architecture/sandbox-profile.md`
- `docs/architecture/cpu-renderer.md`
- `docs/architecture/semantic-maps.md`
- `docs/architecture/ai-tools.md`
- `docs/architecture/patch-engine.md`
- `docs/architecture/security.md`
- `docs/formats/sponge-schem.md`
- `docs/formats/litematic.md`
- `docs/formats/legacy-schematic.md`
- `docs/resource-packs/security-and-resolution.md`
- `docs/cli/offline-cli.md`
- `docs/troubleshooting/assets.md`

## Appendix D - 1.2.0 large-schematic operating contract

The complete, normative appendix is
`docs/agent/LARGE_SCHEMATIC_AUTONOMOUS_APPENDIX.md`. It is part of this manual
and must be read before any large-schematic import, analysis, render, edit or
export.

It exhaustively documents every 1.1/1.2 command/subcommand and parameter, the
patch envelope and preconditions, every supported patch operation, scale/RAM
envelopes, chunk-array streaming, scoped work, exact tiled/resumable rendering,
honest LOD, disk-backed semantic maps, renderer-backed entity/fluid coverage,
verification-on export, warm-cache completeness and hostile-environment
recovery.

Anvil world saves are explicitly outside the schematic-only scope. The exact
Tree of Dreams acceptance gate must remain pending until the untouched
`Tree_of_dreams.schem` is available. See
`TREE_OF_DREAMS_IMPLEMENTATION_TRACEABILITY.md` for the full A-J evidence map.

End of autonomous LLM operating manual.
