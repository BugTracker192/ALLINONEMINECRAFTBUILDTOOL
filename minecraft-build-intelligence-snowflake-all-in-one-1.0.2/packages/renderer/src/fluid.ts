export interface FluidCell { kind: "water" | "lava"; level: number; falling: boolean }
export interface FluidSurface { nw: number; ne: number; se: number; sw: number; sideMask: number }

function height(cell: FluidCell | null): number {
  if (cell === null) return 0;
  if (cell.falling || cell.level <= 0) return 1;
  return Math.max(1 / 9, 1 - Math.min(8, cell.level) / 9);
}

/** Neighbor-aware deterministic fluid top corners. */
export function fluidSurface(center: FluidCell, neighbors: readonly (FluidCell | null)[]): FluidSurface {
  if (neighbors.length !== 8) throw new Error("fluidSurface requires N,NE,E,SE,S,SW,W,NW neighbors");
  const same = neighbors.map((cell) => (cell?.kind === center.kind ? cell : null));
  const corner = (a: number, b: number, diagonal: number) => Math.max(height(center), height(same[a]), height(same[b]), height(same[diagonal]));
  const sideMask = [0, 2, 4, 6].reduce((mask, index, bit) => mask | (same[index] ? 0 : 1 << bit), 0);
  return { nw: corner(0, 6, 7), ne: corner(0, 2, 1), se: corner(2, 4, 3), sw: corner(4, 6, 5), sideMask };
}
