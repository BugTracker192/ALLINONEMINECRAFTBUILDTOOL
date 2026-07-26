import { useWorkspace, type CameraPreset } from "../state/workspace";

const PRESETS: Array<[CameraPreset, string]> = [
  ["front", "Front"], ["back", "Back"], ["left", "Left"], ["right", "Right"],
  ["top", "Top"], ["bottom", "Bottom"], ["isometric_ne", "NE iso"], ["isometric_sw", "SW iso"],
];

export function CameraControls() {
  const preset = useWorkspace((state) => state.cameraPreset);
  const projection = useWorkspace((state) => state.projection);
  const setCameraPreset = useWorkspace((state) => state.setCameraPreset);
  const toggleProjection = useWorkspace((state) => state.toggleProjection);
  return (
    <section className="panel camera-controls" aria-labelledby="camera-heading">
      <h2 id="camera-heading">Camera</h2>
      <div className="button-grid" role="group" aria-label="Camera view presets">
        {PRESETS.map(([value, label]) => (
          <button key={value} type="button" aria-pressed={preset === value} onClick={() => setCameraPreset(value)}>{label}</button>
        ))}
      </div>
      <button type="button" aria-pressed={projection === "orthographic"} onClick={toggleProjection}>
        {projection === "orthographic" ? "Orthographic" : "Perspective"}
      </button>
    </section>
  );
}
