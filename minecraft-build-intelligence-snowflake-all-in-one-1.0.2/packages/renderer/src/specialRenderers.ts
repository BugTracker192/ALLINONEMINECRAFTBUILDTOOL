export type SpecialRendererTier = "exact" | "static_approximation" | "resource_model" | "placeholder";

export interface SpecialRendererDescriptor {
  block: string;
  tier: SpecialRendererTier;
  usesBlockEntity: boolean;
  notes: string;
}

const REGISTRY: Record<string, SpecialRendererDescriptor> = Object.fromEntries([
  ["minecraft:chest", "static_approximation", true, "Double-chest joining and lid angle are derived from neighbors/NBT."],
  ["minecraft:trapped_chest", "static_approximation", true, "Uses chest geometry with trapped texture."],
  ["minecraft:ender_chest", "static_approximation", true, "Uses chest geometry with emissive-capable texture."],
  ["minecraft:bed", "static_approximation", false, "Head/foot state produces a joined static bed."],
  ["minecraft:banner", "static_approximation", true, "Pattern layers are composed from block-entity NBT."],
  ["minecraft:sign", "static_approximation", true, "Text can be rasterized into a bounded canvas texture."],
  ["minecraft:skull", "static_approximation", true, "Player skins require opt-in external resolution."],
  ["minecraft:shulker_box", "static_approximation", true, "Static closed box; animation is intentionally disabled in analysis mode."],
  ["minecraft:decorated_pot", "static_approximation", true, "Sherd faces derive from block-entity data."],
].map(([block, tier, usesBlockEntity, notes]) => [block, { block, tier, usesBlockEntity, notes } as SpecialRendererDescriptor]));

export function specialRendererFor(canonicalState: string): SpecialRendererDescriptor | null {
  const base = canonicalState.split("[", 1)[0];
  if (REGISTRY[base]) return REGISTRY[base];
  for (const [key, descriptor] of Object.entries(REGISTRY)) {
    if ((key.endsWith(":bed") && base.endsWith("_bed")) || (key.endsWith(":banner") && base.endsWith("_banner")) || (key.endsWith(":sign") && (base.endsWith("_sign") || base.endsWith("_hanging_sign"))) || (key.endsWith(":skull") && (base.endsWith("_head") || base.endsWith("_skull"))) || (key.endsWith(":shulker_box") && base.endsWith("shulker_box"))) return descriptor;
  }
  return null;
}
