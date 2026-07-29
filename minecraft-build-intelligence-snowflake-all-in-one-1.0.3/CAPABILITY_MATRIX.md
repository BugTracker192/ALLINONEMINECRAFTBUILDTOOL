# Mandatory Snowflake/CoCo capability matrix

This matrix describes the mandatory offline Python profile, not the optional hosted/web adapters.

| Master-prompt capability | Status | Grounded behavior |
|---|---|---|
| Python-only offline baseline | **Implemented** | Mandatory imports require Python, NumPy and Pillow only; no Node, browser, GL, GPU, Docker, database, queue or external executable is loaded. |
| `pip install .` project build | **Implemented** | A repository-local standard-library PEP 517 backend builds the wheel without downloading setuptools/wheel. Runtime NumPy/Pillow still come from the environment/PyPI as permitted by the prompt. |
| `.schem` import | **Implemented** | Sponge v1/v2/v3 adapters preserve exact coordinates, states, NBT and unknown fields. |
| `.schematic` import | **Implemented with explicit legacy ambiguity** | Numeric ID/data are mapped by profile; unresolved values remain placeholders and are never silently converted to air. |
| Multi-region `.litematic` import | **Implemented** | Signed dimensions, per-region palettes/data, overlaps, entities, block entities and ticks are preserved. |
| Exact symbolic evidence | **Implemented** | CLI and AI tools expose exact block, box, chunk, palette, region, block-entity, room, component and analysis data. |
| CPU textured rendering | **Implemented** | Pure NumPy/Pillow rasterizer resolves blockstates, variants, multipart, model parents, cuboids, rotations, UVs, tint, cutout/translucency and fluids. |
| Flat rendering without assets | **Implemented** | Deterministic Tier 0 output remains available and is truthfully diagnosed as `software-flat`. |
| Global/layer/slice/crop views | **Implemented** | Orthographic/isometric presets, arbitrary orthographic cameras, Y layers, X/Y/Z slices/slabs and coordinate crops are emitted with manifests. |
| Room-aware perspective interiors | **Implemented** | Genuine eye-position perspective cameras support target or yaw/pitch aiming, vertical FOV, near/far clipping, perspective-correct textures, physical/cutaway/hybrid visibility, automatic walkable room shots and multi-room galleries. Interior commands default to perspective while existing exterior and slice behavior remains unchanged. |
| Production interior classification | **Implemented** | Enclosed components record exact seeds, heuristic architectural/natural/decorative scores, confidence, evidence, room-like status, and designed-space or cavity/void classification. |
| Visibility-aware camera selection | **Implemented** | Exact component membership, deterministic voxel rays, multi-sample visibility, collision, clearance, reachability labels, hard rejection gates, and deterministic quality retries prevent technically rendered but blocked views from being accepted silently. |
| Third-person and cutaway evidence | **Implemented** | Elevated and orbit cameras are labeled as non-player evidence; minimal ray-derived, protected wall-off, and roof-off masks are non-destructive and fully recorded by boundary class. |
| Composite interior packets | **Implemented** | Packets include named physical/cutaway perspectives, room-bounded plans and slices, camera candidates and rejections, semantic quality metrics, diagnostics, exact source hashes, and unresolved limitations for multimodal review. |
| Perspective semantic grounding | **Implemented** | Perspective renders preserve exact coordinate, depth, normal, palette, region, occupancy, changed and issue maps, so `pixel-to-block` and `block-to-pixel` remain exact for visible pixels. |
| Pixel-to-block grounding | **Implemented** | Dense semantic maps store exact coordinate, palette, region, depth, normal, occupancy, changed and issue/fallback information. |
| Structural analysis | **Implemented** | Materials, surfaces, components, support, rooms, navigation, symmetry/repetition, facade depth, heuristic lighting and consistency checks. |
| Transactional modification | **Implemented** | Bounded validation, preconditions, visual preview, commit/reject, immutable versions, rollback, branches, checkpoints, comparison and merge conflict detection. |
| Literal LLM vision | **Implemented** | OpenAI Responses, Anthropic Messages and OpenAI-compatible adapters attach actual PNG bytes plus exact tools; fresh images follow previews/commits/rollbacks. |
| AI build generation | **Implemented** | Provider-independent staged plans and provider-driven construction from an all-air bounded document both use render/analyze/critique/revise loops. |
| Verified export | **Implemented** | Sponge v3 and Litematic outputs are re-imported through the normal parser and compared coordinate-by-coordinate and state-by-state. |
| Autonomous agent documentation | **Implemented** | `SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md` is an LLM-only, no-routine-human runbook with complete schemas, operations and recovery rules. |

## Meduseld quality and map-maker capabilities (1.1.0)

| Capability | Status | Grounded behavior |
|---|---|---|
| Whole-volume comprehension | **Implemented** | Block-map CSV/JSONL/optional Parquet, texture gates, palette atlases, labelled contact sheets, slice sweeps, and annotated renders cover symbolic and visual evidence. |
| Exact scalable rendering | **Implemented** | Fit-to-subject framing is default; exact screen-space tiles checkpoint image and semantic slices, validate resume markers, and use disk-backed buffers. Fast preview is explicitly non-texture-exact. |
| Entity-rendered blocks | **Implemented** | Banners/patterns, skulls/heads, signs, beds, and shulker boxes use entity-atlas proxy meshes with distinct `ENTITY_RENDERED` diagnostics. |
| Scoped interior intelligence | **Implemented** | Bounds, structures, manual rooms, conservative envelope sealing, configurable lighting, furnishing/dead-volume metrics, walkthroughs, sightlines, and cumulative packet coverage. |
| Quality feedback loop | **Implemented** | Comparable normalized lighting, coverage, furnishing, facade, structural, circulation, palette, and symmetry scores support thresholds and version diffs. |
| Map-scale structure intelligence | **Implemented** | Streamed classification/segmentation, inventory/names/extracts, checkpoints, room programs, completeness, site/terrain/navigation/sightline/LOD reports, and structure comparisons. |
| Reference-style authoring | **Implemented** | Style profiles, critique, durable anchors, truss/dormer/arcade/bellcast assemblies, fixtures, symmetry edits, greebling, and controlled repetition remain bounded patch operations. |
| Meduseld traceability | **Implemented** | `MEDUSELD_IMPLEMENTATION_TRACEABILITY.md` maps every report item to code, tests, and real-schematic acceptance evidence. |

## Large-schematic capabilities (1.2.0)

| Capability | Status | Grounded behavior |
|---|---|---|
| Chunk-array voxel model | **Implemented** | Sparse 16-cubed `uint32` chunks provide deterministic mapping semantics; lazy region overlays avoid a duplicate flattened Litematic map. |
| Streamed schematic lifecycle | **Implemented** | Sponge/Litematic decoding, canonical hashing/read/write, block-map output and export avoid per-cell Python lists or duplicate JSON payloads. |
| Scale budget | **Implemented; generated gate passed** | The matrix stores 16,777,216 placed voxels in 64 MiB of voxel arrays and streams 4,194,304 Litematic values. Whole-process memory includes additional documented inputs/assets/analysis buffers. |
| Exact tile-local rendering | **Implemented** | Tile geometry counts only emitted blocks, semantic maps are disk-backed, checkpoints are hash-validated, and a 2,097,152-block dense fixture exercises exact resume determinism. |
| Honest LOD | **Implemented** | Large fast overviews use nearest-depth sampling and explicitly report LOD/non-exact status and source count. |
| Terrain-relative structures | **Implemented** | Local surface, cavity, verticality, enclosure, regularity and embedding evidence prevent terrain skins from becoming buildings without making material-specific assumptions. |
| Fluids and entities | **Implemented** | Water/lava levels, waterlogging and all five entity-rendered families count as covered only when their renderer paths resolve. |
| Universality edge matrix | **Implemented** | Rich 50,000 block entities, y=-64..320, 2,000 states, terrain-only and material-independent castle/bridge/dungeon cases are release tests. |
| Anvil worlds | **Explicitly unsupported** | `.mca` and world directories return `ANVIL_WORLD_UNSUPPORTED`; supported scope remains schematic files. |
| Named Tree fixture | **Pending source availability** | Code and generated scale gates are implemented, but the untouched `Tree_of_dreams.schem` must be supplied before its exact end-to-end gate can pass. |

## Literal vision and exact identity

The system does not ask an AI to infer block identity from pixels. The model receives literal rendered PNGs for appearance and geometry, while exact canonical tools and pixel-hit maps provide namespaced IDs, ordered properties, NBT and coordinates. This directly implements the master prompt's central visual-symbolic rule.

## Perspective interior contract

`python -m app.cli interior render` and `interior gallery` are the default human-facing interior presentation paths. They place the camera at validated walkable eye positions inside detected room volumes and record camera, crop and temporary visibility-mask evidence in each manifest. `render --projection perspective` remains available for exact manual camera placement. Orthographic rendering and 2D slices are preserved for exterior presentation and technical evidence.

## Certification boundary

The functional vision and all executable gates in this container are implemented. A claim that the exact **Python 3.12 runtime** passed cannot be made from this container because it exposes Python 3.13.5 and cannot download a 3.12 interpreter. The repository includes a Python 3.12 CI gate, parses mandatory sources against Python 3.12 grammar, and declares Python `>=3.12`. Likewise, a temporary package-mirror outage prevented a genuine clean download of NumPy/Pillow; the project build backend itself was fixed and clean-wheel execution was tested with the already-installed binary runtime.

No finite test suite proves universal flawlessness across every future mod, resource pack, provider, OS or Minecraft client. The defensible statement is: **the mandatory offline profile meets the master-prompt vision and passes the documented support-matrix verification, with the exact Python 3.12/PyPI network gate awaiting execution in an environment that supplies them.**

## Private all-in-one 1.0.3 update

The exact user-supplied Minecraft asset archive is embedded inside the installable package and auto-selected without configuration. `BOOTSTRAP_SNOWFLAKE.py --smoke` verifies installation, asset integrity, Tier 2 textured rendering, and the reference pipeline. The perspective feature patch adds deterministic first-person interior rendering without adding any mandatory dependency. The complete local Python suite passes 90/90 tests, including textured perspective, near-plane clipping, exact semantic grounding, non-destructive cutaways, room camera placement and installed-wheel CLI discovery.
