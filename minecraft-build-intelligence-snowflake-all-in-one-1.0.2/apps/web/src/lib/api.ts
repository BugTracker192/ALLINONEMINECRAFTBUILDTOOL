import type { BlockPage, BuildSummary, JobResponse, PaletteEntry } from "@mbi/protocol";

export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(JSON.stringify(payload));
  }
  return response.json() as Promise<T>;
}

export async function uploadBuild(file: File): Promise<{ uploadId: string; filename: string }> {
  const body = new FormData();
  body.append("file", file);
  return request("/uploads", { method: "POST", body });
}

export async function beginImport(uploadId: string, filename: string): Promise<JobResponse> {
  return request("/builds/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ uploadId, filename }),
  });
}

export const getJob = (jobId: string) => request<JobResponse>(`/jobs/${jobId}`);
export const getBuild = (buildId: string) => request<BuildSummary>(`/builds/${buildId}`);
export const getPalette = (buildId: string) => request<PaletteEntry[]>(`/builds/${buildId}/palette`);
export const getBlocks = (buildId: string, cursor = 0, limit = 250000) => request<BlockPage>(`/builds/${buildId}/blocks?cursor=${cursor}&limit=${limit}`);
export const getAnalysis = (buildId: string) => request<Record<string, unknown>>(`/builds/${buildId}/analysis`);
export const getBlock = (buildId: string, x: number, y: number, z: number) => request<Record<string, unknown>>(`/builds/${buildId}/blocks/${x}/${y}/${z}`);

export async function fetchAllBlocks(buildId: string, onPage?: (blocks: BlockPage["items"], loaded: number, total: number) => void): Promise<BlockPage["items"]> {
  const result: BlockPage["items"] = [];
  let cursor: number | null = 0;
  while (cursor != null) {
    const page = await getBlocks(buildId, cursor);
    result.push(...page.items);
    onPage?.(page.items, result.length, page.total);
    cursor = page.nextCursor;
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  }
  return result;
}
