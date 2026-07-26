export type Axis = 0 | 1 | 2;
export type FaceSign = -1 | 1;

export interface VoxelField {
  size: readonly [number, number, number];
  /** Return 0 for air; positive integers identify exact render-compatible materials. */
  get(x: number, y: number, z: number): number;
  /** True only when the voxel fully occludes the queried face. */
  occludes?(material: number, axis: Axis, sign: FaceSign): boolean;
}

export interface GreedyQuad {
  axis: Axis;
  sign: FaceSign;
  material: number;
  origin: [number, number, number];
  size: [number, number];
}

interface MaskCell {
  material: number;
  sign: FaceSign;
}

function equal(a: MaskCell | null, b: MaskCell | null): boolean {
  return a !== null && b !== null && a.material === b.material && a.sign === b.sign;
}

/** Deterministic 3-axis greedy meshing for fully occluding cube faces. */
export function greedyMesh(field: VoxelField): GreedyQuad[] {
  const dimensions = field.size;
  const occludes = field.occludes ?? ((material: number) => material !== 0);
  const result: GreedyQuad[] = [];
  for (let axis = 0 as Axis; axis < 3; axis = (axis + 1) as Axis) {
    const u = ((axis + 1) % 3) as Axis;
    const v = ((axis + 2) % 3) as Axis;
    const maskWidth = dimensions[u];
    const maskHeight = dimensions[v];
    const coordinate = [0, 0, 0];
    const neighbor = [0, 0, 0];
    for (let slice = -1; slice < dimensions[axis]; slice += 1) {
      const mask: Array<MaskCell | null> = new Array(maskWidth * maskHeight).fill(null);
      let index = 0;
      for (let vv = 0; vv < maskHeight; vv += 1) {
        for (let uu = 0; uu < maskWidth; uu += 1) {
          coordinate[axis] = slice;
          coordinate[u] = uu;
          coordinate[v] = vv;
          neighbor[axis] = slice + 1;
          neighbor[u] = uu;
          neighbor[v] = vv;
          const a = slice >= 0 ? field.get(coordinate[0], coordinate[1], coordinate[2]) : 0;
          const b = slice + 1 < dimensions[axis] ? field.get(neighbor[0], neighbor[1], neighbor[2]) : 0;
          const aVisible = a !== 0 && !occludes(b, axis, 1);
          const bVisible = b !== 0 && !occludes(a, axis, -1);
          mask[index++] = aVisible ? { material: a, sign: 1 } : bVisible ? { material: b, sign: -1 } : null;
        }
      }
      for (let y = 0; y < maskHeight; y += 1) {
        for (let x = 0; x < maskWidth;) {
          const cell = mask[x + y * maskWidth];
          if (cell === null) {
            x += 1;
            continue;
          }
          let width = 1;
          while (x + width < maskWidth && equal(cell, mask[x + width + y * maskWidth])) width += 1;
          let height = 1;
          heightLoop: while (y + height < maskHeight) {
            for (let dx = 0; dx < width; dx += 1) {
              if (!equal(cell, mask[x + dx + (y + height) * maskWidth])) break heightLoop;
            }
            height += 1;
          }
          const origin: [number, number, number] = [0, 0, 0];
          origin[axis] = slice + 1;
          origin[u] = x;
          origin[v] = y;
          result.push({ axis, sign: cell.sign, material: cell.material, origin, size: [width, height] });
          for (let dy = 0; dy < height; dy += 1) {
            for (let dx = 0; dx < width; dx += 1) mask[x + dx + (y + dy) * maskWidth] = null;
          }
          x += width;
        }
      }
    }
  }
  return result;
}
