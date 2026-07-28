# Production interior vision

The interior pipeline combines exact voxel analysis with deterministic visual evidence. It does not treat “an image was written” as proof that a room is visible, and it never describes a temporary cutaway or orbit camera as a physical player view.

## Data flow

```text
canonical document
  -> compact enclosed-air flood fill
  -> architectural / natural / decorative classification
  -> exact selected component and boundary recovery
  -> feature, walkable, elevated, and orbit candidates
  -> collision and multi-sample voxel-ray checks
  -> low-cost deterministic candidate ranking
  -> perspective draft + semantic maps
  -> frame-quality acceptance or deterministic retry
  -> minimal cutaway / wall-off / roof-off fallback
  -> room-bounded plan and vertical slices
  -> composite LLM evidence packet
```

All classification and targeting decisions derive from the canonical `BuildDocument`. Render-only masks are passed to the perspective renderer and do not modify blocks, versions, regions, entities, or exports.

## Enclosed-space classification

`mbi.analysis.rooms.classify_air_volumes` uses a byte-per-expanded-cell flood fill with a default 20-million-cell safety limit. Each enclosed component records its exact seed, bounds, size, floor area, walkable count, heuristic scores, confidence, evidence, and one of the supported labels:

- architectural room, hall, corridor, stairwell, attic, pavilion, tower, workshop, or storage;
- natural cavity or terrain void;
- decorative, roof, wall, vegetation, or fluid void;
- unknown enclosed space.

The scores are heuristic evidence, not asserted Minecraft truth. Natural cavities are not marked `room_like`, and automatic galleries skip non-room voids unless the caller selects them explicitly.

## Exact component and boundary model

The interior layer recovers the selected seed component inside its reported bounds. Features and cameras are evaluated against that exact set rather than the bounding box alone. Solid neighbors are classified as:

- floor and ceiling;
- north, south, east, and west walls;
- internal partitions;
- columns and supports;
- door, window, and opening frames;
- terrain shell;
- roof structure;
- functional or feature structure.

Functional blocks, block entities, columns, opening frames, and other protected structure are excluded from default cutaway masks.

## Camera families and honesty

Candidates include reachable first-person positions, collision-free elevated evidence, and external orbit positions. Each candidate records:

- position and target;
- camera mode and reachability label;
- clearance;
- multi-sample visible ratio;
- deterministic score;
- hard rejection reasons.

`reachable` means a normal walkable candidate in the selected air component. `physically-valid-unreachable` is collision-free elevated evidence and is not described as a normal player view. `non-physical-evidence` is an orbit or cutaway camera.

The visibility engine uses deterministic Amanatides-Woo voxel traversal. It tests the selected feature, room center, lower room volume, and upper room volume. Opaque blockers, camera collision, low clearance, target proximity, and insufficient line of sight are explicit rejection gates.

## Cutaway policy

`physical` hides nothing. `cutaway` collects first ray blockers and opens only a bounded local patch. If that draft fails, the retry path can use a protected wall-off or roof-off mask. `hybrid` declines an unexpectedly broad minimal mask. Every mask is temporary and its manifest records:

- hidden coordinates;
- hidden coordinate hash;
- boundary classification for each hidden coordinate;
- protected-coordinate count;
- requested and effective occlusion modes;
- selected cutaway strategy.

Pixel-to-block and block-to-pixel remain valid because visible pixels still store the exact originating block coordinates.

## Visual quality profiles

Drafts are evaluated with semantic maps, not image appearance alone. Metrics include occupancy and background, room and boundary prominence, unrelated terrain, visible floor/ceiling/walls/openings/features, dominant coordinate/plane/material, depth percentiles and entropy, material entropy, edge density, foreground obstruction, clipped triangles, and fallback-model pixels.

Profiles provide different thresholds for first-person, elevated, feature, coverage, third-person cutaway, roof-off, and presentation evidence. A failed draft retains its camera, metrics, and rejection reasons, then the renderer tries the next deterministic candidate within the caller’s budget.

## Room packets

`interior packet` creates a self-contained evidence directory:

```text
interior_packet.json
room_summary.json
camera_candidates.json
camera_rejections.json
accepted_views.json
physical_first_person.png
physical_first_person.manifest.json
third_person_cutaway.png
third_person_cutaway.manifest.json
top_plan.png
top_plan.manifest.json
central_slice_x.png
central_slice_z.png
feature_slice.png
quality_metrics.json
diagnostics.json
semantic_maps/
```

Slices are cropped to the room bounds plus one block of context. Packet metadata includes the exact build/content hash, classification and confidence, grounded features, heuristic room-purpose evidence, navigation labels, accepted and failed evidence, fallback path, and unresolved limitations.

## CLI

```bash
python -m app.cli interior inspect RUN --room ROOM_ID
python -m app.cli interior diagnose RUN --room ROOM_ID

python -m app.cli interior render RUN \
  --room ROOM_ID \
  --shot coverage \
  --camera-mode auto \
  --occlusion physical \
  --cutaway-strategy minimal-ray \
  --quality-profile room_coverage \
  --max-attempts 8 \
  --out OUTPUT

python -m app.cli interior packet RUN \
  --room ROOM_ID \
  --camera-mode auto \
  --fallback physical,third-person,cutaway,slices \
  --shots doorway,corner,feature,coverage \
  --quality-profile presentation \
  --slice-fallback always \
  --out OUTPUT
```

Existing `render --projection perspective`, orthographic/isometric renders, crops, layers, slices, semantic maps, filters, patches, and exports retain their prior contracts.
