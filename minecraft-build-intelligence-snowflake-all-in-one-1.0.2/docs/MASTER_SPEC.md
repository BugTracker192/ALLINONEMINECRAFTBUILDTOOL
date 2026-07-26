# ULTIMATE MASTER PROMPT

## Build a Production-Grade Minecraft Build Intelligence, Visualization, Analysis, and AI Construction Platform

---

# 0. COMMAND TO THE CODING AI

You are the **Principal Software Architect, Staff Graphics Engineer, Minecraft Data-Format Engineer, AI Systems Engineer, Security Engineer, and Product Engineer** responsible for building this entire application from scratch.

Read this specification completely before writing code.

You are not building:

* A demo.
* A toy schematic viewer.
* A single-page proof of concept.
* A cube renderer with approximate colors.
* A chat wrapper that uploads screenshots to an LLM.
* A parser that works only on one sample file.
* A system that loads every block into one enormous prompt.
* A collection of unfinished stubs, fake services, mocked responses, or TODO comments.

You are building a **production-grade, open-source developer platform** that allows humans and multimodal AI agents to inspect, understand, modify, generate, verify, and export highly detailed Minecraft Java Edition structures.

The completed platform must let an AI reason about a build at the same time through:

1. Exact block coordinates.
2. Exact namespaced block IDs.
3. Exact block-state properties.
4. Block-entity NBT.
5. Region and layer organization.
6. Deterministic 2D slices.
7. Orthographic and perspective renders.
8. Material statistics.
9. Geometric measurements.
10. Structural and interior analysis.
11. Transactional editing tools.
12. Re-rendered visual feedback after every meaningful change.

The central engineering principle is:

> **A build must never be represented to an AI only as an image, and it must never be represented only as a raw block list. The system must merge exact symbolic voxel data with deterministic visual evidence and expose both through an adaptive, queryable tool interface.**

Do not skip difficult subsystems. Do not silently simplify requirements. When an exact Minecraft rendering feature cannot initially be reproduced, implement a documented fallback, expose the limitation in diagnostics, and preserve the underlying block data without loss.

---

# 1. PRODUCT VISION

Create a browser-based application and developer platform that bridges Minecraft Java build formats and advanced AI agents.

A user must be able to:

* Upload `.schematic`, `.schem`, or `.litematic` files.
* See a clear, high-quality, interactive 3D preview.
* Inspect any coordinate and retrieve its exact block state.
* Scrub through Y layers.
* Hide, isolate, or inspect regions and materials.
* Generate deterministic visual datasets for AI analysis.
* Ask an AI to analyze architecture, style, composition, interiors, materials, flaws, or incomplete areas.
* Ask an AI to improve an imported build.
* Ask an AI to create a build from a natural-language brief.
* Watch the AI create and revise the structure through safe block-edit operations.
* Compare every revision visually and structurally.
* Undo or revert any AI operation.
* Export the final result as a valid, current Minecraft Java schematic.
* Verify that exported output can be reopened without block loss or coordinate corruption.

The tool must be suitable for:

* Professional Minecraft map makers.
* Adventure-map creators.
* Build teams.
* Server designers.
* AI-assisted builders.
* Researchers studying voxel-world agents.
* Developers integrating Minecraft structure understanding into other tools.
* Automated benchmark and evaluation systems.

---

# 2. FUNDAMENTAL USE CASES

## 2.1 Human visual inspection

The human user uploads a structure and receives:

* Interactive orbit, pan, and zoom.
* Perspective and orthographic cameras.
* Front, back, left, right, top, bottom, and isometric presets.
* Layer-by-layer inspection.
* Clipping planes.
* Region visibility controls.
* Material isolation.
* Transparency and X-ray modes.
* Coordinate hover and click inspection.
* Selection boxes.
* Distance, area, and volume measurement tools.
* Block-state and block-entity inspection.
* Material counts.
* Region and component statistics.
* A minimap or layer map.
* Search by block ID, property, coordinate, region, or NBT content.

## 2.2 AI analysis of imported builds

The AI must be capable of answering questions such as:

* What architectural style does this build use?
* Which portions are visually under-detailed?
* Is the silhouette balanced from every side?
* Does the interior correspond sensibly to the exterior?
* Are wall thicknesses consistent?
* Are there inaccessible or sealed rooms?
* Are there unsupported floating sections?
* Are windows aligned with interior spaces?
* Which materials dominate the palette?
* Where is repetition excessive?
* Which areas have weak contrast?
* Are staircases navigable?
* Are doors, corridors, and rooms connected?
* Does the build appear unfinished from any major viewpoint?
* Which exact coordinates should be changed?
* Which blocks should be replaced or added?

The AI must support every claim with either:

* Exact coordinate data.
* A cited chunk or slice.
* A deterministic render.
* A measurement.
* A material or connectivity analysis.
* A machine-generated validation result.

## 2.3 AI-generated builds

The AI must be able to create a build through the platform rather than generating an opaque binary file in one pass.

The intended workflow is:

1. Parse the user’s brief.
2. Produce a design specification.
3. Establish dimensions and coordinate bounds.
4. Define architectural massing.
5. Define floors, rooms, circulation, and wall thickness.
6. Choose a constrained block palette.
7. Construct the large forms.
8. Render and inspect the silhouette.
9. Add facade depth and secondary forms.
10. Build interiors.
11. Add detail and decoration.
12. Run structural and accessibility checks.
13. Render all major views and critical slices.
14. Critique the build.
15. Apply coordinate-specific revisions.
16. Repeat until quality thresholds are met.
17. Export the result.

The AI must use structured editing tools. It must not normally return millions of raw block-placement commands in natural-language output.

## 2.4 AI-assisted modification

The user can issue requests such as:

* “Make this castle more Gothic without changing its footprint.”
* “Add complete interiors to all floors.”
* “Make the roof less repetitive.”
* “Replace expensive materials with survival-friendly alternatives.”
* “Turn this facade into a ruined version.”
* “Make the rear as detailed as the front.”
* “Preserve the central tower but redesign the wings.”
* “Add navigable stairs between every floor.”
* “Fix floating or unsupported blocks.”
* “Create a night-lighting pass.”
* “Mirror the left wing while preserving the asymmetric tower.”

Every modification must become a versioned patch with:

* An author.
* A timestamp.
* A reason.
* The affected bounding boxes.
* The previous values.
* The new values.
* Validation results.
* Before-and-after render references.

---

# 3. NON-NEGOTIABLE PRODUCT PRINCIPLES

## 3.1 Exactness

Never reduce a block to only its base name when state properties are present.

Treat these as different states:

* `minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]`
* `minecraft:oak_stairs[facing=south,half=top,shape=inner_left,waterlogged=true]`

Preserve:

* Namespace.
* Block name.
* Every state property.
* Block-entity NBT.
* Entity NBT where supported.
* Biome data where present.
* Scheduled block and fluid ticks where present.
* Region metadata.
* Source DataVersion.
* Unknown or modded tags.

## 3.2 Determinism

Given the same:

* Input file.
* Asset pack.
* renderer version.
* camera specification.
* lighting preset.
* snapshot options.

The system must produce reproducible:

* Canonical block data.
* Chunk hashes.
* Visual snapshots.
* AI manifests.
* Exported schematic data.

## 3.3 Lossless internal representation

Importing a format must not destroy information merely because the initial renderer cannot display it.

Store unsupported information in typed extension fields or raw-NBT preservation containers.

The internal model must distinguish:

* Unsupported visual rendering.
* Unknown block registry entry.
* Invalid block-state property.
* Missing external resource pack.
* Corrupt file data.
* Information that is valid but not understood.
* Information intentionally removed by the user.

## 3.4 Adaptive context

Never send an entire million-block structure to an LLM by default.

The AI receives:

* A global summary first.
* Relevant regions second.
* Exact chunks and slices only when needed.
* Delta information after edits.
* Full raw data only through explicit paginated tool calls.

## 3.5 Human control

All destructive AI changes must be:

* Previewable.
* Transactional.
* Reversible.
* Scope-limited.
* Validated.
* Attributable.
* Diffable.

## 3.6 Provider independence

Do not tightly couple the application to one AI provider.

Implement adapters for multimodal model providers behind one internal interface.

At minimum, design for:

* OpenAI-compatible multimodal APIs.
* Anthropic-compatible multimodal APIs.
* Local OpenAI-compatible servers.
* Future providers.
* A no-AI offline mode.

Current major APIs accept images as multimodal message content, but provider-specific limits, token accounting, file handling, and supported image types vary. Detect capabilities through configuration and keep provider logic isolated.

---

# 4. REQUIRED HIGH-LEVEL ARCHITECTURE

Use a modular monorepo.

A recommended structure is:

```text
/
├─ apps/
│  ├─ web/                    # React + TypeScript browser application
│  ├─ api/                    # FastAPI application
│  ├─ worker/                 # Parsing, rendering, AI, export workers
│  ├─ renderer-service/       # Headless deterministic rendering service
│  └─ docs/                   # User and developer documentation
├─ packages/
│  ├─ protocol/               # Shared JSON Schemas, OpenAPI-derived types
│  ├─ renderer/               # Shared Three.js rendering engine
│  ├─ ui/                     # Reusable UI components
│  ├─ block-assets/           # Resource-pack resolver and model compiler
│  ├─ ai-client/              # Frontend types for AI runs and streaming
│  └─ test-fixtures/          # Generated, redistributable test fixtures
├─ services/
│  ├─ parser/                 # Format adapters and canonicalization
│  ├─ analysis/               # Geometry, rooms, components, metrics
│  ├─ snapshot/               # Layers, semantic maps, camera manifests
│  ├─ ai-orchestrator/        # Tool-driven agent workflows
│  ├─ patch-engine/           # Transactional edits and version graph
│  └─ exporter/               # .schem/.litematic export
├─ migrations/
├─ infrastructure/
│  ├─ docker/
│  ├─ compose/
│  ├─ kubernetes/
│  └─ observability/
├─ scripts/
├─ tests/
├─ .github/workflows/
├─ docker-compose.yml
├─ LICENSE
├─ SECURITY.md
├─ CONTRIBUTING.md
└─ README.md
```

You may alter the exact directory names, but preserve strict subsystem boundaries.

## 4.1 Recommended technology choices

Use current stable, mutually compatible versions at implementation time and pin them in lockfiles.

### Frontend

* TypeScript with strict mode.
* React.
* Vite or another modern production bundler.
* Three.js as the primary renderer.
* React Three Fiber is optional, not mandatory.
* Zustand, Redux Toolkit, or an equivalent predictable state manager.
* TanStack Query or equivalent for server state.
* Web Workers for heavy client-side processing.
* OffscreenCanvas where supported.
* IndexedDB for local caches.
* Accessible component primitives.
* Playwright for end-to-end tests.

### Backend

* Python.
* FastAPI.
* Pydantic models.
* SQLAlchemy or equivalent typed ORM.
* PostgreSQL.
* Redis.
* Celery, Dramatiq, Arq, or an equivalent durable task system.
* S3-compatible object storage.
* Server-sent events or WebSockets for job progress.
* OpenTelemetry.

FastAPI supports streamed upload handling through `UploadFile`; long-running parsing, rendering, and AI operations must be delegated to durable workers rather than performed inside a request handler. A task system must expose progress, retries, failure states, cancellation, and idempotency.

### Optional performance layer

A Rust or C++ acceleration layer may be introduced for:

* NBT parsing.
* Bit unpacking.
* Voxel transforms.
* Greedy meshing.
* Connected-component analysis.
* Compression.
* Large patch application.

Do not introduce native code without:

* Stable language bindings.
* Pure-language fallback or clear installation support.
* Cross-platform CI.
* Memory-safety tests.
* Benchmarks proving the value.

---

# 5. CANONICAL INTERNAL BUILD MODEL

Every input format must be converted into one canonical representation before rendering, analysis, editing, AI packaging, or export.

Do not let the UI, renderer, or AI layer directly depend on `.schem`, `.schematic`, or `.litematic` internals.

## 5.1 Canonical document

Implement a model conceptually equivalent to:

```ts
interface BuildDocument {
  schemaVersion: string;
  buildId: string;
  source: BuildSource;
  metadata: BuildMetadata;
  coordinateSystem: CoordinateSystem;
  bounds: IntBoundingBox;
  origin: IntVector3;
  palette: PaletteEntry[];
  regions: BuildRegion[];
  chunks: ChunkReference[];
  blockEntities: CanonicalBlockEntity[];
  entities: CanonicalEntity[];
  biomes?: CanonicalBiomeContainer;
  pendingBlockTicks?: CanonicalTick[];
  pendingFluidTicks?: CanonicalTick[];
  diagnostics: ImportDiagnostic[];
  extensionData: Record<string, unknown>;
  contentHash: string;
}
```

## 5.2 Source metadata

Store:

```ts
interface BuildSource {
  originalFilename: string;
  detectedFormat:
    | "sponge_schem_v1"
    | "sponge_schem_v2"
    | "sponge_schem_v3"
    | "legacy_mcedit_schematic"
    | "litematic"
    | "unknown";
  compression: "gzip" | "zlib" | "raw_nbt";
  sourceDataVersion?: number;
  sourceFormatVersion?: number;
  sourceSha256: string;
  uploadedSizeBytes: number;
  decompressedSizeBytes: number;
}
```

## 5.3 Canonical block state

```ts
interface PaletteEntry {
  paletteId: number;
  namespace: string;
  blockName: string;
  properties: Record<string, string>;
  canonicalState: string;
  isAirLike: boolean;
  isFluid: boolean;
  renderCategory:
    | "opaque"
    | "cutout"
    | "translucent"
    | "emissive"
    | "special"
    | "unknown";
  sourceLegacyId?: number;
  sourceLegacyData?: number;
  requiredModNamespace?: string;
  diagnostics?: string[];
}
```

Canonicalize property ordering lexicographically so equivalent block states hash identically.

Example:

```text
minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]
```

Never discard unknown properties merely because the installed asset pack lacks a model.

## 5.4 Coordinate conventions

Define and document exactly:

* `+X`: east/right.
* `+Y`: up.
* `+Z`: south/forward.
* Integer coordinates refer to block cells.
* A block at `(x, y, z)` occupies `[x,x+1] × [y,y+1] × [z,z+1]`.
* Region coordinates may be local.
* Canonical coordinates are document-global.
* Camera metadata must record the conversion between world, document, region, and image coordinates.

Every API response containing coordinates must identify its coordinate space.

## 5.5 Internal chunking

Use **16×16×16 voxel sections** as the primary storage and processing unit.

Each chunk record must contain:

* Chunk coordinate.
* Global minimum coordinate.
* Dimensions for edge chunks.
* Palette-index encoding type.
* Occupancy bitset.
* Non-air count.
* Material histogram.
* Content hash.
* Compression type.
* Blob reference.
* Dirty/version flag.
* Optional exposed-face summary.
* Optional connected-component labels.
* Optional room or semantic labels.

Choose an encoding per chunk:

* Single-value chunk.
* Sparse coordinate list.
* Palette-index array using 8-bit values.
* Palette-index array using 16-bit values.
* Palette-index array using 32-bit values.
* Run-length encoding.
* Bit-packed encoding.

Encoding selection must be deterministic and benchmarked.

## 5.6 Chunk storage

Store chunk blobs separately from relational metadata.

Use:

* Content-addressed object keys.
* SHA-256 or BLAKE3 hashes.
* Zstandard or another well-supported compression format.
* Deduplication of identical chunks.
* Immutable chunk versions.
* A manifest that maps a build version to chunk hashes.

This enables:

* Efficient undo.
* Branching versions.
* Partial loading.
* Incremental snapshots.
* AI delta analysis.
* Deduplicated copies.
* Fast comparison.

---

# 6. FILE INGESTION AND NBT SAFETY

All uploaded files are untrusted.

## 6.1 Upload pipeline

The upload process must:

1. Stream the file instead of loading it entirely into request memory.
2. Compute a content hash while streaming.
3. Enforce compressed-size limits.
4. Detect extension and magic bytes independently.
5. Store the original upload in quarantined object storage.
6. Create an import job.
7. Parse inside an isolated worker.
8. Enforce CPU, memory, and wall-clock limits.
9. Produce structured diagnostics.
10. Never execute content from the uploaded file.

## 6.2 Compression detection

Detect by bytes, not filename:

* GZIP magic: `1F 8B`.
* Valid ZLIB headers where supported.
* Raw uncompressed Java NBT.
* Reject unsupported archive nesting unless intentionally processing a resource pack.

Do not repeatedly decompress ambiguous data without a strict attempt limit.

## 6.3 NBT parser limits

Protect against NBT bombs with configurable limits for:

* Maximum decompressed bytes.
* Maximum compound depth.
* Maximum tag count.
* Maximum list length.
* Maximum array length.
* Maximum string length.
* Maximum palette size.
* Maximum structure dimensions.
* Maximum total volume.
* Maximum block-entity count.
* Maximum entity count.
* Maximum regions.
* Maximum diagnostic count.
* Maximum processing time.

All multiplication involving dimensions must use checked arithmetic.

Reject or quarantine a structure when:

```text
abs(width) × abs(height) × abs(length)
```

overflows the selected integer type or exceeds configured limits.

## 6.4 Parser behavior

The parser must distinguish:

* Fatal corruption.
* Unsupported format version.
* Recoverable missing optional tags.
* Invalid array length.
* Out-of-range palette index.
* Unknown block.
* Unknown property.
* Missing resource pack.
* Invalid block entity.
* Duplicate block entity.
* Overlapping regions.
* Unsupported modded content.
* Export-only limitations.

Do not convert every warning into a fatal failure.

---

# 7. SPONGE `.SCHEM` SUPPORT

Support Sponge schematic format versions 1, 2, and 3 through separate version adapters.

The current published Sponge specification is version 3. Version 3 stores the `Schematic` compound under the root, requires case-sensitive fields, uses a block palette and varint-encoded block data, and defines the index order as:

```text
index = x + z × Width + y × Width × Length
```

Version-specific fields and nesting must be validated against the corresponding specification rather than guessed.

## 7.1 Sponge v3 requirements

Handle:

* Root compound.
* Nested `Schematic` compound.
* `Version`.
* `DataVersion`.
* `Metadata`.
* `Width`.
* `Height`.
* `Length`.
* `Offset`.
* `Blocks`.
* `Blocks.Palette`.
* `Blocks.Data`.
* `Blocks.BlockEntities`.
* `Biomes`.
* `Entities`.
* Unknown extension fields.

## 7.2 Unsigned shorts

NBT shorts are signed, but Sponge dimensions use the full unsigned 16-bit range.

Interpret dimensions using:

```text
value & 0xFFFF
```

before checked volume calculation.

## 7.3 Palette parsing

Palette keys contain a block resource location and optional state properties:

```text
minecraft:wheat[age=3]
minecraft:oak_stairs[facing=east,half=top,shape=straight,waterlogged=false]
mod_namespace:custom_block[variant=blue]
```

Implement a real parser.

Do not split properties using naive string operations that fail on malformed content.

Validate:

* Namespace.
* Resource path.
* Bracket matching.
* Duplicate property keys.
* Empty keys or values.
* Palette-index duplicates.
* Palette-index gaps.
* Negative indexes.
* Indexes exceeding data limits.

Preserve malformed entries in diagnostics and raw extension data when possible.

## 7.4 Sponge varint decoding

`Blocks.Data` is an NBT byte array containing consecutive variable-length integers.

Implement strict unsigned varint decoding:

```text
result = 0
shift = 0

repeat:
    byte = next unsigned byte
    result |= (byte & 0x7F) << shift

    if (byte & 0x80) == 0:
        return result

    shift += 7
    if shift exceeds configured integer width:
        error
```

Require exactly:

```text
Width × Height × Length
```

decoded palette indexes.

Report:

* Premature end.
* Excess decoded entries.
* Non-terminating varint.
* Integer overflow.
* Palette index outside the palette.

## 7.5 Sponge block entities

Preserve:

* Relative position.
* Namespaced ID.
* Nested data.
* Unknown fields.
* DataVersion-sensitive content.

Keep block-entity data separate from block state data but index it by canonical coordinate.

## 7.6 Sponge export

Implement v3 export first.

Requirements:

* Deterministic palette order.
* Contiguous palette indexes.
* Correct varint byte stream.
* Correct dimensions and offsets.
* Correct nested compounds.
* Preserved metadata where legal.
* Valid GZIP-compressed NBT.
* Re-import verification as part of the export job.

After export:

1. Parse the newly generated file.
2. Compare canonical dimensions.
3. Compare every block state.
4. Compare block-entity coordinates and normalized NBT.
5. Compare entity counts and supported fields.
6. Fail export validation if the result differs unexpectedly.

---

# 8. LEGACY `.SCHEMATIC` SUPPORT

Support the old MCEdit/Schematica Alpha format as a legacy import adapter.

This format commonly contains:

* Root named `Schematic`.
* `Width`, `Height`, `Length`.
* `Materials`, normally `Alpha`.
* `Blocks`.
* `Data`.
* Optional `AddBlocks`.
* `Entities`.
* `TileEntities`.
* Optional WorldEdit origin and offset fields.

The block index order is:

```text
index = y × width × length + z × width + x
```

Legacy `AddBlocks` stores extra block-ID bits in nibbles, and historical implementations require careful even/odd nibble handling. Use golden fixtures and trusted implementation behavior rather than assumptions.

## 8.1 Legacy block decoding

For every voxel:

* Read low eight bits from `Blocks[index]`.
* Read four additional bits from `AddBlocks` when present.
* Read legacy metadata from `Data[index]`.
* Resolve the numeric ID and metadata through a versioned mapping table.

Do not claim perfect conversion when the originating Minecraft version is unknown.

Expose an import setting:

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

When auto-detection is inconclusive:

* Preserve numeric ID and data.
* Use a placeholder visual.
* Mark the state unresolved.
* Ask the user to select a legacy mapping profile.
* Do not silently replace unknown blocks with air.

## 8.2 Flattening conversion

Legacy numeric IDs and metadata cannot always map perfectly to modern states.

Implement:

* Versioned mapping manifests.
* Explicit conversion warnings.
* User-selectable fallback policy.
* A conversion report.
* Preservation of original numeric values.

Fallback policies:

* Preserve unresolved placeholder.
* Replace with air.
* Replace with a configured block.
* Abort import.
* Allow manual mapping.

## 8.3 Legacy export

Legacy export is optional and must be disabled by default for modern builds.

Only enable it when:

* Every block has an exact supported legacy mapping.
* Dimensions fit format limits.
* Block entities can be converted safely.
* The user explicitly accepts possible loss.

Prefer modern `.schem` output.

---

# 9. `.LITEMATIC` SUPPORT

Treat `.litematic` as a multi-region NBT container, not as a single cuboid.

Typical data includes:

* Metadata.
* Minecraft data version.
* Litematic format version.
* A map of named regions.
* Region positions.
* Signed region sizes.
* Region-local block-state palettes.
* Bit-packed `BlockStates` long arrays.
* Block entities.
* Entities.
* Pending block ticks.
* Pending fluid ticks.

Regions can use negative dimensions, so region normalization must correctly compute canonical minimum and maximum coordinates instead of applying `abs(size)` without adjusting the origin.

## 9.1 Region preservation

Preserve:

* Original region name.
* Original position.
* Original signed size.
* Canonical normalized bounds.
* Region-local palette.
* Region metadata.
* Region block entities.
* Region entities.
* Tick data.
* Unknown fields.

Allow users to:

* Toggle regions.
* Recolor region outlines.
* Rename regions.
* Move regions.
* Merge regions.
* Split selections into regions.
* Export either preserved regions or a flattened structure.

## 9.2 Negative region sizes

Given an origin `P` and signed size `S`, determine the inclusive coordinate sequence correctly.

For each axis:

```text
if size > 0:
    min = position
    max = position + size - 1

if size < 0:
    min = position + size + 1
    max = position
```

Canonical dimension:

```text
abs(size)
```

Test positive and negative sizes independently on X, Y, and Z.

## 9.3 Block-state bit width

Determine bits per palette entry using:

```text
bitsPerEntry = max(2, ceil(log2(max(1, paletteSize))))
```

Validate this calculation against real Litematica-generated fixtures.

Expected long count:

```text
ceil(volume × bitsPerEntry / 64)
```

Reject or diagnose arrays that are too short. Permit trailing words only through a documented compatibility mode.

## 9.4 Signed-long handling

NBT long arrays are signed 64-bit integers, but bit extraction must treat each value as an unsigned 64-bit word.

Never use sign-extending right shifts for packed-data decoding.

## 9.5 Litematic bit-unpacking algorithm

For block linear index `i`:

```text
startBit = i × bitsPerEntry
startWord = floor(startBit / 64)
endWord = floor(((i + 1) × bitsPerEntry - 1) / 64)
bitOffset = startBit mod 64
mask = (1 << bitsPerEntry) - 1
```

If the entry fits in one word:

```text
value = unsigned(data[startWord]) >>> bitOffset
value &= mask
```

If the entry crosses a word boundary:

```text
low = unsigned(data[startWord]) >>> bitOffset
high = unsigned(data[endWord]) << (64 - bitOffset)
value = (low | high) & mask
```

The packed-array behavior must be validated against known Litematica files and property-based tests, including values that cross 64-bit boundaries. A practical implementation of this style uses a minimum of two bits per entry and computes word boundaries from the entry’s bit offset.

## 9.6 Linear coordinate mapping

Use the format’s verified region-local index order and test it with asymmetric dimensions so accidental axis swaps cannot pass.

The expected mapping for supported fixtures should correspond to:

```text
index = x + z × sizeX + y × sizeX × sizeZ
```

Test using structures where:

```text
sizeX != sizeY != sizeZ
```

and where unique blocks occupy every corner.

## 9.7 Palette growth during editing

When a patch introduces a new state:

* Add it to the canonical document palette.
* Do not immediately rewrite every source-format packed array.
* Keep canonical chunks independent of source packing.
* Rebuild region palettes and packed arrays only during export.
* Recompute the minimum valid bit width.
* Verify cross-word values after repacking.

## 9.8 Overlapping regions

A `.litematic` may contain regions whose normalized bounds overlap.

Do not silently discard one.

Support policies:

* Preserve as separate layers.
* Region-priority order.
* Last-region-wins flattening.
* First-region-wins flattening.
* Treat overlap as an error.
* Show overlap heatmap.
* Let the user resolve individual conflicts.

The canonical model should preserve source regions while also offering a deterministic flattened view.

## 9.9 Litematic export

Implement:

* Multi-region export.
* Single-region flattened export.
* Preserved signed dimensions where possible.
* Deterministic region and palette ordering.
* Correct block-state packing.
* Metadata regeneration.
* Non-air and volume statistics.
* Re-import verification.

---

# 10. RESOURCE PACK AND BLOCK-ASSET PIPELINE

A professional viewer must not render every block as a full cube with one texture.

Implement a Minecraft-style resource resolver.

## 10.1 Asset sources

Support a stack of asset sources:

1. Built-in open-source fallback pack.
2. User-supplied vanilla asset source.
3. User-supplied resource packs.
4. Project-specific resource pack.
5. Mod asset packs.
6. Temporary debugging overrides.

Higher-priority packs override lower-priority packs.

Do not redistribute proprietary game assets without confirming permission.

Provide:

* A legal, non-infringing placeholder pack.
* A user workflow to import assets from a resource pack or legally installed client.
* Clear attribution and license metadata for third-party packs.
* A warning that users are responsible for assets they upload.
* Product naming and branding that follows current Minecraft usage rules.

## 10.2 Asset indexing

Index:

```text
assets/<namespace>/blockstates/*.json
assets/<namespace>/models/block/*.json
assets/<namespace>/textures/block/*.png
assets/<namespace>/textures/*.png
assets/<namespace>/atlases/*.json
```

Also preserve pack metadata and namespaces.

## 10.3 Blockstate resolution

Support:

* `variants`.
* Property selectors.
* Multiple matching models with weighted selection.
* `multipart`.
* OR conditions.
* Nested conditions where defined.
* X and Y model rotations.
* UV lock.
* Model weights.
* Deterministic random selection based on coordinate hash.

The same build and seed must choose the same weighted variant every time.

## 10.4 Model inheritance

Resolve:

* Parent chains.
* Texture-variable inheritance.
* `#texture` references.
* Element inheritance behavior.
* Cycles.
* Missing parents.
* Missing textures.
* Built-in/generated special cases.

Cache the resolved model graph.

## 10.5 Model elements

Support cuboid elements with:

* `from`.
* `to`.
* Per-face textures.
* Per-face UVs.
* Culling directions.
* Face rotations.
* Tint indexes.
* Element rotations.
* Rotation origins.
* Rescaling.
* Ambient-occlusion flags.

Minecraft resource systems represent block models and block states through JSON resources, and model selection and rotation are state-dependent. The renderer must resolve these resources rather than assuming one cube model per ID.

## 10.6 Texture handling

Support:

* Nearest-neighbor sampling.
* Pixel-perfect UVs.
* Texture atlases.
* Texture padding to prevent bleeding.
* Animated texture metadata where feasible.
* Alpha testing.
* Transparent textures.
* Emissive metadata through extension configuration.
* Mipmapping options.
* Configurable anisotropic filtering.
* Color-space correctness.
* Resource-pack reload.

## 10.7 Tinting

Provide tint support for:

* Grass.
* Foliage.
* Water.
* Redstone power.
* Stem growth.
* Other state-dependent tint indexes.

Allow:

* A fixed neutral biome.
* User-selected biome presets.
* Imported biome data.
* Custom tint overrides.

AI snapshots must record the tint preset so image colors remain interpretable.

## 10.8 Fluids

Render fluids separately.

Account for:

* Water and lava levels.
* Falling state.
* Neighbor-aware surface heights where feasible.
* Transparent sorting.
* Waterlogged blocks.
* Fluid adjacency.
* User option to hide fluids.

## 10.9 Special renderers

Blocks such as these may require custom treatment:

* Chests.
* Beds.
* Banners.
* Signs.
* Skulls and heads.
* Shulker boxes.
* Decorated pots.
* Bells.
* Lecterns.
* Conduits.
* Enchanting tables.
* Moving or animated blocks.
* Modded block-entity renderers.

Use a tiered system:

1. Exact custom renderer.
2. Static approximated model.
3. Resource-pack model fallback.
4. Clearly marked unknown-block placeholder.

Never omit the block entirely.

Expose render-support status in the inspector.

---

# 11. WEBGL RENDERING ENGINE

Use Three.js unless a written architecture decision demonstrates that Babylon.js is materially better.

Three.js provides instanced meshes to reduce draw calls, orthographic cameras for scale-stable views, render targets for offscreen rendering, and standard orbit controls for orbiting, panning, and zooming.

## 11.1 Rendering strategy

Use a hybrid renderer:

### Full opaque cubes

Use chunk meshing and greedy face merging where textures and lighting constraints permit.

### Repeated non-cube models

Use instancing grouped by:

* Geometry.
* Material.
* Render layer.
* Tint.
* Model rotation.
* Resource-pack variant.

### Unique or complex models

Use merged buffer geometries or bounded object groups.

### Transparent content

Use a separate transparent pipeline with:

* Chunk-level sorting.
* Stable render order.
* Depth-write configuration.
* Optional weighted blended transparency if implemented.
* Diagnostics for known ordering limitations.

## 11.2 Face culling

Cull internal faces when:

* Adjacent opaque faces fully occlude one another.
* The model’s culling direction permits it.
* Blocks lie in adjacent chunks.

Do not incorrectly cull against:

* Transparent blocks.
* Partial blocks.
* Cutout geometry.
* Fluids.
* Models without full-face coverage.

Maintain neighbor data at chunk boundaries.

## 11.3 Incremental mesh updates

When a patch changes blocks:

* Mark only affected chunks dirty.
* Also mark neighboring chunks dirty when boundary faces change.
* Rebuild asynchronously.
* Keep the current mesh visible until replacement is ready.
* Swap atomically.
* Dispose old GPU resources.

## 11.4 Camera controls

Provide:

* Orbit.
* Pan.
* Zoom.
* Fit-to-build.
* Fit-to-selection.
* Perspective/orthographic toggle.
* Camera bookmarks.
* Front/back/left/right/top/bottom/isometric presets.
* Configurable field of view.
* Orthographic zoom.
* Keyboard navigation.
* Touch controls.
* Reset view.

## 11.5 Visual modes

Implement:

* Textured.
* Unlit texture.
* Solid block color.
* Palette-index color.
* Region color.
* Chunk-boundary view.
* Wireframe.
* X-ray.
* Transparency override.
* Lighting heatmap.
* Air-space/room visualization.
* Connected-component visualization.
* Block-state mismatch visualization.
* AI change heatmap.
* Before/after overlay.

## 11.6 Layer and clipping tools

Support:

* Exact Y-layer mode.
* Y range.
* X slice.
* Z slice.
* Six clipping planes.
* Adjustable slab thickness.
* Fade-out outside selected range.
* Hide air.
* Hide selected materials.
* Isolate selected materials.
* Show only exposed blocks.
* Show only interior surfaces.

## 11.7 Picking

Use GPU picking or an optimized spatial index.

On hover or click, return:

* Coordinate.
* Canonical block state.
* Palette ID.
* Region.
* Chunk.
* Block-entity presence.
* Render-support status.
* Current version’s author.
* Last patch affecting that block.

Picking must remain accurate under:

* Region transforms.
* Orthographic mode.
* Clipping.
* Hidden chunks.
* Instancing.
* Non-cube models.

## 11.8 Performance requirements

Do not create one Three.js object per block.

Targets on a documented reference machine:

* One million canonical voxels parsed and chunked without browser lockup.
* Interactive preview after progressive loading begins.
* 60 FPS target on a modern desktop for ordinary navigation.
* 30 FPS minimum target for large scenes after meshing.
* Main-thread tasks normally below 16 ms.
* No unbounded GPU resource growth.
* No complete scene rebuild for a one-block edit.
* Configurable quality tiers.
* Graceful fallback for weak devices.

Expose diagnostics:

* Draw calls.
* Triangles.
* Geometries.
* Textures.
* GPU memory estimate.
* Loaded chunks.
* Visible chunks.
* Mesh build time.
* Frame time.
* Picking time.

## 11.9 Worker rendering

Move CPU-heavy tasks into workers:

* Chunk decoding.
* Geometry generation where practical.
* Layer rasterization.
* Image compression.
* Histogram generation.
* Diff calculation.

Use OffscreenCanvas for worker rendering when supported, with a tested main-thread fallback. OffscreenCanvas can run separately from the DOM and can be used in worker contexts, helping prevent rendering or image-generation work from blocking the interface.

## 11.10 Context loss

Handle WebGL context loss and restoration.

After restoration:

* Recreate materials.
* Recreate atlases.
* Re-upload geometry.
* Restore camera state.
* Restore visibility state.
* Avoid requiring a full page reload when possible.

---

# 12. DETERMINISTIC SNAPSHOT SYSTEM

The AI snapshot system is a first-class subsystem, not a screenshot button.

## 12.1 Snapshot categories

Generate:

### Global views

* Front.
* Back.
* Left.
* Right.
* Top.
* Bottom where useful.
* Four isometric corners.
* Perspective hero view.
* Transparent-background variants.
* Region-colored variants.
* Untextured silhouette variants.

### Layer views

For every relevant Y coordinate:

* Exact layer raster.
* Top-face textured raster.
* Palette-index semantic raster.
* Occupancy mask.
* Edge map.
* Optional block-label overlay.
* Optional grid.
* Optional neighboring-layer context.
* Optional vertical slab render.

### Axis slices

Generate X and Z cross-sections on demand.

### Chunk views

For each selected 16×16×16 chunk:

* Six orthographic views.
* One isometric view.
* Three central slices.
* Palette and occupancy summary.

### Detail crops

The AI or user can request:

* Coordinate-centered crop.
* Bounding-box crop.
* Connected-component crop.
* Room crop.
* Changed-area crop.

## 12.2 Orthographic camera fitting

For deterministic orthographic snapshots:

1. Compute visible bounds.
2. Select camera direction.
3. Transform all bounds into camera space.
4. Fit the orthographic frustum with a configurable margin.
5. Use a fixed pixel density or target resolution.
6. Snap camera parameters to stable values.
7. Record near and far planes.
8. Record world-to-view and projection matrices.
9. Record the exact visible bounding box.
10. Record all hidden materials and clipping settings.

## 12.3 Snapshot manifest

Every image must have metadata:

```json
{
  "snapshotId": "snap_...",
  "buildVersionId": "ver_...",
  "type": "orthographic",
  "direction": "north",
  "resolution": [1536, 1536],
  "coordinateSpace": "document",
  "visibleBounds": {
    "min": [0, 0, 0],
    "max": [99, 79, 99]
  },
  "cameraPosition": [50, 40, -150],
  "cameraTarget": [50, 40, 50],
  "viewMatrix": [],
  "projectionMatrix": [],
  "lightingPreset": "analysis_neutral_v1",
  "assetPackHash": "...",
  "rendererVersion": "...",
  "background": "transparent",
  "hiddenPaletteIds": [],
  "contentHash": "..."
}
```

## 12.4 Semantic image maps

Do not rely only on RGB screenshots.

Generate machine-readable maps:

* Palette ID map.
* Region ID map.
* Depth map.
* Surface-normal map.
* Occupancy map.
* Coordinate map where practical.
* Changed-block mask.
* Error-category map.

For palette IDs, use a lossless encoding capable of representing more than 256 palette entries.

Options:

* 16-bit PNG where supported.
* 24-bit RGB integer encoding.
* Binary sidecar array.
* Compressed NumPy or typed-array blob.

Document decoding exactly.

## 12.5 Pixel-to-block mapping

For exact layer images:

* One logical block should map to a known integer pixel rectangle.
* Store `pixelsPerBlock`.
* Store image origin coordinate.
* Store axis orientation.
* Store whether Z increases upward or downward in image space.
* Never mirror images without recording the transform.
* Add optional coordinate ticks outside the data region.

Provide a tested function:

```text
pixelToBlock(snapshotManifest, px, py)
```

and its inverse:

```text
blockToPixel(snapshotManifest, x, y, z)
```

## 12.6 Headless rendering

The backend must generate snapshots without requiring the user to keep the browser open.

Use a dedicated renderer service that reuses the same renderer package as the frontend.

A practical design is:

* Node.js renderer host.
* Headless Chromium through Playwright.
* WebGL2.
* Software rendering fallback for CI.
* A renderer version embedded in every snapshot.
* A controlled font and GPU-independent analysis-lighting mode.
* Strict timeouts and memory limits.

Do not maintain unrelated frontend and backend rendering implementations that drift visually.

## 12.7 Image quality modes

Support:

* `draft`: fast, low resolution.
* `analysis`: neutral lighting, maximum clarity.
* `presentation`: high-quality shadows and composition.
* `semantic`: flat colors and machine-readable maps.
* `diff`: emphasizes modifications.
* `thumbnail`: small previews.

---

# 13. STRUCTURAL ANALYSIS ENGINE

Derive information that neither an image nor raw block list alone provides.

## 13.1 Material analysis

Calculate:

* Total count per canonical state.
* Total count per base block.
* Percentage of non-air volume.
* Count per region.
* Count per layer.
* Exposed-face count.
* Interior-face count.
* Material transitions.
* Rare materials.
* Palette entropy.
* Repetition patterns.
* Survival-oriented material estimates where mappings exist.

## 13.2 Surface extraction

Identify:

* Exterior exposed surfaces.
* Interior exposed surfaces.
* Roof surfaces.
* Floor surfaces.
* Vertical facades.
* Underground surfaces.
* Fully enclosed blocks.
* Blocks touching air cavities.

## 13.3 Connected components

Calculate connected components using configurable adjacency:

* Six-neighbor face adjacency.
* Eighteen-neighbor adjacency.
* Twenty-six-neighbor adjacency.
* Material-specific adjacency.
* Solid-only adjacency.
* Traversable-space adjacency.

Report:

* Component size.
* Bounds.
* Materials.
* Whether connected to the main build.
* Whether floating.
* Whether likely intentional decoration.
* Distance to nearest major component.

Do not automatically delete small components.

## 13.4 Support analysis

Implement configurable support heuristics:

* Blocks with no supporting path to a foundation.
* Gravity-affected blocks lacking valid support.
* Floating disconnected clusters.
* Thin cantilevers.
* Unsupported columns.
* Suspicious single-block bridges.
* Hanging decorations that may be intentional.

Classify results as:

* Definite invalidity.
* Likely issue.
* Design warning.
* Informational.

## 13.5 Symmetry and repetition

Detect:

* Reflection symmetry.
* Rotational symmetry.
* Repeated modules.
* Repeated facade segments.
* Repeated windows.
* Repeated columns.
* Near-identical rooms.
* Accidental asymmetry.
* Excessively uniform surfaces.

Allow the AI to query:

* Symmetry plane.
* Matching score.
* Coordinates of mismatches.
* Whether asymmetry appears intentional.

## 13.6 Room and air-volume analysis

Treat air as meaningful data.

Detect enclosed or semi-enclosed air volumes.

For each candidate room, calculate:

* Bounds.
* Volume.
* Floor area.
* Ceiling height distribution.
* Doorway candidates.
* Window candidates.
* Connections to other rooms.
* Connections to exterior.
* Navigability.
* Lighting estimate.
* Furnishing density.
* Whether sealed.
* Whether intersected by exterior details.
* Whether too narrow for player movement.

Distinguish:

* Exterior air.
* Interior rooms.
* Corridors.
* Shafts.
* Decorative cavities.
* Wall gaps.
* Hidden maintenance spaces.
* Tiny irrelevant pockets.

Use flood-fill from outside expanded bounds to classify exterior air.

## 13.7 Navigation graph

Build a player-oriented approximate navigation graph.

Model:

* Standable blocks.
* Headroom.
* Step-up limits.
* Drop limits.
* Stairs.
* Slabs.
* Ladders.
* Doors.
* Trapdoors.
* Water traversal as configurable.
* Narrow passages.
* Floor-to-floor links.

Report:

* Unreachable rooms.
* Dead-end corridors.
* Missing stair links.
* Door obstruction.
* Ceiling obstruction.
* Invalid spawn areas.
* Route lengths.

## 13.8 Lighting analysis

Provide an approximation or optional exact game-engine integration.

At minimum:

* Identify obvious dark enclosed areas.
* Count light-emitting blocks.
* Estimate light coverage.
* Mark rooms with no light source.
* Provide heatmaps.
* Let users configure target game rules and assumptions.

Do not present an approximation as exact Minecraft light-engine output.

## 13.9 Facade depth analysis

Measure:

* Large flat surface areas.
* Depth variation.
* Recesses.
* Protrusions.
* Window spacing.
* Pillar spacing.
* Trim density.
* Edge treatment.
* Roofline variation.

Use this to identify bare or overly flat areas.

## 13.10 Interior-exterior consistency

Detect likely inconsistencies:

* Windows opening into solid walls.
* Exterior doors with no interior space.
* Chimneys with no plausible shaft.
* Towers containing no vertical circulation.
* Floors cutting through exterior windows.
* Roofs with inaccessible voids.
* Decorative balconies with no access.
* Interior rooms outside exterior shell.
* Wall thickness changing unexpectedly.

---

# 14. AI-CONTEXT AND PAYLOAD ARCHITECTURE

The AI system must be hierarchical, token-aware, and tool-driven.

## 14.1 Never create one monolithic payload

A 100×100×100 build contains one million cells.

Do not stringify one million coordinate records and send them with every request.

Create multiple representation levels.

## 14.2 Context level 0: project synopsis

Include:

* Build name.
* Source format.
* DataVersion.
* Dimensions.
* Non-air count.
* Region count.
* Palette size.
* Major material histogram.
* Major connected components.
* Detected floors.
* Detected rooms.
* Global renders.
* Import diagnostics.
* Current task.
* Current token and image budget.

## 14.3 Context level 1: structural overview

Include:

* Region summaries.
* Floor summaries.
* Room graph.
* Component graph.
* Symmetry report.
* Material groups.
* Facade metrics.
* Interior metrics.
* Major issue list.
* Orthographic images.

## 14.4 Context level 2: selected areas

Include only relevant:

* Bounding boxes.
* Chunk summaries.
* Layer images.
* Cross-sections.
* Material runs.
* Block entities.
* Local measurements.
* Local issues.
* Nearby context.

## 14.5 Context level 3: exact voxel data

Expose exact data through tools:

* Paginated chunks.
* Coordinate queries.
* Run-length encoded slices.
* Sparse material masks.
* Binary artifacts.
* Palette definitions.
* NBT queries.

## 14.6 Token-efficient textual encoding

Implement several encodings.

### Palette table

Send each canonical state once:

```text
P0=minecraft:air
P1=minecraft:stone_bricks
P2=minecraft:oak_planks
P3=minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]
```

### Run-length rows

```text
Y12 Z04: X00-07=P1 X08-08=P3 X09-15=P0
```

### Sparse records

For low-density chunks:

```text
(x,y,z,paletteId)
```

### Cuboid runs

```text
fill P4 from (10,4,20) to (18,4,28)
```

### Delta encoding

For subsequent versions, send only:

* Added blocks.
* Removed blocks.
* Replaced states.
* Changed NBT.
* Changed room or component metrics.
* Changed snapshots.

## 14.7 Binary machine payloads

For non-LLM consumers, provide:

* CBOR.
* MessagePack.
* Zstandard-compressed typed arrays.
* Content-addressed chunk downloads.
* Manifest files.

Do not base the internal protocol on natural-language encodings.

## 14.8 Context-budget planner

Before every model call, estimate:

* Text tokens.
* Image tokens or provider-equivalent image cost.
* Number of images.
* Maximum context.
* Expected output.
* Tool definitions.
* Conversation history.
* Safety margin.

The planner must choose:

* Relevant images.
* Appropriate image resolution.
* Relevant chunks.
* Summary compression level.
* Whether to split the task.
* Whether to use a map-reduce workflow.
* Whether to ask the AI to query more data.

## 14.9 Image selection

Do not upload hundreds of nearly identical layer images at once.

Select images using:

* Task relevance.
* Changed-area intersection.
* Structural uniqueness.
* Material uniqueness.
* Saliency.
* Floor boundaries.
* Room boundaries.
* Issue locations.
* Requested coordinates.
* Progressive detail.

Create contact sheets only when individual image resolution remains sufficient.

## 14.10 AI evidence references

Every payload item must have an ID.

Examples:

* `view:north:global:v12`
* `slice:y:37:v12`
* `chunk:2:1:-3:v12`
* `room:18:v12`
* `component:4:v12`
* `issue:unsupported:71:v12`

Require the AI to reference these IDs in analysis and patch rationale.

---

# 15. AI TOOL PROTOCOL

Implement an internal tool-calling interface.

The AI should interact with the build through tools such as:

## 15.1 Read-only tools

```text
get_build_summary
get_import_diagnostics
get_palette
get_material_histogram
get_regions
get_region
get_floors
get_rooms
get_room
get_navigation_graph
get_components
get_component
get_symmetry_report
get_lighting_report
get_facade_report
get_interior_report
get_block
query_blocks
get_chunk
get_slice
render_view
render_crop
measure_distance
measure_bounds
find_nearest
find_material
find_block_entities
get_block_entity
compare_versions
get_patch
```

## 15.2 Planning tools

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

## 15.3 Editing tools

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

## 15.4 Transaction tools

```text
begin_patch
preview_patch
validate_patch
commit_patch
rollback_patch
create_checkpoint
restore_checkpoint
branch_version
merge_versions
```

## 15.5 Export tools

```text
validate_export
export_schem
export_litematic
download_artifact
```

## 15.6 Tool schema requirements

Every editing request must include:

* Build version.
* Coordinate space.
* Intended bounding box.
* Maximum affected blocks.
* Operation parameters.
* Reason.
* Optional preconditions.
* Expected outcome.

Example:

```json
{
  "buildVersionId": "ver_12",
  "coordinateSpace": "document",
  "bounds": {
    "min": [10, 20, 30],
    "max": [25, 30, 45]
  },
  "maxAffectedBlocks": 5000,
  "operation": {
    "type": "replace_blocks",
    "from": [
      "minecraft:stone_bricks"
    ],
    "to": "minecraft:cracked_stone_bricks",
    "mask": {
      "type": "surface_noise",
      "seed": 91241,
      "probability": 0.13
    }
  },
  "reason": "Introduce restrained weathering on the exposed tower facade."
}
```

## 15.7 Preconditions

Support optimistic preconditions:

* Coordinate currently equals expected state.
* Chunk hash equals expected hash.
* Region version equals expected version.
* A selection has not changed.
* A block entity exists.
* A room classification remains valid.

Reject stale AI patches cleanly.

---

# 16. TRANSACTIONAL PATCH ENGINE

## 16.1 Patch lifecycle

A patch transitions through:

```text
draft
validated
previewed
committed
rejected
rolled_back
superseded
```

## 16.2 Atomicity

A patch either commits completely or not at all.

No partially applied operation may become the active build version.

## 16.3 Patch contents

Store:

* Parent version.
* New version.
* Operation list.
* Changed coordinates.
* Old palette IDs.
* New palette IDs.
* Block-entity changes.
* Affected chunks.
* Bounding boxes.
* Author.
* AI model and provider where applicable.
* Prompt/run ID.
* Tool-call IDs.
* Validation report.
* Before-and-after hashes.
* Before-and-after snapshot IDs.
* Cost and token usage if enabled.

## 16.4 Undo and redo

Undo must not depend on recomputing inverse procedural commands.

Store exact previous values or immutable parent chunks.

Support:

* Linear undo.
* Branching history.
* Named checkpoints.
* Version comparison.
* Selective patch revert.
* Merge conflict detection.

## 16.5 Patch limits

Enforce:

* Maximum affected volume.
* Maximum changed blocks.
* Maximum palette additions.
* Maximum block entities.
* Allowed coordinate bounds.
* Locked regions.
* Protected materials.
* Protected user selections.
* Per-agent permissions.

Large changes should be split into phases.

---

# 17. AI BUILD-GENERATION WORKFLOW

Implement a formal state machine.

## 17.1 Stage 1: requirements

The AI must extract:

* Build type.
* Theme.
* Era.
* Style.
* Dimensions.
* Orientation.
* Terrain assumptions.
* Intended game version.
* Mod policy.
* Interior requirements.
* Functional requirements.
* Material constraints.
* Symmetry preference.
* Level of ruin or weathering.
* Detail density.
* Performance constraints.
* Export format.

Missing details may receive explicit documented defaults.

## 17.2 Stage 2: design document

Generate a structured design:

```json
{
  "concept": "...",
  "dimensions": [128, 96, 128],
  "primaryAxis": "north_south",
  "floors": [],
  "majorVolumes": [],
  "rooms": [],
  "circulation": [],
  "facadeRhythm": {},
  "roofStrategy": {},
  "palette": {},
  "lightingStrategy": {},
  "interiorStrategy": {},
  "detailHierarchy": {},
  "constructionPhases": []
}
```

## 17.3 Stage 3: block palette

Separate:

* Structural blocks.
* Primary facade blocks.
* Secondary facade blocks.
* Trim.
* Roof.
* Floors.
* Interior walls.
* Accent blocks.
* Glass.
* Lighting.
* Organic materials.
* Weathering blocks.
* Functional blocks.

Set limits to avoid uncontrolled palette sprawl.

## 17.4 Stage 4: massing

Build only the major forms.

Then generate:

* Four orthographic views.
* Top view.
* Two isometric views.
* Silhouette mask.
* Volume statistics.

The AI must critique proportions before proceeding.

## 17.5 Stage 5: floor and room layout

Create:

* Floor slabs.
* Interior walls.
* Vertical circulation.
* Main corridors.
* Room boundaries.
* Door and window alignment.

Run:

* Room detection.
* Navigation.
* Ceiling-height checks.
* Exterior consistency checks.

## 17.6 Stage 6: facade pass

Add:

* Depth.
* Supports.
* Columns.
* Buttresses.
* Trim.
* Window framing.
* Roof transitions.
* Cornices.
* Recesses.
* Balconies.
* Secondary silhouettes.

Analyze large flat surfaces and repetition.

## 17.7 Stage 7: interior pass

Every required room must receive:

* Clear purpose.
* Navigable entrance.
* Appropriate scale.
* Lighting.
* Floor and ceiling treatment.
* Furniture or functional detailing.
* Connection to adjacent spaces.
* Exterior-window consistency.
* Vertical circulation where required.

Do not consider a solid shell with empty rooms complete.

## 17.8 Stage 8: detail hierarchy

Use three detail scales:

### Macro

* Towers.
* Wings.
* Roofs.
* Courtyards.
* Major silhouette.

### Meso

* Windows.
* Pillars.
* Arches.
* Roof segments.
* Room groupings.
* Balconies.

### Micro

* Trim.
* Furniture.
* Lighting.
* Supports.
* Signs.
* Small material variation.

The AI must not apply micro-detail before macro proportions are validated.

## 17.9 Stage 9: critique loop

After each major stage:

1. Render.
2. Analyze.
3. Identify specific defects.
4. Cite evidence.
5. Propose bounded patches.
6. Apply.
7. Validate.
8. Re-render changed areas.
9. Compare.
10. Stop only when acceptance thresholds are met or the configured iteration budget is exhausted.

## 17.10 Stage 10: final verification

Run:

* Unknown-block check.
* Invalid-state check.
* Block-entity check.
* Floating-component report.
* Room accessibility.
* Floor connectivity.
* Window/interior consistency.
* Material histogram.
* Empty-room check.
* Large-flat-surface report.
* Symmetry report.
* Bounds check.
* Export round trip.

---

# 18. OPTIONAL MULTI-AGENT WORKFLOW

Support, but do not require, multiple specialist agents.

Possible roles:

* Lead architect.
* Structural planner.
* Exterior designer.
* Interior designer.
* Landscape designer.
* Minecraft mechanics verifier.
* Material specialist.
* Visual critic.
* Technical validator.
* Cost/context manager.

The lead agent controls final decisions.

Specialists must communicate through structured artifacts, not unrestricted chat.

Example:

```json
{
  "agentRole": "interior_designer",
  "findings": [],
  "proposedPatches": [],
  "evidenceRefs": [],
  "risks": [],
  "confidence": 0.84
}
```

Prevent conflicting simultaneous edits through version preconditions and region locks.

---

# 19. AI PROVIDER ABSTRACTION

Define an interface similar to:

```python
class MultimodalProvider(Protocol):
    async def get_capabilities(self) -> ProviderCapabilities: ...
    async def count_or_estimate_tokens(self, request: ModelRequest) -> TokenEstimate: ...
    async def create_response(self, request: ModelRequest) -> ModelResponse: ...
    async def stream_response(self, request: ModelRequest) -> AsyncIterator[ModelEvent]: ...
    async def cancel(self, request_id: str) -> None: ...
```

## 19.1 Capabilities

Track:

* Text input.
* Image input.
* Maximum images.
* Supported image formats.
* Maximum image dimensions.
* File-reference support.
* Structured output.
* Tool calling.
* Streaming.
* Prompt caching.
* Context window.
* Output limit.
* Token counting.
* Batch support.
* Data-retention mode.
* Provider rate limits.

## 19.2 Bring your own key

API keys must:

* Never be sent to the browser after storage.
* Never appear in logs.
* Be encrypted at rest.
* Be redacted from traces.
* Support per-user deletion.
* Support temporary session-only use.
* Be scoped to a provider adapter.

Also support server-managed keys for self-hosted deployments.

## 19.3 Model configuration

Do not hard-code one model name.

Use database-backed model profiles:

```json
{
  "provider": "openai",
  "model": "configured-model-id",
  "supportsVision": true,
  "supportsTools": true,
  "maxContextTokens": 0,
  "maxOutputTokens": 0,
  "imagePolicy": {},
  "costPolicy": {},
  "enabled": true
}
```

## 19.4 Cost controls

Support:

* Per-run budget.
* Per-user daily budget.
* Maximum iterations.
* Maximum images.
* Maximum resolution.
* Confirmation threshold.
* Cost estimate before execution.
* Hard stop.
* Usage report.

---

# 20. API DESIGN

Use versioned REST endpoints plus streaming progress.

## 20.1 Core endpoints

```text
POST   /api/v1/uploads
POST   /api/v1/builds/import
GET    /api/v1/jobs/{jobId}
POST   /api/v1/jobs/{jobId}/cancel

GET    /api/v1/builds/{buildId}
GET    /api/v1/builds/{buildId}/versions
GET    /api/v1/builds/{buildId}/versions/{versionId}

GET    /api/v1/builds/{buildId}/palette
GET    /api/v1/builds/{buildId}/chunks
GET    /api/v1/builds/{buildId}/chunks/{cx}/{cy}/{cz}
GET    /api/v1/builds/{buildId}/blocks/{x}/{y}/{z}
POST   /api/v1/builds/{buildId}/blocks/query

GET    /api/v1/builds/{buildId}/regions
GET    /api/v1/builds/{buildId}/rooms
GET    /api/v1/builds/{buildId}/components
GET    /api/v1/builds/{buildId}/analysis

POST   /api/v1/builds/{buildId}/snapshots
GET    /api/v1/snapshots/{snapshotId}
GET    /api/v1/snapshots/{snapshotId}/image
GET    /api/v1/snapshots/{snapshotId}/manifest

POST   /api/v1/builds/{buildId}/patches
POST   /api/v1/patches/{patchId}/validate
POST   /api/v1/patches/{patchId}/preview
POST   /api/v1/patches/{patchId}/commit
POST   /api/v1/patches/{patchId}/rollback

POST   /api/v1/builds/{buildId}/ai-runs
GET    /api/v1/ai-runs/{runId}
POST   /api/v1/ai-runs/{runId}/cancel

POST   /api/v1/builds/{buildId}/exports
GET    /api/v1/exports/{exportId}
```

## 20.2 Uploads

Use multipart streaming or signed direct-to-object-storage uploads.

Support:

* Resumable multipart upload.
* Progress.
* Hash verification.
* Cancellation.
* Duplicate detection.
* Maximum size enforcement.
* MIME and magic-byte inspection.

## 20.3 Progress streaming

Emit events such as:

```json
{
  "event": "job.progress",
  "jobId": "job_...",
  "stage": "parsing_litematic_regions",
  "progress": 0.42,
  "message": "Decoded 8 of 19 regions",
  "metrics": {
    "voxelsProcessed": 823004
  }
}
```

Use SSE for simple server-to-client progress or WebSockets when bidirectional control is needed.

## 20.4 Error format

Use a stable error object:

```json
{
  "error": {
    "code": "LITEMATIC_BLOCKSTATE_ARRAY_TOO_SHORT",
    "message": "Region 'Tower' does not contain enough packed words.",
    "details": {
      "expectedWords": 913,
      "actualWords": 902
    },
    "recoverable": false,
    "documentationRef": "errors/litematic-blockstates"
  }
}
```

Never return raw stack traces in production.

## 20.5 Idempotency

Support idempotency keys for:

* Import creation.
* Snapshot requests.
* AI runs.
* Patch commits.
* Exports.

---

# 21. DATABASE MODEL

At minimum, model:

* Users.
* Organizations or workspaces.
* Projects.
* Builds.
* Build source files.
* Build versions.
* Chunk blobs.
* Version chunk manifests.
* Regions.
* Palettes.
* Block entities.
* Entities.
* Analysis results.
* Snapshots.
* Snapshot artifacts.
* Patches.
* Patch operations.
* AI providers.
* AI model profiles.
* AI runs.
* AI tool calls.
* Export jobs.
* Audit events.
* API keys.
* Storage-retention policies.

Use immutable build-version records.

Avoid storing one relational row per block.

---

# 22. FRONTEND APPLICATION

## 22.1 Main workspace layout

Create a professional editor layout:

### Top bar

* Project name.
* Build version.
* Import/export.
* Undo/redo.
* AI run status.
* Save/checkpoint.
* Settings.
* Performance indicator.

### Left panel

* Regions.
* Layers.
* Materials.
* Objects/components.
* Rooms.
* Saved selections.
* Version history.

### Center

* 3D viewport.
* Snapshot viewer.
* Layer viewer.
* Diff viewer.

### Right panel

* Block inspector.
* Selection inspector.
* Analysis findings.
* AI conversation.
* Patch preview.
* Validation results.

### Bottom panel

* Job progress.
* Console diagnostics.
* AI tool calls.
* Performance statistics.
* Import warnings.

## 22.2 Upload experience

Provide:

* Drag and drop.
* File picker.
* Accepted-extension display.
* Size validation.
* Upload progress.
* Parsing stages.
* Warning summary.
* Source-format detection.
* Legacy version selection when needed.
* Resource-pack selection.

## 22.3 Inspector

When a block is selected, display:

* Coordinate.
* Canonical state.
* Namespace.
* Properties.
* Region.
* Palette ID.
* Source-format representation.
* Block-entity NBT tree.
* Model and texture paths.
* Render category.
* Last modification.
* Nearby blocks.
* Copy-state action.

## 22.4 AI panel

Show:

* Current task.
* AI plan.
* Current evidence.
* Images sent.
* Chunks queried.
* Tool calls.
* Patch proposals.
* Validation results.
* Token use.
* Estimated or actual cost.
* Pause.
* Cancel.
* Approve or reject patch.
* Automatic mode controls.

## 22.5 Accessibility

Implement:

* Keyboard navigation.
* Focus indicators.
* ARIA labels.
* Resizable panels.
* High-contrast mode.
* Non-color-only status indicators.
* Reduced-motion option.
* Screen-reader-compatible data tables.
* Accessible dialogs.
* Configurable text size.

---

# 23. SECURITY REQUIREMENTS

## 23.1 File security

Protect against:

* GZIP bombs.
* ZLIB bombs.
* NBT nesting bombs.
* Huge declared arrays.
* Integer overflow.
* Invalid UTF-8.
* Malicious filenames.
* Path traversal.
* Resource-pack ZIP bombs.
* Symlinks in archives.
* Duplicate ZIP entries.
* Oversized images.
* JSON recursion.
* Excessive model-parent chains.

## 23.2 Worker isolation

Parsing and rendering workers must run with:

* No unnecessary network access.
* Read-only base filesystem.
* Temporary per-job directory.
* CPU limit.
* Memory limit.
* Process limit.
* Execution timeout.
* Automatic cleanup.
* Non-root user.
* Restricted capabilities.

## 23.3 API security

Implement:

* Authentication.
* Authorization.
* Project ownership checks.
* CSRF protection where relevant.
* CORS allowlist.
* Rate limiting.
* Request limits.
* Secure cookies.
* Content Security Policy.
* Signed artifact URLs.
* Audit logs.
* Secret redaction.
* Dependency scanning.
* Container scanning.

## 23.4 AI security

Treat model output as untrusted.

Never:

* Execute generated code directly.
* Pass arbitrary shell commands from the AI.
* Let the AI construct storage paths.
* Let the AI exceed patch limits.
* Let model text bypass permission checks.
* Trust AI-provided coordinate counts.
* Trust AI-supplied NBT without validation.

All tool calls must pass server-side schema validation and authorization.

---

# 24. OBSERVABILITY

Use structured logs with correlation IDs.

Track:

* Upload latency.
* Parse latency.
* Parse failures by format.
* Decompressed size.
* Voxels per second.
* Chunk encoding ratio.
* Mesh generation time.
* Snapshot rendering time.
* GPU or software-render fallback.
* AI request latency.
* AI token usage.
* AI image count.
* Tool calls per run.
* Patch rejection rate.
* Export validation failures.
* Worker queue depth.
* Cache hit rate.
* Memory usage.
* Object-storage usage.

Use:

* OpenTelemetry traces.
* Prometheus-compatible metrics.
* Health endpoints.
* Readiness endpoints.
* Worker heartbeat.
* Error aggregation.
* Privacy-aware audit logs.

---

# 25. TESTING STRATEGY

Testing is mandatory.

## 25.1 Unit tests

Cover:

* NBT primitive parsing.
* Compression detection.
* Varint decoding.
* Sponge palette parsing.
* Sponge index mapping.
* Legacy AddBlocks decoding.
* Legacy ID mapping.
* Litematic bit-width calculation.
* Litematic cross-word extraction.
* Negative region sizes.
* Palette canonicalization.
* Chunk encoding.
* Chunk hashing.
* Coordinate transforms.
* Snapshot pixel mapping.
* Patch inversion.
* Export palette generation.

## 25.2 Property-based tests

Generate random:

* Dimensions.
* Palette sizes.
* Palette indexes.
* Bit widths.
* Region signs.
* Coordinates.
* Chunk sparsity.
* Patch sequences.

Properties must include:

* Pack then unpack returns identical indexes.
* Export then import returns equivalent canonical blocks.
* Coordinate-to-index and index-to-coordinate are inverses.
* Patch then rollback restores the original hashes.
* Chunk encoding then decoding is lossless.
* Region normalization preserves every coordinate exactly.

## 25.3 Fuzzing

Fuzz:

* NBT input.
* GZIP/ZLIB input.
* Palette strings.
* Varint streams.
* Long arrays.
* Resource-pack JSON.
* Model inheritance.
* Patch payloads.
* Block-entity NBT.
* API query filters.

Crashes, hangs, and unbounded allocation are failures.

## 25.4 Golden fixtures

Create redistributable fixtures for:

* One block.
* All-air build.
* One block entity.
* Asymmetric dimensions.
* Every corner marked differently.
* Palette sizes around bit boundaries:

  * 1
  * 2
  * 3
  * 4
  * 5
  * 7
  * 8
  * 9
  * 15
  * 16
  * 17
  * 255
  * 256
  * 257
* Cross-word Litematic entries.
* Negative X size.
* Negative Y size.
* Negative Z size.
* Multiple regions.
* Overlapping regions.
* Unknown modded blocks.
* Missing texture.
* Missing model parent.
* Corrupt array lengths.
* Legacy AddBlocks.
* Large sparse structure.
* Large dense structure.
* Waterlogged blocks.
* Transparent blocks.
* Stairs and slabs.
* Multipart models.

## 25.5 Renderer tests

Use screenshot regression tests for:

* Camera orientation.
* Texture orientation.
* UV rotation.
* Stairs.
* Slabs.
* Fences.
* Walls.
* Glass.
* Fluids.
* Tinting.
* Clipping.
* Layer views.
* Semantic palette maps.
* Context restoration.
* Before/after diff.

Allow small platform tolerances for presentation renders, but require exact semantic-map outputs.

## 25.6 Integration tests

Test:

* Upload to completed import.
* Import to browser preview.
* Snapshot job.
* AI tool query.
* Patch preview.
* Patch commit.
* Undo.
* Export.
* Export re-import.
* Object-storage failure.
* Worker retry.
* AI-provider timeout.
* User cancellation.

## 25.7 End-to-end tests

Automate:

1. Open application.
2. Upload fixture.
3. Wait for import.
4. Inspect a known coordinate.
5. Change Y layer.
6. Isolate a material.
7. Generate snapshot.
8. Start mock AI analysis.
9. Preview a patch.
10. Commit it.
11. Undo it.
12. Export `.schem`.
13. Confirm download artifact.

---

# 26. PERFORMANCE BENCHMARKS

Create a repeatable benchmark suite.

Datasets:

* 16³.
* 64³.
* 100³.
* 128³.
* 256×128×256 sparse.
* High-palette structure.
* Many-region Litematic.
* Transparent-block stress test.
* Non-cube-model stress test.
* Block-entity stress test.

Measure:

* Upload throughput.
* Decompression.
* Parse throughput.
* Canonicalization.
* Chunk encoding.
* Storage size.
* Mesh generation.
* Time to first preview.
* Frame rate.
* Snapshot generation.
* Layer-raster generation.
* Analysis time.
* Patch application.
* Export time.
* Peak resident memory.
* Browser heap.
* GPU resource count.

Add CI regression thresholds.

---

# 27. DEPLOYMENT

## 27.1 Local development

Provide one-command startup:

```bash
docker compose up --build
```

Also document native development with:

* Package manager installation.
* Python environment.
* Database migration.
* Redis.
* Object storage.
* Renderer service.
* Worker.
* Web frontend.

## 27.2 Production

Support:

* Container images.
* Non-root execution.
* Horizontal API scaling.
* Independent worker scaling.
* Dedicated rendering workers.
* GPU-enabled renderer workers as optional.
* S3-compatible storage.
* Managed PostgreSQL.
* Managed Redis.
* TLS termination.
* Reverse proxy.
* Autoscaling.
* Backups.
* Migration jobs.
* Rolling deployments.

## 27.3 Retention

Implement configurable policies for:

* Original uploads.
* Parsed chunk blobs.
* Snapshots.
* AI payloads.
* AI responses.
* Exports.
* Audit logs.

Allow users to delete projects and associated provider data where supported.

---

# 28. OPEN-SOURCE REQUIREMENTS

Include:

* A suitable open-source license chosen deliberately.
* `CONTRIBUTING.md`.
* `CODE_OF_CONDUCT.md`.
* `SECURITY.md`.
* Issue templates.
* Pull-request template.
* Architecture decision records.
* Public roadmap.
* Development setup.
* Test instructions.
* Fixture-generation documentation.
* Dependency-license report.
* Third-party asset policy.
* Branding disclaimer.
* Responsible-disclosure process.

Do not commit:

* Proprietary Minecraft textures.
* API keys.
* User schematics.
* Private model payloads.
* Generated secrets.
* Unlicensed sample builds.

---

# 29. REQUIRED DOCUMENTATION

Produce:

```text
docs/
├─ architecture/
│  ├─ overview.md
│  ├─ canonical-model.md
│  ├─ chunk-storage.md
│  ├─ rendering.md
│  ├─ snapshots.md
│  ├─ ai-orchestration.md
│  ├─ patch-engine.md
│  └─ security.md
├─ formats/
│  ├─ sponge-schem.md
│  ├─ legacy-schematic.md
│  └─ litematic.md
├─ api/
├─ deployment/
├─ development/
├─ user-guide/
└─ troubleshooting/
```

Include diagrams for:

* Import pipeline.
* Canonical model.
* Chunk flow.
* Rendering flow.
* Snapshot flow.
* AI context planning.
* Patch lifecycle.
* Version graph.
* Export verification.
* Deployment topology.

---

# 30. IMPLEMENTATION PHASES

Do not attempt to hide unfinished foundations behind UI polish.

## Phase 1: repository and contracts

Deliver:

* Monorepo.
* Formatting.
* Linting.
* Type checking.
* CI.
* Shared schemas.
* Database.
* Object storage.
* Job model.
* Basic frontend shell.
* Architecture documents.

## Phase 2: NBT and canonical model

Deliver:

* Safe NBT reader.
* Compression detection.
* Canonical document.
* Chunk storage.
* Diagnostics.
* Unit and fuzz tests.

## Phase 3: format importers

Deliver in order:

1. Sponge v3.
2. Litematic.
3. Sponge v2 and v1.
4. Legacy `.schematic`.

Each importer requires golden tests.

## Phase 4: basic renderer

Deliver:

* Chunk loading.
* Full-cube textured rendering.
* Camera controls.
* Picking.
* Layer clipping.
* Material isolation.
* Progressive loading.

## Phase 5: resource-pack model engine

Deliver:

* Pack stack.
* Blockstates.
* Models.
* Parent resolution.
* UVs.
* Cutout and transparency.
* Tinting.
* Non-cube blocks.
* Fallback diagnostics.

## Phase 6: deterministic snapshots

Deliver:

* Orthographic cameras.
* Layer rasters.
* Semantic maps.
* Manifests.
* Headless renderer.
* Snapshot regression tests.

## Phase 7: analysis engine

Deliver:

* Histograms.
* Components.
* Surface detection.
* Air volumes.
* Rooms.
* Navigation.
* Flatness.
* Symmetry.
* Interior/exterior checks.

## Phase 8: patch engine

Deliver:

* Operations.
* Validation.
* Preview.
* Commit.
* Undo.
* Version graph.
* Diffs.
* Incremental remeshing.

## Phase 9: AI integration

Deliver:

* Provider adapters.
* Capability registry.
* Context planner.
* Tool protocol.
* Streaming.
* Budget controls.
* Evidence references.
* Analysis workflow.

## Phase 10: AI construction workflow

Deliver:

* Design brief.
* Phased construction.
* Palette planning.
* Room planning.
* Critique loop.
* Automatic re-rendering.
* Interior completion.
* Quality gates.

## Phase 11: exporters

Deliver:

* Sponge v3 export.
* Litematic export.
* Round-trip verification.
* Download artifacts.
* Export diagnostics.

## Phase 12: hardening

Deliver:

* Security sandbox.
* Rate limiting.
* Observability.
* Benchmarks.
* Accessibility.
* Documentation.
* Deployment manifests.
* Backup and retention.
* Release process.

---

# 31. DEFINITION OF DONE

The project is not complete until all of the following are true.

## Import

* Valid `.schem`, `.schematic`, and `.litematic` fixtures import.
* Invalid files produce useful diagnostics.
* Multi-region Litematics preserve regions.
* Negative sizes decode correctly.
* Cross-word packed indexes decode correctly.
* Unknown modded blocks are preserved.
* Block entities survive canonicalization.

## Visual preview

* The user can orbit, pan, and zoom.
* The user can inspect exact coordinates.
* Textures and block models are visibly aligned.
* Common partial blocks are not rendered as full cubes.
* Large builds use chunked rendering.
* Layer and clipping tools work.
* No one-object-per-block architecture exists.

## AI perception

* The AI receives global visual context.
* The AI can request exact chunks and slices.
* The AI can query any coordinate.
* The AI can correlate image pixels to block coordinates.
* Payload size is bounded.
* Evidence IDs are included.
* The system can analyze interiors, not merely exteriors.

## AI editing

* The AI can create bounded patches.
* Patches are previewable.
* Patches are validated.
* Patches can be rejected.
* Commits create immutable versions.
* Undo restores exact prior data.
* Changed regions are automatically re-rendered.
* The AI can iterate based on before/after evidence.

## Export

* Modern `.schem` output loads back into the platform.
* `.litematic` output loads back into the platform.
* Blocks remain at the correct coordinates.
* Block states remain exact.
* Supported block entities remain intact.
* Round-trip mismatches fail validation.

## Engineering

* CI is green.
* Tests cover format algorithms.
* Fuzzing exists.
* Documentation exists.
* Docker development works.
* Production configuration is documented.
* Secrets are protected.
* Workers are isolated.
* Performance benchmarks are recorded.
* No core feature is represented only by a mock.

---

# 32. CODING RULES

While implementing:

* Use strict typing.
* Use explicit schemas.
* Validate every external boundary.
* Avoid global mutable state.
* Avoid giant service classes.
* Avoid circular package dependencies.
* Keep pure decoding functions separate from I/O.
* Keep canonicalization separate from format parsing.
* Keep rendering separate from source-format logic.
* Keep AI provider adapters separate from orchestration.
* Keep patch validation separate from patch application.
* Keep deterministic operations free of wall-clock dependence.
* Include structured errors.
* Include cancellation checks in long loops.
* Include progress reporting.
* Dispose GPU resources.
* Close files and streams.
* Use database transactions.
* Use checked arithmetic.
* Preserve unknown data.
* Write tests alongside implementations.
* Document non-obvious coordinate math.

Do not:

* Hard-code one sample structure’s dimensions.
* Assume air is palette index zero.
* Assume regions are positive-sized.
* Assume all schematics contain one region.
* Assume every block is a cube.
* Assume every texture is opaque.
* Assume every palette fits in one byte.
* Assume bit-packed entries stay inside one 64-bit word.
* Assume filenames identify formats correctly.
* Assume a model response is valid because it matches JSON syntax.
* Assume an export is correct without re-importing it.
* Replace unsupported blocks with air silently.
* Send provider API keys to the frontend.
* block the API request while performing a large parse.
* block the browser main thread with million-voxel loops.
* claim exact Minecraft simulation for heuristic analyses.

---

# 33. REQUIRED INITIAL OUTPUT FROM THE CODING AI

Before creating implementation files, produce:

1. A concise architecture summary.
2. Chosen technology stack and rationale.
3. A dependency-boundary diagram.
4. The canonical data model.
5. Import job state machine.
6. Patch state machine.
7. AI-run state machine.
8. Database entity outline.
9. API route outline.
10. Security threat model.
11. Testing strategy.
12. Phased implementation checklist.
13. Explicit assumptions.
14. Known high-risk areas.
15. A list of facts that must be revalidated against current upstream specifications.

Then begin implementation immediately.

Do not stop after producing the plan.

---

# 34. REQUIRED EXECUTION BEHAVIOR

Work in vertical, testable increments.

For each phase:

1. State the exact objective.
2. Identify affected packages.
3. Implement production code.
4. Add tests.
5. Run tests.
6. Fix failures.
7. Update documentation.
8. Demonstrate the working increment.
9. Record architectural decisions.
10. Proceed to the next phase.

When blocked by an ambiguity:

* Inspect current upstream specifications or source.
* Make the smallest documented assumption.
* Add a compatibility test.
* Preserve unknown data.
* Continue implementation.

Do not use uncertainty as a reason to omit the subsystem.

---

# 35. FINAL PRODUCT STANDARD

The final application should make it possible for a capable multimodal AI to operate like a Minecraft build team rather than a blind script generator.

The AI should be able to:

* See the build globally.
* Inspect it locally.
* Understand every exact block.
* Understand spatial relationships.
* Understand rooms and navigation.
* Detect unfinished work.
* Propose coordinate-specific improvements.
* Apply those improvements safely.
* Review the visual result.
* Reconsider poor decisions.
* Build complete interiors.
* Preserve exact schematic validity.
* Produce a professional, map-maker-grade structure through repeated visual and symbolic verification.

The system succeeds only when the AI no longer has to guess what its generated schematic looks like.
