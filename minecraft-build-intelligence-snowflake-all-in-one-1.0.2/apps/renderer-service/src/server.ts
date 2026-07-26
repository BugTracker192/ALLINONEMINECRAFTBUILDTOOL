import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { chromium, type Browser } from "playwright";
import { z } from "zod";

const camera = z.enum(["front", "back", "left", "right", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"]);
const requestSchema = z.object({
  buildId: z.string().regex(/^build_[a-z0-9]+$/),
  versionId: z.string().regex(/^ver_[a-z0-9]+$/).optional(),
  camera: camera.default("isometric_se"),
  projection: z.enum(["orthographic", "perspective"]).default("orthographic"),
  width: z.number().int().min(128).max(4096).default(1536),
  height: z.number().int().min(128).max(4096).default(1536),
  transparent: z.boolean().default(false),
  quality: z.enum(["draft", "analysis", "presentation"]).default("analysis"),
});

type RenderRequest = z.infer<typeof requestSchema>;
const port = Number(process.env.PORT ?? 8090);
const webBase = new URL(process.env.MBI_WEB_BASE_URL ?? "http://web");
const outputRoot = process.env.MBI_RENDER_OUTPUT_ROOT ?? "/data/snapshots";
const timeoutMs = Number(process.env.MBI_RENDER_TIMEOUT_MS ?? 120_000);
const maxConcurrency = Math.max(1, Number(process.env.MBI_RENDER_CONCURRENCY ?? 2));
const rendererVersion = process.env.MBI_RENDERER_VERSION ?? "1.0.0";
let browser: Browser | undefined;
let active = 0;
const waiters: Array<() => void> = [];

async function acquire(): Promise<() => void> {
  if (active >= maxConcurrency) await new Promise<void>((resolve) => waiters.push(resolve));
  active += 1;
  return () => {
    active -= 1;
    waiters.shift()?.();
  };
}

async function getBrowser(): Promise<Browser> {
  if (!browser || !browser.isConnected()) {
    browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-background-networking"] });
  }
  return browser;
}

async function readBody(request: import("node:http").IncomingMessage): Promise<unknown> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const buffer = Buffer.from(chunk);
    size += buffer.length;
    if (size > 1_000_000) throw new Error("request body too large");
    chunks.push(buffer);
  }
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

async function atomicWrite(path: string, data: Buffer | string): Promise<void> {
  await mkdir(dirname(path), { recursive: true });
  const temporary = `${path}.writing-${process.pid}`;
  await writeFile(temporary, data);
  await rename(temporary, path);
}

async function render(payload: RenderRequest): Promise<Record<string, unknown>> {
  const release = await acquire();
  const instance = await getBrowser();
  const context = await instance.newContext({
    viewport: { width: payload.width, height: payload.height },
    deviceScaleFactor: 1,
    reducedMotion: "reduce",
    colorScheme: "dark",
  });
  try {
    const page = await context.newPage();
    await page.route("**/*", async (route) => {
      const target = new URL(route.request().url());
      if (target.origin === webBase.origin || target.protocol === "data:" || target.protocol === "blob:") await route.continue();
      else await route.abort("blockedbyclient");
    });
    const url = new URL(webBase);
    url.searchParams.set("build", payload.buildId);
    url.searchParams.set("camera", payload.camera);
    url.searchParams.set("projection", payload.projection);
    url.searchParams.set("headless", "1");
    url.searchParams.set("transparent", payload.transparent ? "1" : "0");
    await page.goto(url.toString(), { waitUntil: "networkidle", timeout: timeoutMs });
    await page.waitForFunction(() => (window as unknown as { __MBI_RENDER_READY?: boolean }).__MBI_RENDER_READY === true, undefined, { timeout: timeoutMs });
    const metadata = await page.evaluate(() => (window as unknown as { __MBI_RENDER_METADATA?: Record<string, unknown> }).__MBI_RENDER_METADATA ?? {});
    const image = await page.locator(".viewport canvas").screenshot({ type: "png", omitBackground: payload.transparent, animations: "disabled" });
    const requestHash = createHash("sha256").update(JSON.stringify(payload)).digest("hex");
    const contentHash = createHash("sha256").update(requestHash).update(image).digest("hex");
    const snapshotId = `snap_${contentHash.slice(0, 20)}`;
    const destination = join(outputRoot, snapshotId);
    await mkdir(destination, { recursive: true });
    const manifest = {
      snapshotId,
      buildId: payload.buildId,
      buildVersionId: payload.versionId ?? null,
      type: payload.projection,
      direction: payload.camera,
      quality: payload.quality,
      resolution: [payload.width, payload.height],
      rendererVersion,
      background: payload.transparent ? "transparent" : "workspace",
      requestHash,
      contentHash,
      ...metadata,
    };
    await atomicWrite(join(destination, "color.png"), image);
    await atomicWrite(join(destination, "manifest.json"), JSON.stringify(manifest, null, 2));
    return manifest;
  } finally {
    await context.close();
    release();
  }
}

const server = createServer(async (request, response) => {
  response.setHeader("X-Content-Type-Options", "nosniff");
  response.setHeader("Cache-Control", "no-store");
  if (request.method === "GET" && request.url === "/healthz") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify({ status: "ok", active, maxConcurrency }));
    return;
  }
  if (request.method === "GET" && request.url === "/readyz") {
    try {
      await getBrowser();
      response.writeHead(200, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "ready" }));
    } catch (error) {
      response.writeHead(503, { "content-type": "application/json" });
      response.end(JSON.stringify({ status: "not_ready", error: error instanceof Error ? error.message : String(error) }));
    }
    return;
  }
  if (request.method !== "POST" || request.url !== "/render") {
    response.writeHead(404).end();
    return;
  }
  try {
    const payload = requestSchema.parse(await readBody(request));
    const manifest = await render(payload);
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(manifest));
  } catch (error) {
    const isValidation = error instanceof z.ZodError;
    response.writeHead(isValidation ? 422 : 500, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: { code: isValidation ? "RENDER_REQUEST_INVALID" : "RENDER_FAILED", message: error instanceof Error ? error.message : String(error) } }));
  }
});

async function shutdown(): Promise<void> {
  server.close();
  await browser?.close();
  process.exit(0);
}
process.on("SIGTERM", () => void shutdown());
process.on("SIGINT", () => void shutdown());
server.listen(port, "0.0.0.0", () => console.log(JSON.stringify({ message: "renderer-service listening", port, maxConcurrency })));
