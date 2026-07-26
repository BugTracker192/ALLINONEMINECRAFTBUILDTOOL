from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("MBI_OBJECT_STORE_ROOT", "/tmp/mbi-openapi")
from mbi_api.main import app  # noqa: E402

root = Path(__file__).parents[1]
schema = app.openapi()
target = root / "packages" / "protocol" / "openapi.json"
target.write_text(json.dumps(schema, sort_keys=True, indent=2), "utf-8")
paths = sorted(schema["paths"])
client = root / "packages" / "protocol" / "src" / "generatedClient.ts"
client.write_text(
    "// Generated from FastAPI OpenAPI. Do not edit manually.\n"
    "export const API_PATHS = " + json.dumps(paths, indent=2) + " as const;\n"
    "export type ApiPath = typeof API_PATHS[number];\n"
    "export class MbiApiClient {\n"
    "  constructor(readonly baseUrl = '') {}\n"
    "  async request<T>(path: ApiPath | string, init: RequestInit = {}): Promise<T> {\n"
    "    const response = await fetch(this.baseUrl + path, init);\n"
    "    if (!response.ok) throw new Error(`MBI API ${response.status}: ${await response.text()}`);\n"
    "    return response.json() as Promise<T>;\n"
    "  }\n"
    "}\n",
    "utf-8",
)
print(f"generated {target} and {client} ({len(paths)} paths)")
