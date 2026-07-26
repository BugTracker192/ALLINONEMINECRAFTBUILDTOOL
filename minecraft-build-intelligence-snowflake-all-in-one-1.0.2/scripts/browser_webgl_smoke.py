#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var/reports/browser-webgl-smoke.json"
SCREENSHOT = ROOT / "var/reports/browser-webgl-smoke.png"

HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>MBI WebGL smoke</title>
<style>html,body{margin:0;background:#111;color:#fff;font:16px sans-serif}canvas{display:block;width:512px;height:512px}</style>
</head><body><main aria-label="Renderer smoke test"><canvas id="c" width="512" height="512" aria-label="WebGL renderer"></canvas></main>
<script>
(async () => {
  const canvas = document.getElementById('c');
  const gl = canvas.getContext('webgl2', {antialias:false, preserveDrawingBuffer:true});
  if (!gl) throw new Error('WebGL2 unavailable');
  const vertex = `#version 300 es\nin vec2 p; void main(){gl_Position=vec4(p,0.0,1.0);}`;
  const fragment = `#version 300 es\nprecision highp float; out vec4 c; void main(){c=vec4(gl_FragCoord.x/512.0,gl_FragCoord.y/512.0,0.5,1.0);}`;
  const compile = (type, source) => { const s=gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s); if(!gl.getShaderParameter(s,gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; };
  const program=gl.createProgram(); gl.attachShader(program,compile(gl.VERTEX_SHADER,vertex)); gl.attachShader(program,compile(gl.FRAGMENT_SHADER,fragment)); gl.linkProgram(program); if(!gl.getProgramParameter(program,gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
  gl.useProgram(program); const buffer=gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER,buffer); gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW); const loc=gl.getAttribLocation(program,'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc,2,gl.FLOAT,false,0,0); gl.drawArrays(gl.TRIANGLES,0,3);
  const pixel=new Uint8Array(4); gl.readPixels(256,256,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel); const before=Array.from(pixel);
  const gpuInfo={vendor:gl.getParameter(gl.VENDOR),renderer:gl.getParameter(gl.RENDERER),version:gl.getParameter(gl.VERSION),maxTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE),maxRenderbufferSize:gl.getParameter(gl.MAX_RENDERBUFFER_SIZE)};
  const lose=gl.getExtension('WEBGL_lose_context');
  let lost=false, restored=false;
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); lost=true; });
  canvas.addEventListener('webglcontextrestored', () => { restored=true; });
  if (lose) { lose.loseContext(); await new Promise(r=>setTimeout(r,100)); lose.restoreContext(); await new Promise(r=>setTimeout(r,250)); }
  let offscreen=false, offscreen2d=false;
  if (typeof OffscreenCanvas !== 'undefined') { const o=new OffscreenCanvas(16,16); offscreen=true; offscreen2d=!!o.getContext('2d'); }
  window.__result = {
    webgl2:true,
    ...gpuInfo,
    centerPixel:before,
    offscreenCanvas:offscreen,
    offscreen2d,
    loseContextExtension:!!lose,
    contextLostEvent:lost,
    contextRestoredEvent:restored,
    reducedMotion:matchMedia('(prefers-reduced-motion: reduce)').matches,
    devicePixelRatio,
  };
})();
</script></body></html>"""


def main() -> int:
    started = time.perf_counter()
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="/usr/bin/chromium",
            headless=False,
            args=["--no-sandbox", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=swiftshader"],
        )
        context = browser.new_context(reduced_motion="reduce", viewport={"width": 512, "height": 512})
        page = context.new_page()
        console_errors: list[str] = []
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.set_content(HTML, wait_until="load")
        page.wait_for_function("window.__result !== undefined", timeout=15_000)
        result = page.evaluate("window.__result")
        page.screenshot(path=str(SCREENSHOT))
        browser.close()
    failures: list[str] = []
    if console_errors:
        failures.extend(console_errors)
    for key in ("webgl2", "offscreenCanvas", "offscreen2d", "reducedMotion"):
        if not result.get(key):
            failures.append(f"{key} was not available")
    if result.get("loseContextExtension") and not (result.get("contextLostEvent") and result.get("contextRestoredEvent")):
        failures.append("WebGL context loss/restoration events did not both fire")
    pixel = result.get("centerPixel", [])
    if len(pixel) != 4 or pixel[3] != 255:
        failures.append(f"unexpected center pixel {pixel}")
    report = {
        "schemaVersion": 1,
        "passed": not failures,
        "durationSeconds": round(time.perf_counter() - started, 4),
        "browser": result,
        "screenshot": str(SCREENSHOT.relative_to(ROOT)),
        "failures": failures,
    }
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
