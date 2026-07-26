# Changelog

## 1.0.2 — 2026-07-26 — private all-in-one Snowflake release

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
