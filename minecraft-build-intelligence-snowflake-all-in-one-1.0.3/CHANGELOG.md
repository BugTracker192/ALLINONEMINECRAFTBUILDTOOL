# Changelog

## 1.1.0 — 2026-07-29 — Meduseld quality and map-maker release

- Fixed Litematic block-entity local coordinates/ID normalization and made all
  exact-verification mismatch classes independent.
- Added FIPS-safe non-security hashing, version-aware bootstrap requirements,
  PEP 660 editable installs, local-scratch mirroring, and warm caches.
- Added legacy asset migrations and entity-texture proxy rendering for
  banners, skulls/heads, signs, beds, and shulker boxes.
- Added default auto-fit framing, fast preview, exact resumable tiled rendering,
  slice naming, and reject-by-default interior quality gates.
- Added whole-volume map export, texture audit gates, palette atlases, contact
  sheets, slice sweeps, and annotated renders.
- Added manual seed-and-clip rooms, conservative structure-envelope sealing,
  scoped lighting/navigation, walkthroughs, sightlines, cumulative coverage,
  and furnishing/dead-volume metrics.
- Added normalized facade monotony, exact symmetry, composite quality
  scorecards, CI thresholds, and version-to-version quality diffs.
- Added structure segmentation/classification, inventory/naming/extraction,
  resumable per-structure analysis, interior programs/packets, site plans,
  terrain integration, settlement navigation, approach sightlines, LOD
  rendering, and structure comparison.
- Added reference style profiles, durable room/bay/landmark anchors, critique
  findings, compound assemblies, fixture kits, symmetry-aware edits, seeded
  greebling, and repeated modules.
- Validated against the 108,917-block Meduseld schematic; see
  `MEDUSELD_IMPLEMENTATION_TRACEABILITY.md`.

## 1.0.3-p2 — 2026-07-29 — production interior vision and evidence packets

- Added scalable enclosed-space classification with architectural, natural, terrain, decorative, roof, wall, vegetation, and fluid evidence scores.
- Replaced bounding-box-only targeting with exact seed-component membership and architectural boundary classification.
- Added deterministic 3D voxel ray testing, multi-sample visibility, collision/clearance gates, candidate scoring, rejection diagnostics, and honest reachability labels.
- Added automatic quality-based retries across physical, elevated, orbit, minimal cutaway, protected wall-off, and roof-off evidence.
- Added semantic visual-quality profiles with room prominence, terrain, floor/ceiling/wall/feature, dominant surface/material, depth/entropy, edge, foreground, background, and fallback metrics.
- Added room-bounded slice crops and composite evidence packets with exact source hashes, named perspective views, plan/slices, candidates, rejections, metrics, diagnostics, and semantic maps.
- Added `interior inspect`, `interior diagnose`, and `interior packet`, plus camera-mode, cutaway-strategy, slice-fallback, quality-profile, and threshold controls.
- Preserved canonical documents and all legacy render, semantic grounding, patch, export, security, and package contracts.

## 1.0.3-p1 — 2026-07-28 — room-aware first-person perspective interiors

- Added a deterministic CPU perspective renderer with exact eye position, target or yaw/pitch aiming, vertical FOV and near/far clipping.
- Added Sutherland–Hodgman camera-depth clipping, perspective-correct texture interpolation, perspective-aware face culling and deterministic z-buffering.
- Preserved exact coordinate, palette, region, depth, normal, occupancy, changed and issue maps for perspective renders.
- Added `render --projection perspective` with physical camera controls and non-destructive hidden-coordinate masks.
- Added `interior render` and `interior gallery`, which default to perspective and select validated walkable eye positions for detected rooms.
- Added doorway, corner, center, feature, low, upper, coverage and walkthrough shot presets.
- Added physical, cutaway and hybrid visibility modes, with every temporary hidden block recorded in the render manifest.
- Added interior-neutral, interior-soft and interior-emissive lighting behavior with controlled emissive-material handling.
- Preserved all existing orthographic, isometric, crop, slice, pixel/block grounding and export behavior.
- Added regression, determinism, clipping, textured perspective, camera-placement, cutaway and installed-wheel tests; the complete local suite passes 90/90.

## 1.0.3 — 2026-07-26 — private all-in-one Snowflake release

- Embedded the exact user-supplied Minecraft asset archive inside the installable `app` package.
- Added automatic asset resolution across CLI, Python API, AI tools, patches, snapshots and generation.
- Added `BOOTSTRAP_SNOWFLAKE.py` for no-prompt dependency setup, package install, hash verification and textured smoke testing.
- Added hash-locked asset manifest and explicit private-use redistribution notice.
- Raised the Pillow floor to 12.3 for the private release.
- Added bundled-asset discovery, disable/override and wheel-inclusion tests.

## 1.0.1 — 2026-07-26 — final Snowflake/CoCo audit

- Added a self-contained standard-library PEP 517 backend, eliminating network-sensitive setuptools/wheel build bootstrap.
- Added exact `query chunk` and `query block-entity` CLI commands.
- Added tests for isolated wheel construction and the new exact query paths; suite is now 80/80.
- Added `SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md`, an exhaustive LLM-only autonomous operating manual.
- Added a master-prompt compliance audit and clarified exact Python 3.12/package-index certification boundaries.

## 1.0.0 — 2026-07-26

- Added mandatory offline Python Snowflake/CoCo profile.
- Added deterministic NumPy/Pillow CPU software rasterizer with real resource-pack textures and resolved JSON block models.
- Added orthographic, isometric, slice, slab and crop rendering with coordinate, palette, region, depth, normal, occupancy, issue and changed-block maps.
- Added safe direct ZIP/JAR resource-pack reader and modern texture-object support.
- Added literal PNG delivery to OpenAI Responses, Anthropic Messages and OpenAI-compatible multimodal providers.
- Added visual feedback after render, patch preview, patch commit and rollback tool calls.
- Added provider-independent JSON tool bridge and offline build-plan workflow.
- Added deterministic filesystem run format, content-addressed chunks, immutable versions and exact export verification.
- Preserved optional hosted adapters without making them mandatory dependencies.
