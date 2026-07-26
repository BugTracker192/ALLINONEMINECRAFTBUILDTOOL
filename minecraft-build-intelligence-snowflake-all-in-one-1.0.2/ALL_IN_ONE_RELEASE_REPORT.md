# Private all-in-one Snowflake/CoCo release 1.0.2

## Integrated contents

- Full source repository and autonomous LLM guide.
- Exact user-supplied Minecraft asset archive embedded at `app/bundled_assets/minecraft.zip`.
- Asset SHA-256: `f99aefac7040f85c67b509ebc63a56e542d5f250fd51040d6a3bd7f97e6e5bbc`.
- 16,572 archive members; 8,092 render-relevant assets.
- No resource-pack path or human texture configuration is required.
- `BOOTSTRAP_SNOWFLAKE.py --smoke` installs missing mandatory dependencies, installs the package, verifies the asset hash, and runs a textured reference pipeline.

## Dynamic verification

- 82/82 tests passed.
- Source checkout no-argument pipeline: `software-textured`, Tier 2, 15 snapshots.
- Installed wheel outside the source tree found the asset inside the installed package.
- Installed-wheel pipeline: zero coordinate mismatches and zero state mismatches after export/re-import.
- Wheel: `minecraft_build_intelligence-1.0.2-py3-none-any.whl` (411,616,126 bytes).

## Automatic asset precedence

1. Explicit `--resource-pack` or Python argument.
2. `MBI_RESOURCE_PACK`.
3. Embedded `app/bundled_assets/minecraft.zip`.
4. Nearby workspace pack.

Flat rendering requires explicit opt-out via `MBI_DISABLE_BUNDLED_ASSETS=1` or `--resource-pack none`.

## Private-use notice

The embedded proprietary assets were supplied by the requesting user and are included only in this private deliverable. Do not publicly redistribute them without authorization.
