# Minecraft Build Intelligence — Offline CPU / Multimodal Edition

Minecraft Build Intelligence is an installable Python package for exact Minecraft Java structure import, deterministic CPU rendering, semantic pixel grounding, structural analysis, transactional AI construction and verified export.

Its mandatory baseline follows one rule:

> A build is presented to an AI as both exact symbolic voxel data and deterministic visual evidence.

The default pipeline requires **Python, NumPy and Pillow only**. It does not require Node.js, a browser, Docker, a database, a GPU, OpenGL or an external executable.

## What the AI literally receives

A provider-enabled run attaches actual PNG bytes to the multimodal request. Alongside those images, the model receives exact tools for coordinates, canonical states, regions, rooms, components, analyses, patches and exports. When the model requests another angle or previews/commits a patch, the CPU renderer creates a fresh image and that image is attached to the next model turn.

Every rendered pixel has sidecar maps for:

- Frontmost exact `(x, y, z)` coordinate.
- Palette ID and canonical state lookup.
- Region ID.
- Depth.
- Surface normal.
- Occupancy.
- Changed-block status.
- Render-fallback/issue status.

## Supported data

- Sponge `.schem` versions 1, 2 and 3.
- Multi-region `.litematic`, including signed dimensions and overlapping source regions.
- Legacy MCEdit/Schematica `.schematic` with conservative unresolved-state preservation.
- Complete canonical block state properties.
- Block entities, supported entities, pending ticks, region metadata and unknown extension data.
- Sponge v3 and Litematic export with normal-import reparse and exact coordinate/state verification.

## Install

The private all-in-one release includes the user-supplied Minecraft asset archive and auto-selects it.
For autonomous setup and verification:

```bash
python BOOTSTRAP_SNOWFLAKE.py --smoke
```

Manual equivalent:

```bash
python -m venv /writable/local/scratch/mbi-venv
. /writable/local/scratch/mbi-venv/bin/activate
pip install .
```

On Snowflake/CoCo stages, do not create a repository-local environment or build
a wheel on the mounted stage: those filesystems may reject symlinks and
`zipfile.close()`. Mirror to local scratch and build there:

```bash
python BOOTSTRAP_SNOWFLAKE.py \
  --scratch-root /tmp/mbi-scratch \
  --cache-dir /persistent/mbi-cache \
  --warm-cache --smoke
```

The persistent cache stores the hash-verified reconstructed asset and a compact
source tarball (plus an environment tarball when `--cache-venv` is supplied).
`pip install -e .` is supported through the bundled PEP 660 backend.

`vendor/wheelhouse/` is optional and may be empty. When it is empty, provide an
authenticated index with `--index-url`, configure normal pip credentials, or
explicitly use `--index-url https://pypi.org/simple` where public network access
is permitted. The bootstrap never claims an empty wheelhouse is an offline
dependency source.

Optional live provider adapters:

```bash
pip install '.[ai]'
```

Testing dependencies:

```bash
pip install '.[test]'
```

## Complete offline pipeline

```bash
python -m app.cli pipeline tests/fixtures/reference.schem --out ./run
```

The bundled archive is used automatically:

```bash
python -m app.cli pipeline tests/fixtures/reference.schem --out ./run
```

An explicit resource-pack directory, ZIP, or client JAR can override the bundle with `--resource-pack`.
Set `MBI_DISABLE_BUNDLED_ASSETS=1` or pass `--resource-pack none` only for deliberate flat rendering.
This private deliverable contains the exact user-supplied assets; do not publicly redistribute them.

## Exact queries

```bash
python -m app.cli query block ./run --x -2 --y 3 --z 5 --json
python -m app.cli query box ./run --min=-2,3,5 --max=4,5,9 --json
python -m app.cli query palette ./run --json
python -m app.cli query chunk ./run --cx 0 --cy 0 --cz 0 --json
python -m app.cli query block-entity ./run --x 10 --y 25 --z -4 --json
python -m app.cli query room ./run --id 1 --json
```

## CPU renders

```bash
python -m app.cli render ./run --view isometric_ne --size 1536x1536 \
  --out ./run

python -m app.cli render ./run --slice y:37 --pixels-per-block 8 --out ./run
python -m app.cli render ./run --crop 10,20,30,32,24,32 --view isometric_ne --out ./run
python -m app.cli render ./run --view isometric_ne --fit --zoom 1.2 \
  --margin 1 --accuracy exact --tile-size 512 --resume --out ./run
```

The reusable Python API exposes `app.render.render(...)`, `pixel_to_block(...)`, `block_to_pixel(...)` and exact canonical lookup.

## Quality and map-maker toolkit

Version 1.2.0 includes the 1.1.0 whole-volume comprehension surface and adds
chunk-array large-schematic processing, streamed persistence/export, scoped
structure work, exact tile-local rendering, honest LOD, renderer-backed fluid
coverage and verification-on export. It also retains scoped/structure analysis,
quality gates, map-scale reporting, and reference-style authoring:

```bash
# Whole-volume comprehension and texture gates
python -m app.cli export-map ./run --format csv --out ./block-map.csv
python -m app.cli texture-audit ./run --fail-under 100
python -m app.cli palette-atlas ./run --out ./palette.png
python -m app.cli contact-sheet ./run \
  --views isometric_ne,isometric_sw,south,top --out ./contact-sheet.png
python -m app.cli slice-sweep ./run \
  --slice y:110..170 --step 6 --montage --out ./sections
python -m app.cli annotated-render ./run \
  --view isometric_ne --annotate-materials 8 --out ./annotated.png

# Bounded, manual-room, and detected-structure analysis
python -m app.cli analyze ./run \
  --bounds 100,50,100,180,120,180 \
  --seal-structure-envelope \
  --lighting-max-cells 0 --out ./bounded-run
python -m app.cli analyze ./run \
  --room-bounds 110,55,110,145,75,145 \
  --room-seed 120,56,120
python -m app.cli structure inventory ./run
python -m app.cli structure name ./run STRUCTURE_ID great_hall
python -m app.cli analyze ./run --structure great_hall --out ./great-hall-run
python -m app.cli structure analyze-all ./run --resume
python -m app.cli structure extract ./run great_hall \
  --format litematic --out ./great-hall-extract

# Site, comparison, LOD, interiors, and quality
python -m app.cli structure site-plan ./run --out ./site-plan.png
python -m app.cli structure map-report ./run
python -m app.cli structure compare ./run house_1 house_2
python -m app.cli structure render-all ./run --accuracy fast --resume
python -m app.cli structure interiors ./run --resume
python -m app.cli quality-report ./run --structure great_hall --fail-under 70
python -m app.cli quality-report ./run \
  --from VERSION_A --to VERSION_B
```

For large scenes, exact rendering auto-tiles above the per-tile emitted-geometry
budget; use `--tile-size 512 --resume`. `--accuracy fast` selects the bounded
LOD overview and is explicitly non-exact in its manifest. Limits can be
configured with `MBI_MAX_VISIBLE_BLOCKS`, `MBI_MAX_RENDER_SIZE` and
`MBI_MAX_TOTAL_TILE_WORK`.

The tested chunk-array budget stores 16,777,216 placed voxels in 64 MiB of
voxel arrays. Default parser guards are 100,000,000 volume cells and 65,536
palette states; actual peak memory additionally includes input NBT, palettes,
entities, analyses, assets and outputs. Anvil world saves are not supported.
See `TREE_OF_DREAMS_IMPLEMENTATION_TRACEABILITY.md` and the normative
`docs/agent/LARGE_SCHEMATIC_AUTONOMOUS_APPENDIX.md`.

`analyze --structure` automatically enables conservative structure-envelope
sealing. For caller-supplied bounds, opt in with
`--seal-structure-envelope`. Manual `--room-bounds`/`--room-seed` uses exact
seed-and-clip behavior and reports sealed openings and a leak path.

Reference-style authoring uses durable anchors and bounded patch operations:

```bash
python -m app.cli author style-extract ./run --name rohirric_reference
python -m app.cli author anchor-set ./run hearth --position 120,56,130
python -m app.cli author anchor-room ./run north_wall \
  --room ROOM_ID --face north
python -m app.cli author anchor-bay ./run east_bay_3 \
  --structure great_hall --face east --bay-index 3 --bay-count 7
python -m app.cli author fixture-catalog
python -m app.cli author critique ./run \
  --style-profile ./run/style_profiles/rohirric_reference.json
```

Patch JSON can now use `draw_truss`, `draw_dormer`, `draw_arcade`,
`draw_bellcast_eave`, `place_fixture`, `symmetry_edit`, `greeble_surface`, and
`repeat_module`. Operations may include a named `anchor` and `anchorOffset`.
See `MEDUSELD_IMPLEMENTATION_TRACEABILITY.md` for requirement-by-requirement
coverage and the real-schematic acceptance summary.

## Production interior evidence

Interior analysis distinguishes designed architectural spaces from natural, terrain, decorative, roof, wall, vegetation, and fluid voids. Camera candidates are checked for exact component membership, collision, clearance, multi-sample voxel line of sight, and semantic frame quality before acceptance.

```bash
python -m app.cli interior inspect ./run --room ROOM_ID
python -m app.cli interior diagnose ./run --room ROOM_ID

python -m app.cli interior render ./run \
  --room ROOM_ID --shot coverage \
  --camera-mode auto --occlusion physical \
  --cutaway-strategy minimal-ray \
  --quality-profile room_coverage \
  --max-attempts 8 --out ./run/interiors

python -m app.cli interior packet ./run \
  --room ROOM_ID \
  --camera-mode auto \
  --fallback physical,third-person,cutaway,slices \
  --shots doorway,corner,feature,coverage \
  --quality-profile presentation \
  --slice-fallback always \
  --out ./run/interior-packets/ROOM_ID

python -m app.cli interior walkthrough ./run \
  --room ROOM_ID --frames 8 --out ./run/walkthrough
python -m app.cli interior sightline ./run \
  --room ROOM_ID --out ./run/sightlines.json
```

A packet contains grounded first-person and explicitly labeled third-person cutaway views, room-bounded plans/slices, candidate and rejection records, quality metrics, exact source hashes, and semantic maps. Cutaway masks are render-only and never change the canonical document. See `docs/architecture/interior-perspective.md`.

## Transactional edits

```bash
python -m app.cli patch validate ./run patch.json
python -m app.cli patch preview ./run patch.json --out ./run
python -m app.cli patch commit ./run patch.json --out ./run
python -m app.cli patch rollback ./run --patch-id patch_123 --out ./run
```

A provider-independent JSON operation bridge is also available:

```bash
python -m app.cli tool ./run tool_requests.json --allow-commit
```

A batch shares one patch engine, allowing `begin_patch`, `preview_patch`, `commit_patch`, queries and renders in one atomic agent interaction.

## Build generation

```bash
python -m app.cli build-plan ./run design_brief.json --out ./run
python -m app.cli apply-plan ./run ./run/build_plan.json \
  --out ./run
```

The same bounded operations can be driven by an external coding agent or an optional connected multimodal provider.

## Live multimodal agent

```bash
export MBI_AI_API_KEY='...'
python -m app.cli agent ./run \
  --task task.md \
  --provider openai \
  --model configured-model-id \
  
```

Supported adapters are OpenAI Responses, Anthropic Messages and OpenAI-compatible Chat Completions. Provider output is untrusted and can only act through validated bounded tools.

## Required output layout

A pipeline run is self-contained and includes:

```text
canonical.json                 exact canonical manifest
chunks/                        content-addressed 16³ chunks
raw_preserved/                 original bytes and unknown data
analysis.json                  deterministic grounded analyses
versions/                      immutable build versions
patches/                       transactions and visual previews
snapshots/                     PNGs and manifests
semantic_maps/                 exact binary pixel maps
ai/                            context, evidence, run and tool records
export/                        output structure and verify report
jobs.json                      synchronous job state records
```

## Verification

```bash
pytest
python scripts/verify_snowflake_release.py \
   \
  --output ./verification
```

`VERIFICATION.md` lists what was dynamically executed in the release environment and separates successful checks from environment limitations. `FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.md` maps the implementation to the master prompt definition of done.

An autonomous LLM operating in a Snowflake/CoCo sandbox should start with `SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md`. It is a complete agent-only runbook covering discovery, installation, configuration, all tools and commands, visual-symbolic reasoning, generation, modification, recovery, verification and final reporting without routine human configuration.

## Optional adapters

The repository retains optional FastAPI, React/Three.js, worker and deployment adapters from the broader hosted architecture. They are not imported or required by the mandatory offline package.

See `docs/architecture/sandbox-profile.md`, `docs/architecture/cpu-renderer.md`, `docs/architecture/semantic-maps.md`, `docs/architecture/ai-tools.md` and `CAPABILITY_MATRIX.md`.
