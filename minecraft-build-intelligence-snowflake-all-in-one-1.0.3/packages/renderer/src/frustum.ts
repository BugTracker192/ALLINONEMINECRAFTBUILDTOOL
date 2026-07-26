export interface Plane { normal: readonly [number, number, number]; constant: number }
export interface Aabb { min: readonly [number, number, number]; max: readonly [number, number, number] }

export function aabbIntersectsFrustum(box: Aabb, planes: readonly Plane[]): boolean {
  for (const plane of planes) {
    const [nx, ny, nz] = plane.normal;
    const x = nx >= 0 ? box.max[0] : box.min[0];
    const y = ny >= 0 ? box.max[1] : box.min[1];
    const z = nz >= 0 ? box.max[2] : box.min[2];
    if (nx * x + ny * y + nz * z + plane.constant < 0) return false;
  }
  return true;
}

export interface ChunkCandidate { key: string; bounds: Aabb; center: readonly [number, number, number] }

export function prioritizeVisibleChunks(
  chunks: readonly ChunkCandidate[],
  planes: readonly Plane[],
  camera: readonly [number, number, number],
  limit = Number.POSITIVE_INFINITY,
): ChunkCandidate[] {
  return chunks
    .filter((chunk) => aabbIntersectsFrustum(chunk.bounds, planes))
    .map((chunk) => ({ chunk, distance: Math.hypot(chunk.center[0] - camera[0], chunk.center[1] - camera[1], chunk.center[2] - camera[2]) }))
    .sort((a, b) => a.distance - b.distance || a.chunk.key.localeCompare(b.chunk.key))
    .slice(0, limit)
    .map((item) => item.chunk);
}
