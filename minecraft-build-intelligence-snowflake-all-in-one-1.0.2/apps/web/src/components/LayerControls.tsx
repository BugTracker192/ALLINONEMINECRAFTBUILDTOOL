import { useWorkspace } from "../state/workspace";

export function LayerControls() {
  const build = useWorkspace((state) => state.build);
  const minimum = useWorkspace((state) => state.layerMin);
  const maximum = useWorkspace((state) => state.layerMax);
  const setRange = useWorkspace((state) => state.setLayerRange);
  const showGrid = useWorkspace((state) => state.showGrid);
  const toggleGrid = useWorkspace((state) => state.toggleGrid);
  if (!build) return null;
  return (
    <section className="panel layers">
      <h2>Layers</h2>
      <label>Minimum Y <input type="range" min={build.bounds.min.y} max={build.bounds.max.y} value={minimum} onChange={(e) => setRange(Math.min(Number(e.target.value), maximum), maximum)} /></label>
      <output>{minimum}</output>
      <label>Maximum Y <input type="range" min={build.bounds.min.y} max={build.bounds.max.y} value={maximum} onChange={(e) => setRange(minimum, Math.max(Number(e.target.value), minimum))} /></label>
      <output>{maximum}</output>
      <button type="button" onClick={toggleGrid}>{showGrid ? "Hide" : "Show"} grid</button>
    </section>
  );
}
