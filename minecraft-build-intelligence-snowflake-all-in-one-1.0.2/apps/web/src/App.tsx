import type { CanonicalBlock } from "@mbi/protocol";
import { useEffect, useState } from "react";
import { BuildViewport } from "./components/BuildViewport";
import { CameraControls } from "./components/CameraControls";
import { Inspector } from "./components/Inspector";
import { LayerControls } from "./components/LayerControls";
import { UploadPanel } from "./components/UploadPanel";
import { fetchAllBlocks, getBuild, getPalette } from "./lib/api";
import { useWorkspace } from "./state/workspace";

export default function App() {
  const build = useWorkspace((state) => state.build);
  const palette = useWorkspace((state) => state.palette);
  const setBuild = useWorkspace((state) => state.setBuild);
  const setPalette = useWorkspace((state) => state.setPalette);
  const setCameraPreset = useWorkspace((state) => state.setCameraPreset);
  const setProjection = useWorkspace((state) => state.setProjection);
  const setShowGrid = useWorkspace((state) => state.setShowGrid);
  const [blocks, setBlocks] = useState<CanonicalBlock[]>([]);
  const [loading, setLoading] = useState(false);

  const openBuild = async (buildId: string) => {
    setLoading(true);
    try {
      const [summary, entries] = await Promise.all([getBuild(buildId), getPalette(buildId)]);
      setBuild(summary);
      setPalette(entries);
      const accumulated: CanonicalBlock[] = [];
      const blockData = await fetchAllBlocks(buildId, (page) => {
        accumulated.push(...page);
        setBlocks([...accumulated]);
      });
      setBlocks(blockData);
      history.replaceState(null, "", `?build=${encodeURIComponent(buildId)}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const parameters = new URLSearchParams(location.search);
    const buildId = parameters.get("build");
    const camera = parameters.get("camera");
    const projection = parameters.get("projection");
    const validCameras = new Set(["front", "back", "left", "right", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"]);
    if (camera && validCameras.has(camera)) setCameraPreset(camera as Parameters<typeof setCameraPreset>[0]);
    if (projection === "orthographic" || projection === "perspective") setProjection(projection);
    if (parameters.get("headless") === "1") setShowGrid(false);
    if (buildId) void openBuild(buildId);
  }, []);

  if (!build) return <main className="landing"><UploadPanel onImported={(id) => void openBuild(id)} />{loading && <p>Loading canonical chunks…</p>}</main>;

  return (
    <main className={new URLSearchParams(location.search).get("headless") === "1" ? "workspace headless-workspace" : "workspace"} aria-label="Minecraft Build Intelligence editor">
      <header className="topbar">
        <strong>Minecraft Build Intelligence</strong>
        <span>{build.buildId}</span>
        <span>{build.nonAirCount.toLocaleString()} blocks</span>
        <span>{build.paletteSize} states</span>
        <button type="button" onClick={() => { setBuild(null); setPalette([]); setBlocks([]); history.replaceState(null, "", location.pathname); }}>Import another</button>
      </header>
      <nav className="sidebar" aria-label="Build tools"><CameraControls /><LayerControls /><section className="panel"><h2>Regions</h2><p>{build.regionCount} source region(s)</p></section><section className="panel"><h2>Diagnostics</h2>{build.diagnostics.map((item) => <p key={item.code} className={`severity-${item.severity}`}>{item.code}: {item.message}</p>)}</section></nav>
      <BuildViewport blocks={blocks} palette={palette} />
      <Inspector />
      <footer className="statusbar"><span>Version {build.contentHash.slice(0, 12)}</span><span>Exact +X east, +Y up, +Z south</span></footer>
    </main>
  );
}
