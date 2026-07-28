# Room-aware first-person perspective rendering

This renderer feature update adds a deterministic CPU perspective renderer for genuine interior camera placement while preserving the existing orthographic, isometric, slice, semantic-map, and coordinate-grounding paths.

## Projection policy

- `render --projection auto` keeps exterior renders orthographic unless a physical camera position is supplied.
- `render --projection perspective` uses a real eye position, target or yaw/pitch, vertical FOV, and near/far clipping.
- `interior render` and `interior gallery` default to perspective, physical visibility, eye height 1.62 blocks, and `interior-soft` lighting.
- Existing orthographic presets and 2D slices remain unchanged.

## Perspective correctness

The renderer performs camera-space near/far clipping before projection, perspective-correct UV interpolation, perspective-aware backface culling, deterministic z-buffering, stable translucent sorting, and exact semantic coordinate/depth/normal/palette/region maps.

## Interior intelligence

Detected room volumes are converted into walkable eye-position candidates. Camera presets select doorway, corner, center, feature, low, upper, or automatic shots. Optional non-destructive cutaway masks are recorded in each manifest and never mutate the build document.

## CLI examples

```bash
python -m app.cli render RUN \
  --projection perspective \
  --camera-position 22.5,20.62,9.5 \
  --camera-target 23.5,22.0,15.0 \
  --fov 72 --near 0.05 \
  --size 1600x1000 --lighting interior-soft

python -m app.cli interior render RUN --room 0 --shot doorway --out OUTPUT
python -m app.cli interior gallery RUN --rooms all --shots doorway,corner,feature --out OUTPUT
```

Every perspective render remains compatible with `pixel-to-block` and `block-to-pixel` because semantic maps retain exact originating block coordinates for visible pixels.
