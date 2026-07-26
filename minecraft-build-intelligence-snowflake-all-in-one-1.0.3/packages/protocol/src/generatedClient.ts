// Generated from FastAPI OpenAPI. Do not edit manually.
export const API_PATHS = [
  "/api/v1/admin/retention/run",
  "/api/v1/ai-runs/{run_id}",
  "/api/v1/ai-runs/{run_id}/cancel",
  "/api/v1/ai-runs/{run_id}/events",
  "/api/v1/ai-runs/{run_id}/patches/{patch_id}/approve",
  "/api/v1/ai-runs/{run_id}/patches/{patch_id}/reject",
  "/api/v1/assets/raw/{namespace}/{kind}/{resource}",
  "/api/v1/builds/generate",
  "/api/v1/builds/import",
  "/api/v1/builds/{build_id}",
  "/api/v1/builds/{build_id}/ai-runs",
  "/api/v1/builds/{build_id}/analysis",
  "/api/v1/builds/{build_id}/blocks",
  "/api/v1/builds/{build_id}/blocks/query",
  "/api/v1/builds/{build_id}/blocks/{x}/{y}/{z}",
  "/api/v1/builds/{build_id}/branches/{name}",
  "/api/v1/builds/{build_id}/checkpoints/{name}",
  "/api/v1/builds/{build_id}/chunks",
  "/api/v1/builds/{build_id}/components",
  "/api/v1/builds/{build_id}/exports",
  "/api/v1/builds/{build_id}/merge/{source_version_id}",
  "/api/v1/builds/{build_id}/palette",
  "/api/v1/builds/{build_id}/patches",
  "/api/v1/builds/{build_id}/presentation-snapshots",
  "/api/v1/builds/{build_id}/regions",
  "/api/v1/builds/{build_id}/rooms",
  "/api/v1/builds/{build_id}/snapshots",
  "/api/v1/builds/{build_id}/undo",
  "/api/v1/builds/{build_id}/versions",
  "/api/v1/builds/{build_id}/versions/{version_id}",
  "/api/v1/exports/{export_id}",
  "/api/v1/jobs/{job_id}",
  "/api/v1/jobs/{job_id}/cancel",
  "/api/v1/patches/{patch_id}/commit",
  "/api/v1/patches/{patch_id}/preview",
  "/api/v1/patches/{patch_id}/rollback",
  "/api/v1/patches/{patch_id}/validate",
  "/api/v1/snapshots/{snapshot_id}/artifacts/{artifact}",
  "/api/v1/snapshots/{snapshot_id}/image",
  "/api/v1/snapshots/{snapshot_id}/manifest",
  "/api/v1/uploads",
  "/healthz",
  "/readyz"
] as const;
export type ApiPath = typeof API_PATHS[number];
export class MbiApiClient {
  constructor(readonly baseUrl = '') {}
  async request<T>(path: ApiPath | string, init: RequestInit = {}): Promise<T> {
    const response = await fetch(this.baseUrl + path, init);
    if (!response.ok) throw new Error(`MBI API ${response.status}: ${await response.text()}`);
    return response.json() as Promise<T>;
  }
}
