# Build report — Offline Snowflake/CoCo release

The repository now implements the updated mandatory Python sandbox profile rather than relying on the older hosted web stack.

## Central product requirement

The previously missing pathway is complete: an AI receives **both** literal deterministic rendered PNGs and exact symbolic voxel tools. After edits, the system re-renders the affected build and attaches fresh pixels to the next model turn. The model can inspect exact coordinates before editing and can verify the visible result afterward.

## Included foundations

- Safe Sponge, Litematic and legacy schematic import.
- Lossless canonical state/entity/region representation.
- Content-addressed deterministic local chunks and immutable versions.
- Secure direct resource-pack reading.
- Pure CPU Tier 0/1/2 rendering and exact pixel maps.
- Full structural analysis suite.
- Bounded transactional tools and persistent version graph.
- Offline JSON planning/apply workflow.
- Optional real multimodal provider adapters.
- AI construction from blank and AI modification of imports.
- Deterministic verified Sponge/Litematic export.
- Reproducible release-verification command.

## Packaging policy

The source release excludes the user-provided `minecraft.zip`, extracted proprietary textures, API keys, dependency caches and temporary run directories. It includes the exact asset reader/indexer, generated redistributable fixtures, tests, reports and the updated master specification.


## Private all-in-one 1.0.3 update

The exact user-supplied Minecraft asset archive is embedded inside the installable package and auto-selected without configuration. `BOOTSTRAP_SNOWFLAKE.py --smoke` verifies installation, asset integrity, Tier 2 textured rendering, and the reference pipeline. The current suite passes 82/82 tests, and the installed-wheel pipeline passes exact export/re-import verification.
