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
| Global/layer/slice/crop views | **Implemented** | Orthographic/isometric presets, arbitrary cameras, Y layers, X/Y/Z slices/slabs and coordinate crops are emitted with manifests. |
| Pixel-to-block grounding | **Implemented** | Dense semantic maps store exact coordinate, palette, region, depth, normal, occupancy, changed and issue/fallback information. |
| Structural analysis | **Implemented** | Materials, surfaces, components, support, rooms, navigation, symmetry/repetition, facade depth, heuristic lighting and consistency checks. |
| Transactional modification | **Implemented** | Bounded validation, preconditions, visual preview, commit/reject, immutable versions, rollback, branches, checkpoints, comparison and merge conflict detection. |
| Literal LLM vision | **Implemented** | OpenAI Responses, Anthropic Messages and OpenAI-compatible adapters attach actual PNG bytes plus exact tools; fresh images follow previews/commits/rollbacks. |
| AI build generation | **Implemented** | Provider-independent staged plans and provider-driven construction from an all-air bounded document both use render/analyze/critique/revise loops. |
| Verified export | **Implemented** | Sponge v3 and Litematic outputs are re-imported through the normal parser and compared coordinate-by-coordinate and state-by-state. |
| Autonomous agent documentation | **Implemented** | `SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md` is an LLM-only, no-routine-human runbook with complete schemas, operations and recovery rules. |

## Literal vision and exact identity

The system does not ask an AI to infer block identity from pixels. The model receives literal rendered PNGs for appearance and geometry, while exact canonical tools and pixel-hit maps provide namespaced IDs, ordered properties, NBT and coordinates. This directly implements the master prompt's central visual-symbolic rule.

## Certification boundary

The functional vision and all executable gates in this container are implemented. A claim that the exact **Python 3.12 runtime** passed cannot be made from this container because it exposes Python 3.13.5 and cannot download a 3.12 interpreter. The repository includes a Python 3.12 CI gate, parses mandatory sources against Python 3.12 grammar, and declares Python `>=3.12`. Likewise, a temporary package-mirror outage prevented a genuine clean download of NumPy/Pillow; the project build backend itself was fixed and clean-wheel execution was tested with the already-installed binary runtime.

No finite test suite proves universal flawlessness across every future mod, resource pack, provider, OS or Minecraft client. The defensible statement is: **the mandatory offline profile meets the master-prompt vision and passes the documented support-matrix verification, with the exact Python 3.12/PyPI network gate awaiting execution in an environment that supplies them.**


## Private all-in-one 1.0.2 update

The exact user-supplied Minecraft asset archive is embedded inside the installable package and auto-selected without configuration. `BOOTSTRAP_SNOWFLAKE.py --smoke` verifies installation, asset integrity, Tier 2 textured rendering, and the reference pipeline. The current suite passes 82/82 tests, and the installed-wheel pipeline passes exact export/re-import verification.
