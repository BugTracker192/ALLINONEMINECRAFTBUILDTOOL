# Rendering

The renderer resolves blockstate `variants` and `multipart`, deterministic coordinate-selected alternatives, model parent inheritance, texture variables, JSON cuboid elements, rotations, cutout/translucent categories, and visible fallback models. Instances are grouped by state/model; no Three.js object is created per voxel.

Next fidelity gates are full UV rotation/uvlock, tint indexes, neighbor-aware fluids, cullface coverage, greedy opaque meshing, and special block-entity renderers.
