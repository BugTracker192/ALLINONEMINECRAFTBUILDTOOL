export type CameraPreset = "front" | "back" | "left" | "right" | "top" | "bottom" | "isometric_ne" | "isometric_nw" | "isometric_se" | "isometric_sw";
export interface Bounds3 { min: readonly [number, number, number]; max: readonly [number, number, number] }
export interface CameraFit { position: [number, number, number]; target: [number, number, number]; orthographicHalfWidth: number; orthographicHalfHeight: number; near: number; far: number }

export function fitCamera(bounds: Bounds3, preset: CameraPreset, aspect = 1, margin = 1.1): CameraFit {
  const size: [number, number, number] = [bounds.max[0] - bounds.min[0] + 1, bounds.max[1] - bounds.min[1] + 1, bounds.max[2] - bounds.min[2] + 1];
  const target: [number, number, number] = [(bounds.min[0] + bounds.max[0] + 1) / 2, (bounds.min[1] + bounds.max[1] + 1) / 2, (bounds.min[2] + bounds.max[2] + 1) / 2];
  const radius = Math.hypot(...size) * margin;
  const vectors: Record<CameraPreset, [number, number, number]> = {
    front: [0, 0, -1], back: [0, 0, 1], left: [-1, 0, 0], right: [1, 0, 0], top: [0, 1, 0], bottom: [0, -1, 0],
    isometric_ne: [1, 1, -1], isometric_nw: [-1, 1, -1], isometric_se: [1, 1, 1], isometric_sw: [-1, 1, 1],
  };
  const vector = vectors[preset];
  const magnitude = Math.hypot(...vector);
  const position: [number, number, number] = [target[0] + vector[0] / magnitude * radius, target[1] + vector[1] / magnitude * radius, target[2] + vector[2] / magnitude * radius];
  const projectedWidth = ["front", "back", "top", "bottom"].includes(preset) ? size[0] : ["left", "right"].includes(preset) ? size[2] : (size[0] + size[2]) / Math.SQRT2;
  const projectedHeight = ["top", "bottom"].includes(preset) ? size[2] : ["front", "back", "left", "right"].includes(preset) ? size[1] : size[1] + (size[0] + size[2]) / (2 * Math.SQRT2);
  const halfHeight = Math.max(projectedHeight / 2, projectedWidth / (2 * Math.max(0.01, aspect))) * margin;
  return { position, target, orthographicHalfWidth: halfHeight * aspect, orthographicHalfHeight: halfHeight, near: Math.max(0.01, radius - Math.hypot(...size)), far: radius + Math.hypot(...size) };
}
