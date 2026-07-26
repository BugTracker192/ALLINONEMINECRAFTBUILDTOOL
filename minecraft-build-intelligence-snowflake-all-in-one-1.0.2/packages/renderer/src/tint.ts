export interface TintPreset {
  grass: number;
  foliage: number;
  water: number;
}

export const NEUTRAL_ANALYSIS_TINT: TintPreset = { grass: 0x7fb238, foliage: 0x59ae30, water: 0x3f76e4 };

export function multiplySrgb(base: number, tint: number): number {
  const channel = (value: number, shift: number) => (value >> shift) & 0xff;
  const combine = (shift: number) => Math.round((channel(base, shift) * channel(tint, shift)) / 255) << shift;
  return (combine(16) | combine(8) | combine(0)) >>> 0;
}

export function stateTintIndex(state: string, tintIndex: number, preset: TintPreset = NEUTRAL_ANALYSIS_TINT): number | null {
  if (tintIndex < 0) return null;
  const base = state.split("[", 1)[0];
  if (base.includes("grass") || base.includes("fern") || base.includes("sugar_cane")) return preset.grass;
  if (base.includes("leaves") || base.includes("vine")) return preset.foliage;
  if (base === "minecraft:water" || state.includes("waterlogged=true")) return preset.water;
  if (base.includes("redstone_wire")) {
    const power = Number(/(?:\[|,)power=(\d+)/.exec(state)?.[1] ?? 0);
    const red = Math.round(96 + (159 * power) / 15);
    return (red << 16) | (Math.round((power / 15) ** 2 * 64) << 8);
  }
  return null;
}
