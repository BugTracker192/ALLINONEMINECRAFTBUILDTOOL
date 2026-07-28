# Production interior vision: implementation and verification report

## Outcome

Revision `1.0.3-p2-production-interior-vision` replaces permissive center-targeted perspective rendering with a room-aware evidence pipeline. It recovers exact navigable air components, classifies designed and natural voids separately, derives architectural boundaries, generates collision-checked camera candidates, proves target visibility with deterministic voxel rays, scores semantic frame quality, retries weak views, applies protected minimal cutaways only when needed, and emits room-bounded slices plus a composite evidence packet.

## Root cause

The previous workflow treated a coarse room bounding box as sufficient geometry and aimed a camera at its center. Candidate acceptance did not prove that the camera was inside the selected component, that its ray reached a relevant interior feature, or that the resulting frame contained useful interior evidence. Exterior terrain, walls, roofs, and block entities could therefore dominate an accepted frame.

The correction moves the invariant upstream: a view is derived from one exact air component and its classified boundary. Candidate position, target membership, ray visibility, collision clearance, hidden geometry, semantic coverage, and reachability are all recorded and validated.

## Architecture

- `services/core/src/mbi/analysis/rooms.py` performs compact bounded flood fill and distinguishes architectural rooms, halls, corridors, stairwells, attics, pavilions, tower interiors, workshops, storage, and natural/decorative void classes.
- `app/interior/model.py` recovers exact geometry and boundary roles, selects evidence-bearing feature targets, traces deterministic Amanatides-Woo voxel rays, evaluates camera clearance/visibility, and derives protected ray-minimal cutaways.
- `app/interior/quality.py` measures semantic coverage, foreground obstruction, dominant surfaces/materials, depth distribution, entropy, edge density, clipping, and fallback-model use against purpose-specific acceptance profiles.
- `app/interior/rendering.py` orchestrates inspect, diagnose, render, gallery, and packet workflows with bounded retries and explicit fallback/reachability labels.
- `app/render/software.py` adds room-bounded slice crops whose visible bounds participate in deterministic artifact hashes.
- `app/cli/__init__.py` exposes the production controls without changing existing render commands.

No edits are applied to the source schematic. Cutaways are view-local hidden-block sets. Floors, doors, windows, frames, functional blocks, and feature targets are protected; wall or roof removal is used only as a labeled non-physical evidence fallback.

## CLI contract

```bash
python -m app.cli interior inspect build.schem --seed 12,8,24
python -m app.cli interior diagnose build.schem --seed 12,8,24
python -m app.cli interior render build.schem --seed 12,8,24 --camera-mode physical_first_person
python -m app.cli interior render build.schem --seed 12,8,24 --camera-mode orbit --cutaway-strategy minimal
python -m app.cli interior gallery build.schem --seed 12,8,24
python -m app.cli interior packet build.schem --seed 12,8,24 --fallback slice
```

Quality thresholds, maximum attempts, cutaway policy, occlusion search, camera mode, and slice fallback are configurable. Each manifest records source hashes, exact room/component membership, camera/target vectors, ray hits, hidden boundary classes, quality metrics, rejection reasons, fallback path, reachability, and unresolved limitations.

## Evidence packet

`interior packet` writes:

- `interior_packet.json`
- `room_summary.json`
- `camera_candidates.json`
- `camera_rejections.json`
- `accepted_views.json`
- `physical_first_person.png` and manifest
- `third_person_cutaway.png` and manifest
- `top_plan.png` and manifest
- `central_slice_x.png`, `central_slice_z.png`, and `feature_slice.png`
- `quality_metrics.json`
- `diagnostics.json`
- semantic maps

The packet distinguishes physically reachable views, physically valid but unreachable views, and non-physical evidence views.

## Verification

The uninterrupted local release verifier passed on Python 3.12.13:

- 81 tests with zero failures or skips.
- Offline-profile and source-security audits.
- Flat and textured end-to-end pipelines.
- Literal OpenAI Responses, Anthropic Messages, and OpenAI-compatible protocol loops.
- AI construction from an all-air document followed by critique and exact export.
- CPU model coverage and 5,000 malformed-input mutations with zero unexpected failures.
- Flat and textured benchmarks.
- Two byte-identical pipeline trees containing 195 artifacts.
- Installed-wheel pipeline outside the source tree with exact export/re-import verification.
- 8,092 indexed resource-pack assets with zero model-parent audit failures.

The wheel is 408,248,329 bytes with SHA-256 `86c84e11fea4c535fa6a1390808d2dfb7a9c9befd313caa9293fe4ef27dde2a3`.

Focused Ruff checks pass for the new production-interior modules and strict mypy passes for the interior, room-analysis, and release-overlay modules.

## Benchmark boundary

The requested Japanese lobby benchmark was located at its official Planet Minecraft project page. Its static `.schem` download returned browser/CDN blocking in this environment, so it was not obtained, committed, or redistributed. The regression suite uses a deterministic synthetic structure that reproduces the same failure mechanism: a valid designed interior hidden behind an exterior wall/terrain plane. It verifies exact component targeting, voxel visibility, dominant-surface rejection, retry behavior, protected cutaway, and room-bounded slice fallback.

The real Japan file remains a clearly named, legally acquired private acceptance gate. This report does not claim a before/after run that was not executed.

## Operational and rollback notes

The implementation is additive at the CLI and data-model boundary; existing perspective and slice entry points remain supported. New dataclass fields have defaults for compatibility. The release overlay captures every changed file and validates the effective base-plus-overlay tree. Rollback is a normal revert of revision `1.0.3-p2-production-interior-vision`; source schematics and prior generated artifacts are not mutated.
