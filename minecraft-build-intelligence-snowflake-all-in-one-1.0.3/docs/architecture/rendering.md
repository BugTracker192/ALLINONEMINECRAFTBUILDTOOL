# Rendering architecture

The mandatory renderer is a deterministic NumPy/Pillow CPU rasterizer. Orthographic, isometric, crop and technical slice paths remain stable and continue to emit dense semantic maps.

The perspective extension adds genuine physical eye positions for interiors. It clips geometry against camera near/far planes before projection, uses perspective-correct UV interpolation, performs perspective-aware face visibility and writes the same exact coordinate/palette/region/depth/normal/occupancy/issue maps as orthographic rendering.

Interior commands use detected room volumes and walkable air columns to choose safe eye-height positions. Visibility is physical by default; optional cutaway and hybrid modes hide only a documented temporary coordinate mask and never alter the canonical build.

See `interior-perspective.md` for CLI contracts and defaults.
