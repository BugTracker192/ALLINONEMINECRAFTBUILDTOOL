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
python -m venv .venv
. .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install .
```

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
```

The reusable Python API exposes `app.render.render(...)`, `pixel_to_block(...)`, `block_to_pixel(...)` and exact canonical lookup.

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
