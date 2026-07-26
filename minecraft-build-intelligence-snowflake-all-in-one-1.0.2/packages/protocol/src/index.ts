export interface IntVector3 { x: number; y: number; z: number }
export interface IntBoundingBox { min: IntVector3; max: IntVector3 }

export interface BuildSummary {
  schemaVersion: string;
  buildId: string;
  bounds: IntBoundingBox;
  origin: IntVector3;
  paletteSize: number;
  regionCount: number;
  nonAirCount: number;
  blockEntityCount: number;
  entityCount: number;
  contentHash: string;
  diagnostics: ImportDiagnostic[];
}

export interface ImportDiagnostic {
  code: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  details: Record<string, unknown>;
}

export interface PaletteEntry {
  palette_id: number;
  namespace: string;
  block_name: string;
  properties: Record<string, string>;
  canonical_state: string;
  is_air_like: boolean;
  is_fluid: boolean;
  render_category: "opaque" | "cutout" | "translucent" | "emissive" | "special" | "unknown";
  diagnostics: string[];
}

export interface CanonicalBlock {
  position: IntVector3;
  paletteId: number;
}

export interface BlockPage {
  coordinateSpace: "document";
  items: CanonicalBlock[];
  nextCursor: number | null;
  total: number;
}

export interface JobResponse {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  stage: string;
  progress: number;
  message: string;
  result: { buildId: string; summary: BuildSummary } | null;
  error: { code: string; message: string; details: Record<string, unknown> } | null;
}
export * from "./generatedClient.js";
