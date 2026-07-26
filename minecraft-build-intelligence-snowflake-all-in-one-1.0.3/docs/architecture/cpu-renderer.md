# Pure-Python CPU Renderer

## Pipeline

```text
canonical blocks
  → blockstate variants/multipart
  → deterministic weighted model choice
  → model-parent + texture-variable resolution
  → cuboid element geometry
  → model/element rotation and UV handling
  → safe face culling
  → orthographic camera transform
  → triangle clipping and rasterization
  → opaque z-buffer pass
  → alpha-test pass
  → stable back-to-front translucent pass
  → PNG + semantic buffers
```

The renderer uses NumPy arrays and Pillow image decoding/writing. It never creates an OpenGL context.

## Fidelity tiers

- Tier 0: deterministic flat color with normal-based shading.
- Tier 1: actual textures for cube faces and slice cells.
- Tier 2: resolved JSON model elements, variants, multipart, rotations, UVs and tint indexes.

Unsupported dynamic/block-entity models remain exact canonical blocks and are rendered through a visible fallback with coordinate-level diagnostics.

## Determinism

Camera values are quantized, geometry is stably sorted, weighted variants are coordinate-seeded, PNG compression is fixed and wall-clock metrics are excluded from evidence manifests.
