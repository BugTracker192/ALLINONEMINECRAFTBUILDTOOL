import type { CanonicalBlock, PaletteEntry } from "@mbi/protocol";
import {
  BufferGeometry,
  Color,
  DoubleSide,
  Euler,
  Float32BufferAttribute,
  Group,
  InstancedMesh,
  Intersection,
  LinearFilter,
  Matrix4,
  Mesh,
  MeshLambertMaterial,
  NearestFilter,
  Quaternion,
  RepeatWrapping,
  Texture,
  TextureLoader,
  Vector3,
} from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { fluidSurface, type FluidCell, type FluidSurface } from "./fluid.js";
import { greedyMesh, type GreedyQuad } from "./greedyMesher.js";
import { ResourcePackClient, type ModelElement, type ModelFace, type ModelRef, type ResolvedModel } from "./resourcePack.js";
import { specialRendererFor } from "./specialRenderers.js";
import { stateTintIndex } from "./tint.js";

const FACE_ORDER = ["east", "west", "up", "down", "south", "north"] as const;
type FaceName = (typeof FACE_ORDER)[number];

export interface PickingRecord {
  position: { x: number; y: number; z: number };
  palette: PaletteEntry;
}

interface CompiledElement {
  geometry: BufferGeometry;
  groups: Array<{ start: number; count: number; materialIndex: number }>;
}

interface ModelGroup {
  entry: PaletteEntry;
  ref: ModelRef;
  instances: CanonicalBlock[];
}

interface GreedyPickingRecord {
  palette: PaletteEntry;
  occupied: Set<string>;
}

interface FluidInstance {
  block: CanonicalBlock;
  entry: PaletteEntry;
  cell: FluidCell;
}

function positionKey(position: { x: number; y: number; z: number }): string {
  return `${position.x},${position.y},${position.z}`;
}

function parseProperties(state: string): Record<string, string> {
  const start = state.indexOf("[");
  if (start < 0 || !state.endsWith("]")) return {};
  return Object.fromEntries(
    state
      .slice(start + 1, -1)
      .split(",")
      .filter(Boolean)
      .map((pair) => pair.split("=", 2) as [string, string]),
  );
}

function fluidCell(entry: PaletteEntry): FluidCell | null {
  const base = entry.canonical_state.split("[", 1)[0];
  const properties = parseProperties(entry.canonical_state);
  if (base === "minecraft:water" || base === "minecraft:lava") {
    const level = Math.max(0, Math.min(15, Number(properties.level ?? 0)));
    return { kind: base.endsWith("water") ? "water" : "lava", level: level & 7, falling: level >= 8 };
  }
  if (properties.waterlogged === "true") return { kind: "water", level: 0, falling: false };
  return null;
}

function specialElements(state: string): ModelElement[] | null {
  const base = state.split("[", 1)[0];
  const cube = (from: [number, number, number], to: [number, number, number]): ModelElement => ({
    from,
    to,
    faces: Object.fromEntries(FACE_ORDER.map((face) => [face, { texture: "" }])) as ModelElement["faces"],
  });
  if (base.endsWith("_bed")) return [cube([0, 0, 0], [16, 9, 16])];
  if (base.includes("chest")) return [cube([1, 0, 1], [15, 14, 15]), cube([1, 14, 2], [15, 16, 14])];
  if (base.endsWith("_hanging_sign") || base.endsWith("_wall_hanging_sign")) return [cube([1, 3, 7], [15, 13, 9])];
  if (base.endsWith("_sign") || base.endsWith("_wall_sign")) return [cube([1, 8, 7], [15, 16, 9]), cube([7, 0, 7], [9, 8, 9])];
  if (base.endsWith("_head") || base.endsWith("_skull")) return [cube([4, 0, 4], [12, 8, 12])];
  if (base.endsWith("shulker_box")) return [cube([0, 0, 0], [16, 8, 16]), cube([0, 8, 0], [16, 16, 16])];
  if (base === "minecraft:decorated_pot") return [cube([3, 0, 3], [13, 16, 13])];
  if (base.endsWith("_banner") || base.endsWith("_wall_banner")) return [cube([1, 2, 7], [15, 16, 9])];
  return null;
}

export class BlockScene {
  readonly root = new Group();
  private readonly textureLoader = new TextureLoader();
  private readonly pickRecords = new WeakMap<InstancedMesh, PickingRecord[]>();
  private readonly greedyPickRecords = new WeakMap<Mesh, GreedyPickingRecord>();
  private disposed = false;

  constructor(private readonly assets: ResourcePackClient) {}

  async build(blocks: CanonicalBlock[], palette: PaletteEntry[]): Promise<void> {
    this.disposeChildren();
    this.disposed = false;
    const paletteById = new Map(palette.map((entry) => [entry.palette_id, entry]));
    const modelGroups = new Map<string, ModelGroup>();
    const fallbackGroups = new Map<number, CanonicalBlock[]>();
    const fluids: FluidInstance[] = [];

    // Weighted blockstate variants are selected independently per coordinate, then
    // instances with the same exact resolved reference are grouped for draw-call economy.
    for (const block of blocks) {
      const entry = paletteById.get(block.paletteId);
      if (!entry || entry.is_air_like) continue;
      const fluid = fluidCell(entry);
      if (fluid) fluids.push({ block, entry, cell: fluid });
      const base = entry.canonical_state.split("[", 1)[0];
      if (base === "minecraft:water" || base === "minecraft:lava") continue;
      try {
        const refs = await this.assets.selectModels(entry, block.position);
        if (!refs.length) throw new Error("no selected model");
        for (const ref of refs) {
          const key = [entry.palette_id, ref.model, ref.x ?? 0, ref.y ?? 0, ref.uvlock ? 1 : 0].join("|");
          const group = modelGroups.get(key) ?? { entry, ref, instances: [] };
          group.instances.push(block);
          modelGroups.set(key, group);
        }
      } catch {
        const list = fallbackGroups.get(entry.palette_id) ?? [];
        list.push(block);
        fallbackGroups.set(entry.palette_id, list);
      }
    }

    for (const group of modelGroups.values()) {
      try {
        const model = await this.assets.resolveModel(group.ref.model);
        if (!model.elements.length) throw new Error("model has no static elements");
        if (this.canGreedyMesh(group.entry, group.ref, model, group.instances)) {
          await this.addGreedyCubeInstances(group.entry, group.instances, model);
        } else {
          await this.addModelInstances(group.entry, group.instances, group.ref, model);
        }
      } catch {
        const list = fallbackGroups.get(group.entry.palette_id) ?? [];
        list.push(...group.instances);
        fallbackGroups.set(group.entry.palette_id, list);
      }
    }
    for (const [paletteId, instances] of fallbackGroups) {
      const entry = paletteById.get(paletteId);
      if (entry) this.addFallbackInstances(entry, instances, specialElements(entry.canonical_state) ?? undefined);
    }
    if (fluids.length) await this.addFluids(fluids);
  }

  private canGreedyMesh(entry: PaletteEntry, ref: ModelRef, model: ResolvedModel, instances: CanonicalBlock[]): boolean {
    if (entry.render_category !== "opaque" || (ref.x ?? 0) !== 0 || (ref.y ?? 0) !== 0 || ref.uvlock) return false;
    if (model.elements.length !== 1) return false;
    const element = model.elements[0];
    if (element.rotation || element.from.some((value) => value !== 0) || element.to.some((value) => value !== 16)) return false;
    if (!FACE_ORDER.every((face) => Boolean(element.faces?.[face]))) return false;
    const xs = instances.map((item) => item.position.x);
    const ys = instances.map((item) => item.position.y);
    const zs = instances.map((item) => item.position.z);
    const volume = (Math.max(...xs) - Math.min(...xs) + 1) * (Math.max(...ys) - Math.min(...ys) + 1) * (Math.max(...zs) - Math.min(...zs) + 1);
    return volume <= 4_000_000 && instances.length / volume >= 0.08;
  }

  private async cubeFaceMaterials(entry: PaletteEntry, model: ResolvedModel): Promise<{ materials: MeshLambertMaterial[]; indices: Record<FaceName, number> }> {
    const materials: MeshLambertMaterial[] = [];
    const indices = {} as Record<FaceName, number>;
    const element = model.elements[0];
    for (const faceName of FACE_ORDER) {
      const face = element.faces[faceName]!;
      const texture = await this.loadTexture(this.assets.textureUrl(this.resolveFaceTexture(model, face)));
      const tint = stateTintIndex(entry.canonical_state, face.tintindex ?? -1);
      indices[faceName] = materials.length;
      materials.push(new MeshLambertMaterial({ map: texture, color: tint == null ? 0xffffff : tint }));
    }
    return { materials, indices };
  }

  private greedyGeometry(quads: GreedyQuad[], origin: [number, number, number], materialIndices: Record<FaceName, number>): BufferGeometry {
    const positions: number[] = [];
    const normals: number[] = [];
    const uvs: number[] = [];
    const indices: number[] = [];
    const groups: Array<{ start: number; count: number; materialIndex: number }> = [];
    const faceName = (axis: 0 | 1 | 2, sign: -1 | 1): FaceName =>
      axis === 0 ? (sign > 0 ? "east" : "west") : axis === 1 ? (sign > 0 ? "up" : "down") : sign > 0 ? "south" : "north";
    for (const quad of quads) {
      const u = ((quad.axis + 1) % 3) as 0 | 1 | 2;
      const v = ((quad.axis + 2) % 3) as 0 | 1 | 2;
      const base = [quad.origin[0] + origin[0], quad.origin[1] + origin[1], quad.origin[2] + origin[2]];
      const corners = [base.slice(), base.slice(), base.slice(), base.slice()];
      corners[1][u] += quad.size[0];
      corners[2][u] += quad.size[0];
      corners[2][v] += quad.size[1];
      corners[3][v] += quad.size[1];
      const vertexOffset = positions.length / 3;
      corners.forEach((corner) => positions.push(...corner));
      for (let i = 0; i < 4; i += 1) {
        const normal = [0, 0, 0];
        normal[quad.axis] = quad.sign;
        normals.push(...normal);
      }
      uvs.push(0, 0, quad.size[0], 0, quad.size[0], quad.size[1], 0, quad.size[1]);
      const indexStart = indices.length;
      if (quad.sign > 0) indices.push(vertexOffset, vertexOffset + 1, vertexOffset + 2, vertexOffset, vertexOffset + 2, vertexOffset + 3);
      else indices.push(vertexOffset, vertexOffset + 3, vertexOffset + 2, vertexOffset, vertexOffset + 2, vertexOffset + 1);
      groups.push({ start: indexStart, count: 6, materialIndex: materialIndices[faceName(quad.axis, quad.sign)] });
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new Float32BufferAttribute(normals, 3));
    geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    groups.forEach((group) => geometry.addGroup(group.start, group.count, group.materialIndex));
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    return geometry;
  }

  private async addGreedyCubeInstances(entry: PaletteEntry, instances: CanonicalBlock[], model: ResolvedModel): Promise<void> {
    const minX = Math.min(...instances.map((item) => item.position.x));
    const minY = Math.min(...instances.map((item) => item.position.y));
    const minZ = Math.min(...instances.map((item) => item.position.z));
    const maxX = Math.max(...instances.map((item) => item.position.x));
    const maxY = Math.max(...instances.map((item) => item.position.y));
    const maxZ = Math.max(...instances.map((item) => item.position.z));
    const occupied = new Set(instances.map((item) => positionKey(item.position)));
    const quads = greedyMesh({
      size: [maxX - minX + 1, maxY - minY + 1, maxZ - minZ + 1],
      get: (x, y, z) => occupied.has(`${x + minX},${y + minY},${z + minZ}`) ? 1 : 0,
    });
    const { materials, indices } = await this.cubeFaceMaterials(entry, model);
    const mesh = new Mesh(this.greedyGeometry(quads, [minX, minY, minZ], indices), materials);
    mesh.name = entry.canonical_state;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.renderSupport = "greedy_exact_cube";
    mesh.userData.quadCount = quads.length;
    this.greedyPickRecords.set(mesh, { palette: entry, occupied });
    this.root.add(mesh);
  }

  private async addModelInstances(entry: PaletteEntry, instances: CanonicalBlock[], ref: ModelRef, model: ResolvedModel): Promise<void> {
    const { geometry, materials } = await this.compileModel(model, entry, ref);
    const mesh = new InstancedMesh(geometry, materials, instances.length);
    mesh.name = entry.canonical_state;
    mesh.castShadow = entry.render_category === "opaque";
    mesh.receiveShadow = true;
    mesh.renderOrder = entry.render_category === "translucent" ? 10 : 0;
    const special = specialRendererFor(entry.canonical_state);
    mesh.userData.renderSupport = special?.tier ?? "resource_model";
    mesh.userData.renderNotes = special?.notes ?? "Resolved from blockstate and block-model resources.";
    const records: PickingRecord[] = [];
    const rotation = new Quaternion().setFromEuler(
      new Euler(((ref.x ?? 0) * Math.PI) / 180, ((ref.y ?? 0) * Math.PI) / 180, 0, "XYZ"),
    );
    const rotationMatrix = new Matrix4().makeRotationFromQuaternion(rotation);
    const matrix = new Matrix4();
    const beforePivot = new Matrix4().makeTranslation(-0.5, -0.5, -0.5);
    const afterPivot = new Matrix4().makeTranslation(0.5, 0.5, 0.5);
    for (let index = 0; index < instances.length; index += 1) {
      const block = instances[index];
      matrix
        .makeTranslation(block.position.x, block.position.y, block.position.z)
        .multiply(afterPivot)
        .multiply(rotationMatrix)
        .multiply(beforePivot);
      mesh.setMatrixAt(index, matrix);
      records.push({ position: block.position, palette: entry });
    }
    mesh.instanceMatrix.needsUpdate = true;
    this.pickRecords.set(mesh, records);
    this.root.add(mesh);
  }

  private async compileModel(model: ResolvedModel, entry: PaletteEntry, ref: ModelRef): Promise<{ geometry: BufferGeometry; materials: MeshLambertMaterial[] }> {
    const materials: MeshLambertMaterial[] = [];
    const materialIndex = new Map<string, number>();
    const compiled: CompiledElement[] = [];
    for (const element of model.elements) {
      const faceMaterial = new Map<FaceName, number>();
      for (const faceName of FACE_ORDER) {
        const definition = element.faces?.[faceName];
        if (!definition) continue;
        const textureResource = this.resolveFaceTexture(model, definition);
        const tint = stateTintIndex(entry.canonical_state, definition.tintindex ?? -1);
        const key = `${textureResource}|${tint ?? "none"}|${entry.render_category}`;
        let index = materialIndex.get(key);
        if (index == null) {
          const texture = await this.loadTexture(this.assets.textureUrl(textureResource));
          index = materials.length;
          materialIndex.set(key, index);
          const translucent = entry.render_category === "translucent";
          const cutout = entry.render_category === "cutout";
          materials.push(
            new MeshLambertMaterial({
              map: texture,
              color: tint == null ? 0xffffff : tint,
              transparent: translucent,
              opacity: translucent ? 0.78 : 1,
              alphaTest: cutout ? 0.1 : 0,
              depthWrite: !translucent,
              side: DoubleSide,
            }),
          );
        }
        faceMaterial.set(faceName, index);
      }
      compiled.push(this.elementGeometry(element, faceMaterial, ref));
    }
    const geometries = compiled.map((item) => item.geometry);
    const merged = mergeGeometries(geometries, false);
    if (!merged) throw new Error("model geometry merge failed");
    merged.clearGroups();
    let indexOffset = 0;
    for (const item of compiled) {
      for (const group of item.groups) merged.addGroup(indexOffset + group.start, group.count, group.materialIndex);
      indexOffset += item.geometry.index?.count ?? item.geometry.getAttribute("position").count;
    }
    geometries.forEach((geometry) => geometry.dispose());
    return { geometry: merged, materials };
  }

  private resolveFaceTexture(model: ResolvedModel, face: ModelFace): string {
    try {
      return this.assets.resolveTexture(model.textures, face.texture);
    } catch {
      return "minecraft:block/missingno";
    }
  }

  private elementGeometry(element: ModelElement, faceMaterials: Map<FaceName, number>, ref?: ModelRef): CompiledElement {
    const x0 = element.from[0] / 16;
    const y0 = element.from[1] / 16;
    const z0 = element.from[2] / 16;
    const x1 = element.to[0] / 16;
    const y1 = element.to[1] / 16;
    const z1 = element.to[2] / 16;
    const quads: Record<FaceName, { vertices: number[][]; normal: number[] }> = {
      east: { vertices: [[x1, y0, z0], [x1, y0, z1], [x1, y1, z1], [x1, y1, z0]], normal: [1, 0, 0] },
      west: { vertices: [[x0, y0, z1], [x0, y0, z0], [x0, y1, z0], [x0, y1, z1]], normal: [-1, 0, 0] },
      up: { vertices: [[x0, y1, z0], [x1, y1, z0], [x1, y1, z1], [x0, y1, z1]], normal: [0, 1, 0] },
      down: { vertices: [[x0, y0, z1], [x1, y0, z1], [x1, y0, z0], [x0, y0, z0]], normal: [0, -1, 0] },
      south: { vertices: [[x1, y0, z1], [x0, y0, z1], [x0, y1, z1], [x1, y1, z1]], normal: [0, 0, 1] },
      north: { vertices: [[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0]], normal: [0, 0, -1] },
    };
    const positions: number[] = [];
    const normals: number[] = [];
    const uvs: number[] = [];
    const indices: number[] = [];
    const groups: CompiledElement["groups"] = [];
    let vertexOffset = 0;
    let indexOffset = 0;
    for (const faceName of FACE_ORDER) {
      const face = element.faces?.[faceName];
      const material = faceMaterials.get(faceName);
      if (!face || material == null) continue;
      const quad = quads[faceName];
      for (const vertex of quad.vertices) positions.push(...vertex);
      for (let i = 0; i < 4; i += 1) normals.push(...quad.normal);
      uvs.push(...this.faceUvs(face, faceName, ref));
      indices.push(vertexOffset, vertexOffset + 1, vertexOffset + 2, vertexOffset, vertexOffset + 2, vertexOffset + 3);
      groups.push({ start: indexOffset, count: 6, materialIndex: material });
      vertexOffset += 4;
      indexOffset += 6;
    }
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.setAttribute("normal", new Float32BufferAttribute(normals, 3));
    geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    if (element.rotation) {
      const origin = new Vector3(...element.rotation.origin).multiplyScalar(1 / 16);
      const radians = (element.rotation.angle * Math.PI) / 180;
      const rotation = new Matrix4();
      if (element.rotation.axis === "x") rotation.makeRotationX(radians);
      if (element.rotation.axis === "y") rotation.makeRotationY(radians);
      if (element.rotation.axis === "z") rotation.makeRotationZ(radians);
      let transform = new Matrix4().makeTranslation(-origin.x, -origin.y, -origin.z);
      if (element.rotation.rescale) {
        const factor = 1 / Math.max(0.001, Math.cos(Math.abs(radians)));
        const scale =
          element.rotation.axis === "x"
            ? new Matrix4().makeScale(1, factor, factor)
            : element.rotation.axis === "y"
              ? new Matrix4().makeScale(factor, 1, factor)
              : new Matrix4().makeScale(factor, factor, 1);
        transform = scale.multiply(transform);
      }
      transform = rotation.multiply(transform);
      transform = new Matrix4().makeTranslation(origin.x, origin.y, origin.z).multiply(transform);
      geometry.applyMatrix4(transform);
    }
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    return { geometry, groups };
  }

  private faceUvs(face: ModelFace, faceName: FaceName, ref?: ModelRef): number[] {
    const [u1, v1, u2, v2] = face.uv ?? [0, 0, 16, 16];
    let corners: Array<[number, number]> = [
      [u1 / 16, 1 - v2 / 16],
      [u2 / 16, 1 - v2 / 16],
      [u2 / 16, 1 - v1 / 16],
      [u1 / 16, 1 - v1 / 16],
    ];
    let turns = ((face.rotation ?? 0) / 90) % 4;
    if (ref?.uvlock) {
      // Preserve approximate world-space texture orientation under blockstate rotation.
      const modelTurns = Math.round((ref.y ?? 0) / 90) + (faceName === "up" || faceName === "down" ? Math.round((ref.x ?? 0) / 90) : 0);
      turns = (turns - modelTurns + 8) % 4;
    }
    for (let i = 0; i < turns; i += 1) corners = [corners[3], corners[0], corners[1], corners[2]];
    return corners.flat();
  }

  private async loadTexture(url: string): Promise<Texture> {
    const texture = await this.textureLoader.loadAsync(url);
    texture.magFilter = NearestFilter;
    texture.minFilter = LinearFilter;
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.colorSpace = "srgb";
    texture.flipY = false;
    return texture;
  }

  private fluidGeometry(surface: FluidSurface): BufferGeometry {
    const positions: number[] = [];
    const uvs: number[] = [];
    const indices: number[] = [];
    const addQuad = (vertices: number[][], textureUvs: number[][]) => {
      const offset = positions.length / 3;
      vertices.forEach((vertex) => positions.push(...vertex));
      textureUvs.forEach((uv) => uvs.push(...uv));
      indices.push(offset, offset + 1, offset + 2, offset, offset + 2, offset + 3);
    };
    const e = 0.001;
    addQuad(
      [[e, surface.nw, e], [1 - e, surface.ne, e], [1 - e, surface.se, 1 - e], [e, surface.sw, 1 - e]],
      [[0, 0], [1, 0], [1, 1], [0, 1]],
    );
    if (surface.sideMask & 1) addQuad([[e, 0, e], [1 - e, 0, e], [1 - e, surface.ne, e], [e, surface.nw, e]], [[0, 1], [1, 1], [1, 0], [0, 0]]);
    if (surface.sideMask & 2) addQuad([[1 - e, 0, e], [1 - e, 0, 1 - e], [1 - e, surface.se, 1 - e], [1 - e, surface.ne, e]], [[0, 1], [1, 1], [1, 0], [0, 0]]);
    if (surface.sideMask & 4) addQuad([[1 - e, 0, 1 - e], [e, 0, 1 - e], [e, surface.sw, 1 - e], [1 - e, surface.se, 1 - e]], [[0, 1], [1, 1], [1, 0], [0, 0]]);
    if (surface.sideMask & 8) addQuad([[e, 0, 1 - e], [e, 0, e], [e, surface.nw, e], [e, surface.sw, 1 - e]], [[0, 1], [1, 1], [1, 0], [0, 0]]);
    const geometry = new BufferGeometry();
    geometry.setAttribute("position", new Float32BufferAttribute(positions, 3));
    geometry.setAttribute("uv", new Float32BufferAttribute(uvs, 2));
    geometry.setIndex(indices);
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    geometry.computeBoundingSphere();
    return geometry;
  }

  private async addFluids(instances: FluidInstance[]): Promise<void> {
    const byPosition = new Map(instances.map((item) => [positionKey(item.block.position), item]));
    const groups = new Map<string, { surface: FluidSurface; kind: "water" | "lava"; items: FluidInstance[] }>();
    const offsets = [[0, 0, -1], [1, 0, -1], [1, 0, 0], [1, 0, 1], [0, 0, 1], [-1, 0, 1], [-1, 0, 0], [-1, 0, -1]] as const;
    for (const item of instances) {
      const p = item.block.position;
      const neighbors = offsets.map(([x, y, z]) => byPosition.get(`${p.x + x},${p.y + y},${p.z + z}`)?.cell ?? null);
      const surface = fluidSurface(item.cell, neighbors);
      const signature = `${item.cell.kind}|${surface.nw.toFixed(4)}|${surface.ne.toFixed(4)}|${surface.se.toFixed(4)}|${surface.sw.toFixed(4)}|${surface.sideMask}`;
      const group = groups.get(signature) ?? { surface, kind: item.cell.kind, items: [] };
      group.items.push(item);
      groups.set(signature, group);
    }
    for (const group of groups.values()) {
      const geometry = this.fluidGeometry(group.surface);
      const texture = await this.loadTexture(this.assets.textureUrl(`minecraft:block/${group.kind}_still`));
      const material = new MeshLambertMaterial({
        map: texture,
        color: group.kind === "water" ? 0x3f76e4 : 0xffffff,
        transparent: group.kind === "water",
        opacity: group.kind === "water" ? 0.72 : 1,
        depthWrite: group.kind !== "water",
        emissive: group.kind === "lava" ? new Color(0x8a3f00) : new Color(0x000000),
        emissiveIntensity: group.kind === "lava" ? 0.55 : 0,
        side: DoubleSide,
      });
      const mesh = new InstancedMesh(geometry, material, group.items.length);
      mesh.renderOrder = group.kind === "water" ? 20 : 2;
      mesh.name = `minecraft:${group.kind}`;
      mesh.userData.renderSupport = "exact_fluid_static";
      const matrix = new Matrix4();
      const records: PickingRecord[] = [];
      group.items.forEach((item, index) => {
        matrix.makeTranslation(item.block.position.x, item.block.position.y, item.block.position.z);
        mesh.setMatrixAt(index, matrix);
        records.push({ position: item.block.position, palette: item.entry });
      });
      mesh.instanceMatrix.needsUpdate = true;
      this.pickRecords.set(mesh, records);
      this.root.add(mesh);
    }
  }

  private addFallbackInstances(entry: PaletteEntry, instances: CanonicalBlock[], elements?: ModelElement[]): void {
    const fallbackElements = elements ?? [{
      from: [0, 0, 0],
      to: [16, 16, 16],
      faces: Object.fromEntries(FACE_ORDER.map((face) => [face, { texture: "" }])) as ModelElement["faces"],
    } satisfies ModelElement];
    const parts = fallbackElements.map((element) => this.elementGeometry(element, new Map(FACE_ORDER.map((face) => [face, 0]))));
    const geometry = mergeGeometries(parts.map((item) => item.geometry), false) ?? parts[0].geometry;
    parts.forEach((item) => item.geometry !== geometry && item.geometry.dispose());
    let hash = 0;
    for (const char of entry.canonical_state) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    const special = specialRendererFor(entry.canonical_state);
    const material = new MeshLambertMaterial({ color: new Color((hash >>> 0) & 0xffffff), wireframe: entry.render_category === "unknown" && !special });
    const mesh = new InstancedMesh(geometry, material, instances.length);
    mesh.userData.renderSupport = special ? "static_approximation" : "placeholder";
    mesh.userData.renderNotes = special?.notes ?? "No resource-pack model could be resolved; visible placeholder retained.";
    const matrix = new Matrix4();
    const records: PickingRecord[] = [];
    instances.forEach((block, index) => {
      matrix.makeTranslation(block.position.x, block.position.y, block.position.z);
      mesh.setMatrixAt(index, matrix);
      records.push({ position: block.position, palette: entry });
    });
    mesh.instanceMatrix.needsUpdate = true;
    this.pickRecords.set(mesh, records);
    this.root.add(mesh);
  }

  pick(mesh: InstancedMesh, instanceId: number): PickingRecord | null {
    return this.pickRecords.get(mesh)?.[instanceId] ?? null;
  }

  pickIntersection(hit: Intersection): PickingRecord | null {
    if (hit.object instanceof InstancedMesh && hit.instanceId != null) return this.pick(hit.object, hit.instanceId);
    if (!(hit.object instanceof Mesh) || !hit.face) return null;
    const record = this.greedyPickRecords.get(hit.object);
    if (!record) return null;
    const normal = hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
    const inside = hit.point.clone().addScaledVector(normal, -0.001);
    const position = { x: Math.floor(inside.x), y: Math.floor(inside.y), z: Math.floor(inside.z) };
    return record.occupied.has(positionKey(position)) ? { position, palette: record.palette } : null;
  }

  private disposeChildren(): void {
    for (const child of [...this.root.children]) {
      if (child instanceof Mesh) {
        child.geometry.dispose();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        for (const material of materials) {
          const mapped = material as MeshLambertMaterial;
          mapped.map?.dispose();
          mapped.dispose();
        }
      }
      this.root.remove(child);
    }
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposeChildren();
    this.disposed = true;
  }
}
