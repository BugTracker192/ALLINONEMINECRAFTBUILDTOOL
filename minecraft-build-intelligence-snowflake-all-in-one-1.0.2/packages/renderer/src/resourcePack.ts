import type { PaletteEntry } from "@mbi/protocol";

export interface ModelRef {
  model: string;
  x?: number;
  y?: number;
  uvlock?: boolean;
  weight?: number;
}

export interface ModelFace {
  texture: string;
  uv?: [number, number, number, number];
  rotation?: 0 | 90 | 180 | 270;
  cullface?: string;
  tintindex?: number;
}

export interface ModelElement {
  from: [number, number, number];
  to: [number, number, number];
  faces: Partial<Record<"down" | "up" | "north" | "south" | "west" | "east", ModelFace>>;
  rotation?: {
    origin: [number, number, number];
    axis: "x" | "y" | "z";
    angle: number;
    rescale?: boolean;
  };
  shade?: boolean;
}

export interface ResolvedModel {
  elements: ModelElement[];
  textures: Record<string, string>;
  ambientOcclusion: boolean;
}

function parseState(state: string): { resource: string; properties: Record<string, string> } {
  const bracket = state.indexOf("[");
  if (bracket < 0) return { resource: state, properties: {} };
  const properties: Record<string, string> = {};
  for (const pair of state.slice(bracket + 1, -1).split(",")) {
    const [key, value] = pair.split("=", 2);
    properties[key] = value;
  }
  return { resource: state.slice(0, bracket), properties };
}

function splitResource(resource: string, fallback = "minecraft"): [string, string] {
  const separator = resource.indexOf(":");
  return separator >= 0 ? [resource.slice(0, separator), resource.slice(separator + 1)] : [fallback, resource];
}

function selectorMatches(selector: string, properties: Record<string, string>): boolean {
  if (!selector) return true;
  return selector.split(",").every((pair) => {
    const [key, value] = pair.split("=", 2);
    return properties[key] === value;
  });
}

function multipartMatches(condition: unknown, properties: Record<string, string>): boolean {
  if (condition == null) return true;
  if (typeof condition !== "object" || Array.isArray(condition)) return false;
  const object = condition as Record<string, unknown>;
  if (Array.isArray(object.OR)) return object.OR.some((item) => multipartMatches(item, properties));
  if (Array.isArray(object.AND)) return object.AND.every((item) => multipartMatches(item, properties));
  return Object.entries(object).every(([key, value]) => String(value).split("|").includes(properties[key]));
}

function deterministicHash(x: number, y: number, z: number, salt: string): number {
  let hash = 2166136261;
  for (const code of `${x},${y},${z}:${salt}`) {
    hash ^= code.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function weightedModel(models: ModelRef[], x: number, y: number, z: number, salt: string): ModelRef {
  const total = models.reduce((sum, model) => sum + Math.max(1, model.weight ?? 1), 0);
  let pick = deterministicHash(x, y, z, salt) % total;
  for (const model of models) {
    pick -= Math.max(1, model.weight ?? 1);
    if (pick < 0) return model;
  }
  return models[models.length - 1];
}

export class ResourcePackClient {
  private readonly blockstateCache = new Map<string, Promise<Record<string, unknown>>>();
  private readonly modelCache = new Map<string, Promise<Record<string, unknown>>>();
  private readonly resolvedModelCache = new Map<string, Promise<ResolvedModel>>();

  constructor(private readonly apiBase: string) {}

  async fetchBlockstate(namespace: string, block: string): Promise<Record<string, unknown>> {
    const key = `${namespace}:${block}`;
    let pending = this.blockstateCache.get(key);
    if (!pending) {
      pending = (async () => {
        const response = await fetch(`${this.apiBase}/assets/raw/${encodeURIComponent(namespace)}/blockstate/${block}`);
        if (!response.ok) throw new Error(`blockstate ${namespace}:${block} unavailable`);
        return response.json() as Promise<Record<string, unknown>>;
      })();
      this.blockstateCache.set(key, pending);
      pending.catch(() => this.blockstateCache.delete(key));
    }
    return pending;
  }

  async fetchModel(resource: string, fallbackNamespace = "minecraft"): Promise<Record<string, unknown>> {
    let [namespace, path] = splitResource(resource, fallbackNamespace);
    if (path.startsWith("block/")) path = path.slice(6);
    const key = `${namespace}:${path}`;
    let pending = this.modelCache.get(key);
    if (!pending) {
      pending = (async () => {
        const response = await fetch(`${this.apiBase}/assets/raw/${encodeURIComponent(namespace)}/model/${path}`);
        if (!response.ok) throw new Error(`model ${namespace}:${path} unavailable`);
        return response.json() as Promise<Record<string, unknown>>;
      })();
      this.modelCache.set(key, pending);
      pending.catch(() => this.modelCache.delete(key));
    }
    return pending;
  }

  textureUrl(resource: string, fallbackNamespace = "minecraft"): string {
    let [namespace, path] = splitResource(resource, fallbackNamespace);
    if (path.startsWith("textures/")) path = path.slice(9);
    return `${this.apiBase}/assets/raw/${encodeURIComponent(namespace)}/texture/${path}`;
  }

  async selectModels(entry: PaletteEntry, coordinate: { x: number; y: number; z: number }): Promise<ModelRef[]> {
    const { properties } = parseState(entry.canonical_state);
    const blockstate = await this.fetchBlockstate(entry.namespace, entry.block_name);
    const selected: ModelRef[] = [];
    const variants = blockstate.variants;
    if (variants && typeof variants === "object" && !Array.isArray(variants)) {
      for (const [selector, raw] of Object.entries(variants as Record<string, unknown>)) {
        if (!selectorMatches(selector, properties)) continue;
        const models = (Array.isArray(raw) ? raw : [raw]).filter((item): item is ModelRef => typeof item === "object" && item !== null && "model" in item);
        if (models.length) selected.push(weightedModel(models, coordinate.x, coordinate.y, coordinate.z, selector));
        break;
      }
    }
    if (Array.isArray(blockstate.multipart)) {
      for (const rawPart of blockstate.multipart) {
        if (typeof rawPart !== "object" || rawPart === null) continue;
        const part = rawPart as Record<string, unknown>;
        if (!multipartMatches(part.when, properties)) continue;
        const models = (Array.isArray(part.apply) ? part.apply : [part.apply]).filter((item): item is ModelRef => typeof item === "object" && item !== null && "model" in item);
        if (models.length) selected.push(weightedModel(models, coordinate.x, coordinate.y, coordinate.z, String(selected.length)));
      }
    }
    return selected;
  }

  async resolveModel(resource: string, maxDepth = 64): Promise<ResolvedModel> {
    const key = `${resource}|${maxDepth}`;
    let pending = this.resolvedModelCache.get(key);
    if (!pending) {
      pending = this.resolveModelUncached(resource, maxDepth);
      this.resolvedModelCache.set(key, pending);
      pending.catch(() => this.resolvedModelCache.delete(key));
    }
    return pending;
  }

  private async resolveModelUncached(resource: string, maxDepth = 64): Promise<ResolvedModel> {
    const chain: Record<string, unknown>[] = [];
    const seen = new Set<string>();
    let current = resource;
    let namespace = splitResource(resource)[0];
    for (let depth = 0; depth < maxDepth; depth += 1) {
      if (seen.has(current)) throw new Error(`model parent cycle at ${current}`);
      seen.add(current);
      const model = await this.fetchModel(current, namespace);
      chain.push(model);
      const parent = model.parent;
      if (typeof parent !== "string") break;
      namespace = splitResource(parent, namespace)[0];
      current = parent;
    }
    const textures: Record<string, string> = {};
    let elements: ModelElement[] = [];
    let ambientOcclusion = true;
    for (const model of chain.reverse()) {
      if (typeof model.ambientocclusion === "boolean") ambientOcclusion = model.ambientocclusion;
      if (model.textures && typeof model.textures === "object" && !Array.isArray(model.textures)) {
        Object.assign(textures, model.textures);
      }
      if (Array.isArray(model.elements)) elements = model.elements as ModelElement[];
    }
    return { elements, textures, ambientOcclusion };
  }

  resolveTexture(textures: Record<string, string>, raw: string): string {
    const seen = new Set<string>();
    let current = raw;
    while (current.startsWith("#")) {
      const key = current.slice(1);
      if (seen.has(key)) throw new Error(`texture cycle at #${key}`);
      seen.add(key);
      current = textures[key];
      if (!current) throw new Error(`missing texture variable #${key}`);
    }
    return current;
  }
}
