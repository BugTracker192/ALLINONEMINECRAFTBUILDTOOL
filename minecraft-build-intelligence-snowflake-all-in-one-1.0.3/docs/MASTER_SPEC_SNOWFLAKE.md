# ULTIMATE MASTER PROMPT
## Build a Production-Grade Minecraft Build Intelligence, Visualization, Analysis, AI Construction, Modification, and Verified Export Platform
### Mandatory Offline Python 3.12 / Snowflake–CoCo Sandbox Execution Profile

---

# 0. COMMAND TO THE CODING AI

You are the **Principal Software Architect, Staff Python Engineer, Minecraft NBT and Schematic-Format Engineer, CPU Graphics Engineer, AI Systems Engineer, Security Engineer, Test Engineer, and Open-Source Maintainer** responsible for building this entire application from scratch.

Read this specification completely before writing code.

You are not building:

- A toy schematic parser.
- A demo that works only on one file.
- A cube preview using approximate colors while claiming full texture support.
- A script that dumps millions of blocks into one LLM prompt.
- A screenshot generator with no pixel-to-coordinate grounding.
- A one-shot AI code generator that cannot inspect or revise its own build.
- A fake service with mocked parsers, placeholder exporters, TODO functions, or hard-coded fixtures.
- A browser application that cannot run in the target environment.
- A GPU renderer disguised as a CPU-compatible implementation.

You are building a **production-grade, open-source Minecraft Java build intelligence platform** whose mandatory baseline must run inside a constrained Python sandbox.

The application must let a human operator or external AI agent:

1. Import `.schem`, `.schematic`, and `.litematic` files.
2. Decode their NBT structures safely and losslessly.
3. Query every block by exact coordinate, namespaced block ID, and complete state.
4. Preserve block entities, entities, region metadata, unknown tags, and unsupported modded data.
5. Render the build headlessly into deterministic textured images using a pure-Python CPU renderer.
6. Generate orthographic views, isometric views, Y layers, X/Z slices, detail crops, semantic maps, depth maps, and pixel-to-block maps.
7. Analyze materials, geometry, components, rooms, navigation, facade depth, structural support, symmetry, lighting heuristics, and interior/exterior consistency.
8. Expose the canonical build to an AI through token-efficient, queryable tools rather than a monolithic payload.
9. Let the AI create, modify, critique, and repair builds through bounded transactional operations.
10. Re-render changed areas after modifications so the AI receives visual feedback.
11. Undo, branch, compare, and roll back changes exactly.
12. Export valid modern `.schem` and `.litematic` files.
13. Re-import every export and prove round-trip block and coordinate equality.

The central rule is:

> **A build must never be represented to an AI only as an image, and it must never be represented only as a raw block list. The system must combine exact symbolic voxel data with deterministic visual evidence and expose both through an adaptive tool interface.**

The mandatory target is the **Offline Python CLI Profile**, also called the **Snowflake Sandbox Profile** or **CoCo Sandbox Profile** in this specification.

Do not silently substitute a web frontend, Node process, external database, background queue, GPU context, Docker service, or remote object store. Those facilities are physically unavailable in the mandatory environment.

Do not remove AI capability merely because live human interactivity is unavailable. The following remain non-negotiable:

- Textured rendering through a CPU software rasterizer.
- Multi-angle orthographic and isometric snapshots.
- Layer-by-layer and arbitrary-axis slices.
- Exact coordinate and block-state querying.
- Pixel-to-block grounding.
- AI perceive → analyze → plan → generate/modify → render → critique → verify → export loop.
- Lossless canonical representation.
- Transactional edits and rollback.
- Export round-trip verification.

The only major features omitted from the mandatory sandbox build are:

- A live interactive Three.js/WebGL viewport.
- A React/Vite human-facing web application.
- Browser mouse-orbit controls.
- GPU and real-time 60 FPS requirements.
- Multi-service deployment using Postgres, Redis, S3, Celery, Docker, Kubernetes, or headless Chromium.

These are optional future adapters, not required foundations.

---

# 1. MANDATORY RUNTIME CONTRACT

The finished project must run in an ephemeral Python sandbox with:

- Python 3.12.
- `pip` access to PyPI during installation.
- No Node.js or npm.
- No Docker.
- No `apt`, system package manager, or administrator access.
- No PostgreSQL server.
- No Redis server.
- No S3 service.
- No GPU.
- No hardware OpenGL context.
- No browser to serve or automate.
- No Chromium, Playwright, Puppeteer, or browser renderer.
- A writable local working directory.
- Potentially limited memory and execution time.

## 1.1 Installation guarantee

This command must succeed in a fresh Python 3.12 virtual environment:

```bash
pip install .
```

It must:

- Require no interactive prompts.
- Require no system packages.
- Avoid source compilation of native graphics libraries.
- Use pure-Python dependencies or prebuilt manylinux wheels available from PyPI.
- Pin direct dependencies to tested compatible ranges.
- Include a lock or reproducible constraints file.

## 1.2 Allowed dependencies

Prefer the standard library. Allowed dependencies include:

- `numpy`.
- `Pillow`.
- `nbtlib`, if its behavior is verified and wrapped behind an internal NBT interface.
- `pydantic`.
- `click`, `typer`, or `argparse`.
- `pytest`.
- `hypothesis`.
- `msgpack`, if a wheel is available and deterministic encoding is controlled.
- `zstandard`, if a wheel is available and a pure fallback or clear optional-dependency path exists.

Do not add a dependency merely for a trivial helper.

## 1.3 Forbidden dependencies in the mandatory profile

Do not require:

- Three.js.
- Babylon.js.
- React.
- Vite.
- Node.js.
- Electron.
- Tauri.
- PyOpenGL requiring real GL.
- ModernGL requiring EGL or hardware GL.
- `pyrender` with hardware rendering.
- Blender.
- Panda3D.
- Godot.
- Chromium.
- Playwright.
- Puppeteer.
- PostgreSQL drivers as mandatory dependencies.
- Redis clients as mandatory dependencies.
- Celery or remote queue infrastructure as mandatory dependencies.
- Docker SDK.
- Native executables downloaded at runtime.

Optional future profiles may add these behind interfaces, but the default package and test suite must not depend on them.

---

# 2. PRODUCT VISION

Create a headless developer tool that gives an AI reliable perception and control over Minecraft Java structures.

The platform exists because an AI that generates a schematic without seeing it will often produce:

- Bare shells.
- Flat facades.
- Weak silhouettes.
- Misaligned stairs.
- Sealed rooms.
- Missing interiors.
- Inconsistent wall thickness.
- Floating details.
- Repetitive block placement.
- Exterior windows that do not correspond to interior spaces.
- Roofs, towers, and decorations that look acceptable in data but poor in actual views.

This application must close that feedback gap.

The AI must be able to alternate between:

- Exact data inspection.
- Textured visual inspection.
- Structural analysis.
- Coordinate-specific edits.
- Re-rendering.
- Critique.
- Validation.

A high-quality build is not considered complete until the AI has evaluated both exterior and interior views and the system has verified the exported structure.

---

# 3. REQUIRED USE CASES

## 3.1 Import and exact inspection

The operator imports any supported file and can query:

- Build dimensions.
- Source format and version.
- Source `DataVersion`.
- Regions.
- Every exact block coordinate.
- Every exact namespaced block ID.
- Every block-state property.
- Block entities and their NBT.
- Entities where supported.
- Pending block and fluid ticks where supported.
- Biome data where present.
- Unknown or modded data.
- Import diagnostics.

## 3.2 Headless visual inspection

The system must generate viewable PNG images for:

- North, south, east, west, top, and bottom orthographic views.
- Configurable isometric views.
- Configurable arbitrary orthographic cameras.
- Every requested Y layer.
- Arbitrary X and Z slices.
- Multi-layer slabs.
- Detail crops.
- Region-isolated views.
- Material-isolated views.
- Before-and-after comparisons.
- AI change heatmaps.
- Flat semantic renders.
- Textured renders when assets are supplied.

Each image must have machine-readable metadata that maps visible pixels back to exact blocks.

## 3.3 AI analysis

The AI must be able to answer:

- What style is this build?
- Which sides are under-detailed?
- Where are large flat surfaces?
- Which materials dominate?
- Are wall thicknesses coherent?
- Are there sealed or inaccessible rooms?
- Do windows align with rooms and floors?
- Are stairs and corridors navigable?
- Are any clusters disconnected or floating?
- Is the silhouette balanced from all major views?
- Is the interior complete?
- Which coordinates need changes?
- What exact replacement states should be used?

Every conclusion should cite evidence identifiers such as:

- Snapshot IDs.
- Slice IDs.
- Chunk IDs.
- Room IDs.
- Component IDs.
- Issue IDs.
- Exact coordinate ranges.

## 3.4 AI generation

The AI must be able to build a structure through the tool in phases:

1. Parse the creative brief.
2. Define bounds and orientation.
3. Establish a block palette.
4. Plan massing and silhouette.
5. Plan floors, rooms, circulation, and wall thickness.
6. Construct major volumes.
7. Render global views.
8. Critique proportions.
9. Add facade depth and secondary forms.
10. Build interiors.
11. Add lighting and decoration.
12. Run structural and navigation checks.
13. Render layers, slices, and room crops.
14. Apply bounded corrections.
15. Repeat until quality gates pass.
16. Export and re-import for verification.

## 3.5 AI modification

The AI must support instructions such as:

- “Add full interiors without changing the exterior footprint.”
- “Make the rear facade as detailed as the front.”
- “Convert this castle to Gothic style.”
- “Preserve the main tower but redesign both wings.”
- “Repair inaccessible floors.”
- “Reduce palette cost while preserving appearance.”
- “Make the roof less repetitive.”
- “Create a ruined variant.”
- “Fix floating and unsupported details.”
- “Add believable lighting.”

Every modification must become a versioned transaction.

---

# 4. NON-NEGOTIABLE ENGINEERING PRINCIPLES

## 4.1 Exactness

Never reduce a block to only its base name when properties exist.

These are distinct states:

```text
minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]
minecraft:oak_stairs[facing=south,half=top,shape=inner_left,waterlogged=true]
```

Preserve:

- Namespace.
- Block name.
- Complete property map.
- Canonical property ordering.
- Block-entity NBT.
- Entity NBT.
- Region identity.
- Source `DataVersion`.
- Unknown tags.
- Original legacy numeric IDs where conversion is incomplete.

## 4.2 Determinism

Given the same:

- Input bytes.
- Program version.
- Configuration.
- Resource-pack bytes.
- Camera parameters.
- Rendering mode.
- Random seed.

The system must produce byte-identical:

- Canonical manifests.
- Chunk blobs.
- Diagnostics.
- Analysis JSON.
- Snapshot manifests.
- Semantic maps.
- PNG images where the same Pillow/zlib build is used.
- Exported schematic bytes.
- Verification reports.

Deterministic-output rules:

- Sort JSON object keys.
- Use fixed separators and UTF-8.
- End text files with exactly one newline.
- Never write timestamps into deterministic artifacts unless explicitly excluded from hashing.
- Use fixed seeds.
- Sort palette entries deterministically.
- Sort region, entity, and block-entity records deterministically.
- Use fixed PNG compression parameters.
- Do not write PNG time metadata.
- Use deterministic GZIP headers with `mtime=0`.
- Do not depend on hash-randomization order.
- Quantize camera and floating-point metadata consistently.

## 4.3 Lossless representation

Rendering fidelity must never determine data fidelity.

An unsupported model must remain an exact block in canonical storage. The renderer may use a fallback visual, but must record:

- The exact block state.
- The fallback tier.
- The reason.
- The affected coordinates or counts.

Distinguish:

- Unknown block registry entry.
- Missing resource-pack asset.
- Unsupported model feature.
- Unsupported block-entity renderer.
- Invalid source state.
- Corrupt source data.
- Deliberate user replacement.

## 4.4 Adaptive context

Never send a million-block JSON dump to an LLM by default.

Provide:

- Global summary first.
- Relevant regions and images second.
- Exact chunks or slices on demand.
- Deltas after modifications.
- Paginated exact block data through tools.

## 4.5 Human and agent control

All edits must be:

- Bounded.
- Previewable.
- Validated.
- Atomic.
- Reversible.
- Versioned.
- Attributable.
- Diffable.

## 4.6 Adapter boundaries

The sandbox implementation is not a throwaway fork.

Use interfaces for:

- Storage.
- Jobs/tasks.
- Rendering.
- AI providers.
- Canonical serialization.
- Source formats.
- Export formats.

The mandatory implementations are:

- Local filesystem storage.
- Optional SQLite metadata storage.
- Synchronous in-process jobs.
- Pure-Python CPU rendering.
- No-AI offline mode.
- CLI entrypoint.

Future implementations may add web services, GPUs, or remote storage without changing core domain logic.

---

# 5. REQUIRED REPOSITORY ARCHITECTURE

Use a Python-first modular repository.

Recommended structure:

```text
/
├─ pyproject.toml
├─ README.md
├─ LICENSE
├─ SECURITY.md
├─ CONTRIBUTING.md
├─ CHANGELOG.md
├─ app/
│  ├─ __init__.py
│  ├─ cli.py
│  ├─ config.py
│  ├─ errors.py
│  ├─ version.py
│  ├─ domain/
│  │  ├─ models.py
│  │  ├─ coordinates.py
│  │  ├─ palette.py
│  │  ├─ chunks.py
│  │  ├─ diagnostics.py
│  │  ├─ versions.py
│  │  └─ jobs.py
│  ├─ nbt/
│  │  ├─ reader.py
│  │  ├─ writer.py
│  │  ├─ limits.py
│  │  └─ canonical_nbt.py
│  ├─ formats/
│  │  ├─ base.py
│  │  ├─ detect.py
│  │  ├─ sponge_v1.py
│  │  ├─ sponge_v2.py
│  │  ├─ sponge_v3.py
│  │  ├─ legacy_schematic.py
│  │  ├─ litematic.py
│  │  └─ legacy_mapping.py
│  ├─ storage/
│  │  ├─ base.py
│  │  ├─ filesystem.py
│  │  └─ sqlite_metadata.py
│  ├─ assets/
│  │  ├─ resource_pack.py
│  │  ├─ blockstates.py
│  │  ├─ models.py
│  │  ├─ textures.py
│  │  ├─ atlas.py
│  │  └─ fallback_palette.py
│  ├─ render/
│  │  ├─ base.py
│  │  ├─ software.py
│  │  ├─ camera.py
│  │  ├─ geometry.py
│  │  ├─ rasterizer.py
│  │  ├─ texture_sampling.py
│  │  ├─ semantic_maps.py
│  │  ├─ slices.py
│  │  └─ manifests.py
│  ├─ analysis/
│  │  ├─ materials.py
│  │  ├─ surfaces.py
│  │  ├─ components.py
│  │  ├─ support.py
│  │  ├─ rooms.py
│  │  ├─ navigation.py
│  │  ├─ symmetry.py
│  │  ├─ facade.py
│  │  ├─ lighting.py
│  │  └─ consistency.py
│  ├─ patches/
│  │  ├─ models.py
│  │  ├─ operations.py
│  │  ├─ validation.py
│  │  ├─ engine.py
│  │  ├─ diff.py
│  │  └─ history.py
│  ├─ ai/
│  │  ├─ providers.py
│  │  ├─ context.py
│  │  ├─ tools.py
│  │  ├─ evidence.py
│  │  ├─ workflows.py
│  │  └─ budgets.py
│  ├─ export/
│  │  ├─ sponge_v3.py
│  │  ├─ litematic.py
│  │  └─ verify.py
│  └─ serialization/
│     ├─ canonical_json.py
│     ├─ chunk_codec.py
│     └─ hashing.py
├─ tests/
│  ├─ unit/
│  ├─ property/
│  ├─ fuzz/
│  ├─ integration/
│  ├─ golden/
│  └─ fixtures/
├─ docs/
├─ scripts/
└─ examples/
```

Keep pure domain logic independent of CLI and filesystem I/O.

---

# 6. REQUIRED CLI CONTRACT

The package must be invokable as:

```bash
python -m app.cli
```

Every command must:

- Be deterministic.
- Read and write only explicitly provided paths.
- Write artifacts under `--out` unless a specific output file is supplied.
- Print machine-readable errors to stderr when `--json-errors` is enabled.
- Return non-zero exit codes on failure.
- Avoid network calls unless the user explicitly selects an AI provider.
- Support `--quiet`, `--verbose`, and `--log-json`.

## 6.1 Mandatory commands

```bash
# Import and canonicalize any supported structure.
python -m app.cli import <file.schem|file.schematic|file.litematic> --out ./run

# Analyze an imported canonical build.
python -m app.cli analyze ./run --out ./run

# Generate global views, layers, and slices.
python -m app.cli snapshot ./run --views global,layers,slices --out ./run

# Export and prove round-trip equivalence.
python -m app.cli export ./run --format schem --verify --out ./run

# Run the complete offline pipeline.
python -m app.cli pipeline <file> --out ./run
```

## 6.2 Mandatory resource-pack option

```bash
python -m app.cli snapshot ./run \
  --views global,layers,slices \
  --resource-pack /path/to/resourcepack.zip \
  --out ./run
```

Accept:

- Resource-pack directory.
- Resource-pack ZIP.
- Legally obtained Minecraft client JAR containing `assets/`.

Do not bundle Mojang textures.

## 6.3 Required query commands

```bash
python -m app.cli query block ./run --x 10 --y 25 --z -4
python -m app.cli query box ./run --min 0,0,0 --max 15,15,15
python -m app.cli query palette ./run
python -m app.cli query region ./run --name Tower
python -m app.cli query room ./run --id room_12
python -m app.cli query issues ./run --type unsupported
```

Machine-readable output must be available through `--json`.

## 6.4 Required render-on-demand command

```bash
python -m app.cli render ./run \
  --camera-azimuth 45 \
  --camera-elevation 30 \
  --zoom 1.0 \
  --size 1536x1536 \
  --mode textured \
  --out ./run
```

Slice examples:

```bash
python -m app.cli render ./run --slice y:37 --size 1024x1024 --out ./run
python -m app.cli render ./run --slice x:12 --size 1024x1024 --out ./run
python -m app.cli render ./run --crop 10,20,30,32,24,32 --view isometric --out ./run
```

The reusable Python API must expose an equivalent function:

```python
render(
    build,
    camera={"azimuth": 45, "elevation": 30, "zoom": 1.0},
    slice_spec=None,
    crop=None,
    size=(1536, 1536),
    mode="textured",
) -> RenderResult
```

`RenderResult` must contain:

- PNG path.
- Snapshot manifest entry.
- Visible-block hit map.
- Palette-ID map.
- Depth map.
- Diagnostics.

## 6.5 Required patch commands

```bash
python -m app.cli patch validate ./run patch.json
python -m app.cli patch preview ./run patch.json --out ./run
python -m app.cli patch commit ./run patch.json --out ./run
python -m app.cli patch rollback ./run --patch-id patch_123 --out ./run
python -m app.cli version list ./run
python -m app.cli version compare ./run --from ver_1 --to ver_2
```

## 6.6 Required generation workflow command

Provide a provider-independent workflow runner:

```bash
python -m app.cli build-plan ./run design_brief.json --out ./run
python -m app.cli apply-plan ./run build_plan.json --out ./run
```

The no-AI default must accept structured JSON plans and patches produced by an external coding agent.

An optional provider-enabled command may be added:

```bash
python -m app.cli agent ./run --task task.md --provider <profile> --out ./run
```

It must not be required for core tests.

## 6.7 Exit codes

Define stable exit codes, for example:

- `0`: success.
- `2`: invalid CLI usage.
- `10`: unsupported or undetected format.
- `11`: malformed NBT.
- `12`: configured safety limit exceeded.
- `20`: canonicalization failure.
- `30`: rendering failure.
- `31`: missing assets with strict texture mode.
- `40`: patch validation failure.
- `41`: stale patch precondition.
- `50`: export failure.
- `51`: round-trip verification mismatch.
- `60`: optional AI provider failure.

Document the codes.

---

# 7. REQUIRED OUTPUT LAYOUT

The complete pipeline must produce:

```text
run/
├─ canonical.json
├─ chunks/
│  ├─ manifest.json
│  └─ <content-hash>.chunk
├─ raw_preserved/
│  ├─ source.nbt.gz-or-original
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
│  ├─ global_north.png
│  ├─ global_south.png
│  ├─ global_east.png
│  ├─ global_west.png
│  ├─ global_top.png
│  ├─ global_iso_ne.png
│  ├─ layer_y_<n>.png
│  └─ slice_<axis>_<n>.png
├─ semantic_maps/
│  ├─ <snapshot-id>.palette.png-or-bin
│  ├─ <snapshot-id>.coordinate.bin
│  ├─ <snapshot-id>.depth.png-or-bin
│  └─ <snapshot-id>.metadata.json
├─ analysis_artifacts/
├─ ai/
│  ├─ context_manifests/
│  ├─ evidence/
│  ├─ runs/
│  └─ tool_results/
└─ export/
   ├─ out.schem-or.litematic
   └─ verify_report.json
```

## 7.1 `canonical.json`

`canonical.json` may act as a deterministic manifest rather than embedding all voxel arrays inline.

It must contain enough information to locate immutable chunk blobs and recover every exact block.

It must include:

- Canonical schema version.
- Build ID derived from deterministic content.
- Source metadata.
- Coordinate conventions.
- Global bounds.
- Origin.
- Palette.
- Regions.
- Chunk manifest reference.
- Block-entity references.
- Entity references.
- Extension-data references.
- Content hashes.

## 7.2 Required diagnostics

`diagnostics.json` must include:

```json
{
  "render_mode": "software-textured",
  "render_tier": 1,
  "resource_pack": {
    "provided": true,
    "content_hash": "..."
  },
  "fallbacks": [],
  "unsupported_models": [],
  "unknown_blocks": [],
  "degraded_features": [
    "no-live-browser-viewport",
    "no-real-time-orbit-controls"
  ]
}
```

When no pack is supplied, report:

```json
{
  "render_mode": "software-flat",
  "render_tier": 0
}
```

Never report `software-textured` when textures were not actually sampled.

## 7.3 Failure behavior

- `import` must fail non-zero for fatal parse or canonicalization errors.
- `export --verify` must fail non-zero when block states, coordinates, required block entities, or supported entity data differ.
- Rendering in non-strict mode may fall back, but must record every fallback.
- `--strict-textures` must fail if any visible block lacks the requested texture/model support.

---

# 8. CANONICAL INTERNAL BUILD MODEL

Every source format must be converted into one canonical model before rendering, analysis, patching, AI packaging, or export.

Source-format internals must never leak into unrelated subsystems.

## 8.1 Canonical document

Implement a model conceptually equivalent to:

```python
class BuildDocument:
    schema_version: str
    build_id: str
    source: BuildSource
    metadata: BuildMetadata
    coordinate_system: CoordinateSystem
    bounds: IntBoundingBox
    origin: IntVector3
    palette: list[PaletteEntry]
    regions: list[BuildRegion]
    chunks: list[ChunkReference]
    block_entities: list[CanonicalBlockEntity]
    entities: list[CanonicalEntity]
    biomes: CanonicalBiomeContainer | None
    pending_block_ticks: list[CanonicalTick]
    pending_fluid_ticks: list[CanonicalTick]
    diagnostics: list[ImportDiagnostic]
    extension_data: dict[str, object]
    content_hash: str
```

Use validated immutable or effectively immutable Pydantic/dataclass domain models.

## 8.2 Source metadata

Store:

```python
class BuildSource:
    original_filename: str
    detected_format: str
    compression: str
    source_data_version: int | None
    source_format_version: int | None
    source_sha256: str
    uploaded_size_bytes: int
    decompressed_size_bytes: int
```

Detected formats:

- `sponge_schem_v1`.
- `sponge_schem_v2`.
- `sponge_schem_v3`.
- `legacy_mcedit_schematic`.
- `litematic`.
- `unknown`.

## 8.3 Canonical block state

```python
class PaletteEntry:
    palette_id: int
    namespace: str
    block_name: str
    properties: dict[str, str]
    canonical_state: str
    is_air_like: bool
    is_fluid: bool
    render_category: str
    source_legacy_id: int | None
    source_legacy_data: int | None
    required_mod_namespace: str | None
    diagnostics: tuple[str, ...]
```

Canonical property keys must be ordered lexicographically.

## 8.4 Coordinate conventions

Document and enforce:

- `+X`: east.
- `+Y`: up.
- `+Z`: south.
- A block at integer `(x, y, z)` occupies `[x,x+1] × [y,y+1] × [z,z+1]`.
- Region-local and document-global coordinates are distinct types or explicitly tagged values.
- Camera and image manifests identify their coordinate space.

Provide tested transforms among:

- Source-file coordinates.
- Region-local coordinates.
- Canonical document coordinates.
- Camera space.
- Image pixel space.

## 8.5 Chunking

Use 16×16×16 canonical voxel sections as the primary unit.

Each chunk must store:

- Chunk coordinate.
- Global minimum coordinate.
- Edge dimensions.
- Encoding type.
- Palette-index payload.
- Occupancy bitset.
- Non-air count.
- Material histogram.
- Content hash.
- Compression metadata.
- Dirty/version flag.

Choose deterministic encodings:

- Single value.
- Sparse coordinates.
- RLE.
- 8-bit palette indexes.
- 16-bit palette indexes.
- 32-bit palette indexes.
- Bit-packed indexes.

## 8.6 Local content-addressed storage

Store immutable chunk blobs under `run/chunks/`.

Use:

- SHA-256 or BLAKE3 when available.
- Standard-library SHA-256 as mandatory fallback.
- Optional Zstandard compression.
- Standard-library zlib fallback.
- Deduplication by content hash.
- Atomic write-then-rename.

This enables exact version history without one database row per block.

---

# 9. FILE INGESTION AND NBT SECURITY

All uploads are untrusted.

## 9.1 Streaming import

The importer must:

1. Open the file in binary mode.
2. Hash while reading.
3. Enforce compressed-size limits.
4. Detect format and compression by bytes and NBT structure, not extension alone.
5. Preserve original bytes under `raw_preserved/` when configured.
6. Parse with depth, size, and count limits.
7. Canonicalize in-process.
8. Emit job progress to stdout/log artifacts.
9. Write outputs atomically.
10. Clean temporary files on failure.

## 9.2 Compression detection

Recognize:

- GZIP by `1F 8B`.
- ZLIB by validated header/checksum behavior.
- Raw Java NBT.

Do not recursively decompress arbitrary nested content.

## 9.3 NBT safety limits

Configure limits for:

- Compressed bytes.
- Decompressed bytes.
- Compound nesting depth.
- Total tag count.
- String length.
- List length.
- Byte/int/long array length.
- Palette size.
- Region count.
- Dimension magnitude.
- Total volume.
- Block-entity count.
- Entity count.
- Resource-pack archive members.
- JSON model depth.
- Texture dimensions.
- Processing time where enforceable.

Use checked arithmetic for all dimension products.

## 9.4 Error classification

Distinguish:

- Fatal corruption.
- Unsupported format version.
- Recoverable optional-tag omission.
- Invalid array length.
- Out-of-range palette index.
- Unknown block.
- Unknown property.
- Missing resource asset.
- Unsupported visual feature.
- Duplicate block entity.
- Overlapping regions.
- Legacy mapping ambiguity.

Do not convert every warning into a fatal error.

---

# 10. SPONGE `.SCHEM` SUPPORT

Support Sponge schematic versions 1, 2, and 3 through separate adapters.

Do not implement one permissive parser that guesses field meanings across versions.

## 10.1 Sponge v3

Handle:

- Root NBT compound.
- Nested `Schematic` compound.
- `Version`.
- `DataVersion`.
- `Metadata`.
- `Width`.
- `Height`.
- `Length`.
- `Offset`.
- `Blocks`.
- `Blocks.Palette`.
- `Blocks.Data`.
- `Blocks.BlockEntities`.
- `Biomes`.
- `Entities`.
- Unknown extension fields.

Use the verified index order:

```text
index = x + z * Width + y * Width * Length
```

## 10.2 Unsigned dimensions

NBT shorts are signed. Interpret Sponge dimensions using:

```text
value & 0xFFFF
```

before checked multiplication.

## 10.3 Palette parser

Parse strings such as:

```text
minecraft:wheat[age=3]
minecraft:oak_stairs[facing=east,half=top,shape=straight,waterlogged=false]
mod_namespace:custom_block[variant=blue]
```

Validate:

- Namespace syntax.
- Resource path.
- Brackets.
- Duplicate properties.
- Empty property names or values.
- Duplicate palette indexes.
- Negative indexes.
- Index gaps.

Preserve malformed original strings in diagnostics.

## 10.4 Varint decoding

`Blocks.Data` contains consecutive variable-length integers.

Implement strict decoding:

```text
result = 0
shift = 0
repeat:
    byte = next unsigned byte
    result |= (byte & 0x7F) << shift
    if (byte & 0x80) == 0:
        return result
    shift += 7
    if shift exceeds supported width:
        fail
```

Require exactly:

```text
Width * Height * Length
```

indexes.

Report:

- Premature end.
- Excess values.
- Non-terminating varint.
- Integer overflow.
- Palette index out of range.

## 10.5 Block entities

Preserve:

- Relative position.
- Canonical global position.
- Namespaced ID.
- Nested NBT.
- Unknown fields.

## 10.6 Sponge export

Implement deterministic v3 export.

Requirements:

- Deterministic contiguous palette.
- Correct varints.
- Correct dimensions.
- Correct offset.
- Correct block entities.
- Correct nested tags.
- Deterministic NBT compound ordering in this implementation.
- GZIP `mtime=0`.
- Re-import verification.

---

# 11. LEGACY `.SCHEMATIC` SUPPORT

Support MCEdit/Schematica Alpha structures.

Typical fields:

- `Schematic` root.
- `Width`, `Height`, `Length`.
- `Materials`.
- `Blocks`.
- `Data`.
- Optional `AddBlocks`.
- `Entities`.
- `TileEntities`.
- Optional WorldEdit offsets and origins.

Use:

```text
index = y * width * length + z * width + x
```

## 11.1 Legacy ID decoding

For every block:

- Read low 8 bits from `Blocks[index]`.
- Read high 4 bits from `AddBlocks` nibble storage when present.
- Read metadata from `Data[index]`.
- Resolve through a versioned mapping profile.

Test even and odd nibble positions explicitly.

## 11.2 Source-version profile

Support:

```text
legacySourceVersion:
  auto
  1.7.x
  1.8.x
  1.9.x
  1.10.x
  1.11.x
  1.12.2
```

When resolution is ambiguous:

- Preserve numeric ID and metadata.
- Emit an unresolved canonical placeholder.
- Never silently convert to air.
- Allow manual mapping.

## 11.3 Flattening diagnostics

Report:

- Exact mappings.
- Approximate mappings.
- Unresolved mappings.
- Block entities that cannot be converted.
- User-selected fallback policy.

Legacy export is optional and must not be part of the minimum definition of done.

---

# 12. `.LITEMATIC` SUPPORT

Treat `.litematic` as a multi-region container.

Preserve:

- Metadata.
- Minecraft data version.
- Litematic format version.
- Named regions.
- Signed region sizes.
- Region positions.
- Region-local palettes.
- Packed block-state arrays.
- Block entities.
- Entities.
- Pending block ticks.
- Pending fluid ticks.
- Unknown fields.

## 12.1 Region normalization

For each axis:

```text
if size > 0:
    minimum = position
    maximum = position + size - 1

if size < 0:
    minimum = position + size + 1
    maximum = position
```

Canonical dimension is `abs(size)`.

Test every sign combination.

## 12.2 Bits per entry

Use the verified Litematic rule:

```text
bits_per_entry = max(2, ceil(log2(max(1, palette_size))))
```

Expected word count:

```text
ceil(volume * bits_per_entry / 64)
```

## 12.3 Unsigned long handling

NBT longs are signed, but packed extraction must treat them as unsigned 64-bit words:

```python
word_unsigned = signed_word & 0xFFFFFFFFFFFFFFFF
```

## 12.4 Bit unpacking

For index `i`:

```text
start_bit = i * bits_per_entry
start_word = floor(start_bit / 64)
end_word = floor(((i + 1) * bits_per_entry - 1) / 64)
bit_offset = start_bit mod 64
mask = (1 << bits_per_entry) - 1
```

Single-word case:

```text
value = (unsigned(data[start_word]) >> bit_offset) & mask
```

Cross-word case:

```text
low = unsigned(data[start_word]) >> bit_offset
high = unsigned(data[end_word]) << (64 - bit_offset)
value = (low | high) & mask
```

Implement the inverse packer and prove with property tests that:

```text
unpack(pack(values, bits), bits) == values
```

## 12.5 Coordinate order

Use verified region-local mapping:

```text
index = x + z * size_x + y * size_x * size_z
```

Test asymmetric dimensions and unique corner markers.

## 12.6 Overlapping regions

Preserve source regions and expose deterministic flattening policies:

- Preserve layered regions.
- First region wins.
- Last region wins.
- Explicit priority.
- Error on overlap.

Generate an overlap diagnostic map.

## 12.7 Palette growth

Canonical chunks are independent of source packing.

When editing introduces a state:

- Add it to the canonical palette.
- Do not rewrite source packed arrays immediately.
- Rebuild region palettes only during export.
- Recompute bit width.
- Verify cross-word packing.

## 12.8 Litematic export

Implement:

- Multi-region export.
- Flattened single-region export.
- Deterministic region order.
- Deterministic palettes.
- Correct signed sizes.
- Correct long-array packing.
- Correct metadata.
- Re-import verification.

---

# 13. RESOURCE-PACK AND BLOCK-ASSET PIPELINE

Do not bundle proprietary Mojang textures.

Accept assets at runtime through `--resource-pack`.

## 13.1 Supported sources

- Resource-pack directory.
- Resource-pack ZIP.
- Legally obtained client JAR.
- Open-source fallback asset pack supplied under a compatible license.
- Built-in deterministic flat-color map.

## 13.2 ZIP/JAR security

Protect against:

- Path traversal.
- Absolute paths.
- `..` components.
- Symlinks.
- Duplicate entries.
- ZIP bombs.
- Excess members.
- Excess decompressed bytes.
- Oversized images.
- Malformed PNG files.

Read assets directly from the archive when practical rather than extracting everything.

## 13.3 Asset index

Resolve:

```text
assets/<namespace>/blockstates/*.json
assets/<namespace>/models/block/*.json
assets/<namespace>/textures/block/*.png
assets/<namespace>/textures/*.png
assets/<namespace>/atlases/*.json
```

## 13.4 Blockstate resolution

Support:

- `variants`.
- Property selectors.
- Weighted model choices.
- `multipart`.
- OR conditions.
- Nested conditions where defined.
- X and Y rotations.
- UV lock.
- Deterministic weighted choice based on coordinate and seed.

## 13.5 Model inheritance

Resolve:

- Parent models.
- Texture-variable inheritance.
- `#texture` references.
- Model cycles.
- Missing parents.
- Missing textures.
- Built-in model aliases when explicitly supported.

Cache resolved models by content hash.

## 13.6 Model elements

Support CPU generation of cuboid model elements with:

- `from` and `to`.
- Per-face textures.
- Per-face UVs.
- Cullface.
- Face rotation.
- Tint index.
- Element rotation.
- Rotation origin.
- Rescale.
- Ambient-occlusion flag.

This generic model path should cover many slabs, stairs, panes, walls, fences, doors, trapdoors, and decorative blocks when their JSON models are resolvable.

## 13.7 Texture processing

Use Pillow and NumPy to support:

- RGBA textures.
- Nearest-neighbor sampling.
- UV rotation.
- Texture-variable resolution.
- Atlas or direct-image caching.
- Alpha testing.
- Transparent pixels.
- Tint multiplication.
- Animated-texture first-frame fallback with diagnostics.
- Deterministic image conversion.

## 13.8 Tinting

Support configurable deterministic tints for:

- Grass.
- Foliage.
- Water.
- Redstone.
- Stems.
- Generic tint indexes.

Record the tint preset in snapshot manifests.

## 13.9 Special blocks

Some blocks require block-entity or dynamic renderers.

Use ordered fallback:

1. Exact supported static/custom renderer.
2. Resolved static block model.
3. Textured full-cube approximation when defensible.
4. Flat-color bounding-box placeholder.

List every approximation in diagnostics.

Never omit the block.

---

# 14. PURE-PYTHON CPU SOFTWARE RENDERER

This is a core requirement.

The renderer must use only CPU operations through Python, NumPy, and Pillow. It must not create or require a GL context.

## 14.1 Fidelity tiers

### Tier 0 — deterministic flat color

Always available.

- Map canonical block state or base block to RGB/RGBA.
- Apply deterministic face-normal shading.
- Preserve transparent/air-like handling.
- Report `render_mode: software-flat`.

### Tier 1 — textured cubes

Primary minimum target for textured builds.

- Apply actual resource-pack textures to cube faces.
- Resolve top, bottom, and side textures.
- Correctly rotate UVs.
- Use nearest-neighbor sampling.
- Support alpha-tested and translucent faces.
- Report `render_mode: software-textured`.

### Tier 2 — resolved block models

Staged but architecturally required.

- Render JSON model cuboids.
- Support model rotations.
- Support multipart combinations.
- Support partial geometry such as slabs, stairs, walls, fences, panes, doors, trapdoors, and rails where model data is sufficient.
- Fall back per block when unsupported.
- Report support statistics.

## 14.2 Rendering pipeline

Implement a deterministic pipeline:

1. Determine visible region and block selection.
2. Resolve block states to render models.
3. Generate world-space triangles or quads.
4. Apply model transformations.
5. Apply camera view transform.
6. Apply orthographic projection.
7. Clip against near/far and image bounds.
8. Rasterize triangles using a CPU z-buffer.
9. Interpolate UV coordinates.
10. Sample textures with nearest-neighbor rules.
11. Apply tint and directional shading.
12. Alpha-test cutout pixels.
13. Composite translucent surfaces using a documented deterministic policy.
14. Write RGB/RGBA output.
15. Write semantic maps in the same raster pass.

## 14.3 Geometry culling

Cull faces only when safely fully occluded.

Do not cull against:

- Air-like blocks.
- Transparent blocks.
- Partial blocks that do not cover the face.
- Fluids.
- Models without full-face occupancy.

Maintain cross-chunk neighbor access.

## 14.4 Orthographic camera

Support camera specification:

```python
class CameraSpec:
    azimuth_degrees: float
    elevation_degrees: float
    roll_degrees: float = 0
    zoom: float
    target: tuple[float, float, float] | None
    fit_bounds: bool
    margin_blocks: float
    near: float
    far: float
```

Presets:

- North.
- South.
- East.
- West.
- Top.
- Bottom.
- Isometric northeast.
- Isometric northwest.
- Isometric southeast.
- Isometric southwest.

## 14.5 Camera fitting

For deterministic fitting:

1. Compute selected bounds.
2. Transform all eight bounding-box corners into camera space.
3. Compute extents.
4. Apply fixed margin.
5. Choose orthographic scale.
6. Quantize scale and target.
7. Record view and projection matrices.

## 14.6 Rasterizer requirements

Implement:

- Integer image dimensions.
- Float or fixed-point depth buffer.
- Deterministic triangle edge rules.
- Backface culling configurable by material.
- Top-left fill convention or another documented rule.
- Perspective-correct UV not required for orthographic projection, but interpolation must remain correct.
- Tile-based processing or bounded batches for memory control.
- Early rejection for off-screen geometry.
- Stable ordering by chunk, block coordinate, face, and triangle ID.

## 14.7 Transparency

CPU transparency is difficult and must be explicit.

Required minimum:

- Opaque pass with z-buffer.
- Cutout pass with alpha threshold.
- Translucent pass sorted back-to-front by stable depth key.
- Optional weighted blending later.

Record limitations for intersecting translucent geometry.

## 14.8 Lighting

Analysis renders must prioritize legibility over cinematic realism.

Implement deterministic face lighting:

- Ambient term.
- Directional key light.
- Optional secondary fill.
- Normal-based brightness.
- Optional ambient-occlusion heuristic.
- Optional emissive material contribution.

Provide presets:

- `analysis-neutral`.
- `unlit-texture`.
- `flat-semantic`.
- `presentation-soft`.
- `diff-highlight`.

## 14.9 Performance

No real-time FPS requirement exists, but rendering must be bounded and practical.

Use:

- Chunk visibility filtering.
- Face culling.
- Geometry caching.
- Model caching.
- Texture caching.
- NumPy arrays.
- Batched rasterization.
- Incremental re-rendering of affected crops.
- Resolution limits.
- Progress reporting.
- Cancellation checks between chunks or tiles.

Do not allocate all faces for a huge build at once if streaming batches can be used.

## 14.10 Render diagnostics

Record:

- Blocks considered.
- Blocks visible.
- Faces emitted.
- Faces culled.
- Triangles rasterized.
- Texture cache hits.
- Unsupported models.
- Fallback counts.
- Render duration.
- Peak estimated working memory.
- Transparency limitations.

---

# 15. LAYER, SLICE, CROP, AND SEMANTIC RENDERING

## 15.1 Exact Y-layer raster

For each requested Y level:

- Render a top-down grid.
- Use a known integer `pixels_per_block`.
- Preserve exact X/Z orientation.
- Optionally render top texture, canonical color, palette ID, or occupancy.
- Record image origin.
- Record axis direction.
- Record block bounds.

## 15.2 Axis slices

Support:

- `x = index`.
- `y = index`.
- `z = index`.
- Inclusive slabs such as `y=20..24`.

Slice modes:

- Exact cell matrix.
- Frontmost visible surface within slab.
- Maximum-occupancy projection.
- Textured cut surface.
- Palette semantic map.

## 15.3 Detail crops

Render a coordinate-aligned bounding box with:

- Requested camera.
- Requested resolution.
- Optional context margin.
- Optional hidden exterior shell.
- Optional isolated room/component/region.

## 15.4 Snapshot manifest

Every render must include:

```json
{
  "snapshot_id": "snap_...",
  "build_version_id": "ver_...",
  "type": "orthographic",
  "direction": "north",
  "resolution": [1536, 1536],
  "coordinate_space": "document",
  "visible_bounds": {
    "min": [0, 0, 0],
    "max": [99, 79, 99]
  },
  "camera": {
    "azimuth": 0,
    "elevation": 0,
    "zoom": 1.0,
    "target": [50, 40, 50]
  },
  "view_matrix": [],
  "projection_matrix": [],
  "lighting_preset": "analysis-neutral",
  "render_mode": "software-textured",
  "render_tier": 1,
  "resource_pack_hash": "...",
  "renderer_version": "...",
  "background": [0, 0, 0, 0],
  "content_hash": "...",
  "semantic_maps": {}
}
```

## 15.5 Pixel-to-block grounding

Each render must produce a visible-surface hit map.

At minimum, every rendered pixel must encode:

- Whether it hit a block.
- The frontmost canonical block coordinate.
- Palette ID.
- Depth.
- Region ID where applicable.

Recommended storage:

- Dense binary NumPy-compatible arrays with a documented header.
- Compressed `.npz` only if deterministic ZIP metadata is controlled.
- Raw little-endian arrays plus JSON metadata for maximum determinism.
- Lossless PNG for palette IDs when within representable range.

For transparent surfaces, optionally store:

- Primary visible hit.
- Up to N additional ordered hits.
- A truncation flag.

Exact block identity must always come from canonical lookup, not inferred from color.

## 15.6 Mapping functions

Provide tested APIs:

```python
pixel_to_block(snapshot_manifest, px, py) -> PixelHit | None
block_to_pixel(snapshot_manifest, x, y, z) -> list[PixelProjection]
block_at(build, x, y, z) -> CanonicalBlock
```

## 15.7 Semantic maps

Generate:

- Palette-ID map.
- Coordinate hit map.
- Region-ID map.
- Depth map.
- Surface-normal map.
- Occupancy map.
- Changed-block map.
- Issue-category map.

These maps must use exact, documented encodings.

---

# 16. STRUCTURAL ANALYSIS ENGINE

Analysis must run locally and synchronously.

## 16.1 Material analysis

Calculate:

- Count per exact canonical state.
- Count per base block.
- Count per region.
- Count per chunk.
- Count per layer.
- Non-air percentage.
- Exposed-face count.
- Interior-face count.
- Rare materials.
- Palette entropy.
- Material transition frequencies.
- Survival-oriented estimates where mappings exist.

## 16.2 Surface extraction

Classify:

- Exterior surfaces.
- Interior surfaces.
- Roof surfaces.
- Floors.
- Vertical facades.
- Underground surfaces.
- Fully enclosed blocks.
- Blocks touching interior cavities.

## 16.3 Connected components

Support:

- 6-neighbor adjacency.
- 18-neighbor adjacency.
- 26-neighbor adjacency.
- Solid-only adjacency.
- Material-specific adjacency.
- Traversable-air adjacency.

Report:

- Bounds.
- Volume.
- Non-air count.
- Materials.
- Connection to main component.
- Foundation connection.
- Floating status.
- Nearest major component.

## 16.4 Support analysis

Detect:

- Disconnected floating clusters.
- Gravity-affected blocks lacking support.
- Thin unsupported projections.
- Suspicious one-block connectors.
- Unsupported columns.
- Hanging details likely to be intentional.

Classify confidence:

- Definite.
- Likely.
- Warning.
- Informational.

## 16.5 Symmetry and repetition

Detect:

- Reflection symmetry.
- Rotational symmetry.
- Repeated facade modules.
- Repeated windows.
- Repeated room layouts.
- Near-identical chunks.
- Mismatch coordinates.
- Excess uniformity.

## 16.6 Air-volume and room analysis

Flood-fill from outside expanded bounds to classify exterior air.

Detect enclosed and semi-enclosed air volumes.

For each room:

- ID.
- Bounds.
- Volume.
- Floor area.
- Ceiling heights.
- Doorway candidates.
- Window candidates.
- Adjacent rooms.
- Exterior connections.
- Navigability.
- Lighting estimate.
- Furnishing density.
- Sealed status.
- Floor association.

Distinguish tiny cavities from functional rooms.

## 16.7 Navigation graph

Model approximate player movement:

- Standable surfaces.
- Headroom.
- Step-up height.
- Drops.
- Stairs.
- Slabs.
- Ladders.
- Doors.
- Trapdoors.
- Water when configured.
- Narrow passages.
- Floor transitions.

Report:

- Unreachable rooms.
- Dead ends.
- Missing stairs.
- Obstructed doors.
- Invalid headroom.
- Route lengths.

## 16.8 Lighting analysis

Provide an explicitly heuristic CPU analysis unless a future exact Minecraft light engine is integrated.

Calculate:

- Light-emitting blocks.
- Enclosed rooms with no emitter.
- Approximate coverage.
- Dark-area risk.
- Lighting heatmaps.

Never label heuristic output as exact game light values.

## 16.9 Facade depth

Measure:

- Large flat areas.
- Recess depth.
- Projection depth.
- Window spacing.
- Pillar rhythm.
- Trim density.
- Roofline variation.
- Edge treatment.

## 16.10 Interior/exterior consistency

Detect:

- Windows opening into solid fill.
- Exterior doors with no interior space.
- Floors crossing windows.
- Chimneys with no shaft.
- Towers without circulation.
- Inaccessible balconies.
- Rooms outside the shell.
- Unexpected wall-thickness changes.
- Sealed roof voids.

## 16.11 Analysis artifact

Write deterministic `analysis.json` with:

- Schema version.
- Build-version hash.
- Algorithms and configuration.
- Results.
- Evidence references.
- Warnings and limitations.

---

# 17. AI CONTEXT AND PAYLOAD ARCHITECTURE

The core pipeline must work without an AI provider. It produces artifacts an external multimodal AI can inspect.

Keep provider adapters optional.

## 17.1 Context levels

### Level 0 — project synopsis

Include:

- Dimensions.
- Source format.
- Data version.
- Non-air count.
- Region count.
- Palette size.
- Major materials.
- Major components.
- Detected floors and rooms.
- Global render references.
- Diagnostics.

### Level 1 — structural overview

Include:

- Region summaries.
- Room graph.
- Navigation summary.
- Symmetry report.
- Facade report.
- Interior report.
- Major issues.
- Orthographic views.

### Level 2 — selected areas

Include:

- Relevant chunks.
- Relevant slices.
- Crops.
- Local materials.
- Local issues.
- Nearby context.

### Level 3 — exact voxel data

Expose through tools:

- Block lookup.
- Box query.
- Chunk fetch.
- RLE slices.
- Sparse masks.
- Palette definitions.
- Block-entity lookup.

## 17.2 Token-efficient encodings

Palette table:

```text
P0=minecraft:air
P1=minecraft:stone_bricks
P2=minecraft:oak_planks
P3=minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]
```

Run rows:

```text
Y12 Z04: X00-07=P1 X08=P3 X09-15=P0
```

Sparse records:

```text
(x,y,z,palette_id)
```

Cuboid runs:

```text
fill P4 from (10,4,20) to (18,4,28)
```

Delta payload:

- Added blocks.
- Removed blocks.
- Replacements.
- Block-entity changes.
- Metric changes.
- Snapshot changes.

## 17.3 Context manifest

Create deterministic context manifests that list:

- Selected text artifacts.
- Selected images.
- Selected semantic maps.
- Coordinate ranges.
- Evidence IDs.
- Estimated tokens.
- Provider capability assumptions.
- Excluded data and why.

## 17.4 Image selection

Do not include every layer automatically.

Select by:

- Task relevance.
- Changed areas.
- Structural uniqueness.
- Floor boundaries.
- Room boundaries.
- Issue locations.
- Saliency.
- Requested coordinates.

## 17.5 Evidence identifiers

Use IDs such as:

- `view:north:global:ver_12`.
- `slice:y:37:ver_12`.
- `chunk:2:1:-3:ver_12`.
- `room:18:ver_12`.
- `component:4:ver_12`.
- `issue:unsupported:71:ver_12`.

Require AI-generated findings and patches to cite evidence IDs.

---

# 18. AI TOOL PROTOCOL

Expose tools as Python functions and CLI-accessible JSON operations.

## 18.1 Read-only tools

- `get_build_summary`.
- `get_import_diagnostics`.
- `get_palette`.
- `get_material_histogram`.
- `get_regions`.
- `get_region`.
- `get_floors`.
- `get_rooms`.
- `get_room`.
- `get_navigation_graph`.
- `get_components`.
- `get_component`.
- `get_symmetry_report`.
- `get_lighting_report`.
- `get_facade_report`.
- `get_interior_report`.
- `get_block`.
- `query_blocks`.
- `get_chunk`.
- `get_slice`.
- `render_view`.
- `render_crop`.
- `measure_distance`.
- `measure_bounds`.
- `find_nearest`.
- `find_material`.
- `find_block_entities`.
- `get_block_entity`.
- `compare_versions`.
- `get_patch`.

## 18.2 Planning tools

- `create_design_brief`.
- `define_build_bounds`.
- `define_palette_constraints`.
- `create_floor_plan`.
- `create_room_program`.
- `create_build_phase`.
- `estimate_materials`.
- `validate_plan`.

## 18.3 Editing tools

- `set_block`.
- `set_blocks`.
- `fill_cuboid`.
- `hollow_cuboid`.
- `replace_blocks`.
- `draw_line`.
- `draw_polyline`.
- `draw_wall`.
- `draw_floor`.
- `draw_roof`.
- `draw_circle`.
- `draw_ellipse`.
- `draw_cylinder`.
- `draw_sphere`.
- `draw_dome`.
- `draw_arch`.
- `draw_bezier`.
- `extrude_profile`.
- `loft_profiles`.
- `copy_region`.
- `move_region`.
- `rotate_region`.
- `mirror_region`.
- `apply_noise_mask`.
- `apply_gradient_palette`.
- `paste_template`.
- `clear_region`.
- `set_block_entity`.
- `remove_block_entity`.

## 18.4 Transaction tools

- `begin_patch`.
- `preview_patch`.
- `validate_patch`.
- `commit_patch`.
- `rollback_patch`.
- `create_checkpoint`.
- `restore_checkpoint`.
- `branch_version`.
- `merge_versions`.

## 18.5 Export tools

- `validate_export`.
- `export_schem`.
- `export_litematic`.
- `get_export_artifact`.

## 18.6 Tool request schema

Every edit must include:

- Build version ID.
- Coordinate space.
- Intended bounds.
- Maximum affected blocks.
- Operation.
- Reason.
- Evidence references.
- Preconditions.

Example:

```json
{
  "build_version_id": "ver_12",
  "coordinate_space": "document",
  "bounds": {
    "min": [10, 20, 30],
    "max": [25, 30, 45]
  },
  "max_affected_blocks": 5000,
  "operation": {
    "type": "replace_blocks",
    "from": ["minecraft:stone_bricks"],
    "to": "minecraft:cracked_stone_bricks",
    "mask": {
      "type": "surface_noise",
      "seed": 91241,
      "probability": 0.13
    }
  },
  "reason": "Add restrained weathering to the tower facade.",
  "evidence_refs": ["view:north:global:ver_12"],
  "preconditions": {
    "chunk_hashes": {}
  }
}
```

## 18.7 Tool execution transport

At minimum support:

- Direct Python calls.
- JSON request file to CLI command.
- JSON result file.

Optional:

- JSON Lines stdin/stdout agent bridge.
- Local FastAPI adapter.

The optional API must not be required for the sandbox definition of done.

---

# 19. TRANSACTIONAL PATCH ENGINE

## 19.1 Lifecycle

```text
draft
validated
previewed
committed
rejected
rolled_back
superseded
```

## 19.2 Atomicity

Apply changes to a new immutable version manifest. Do not mutate the active version in place.

Use temporary files and atomic rename.

## 19.3 Patch record

Store:

- Parent version.
- New version.
- Operations.
- Changed coordinates or compressed runs.
- Old palette IDs.
- New palette IDs.
- Block-entity changes.
- Affected chunks.
- Bounds.
- Author.
- Model/provider/run ID when applicable.
- Evidence refs.
- Validation report.
- Before/after hashes.
- Before/after snapshots.

## 19.4 Preconditions

Support:

- Expected block state.
- Expected chunk hash.
- Expected version ID.
- Region lock.
- Protected selection.
- Block-entity existence.

Reject stale patches.

## 19.5 Patch limits

Enforce:

- Maximum bounding volume.
- Maximum changed blocks.
- Maximum palette additions.
- Maximum block entities.
- Coordinate bounds.
- Protected materials.
- Locked regions.
- User-configured operation allowlist.

## 19.6 Preview

A preview must produce:

- Diff summary.
- Changed-block list or compressed representation.
- Before/after crops.
- Semantic change map.
- Analysis regressions and improvements.
- Estimated export impact.

## 19.7 Undo and branching

Support:

- Exact rollback.
- Named checkpoints.
- Branches.
- Version comparison.
- Selective patch revert.
- Merge conflict detection.

Do not rely solely on regenerating inverse procedural commands.

---

# 20. AI BUILD-GENERATION WORKFLOW

Implement the workflow as a deterministic state machine that can be driven by an external AI using structured artifacts.

## 20.1 Requirements extraction

Capture:

- Build type.
- Theme.
- Era/style.
- Dimensions.
- Orientation.
- Minecraft target version.
- Mod policy.
- Interior requirements.
- Functional requirements.
- Material constraints.
- Symmetry preference.
- Weathering level.
- Detail density.
- Export format.

## 20.2 Design specification

Produce:

```json
{
  "concept": "...",
  "dimensions": [128, 96, 128],
  "primary_axis": "north_south",
  "floors": [],
  "major_volumes": [],
  "rooms": [],
  "circulation": [],
  "facade_rhythm": {},
  "roof_strategy": {},
  "palette": {},
  "lighting_strategy": {},
  "interior_strategy": {},
  "detail_hierarchy": {},
  "construction_phases": []
}
```

## 20.3 Palette planning

Separate:

- Structural blocks.
- Primary facade.
- Secondary facade.
- Trim.
- Roof.
- Floors.
- Interior walls.
- Accent.
- Glass.
- Lighting.
- Organic materials.
- Weathering.
- Functional blocks.

## 20.4 Massing pass

Build major forms first.

Then render:

- Four side orthographic views.
- Top view.
- At least two isometric views.
- Silhouette masks.

Critique proportions before adding micro-detail.

## 20.5 Floor and room pass

Create:

- Floor slabs.
- Wall shells.
- Interior walls.
- Corridors.
- Stairs.
- Door openings.
- Window alignment.
- Vertical circulation.

Run room and navigation analysis.

## 20.6 Facade pass

Add:

- Recesses.
- Projections.
- Supports.
- Columns.
- Arches.
- Trim.
- Window framing.
- Roof transitions.
- Balconies.
- Secondary silhouettes.

Run facade-depth analysis.

## 20.7 Interior pass

Every required room must have:

- Purpose.
- Entrance.
- Navigable area.
- Suitable dimensions.
- Floor and ceiling treatment.
- Lighting.
- Furnishing or functional detail.
- Connections to neighboring spaces.
- Consistency with exterior openings.

An empty shell is not complete.

## 20.8 Detail hierarchy

Macro:

- Wings.
- Towers.
- Roofs.
- Courtyards.
- Silhouette.

Meso:

- Windows.
- Pillars.
- Arches.
- Roof segments.
- Room groupings.

Micro:

- Trim.
- Furniture.
- Lighting.
- Small supports.
- Material variation.

## 20.9 Critique loop

After each stage:

1. Render global views.
2. Render relevant slices/crops.
3. Run analyses.
4. Identify coordinate-specific defects.
5. Cite evidence.
6. Propose bounded patches.
7. Validate.
8. Preview.
9. Commit.
10. Re-render changed areas.
11. Compare.
12. Continue until quality gates pass or a configured iteration limit is reached.

## 20.10 Final quality gates

Require:

- No unresolved invalid states unless explicitly accepted.
- No unexpected unknown blocks.
- No unintended disconnected major components.
- Required rooms accessible.
- Floors connected.
- Windows/interiors consistent.
- No unreviewed large flat facade regions.
- Interior completeness threshold met.
- Export round trip passes.

---

# 21. OPTIONAL AI PROVIDER ABSTRACTION

The default mode is no-AI/offline.

The coding agent or another multimodal reviewer consumes generated PNGs, semantic maps, analysis, and tool outputs.

Keep an optional provider interface:

```python
class MultimodalProvider(Protocol):
    def get_capabilities(self) -> ProviderCapabilities: ...
    def estimate_tokens(self, request: ModelRequest) -> TokenEstimate: ...
    def create_response(self, request: ModelRequest) -> ModelResponse: ...
    def stream_response(self, request: ModelRequest): ...
    def cancel(self, request_id: str) -> None: ...
```

Track capabilities:

- Text input.
- Image input.
- Tool calling.
- Structured output.
- Streaming.
- Context limit.
- Image limits.
- File references.
- Token estimates.
- Cost policy.

API keys must:

- Never be written to normal logs.
- Be supplied through environment variables or explicit secure configuration.
- Never be embedded in artifacts.
- Be redacted from exceptions.

No provider is required for core installation or tests.

---

# 22. IN-PROCESS JOB SYSTEM

Retain job objects and state enums even though execution is synchronous.

## 22.1 Job states

```text
pending
running
succeeded
failed
cancelled
```

## 22.2 Job record

Store:

- Job ID.
- Type.
- Input hashes.
- Configuration.
- Stage.
- Progress.
- Start/end status.
- Deterministic result references.
- Error object.

Avoid nondeterministic timestamps in hashed artifacts. Operational logs may contain timestamps separately.

## 22.3 Progress

Print concise progress to stderr and persist final status in `jobs.json`.

Example:

```json
{
  "event": "job.progress",
  "job_id": "job_...",
  "stage": "parsing_litematic_regions",
  "progress": 0.42,
  "message": "Decoded 8 of 19 regions",
  "metrics": {
    "voxels_processed": 823004
  }
}
```

## 22.4 Cancellation

Support cooperative cancellation through:

- Keyboard interrupt.
- Cancellation token in Python API.
- Checks between chunks, regions, render tiles, and analysis components.

Clean partial temporary outputs.

---

# 23. LOCAL STORAGE AND METADATA

Use local filesystem as the mandatory storage adapter.

Optional SQLite may store searchable metadata but must not be required to recover the build.

## 23.1 Filesystem adapter

Provide methods conceptually equivalent to:

```python
put_bytes(key, data) -> URI
get_bytes(key) -> bytes
exists(key) -> bool
list(prefix) -> list[str]
delete(key) -> None
atomic_write(key, producer) -> URI
```

Use `file://` URIs internally where a URI is needed.

## 23.2 SQLite adapter

If used:

- Use standard-library `sqlite3`.
- Store projects, versions, jobs, snapshots, patches, and indexes.
- Do not store one row per block.
- Keep chunk blobs on disk.
- Enable transactions.
- Include migrations.
- Make SQLite optional.

## 23.3 Recovery

A `run/` directory copied to another machine must remain self-describing and readable without an external server.

---

# 24. EXPORT AND ROUND-TRIP VERIFICATION

Export is not complete until verification passes.

## 24.1 Sponge v3 export

Generate:

- Correct root/nested compounds.
- Correct dimensions.
- Correct offset.
- Deterministic palette.
- Varint block data.
- Block entities.
- Entities where supported.
- Metadata.
- Deterministic GZIP.

## 24.2 Litematic export

Generate:

- Metadata.
- Regions.
- Signed positions and sizes.
- Region palettes.
- Packed long arrays.
- Block entities.
- Entities and ticks where supported.

## 24.3 Verification process

After export:

1. Import the generated file through the normal importer.
2. Normalize both source canonical version and re-imported version.
3. Compare global bounds.
4. Compare every coordinate and exact canonical state.
5. Compare required block entities and normalized NBT.
6. Compare regions according to the chosen export policy.
7. Compare supported entities.
8. Compare counts and hashes.
9. Write `verify_report.json`.
10. Exit with code `51` on any unacceptable mismatch.

## 24.4 Verification report

Include:

```json
{
  "passed": true,
  "source_version": "ver_12",
  "export_format": "schem_v3",
  "block_count_source": 100000,
  "block_count_reimported": 100000,
  "coordinate_mismatches": 0,
  "state_mismatches": 0,
  "block_entity_mismatches": 0,
  "entity_mismatches": 0,
  "accepted_loss": [],
  "hashes": {}
}
```

Do not use only aggregate counts; exact coordinate comparison is mandatory.

---

# 25. SECURITY REQUIREMENTS

## 25.1 Structure files

Protect against:

- GZIP bombs.
- ZLIB bombs.
- NBT depth bombs.
- Huge declared arrays.
- Integer overflow.
- Invalid UTF-8.
- Malicious filenames.
- Path traversal.
- Excess dimensions.
- Excess regions.
- Excess block entities.

## 25.2 Resource packs

Protect against:

- ZIP bombs.
- Path traversal.
- Duplicate entries.
- Symlinks.
- Huge textures.
- Malformed JSON.
- Parent-model cycles.
- Excess model depth.
- Excess multipart branches.
- Decompression abuse.

## 25.3 AI output

Treat all model-generated JSON as untrusted.

Never:

- Execute generated Python or shell code automatically.
- Allow arbitrary file paths.
- Allow edits outside bounds.
- Bypass patch limits.
- Trust AI-computed affected-block counts.
- Accept invalid NBT.
- Accept stale version IDs.

## 25.4 Filesystem safety

- Resolve paths beneath the selected output root.
- Reject path escapes.
- Use atomic writes.
- Avoid following symlinks by default.
- Avoid overwriting the original input unless explicitly requested.

---

# 26. OBSERVABILITY AND DIAGNOSTICS

Use structured local logs.

Track:

- Input bytes.
- Decompressed bytes.
- Parse duration.
- Voxels per second.
- Chunk encoding ratio.
- Canonicalization duration.
- Analysis duration.
- Render duration.
- Faces and triangles.
- Fallback counts.
- Snapshot count.
- Patch changes.
- Export duration.
- Verification duration.
- Peak estimated memory.

Provide:

- Human-readable console output.
- JSON log mode.
- Correlation IDs.
- Precise error codes.
- Diagnostic documentation.

Do not expose secrets or full private NBT in logs by default.

---

# 27. TESTING STRATEGY

Testing is mandatory.

## 27.1 Unit tests

Cover:

- NBT primitives.
- Compression detection.
- Varints.
- Sponge palette parser.
- Sponge index mapping.
- Legacy nibbles.
- Legacy mappings.
- Litematic bits-per-entry.
- Signed-to-unsigned longs.
- Cross-word extraction.
- Negative region dimensions.
- Canonical state ordering.
- Chunk codecs.
- Hashing.
- Camera transforms.
- Projection.
- Triangle rasterization.
- UV interpolation.
- Texture sampling.
- Alpha testing.
- Pixel-to-block mapping.
- Patch validation.
- Patch rollback.
- Export packers.

## 27.2 Property-based tests

Use Hypothesis for:

- Pack/unpack equality.
- Coordinate/index inverse relationships.
- Random region signs.
- Random palette sizes.
- Random bit widths.
- Chunk encode/decode equality.
- Patch/rollback equality.
- Export/import equality for generated fixtures.
- Pixel/block mapping consistency for exact layer renders.

## 27.3 Fuzz tests

Fuzz:

- NBT.
- GZIP/ZLIB.
- Palette strings.
- Varints.
- Packed long arrays.
- Resource-pack JSON.
- Model inheritance.
- Patch JSON.
- Block-entity NBT.

No crash, hang, or unbounded allocation is acceptable.

## 27.4 Golden fixtures

Include redistributable generated fixtures:

- One block.
- All air.
- One block entity.
- Asymmetric dimensions.
- Unique blocks at all corners.
- Palette sizes around power-of-two boundaries.
- Cross-word packed entries.
- Negative X/Y/Z sizes.
- Multi-region litematic.
- Overlap.
- Unknown modded blocks.
- Missing texture.
- Model-parent cycle.
- Legacy AddBlocks.
- Sparse large build.
- Dense large build.
- Waterlogged states.
- Transparent blocks.
- Stairs and slabs.
- Multipart fence/wall.

## 27.5 Renderer golden tests

Require exact semantic-map comparisons for:

- Camera orientation.
- Layer orientation.
- Coordinate hit maps.
- Palette maps.
- Depth order.
- Cube texture selection.
- UV rotations.
- Face shading.
- Cutout alpha.
- Slab geometry.
- Stair geometry.
- Model rotation.

PNG visual tests may use exact bytes within the pinned environment and pixel tolerances in cross-platform optional tests.

## 27.6 Integration tests

Test:

1. Install package.
2. Import fixture.
3. Query known coordinate.
4. Analyze.
5. Render global views.
6. Render one layer.
7. Validate pixel-to-block map.
8. Preview patch.
9. Commit patch.
10. Roll back patch.
11. Export `.schem`.
12. Re-import.
13. Verify exact equality.

## 27.7 Mandatory clean-environment test

CI must create a fresh Python 3.12 environment and run:

```bash
pip install .
python -m app.cli pipeline tests/fixtures/reference.schem --out ./run
pytest
```

No Node, Docker, database, browser, or GPU may be present or required.

---

# 28. PERFORMANCE AND MEMORY BENCHMARKS

No live FPS target applies, but batch operations must be efficient and bounded.

Datasets:

- 16³.
- 64³.
- 100³.
- 128³.
- 256×128×256 sparse.
- High-palette.
- Multi-region.
- Transparent stress test.
- Non-cube-model stress test.
- Block-entity stress test.

Measure:

- Parse throughput.
- Canonicalization throughput.
- Chunk storage ratio.
- Peak memory.
- Analysis time.
- Global snapshot time.
- Layer snapshot time.
- Geometry cache hit rate.
- Patch time.
- Export time.
- Verification time.

Implement quality/performance profiles:

- `draft`.
- `analysis`.
- `presentation`.
- `semantic`.

Allow configurable:

- Resolution.
- Maximum visible blocks.
- Tile size.
- Geometry cache size.
- Texture cache size.
- Layer range.
- Render tier.

---

# 29. DOCUMENTATION

Produce:

```text
docs/
├─ architecture/
│  ├─ overview.md
│  ├─ sandbox-profile.md
│  ├─ canonical-model.md
│  ├─ chunk-storage.md
│  ├─ cpu-renderer.md
│  ├─ semantic-maps.md
│  ├─ ai-tools.md
│  ├─ patch-engine.md
│  └─ security.md
├─ formats/
│  ├─ sponge-schem.md
│  ├─ legacy-schematic.md
│  └─ litematic.md
├─ cli/
├─ resource-packs/
├─ development/
├─ user-guide/
└─ troubleshooting/
```

Documentation must state clearly:

- Textured rendering does not require a GPU.
- A resource pack is required for real Minecraft textures.
- Mojang assets are not bundled.
- Complex model coverage may fall back with diagnostics.
- The absent feature is live browser interactivity, not AI visual perception.
- Images provide geometry and appearance; canonical data provides exact identity.
- Every export is verified by re-import.

---

# 30. OPEN-SOURCE REQUIREMENTS

Include:

- Deliberately chosen license.
- `CONTRIBUTING.md`.
- `CODE_OF_CONDUCT.md`.
- `SECURITY.md`.
- Issue templates.
- Pull-request template.
- Architecture decision records.
- Development setup.
- Test instructions.
- Fixture-generation guide.
- Third-party dependency notices.
- Asset and trademark policy.

Do not commit:

- Mojang textures.
- User structures.
- API keys.
- Private AI payloads.
- Unlicensed builds.

---

# 31. IMPLEMENTATION PHASES

Work in vertical, testable increments.

## Phase 1 — package and contracts

Deliver:

- `pyproject.toml`.
- Python 3.12 package.
- CLI shell.
- Configuration.
- Error model.
- Storage, job, renderer, and format interfaces.
- CI.
- Documentation skeleton.

## Phase 2 — NBT and canonical model

Deliver:

- Safe NBT parser/wrapper.
- Compression detection.
- Canonical models.
- Chunk storage.
- Deterministic serialization.
- Unit/fuzz tests.

## Phase 3 — format importers

Order:

1. Sponge v3.
2. Litematic.
3. Sponge v2/v1.
4. Legacy schematic.

Each requires golden and property tests.

## Phase 4 — exact querying

Deliver:

- `block_at`.
- Box query.
- Chunk query.
- Palette query.
- Region query.
- Block-entity query.
- JSON CLI output.

## Phase 5 — Tier 0 software renderer

Deliver:

- Orthographic cameras.
- Flat-color cubes.
- Z-buffer.
- Directional shading.
- Global views.
- Layer/slice rendering.
- Pixel-to-block maps.
- Semantic maps.

## Phase 6 — Tier 1 textured cube renderer

Deliver:

- Resource-pack loader.
- Cube model texture resolution.
- UV mapping.
- Alpha cutout.
- Tinting.
- Diagnostics.
- Golden tests.

## Phase 7 — Tier 2 model engine

Deliver:

- Blockstate variants.
- Multipart.
- Parent models.
- Model elements.
- Rotations.
- Partial-block geometry.
- Fallback accounting.

## Phase 8 — analysis engine

Deliver:

- Materials.
- Surfaces.
- Components.
- Support.
- Rooms.
- Navigation.
- Symmetry.
- Facade depth.
- Interior consistency.

## Phase 9 — patch engine

Deliver:

- Operations.
- Validation.
- Preview.
- Commit.
- Version history.
- Rollback.
- Changed-area rendering.

## Phase 10 — AI context and tools

Deliver:

- Context manifests.
- Evidence IDs.
- Read tools.
- Edit tools.
- JSON request/response bridge.
- Budget planner.
- No-AI external-agent workflow.

## Phase 11 — generation workflow

Deliver:

- Design brief schema.
- Build-plan schema.
- Phased execution.
- Critique loop.
- Quality gates.
- Interior completion checks.

## Phase 12 — exporters

Deliver:

- Sponge v3 export.
- Litematic export.
- Exact re-import verification.
- Failure reports.

## Phase 13 — hardening

Deliver:

- Security limits.
- Clean-environment install test.
- Benchmarks.
- Determinism tests.
- Documentation.
- Release process.

---

# 32. DEFINITION OF DONE — MANDATORY SANDBOX PROFILE

The project is not complete until all conditions below pass.

## 32.1 Installation

```bash
pip install .
```

succeeds in a clean Python 3.12 virtual environment using only PyPI and no system package installation.

## 32.2 Pipeline

```bash
python -m app.cli pipeline tests/fixtures/reference.schem --out ./run
```

exits `0` and creates:

- `canonical.json`.
- Chunk data.
- `raw_preserved/`.
- `diagnostics.json`.
- `analysis.json`.
- Global snapshots.
- Layer snapshots.
- Slice snapshots.
- Snapshot manifest.
- Semantic maps.
- Exported schematic.
- Verification report.

## 32.3 Exact data

- Every block is queryable by coordinate.
- Exact namespace, block ID, and state are preserved.
- Air is not assumed to be palette index zero.
- Block entities are preserved.
- Unknown modded data is preserved.

## 32.4 Rendering

- PNGs legibly show the build.
- With a valid resource pack, common full-cube blocks use real textures.
- Without a pack, Tier 0 flat mode works.
- Every fallback is recorded.
- Orthographic views work.
- Isometric views work.
- Y layers work.
- X/Z slices work.
- Detail crops work.
- Pixel-to-block maps work.
- The renderer requires no GL context.

## 32.5 Analysis

- Material analysis works.
- Connected components work.
- Room detection works on fixtures.
- Navigation reports work.
- Facade flatness analysis works.
- Interior/exterior checks emit grounded findings.

## 32.6 AI loop

- An external AI can inspect snapshots and semantic maps.
- It can query exact blocks.
- It can submit a bounded patch.
- The patch can be previewed.
- The patch can be committed.
- Changed areas can be re-rendered.
- The patch can be rolled back exactly.

## 32.7 Export

- `.schem` export works.
- `.litematic` export works.
- Export re-import performs exact coordinate/state comparison.
- Any mismatch exits non-zero with a precise diff.

## 32.8 Tests

- `pytest` passes.
- Litematic bit-unpacking property tests pass.
- Export/import property tests pass.
- CPU-renderer semantic-map tests pass.
- Clean-environment CLI integration test passes.

## 32.9 Diagnostics

`diagnostics.json` explicitly reports the render mode and every degraded feature.

If no resource pack is provided, the minimum expected value is:

```json
{
  "render_mode": "software-flat"
}
```

If a pack is provided and Tier 1 succeeds:

```json
{
  "render_mode": "software-textured"
}
```

## 32.10 No forbidden hidden dependency

The project fails the definition of done if core execution secretly requires:

- Node.
- Browser automation.
- Docker.
- Postgres.
- Redis.
- S3.
- GPU.
- OpenGL.
- External executable.

---

# 33. EXPLICITLY OUT OF SCOPE FOR THE MANDATORY PROFILE

The following are not required and must not block completion:

- Interactive Three.js/WebGL browser viewport.
- React/Vite web application.
- Mouse orbit/pan/zoom UI.
- 60 FPS real-time rendering.
- GPU rendering.
- Headless Chromium rendering.
- Postgres.
- Redis.
- Celery.
- S3.
- Docker.
- Kubernetes.
- Multi-user authentication UI.

These may be documented as future adapters.

Textured rendering is **not** out of scope.

AI visual inspection is **not** out of scope.

Exact per-block reporting is **not** out of scope.

Generation, modification, critique, export, and verification are **not** out of scope.

---

# 34. OPTIONAL FUTURE FULL-PRODUCT ADAPTERS

After the mandatory profile is complete and passing, the architecture may support optional adapters for:

- FastAPI HTTP API.
- React/Three.js viewer.
- PostgreSQL metadata.
- Redis task queue.
- S3 object storage.
- GPU renderer.
- Multi-user workspaces.
- Hosted AI integrations.

These must reuse:

- Canonical models.
- Format adapters.
- Analysis engine.
- Patch engine.
- AI tool schemas.
- Exporters.

Do not implement these first. Do not make the sandbox baseline depend on them.

---

# 35. CODING RULES

Use:

- Strict type hints.
- Pydantic or validated dataclasses at boundaries.
- Explicit error classes.
- Pure functions for coordinate and bit math.
- Checked arithmetic.
- Atomic filesystem writes.
- Stable sorting.
- Content hashes.
- Cancellation checks.
- Progress reporting.
- Tests beside complex algorithms.

Do not:

- Assume one region.
- Assume positive dimensions.
- Assume air index zero.
- Assume palette fits in one byte.
- Assume packed values fit in one long.
- Assume filenames identify formats.
- Assume every block is a cube.
- Assume every texture is opaque.
- Assume unsupported blocks can become air.
- Assume aggregate export counts prove equality.
- Load one million Python block objects if chunk arrays can represent them compactly.
- Create one image without a corresponding manifest.
- Infer exact IDs from rendered pixels.
- Execute AI-generated code.
- Hide fallback rendering.
- Write nondeterministic timestamps into content-hashed output.
- Stop after architecture planning.

---

# 36. REQUIRED INITIAL OUTPUT FROM THE CODING AI

Before creating implementation files, provide:

1. Concise architecture summary.
2. Dependency list proving sandbox compatibility.
3. Package boundary diagram.
4. Canonical data model.
5. Filesystem artifact layout.
6. Job state machine.
7. Patch state machine.
8. AI workflow state machine.
9. CPU renderer pipeline diagram.
10. Pixel-to-block encoding design.
11. Security threat model.
12. Test strategy.
13. Phased implementation checklist.
14. Explicit assumptions.
15. High-risk areas.
16. Current upstream format facts that must be verified.

Then begin implementation immediately.

Do not stop after the plan.

---

# 37. REQUIRED EXECUTION BEHAVIOR

For each phase:

1. State the objective.
2. Identify files/packages.
3. Implement production code.
4. Add tests.
5. Run tests.
6. Fix failures.
7. Run the relevant CLI command.
8. Inspect generated artifacts.
9. Update documentation.
10. Proceed.

When encountering ambiguity:

- Inspect current upstream specifications when internet access is available.
- Preserve raw data.
- Make the smallest documented assumption.
- Add a fixture or compatibility test.
- Continue.

Do not use uncertainty as a reason to omit a subsystem.

---

# 38. FINAL PRODUCT STANDARD

The system succeeds only when a capable AI can operate like a Minecraft build team rather than a blind schematic generator.

The AI must be able to:

- See global form through textured CPU renders.
- Request any additional angle.
- Inspect every layer and cross-section.
- Map visible pixels to exact blocks.
- Query exact coordinates and states.
- Understand regions, rooms, surfaces, and navigation.
- Identify unfinished exterior and interior areas.
- Propose coordinate-specific changes.
- Preview and apply changes safely.
- Re-render the result.
- Critique its own work.
- Undo mistakes.
- Export a legitimate Minecraft Java structure.
- Prove that export preserved every required block and coordinate.

The absence of a browser must not make the AI blind.

The absence of a GPU must not eliminate textures.

The absence of remote services must not weaken exactness, analysis, editing, or verification.

The finished mandatory profile must demonstrate, end to end:

> **Import → canonicalize → query every block → render textured views on CPU → generate semantic grounding → analyze → modify transactionally → re-render → export → re-import → verify zero block/coordinate loss.**
