import type { BuildSummary, PaletteEntry } from "@mbi/protocol";
import { create } from "zustand";

export type CameraPreset = "front" | "back" | "left" | "right" | "top" | "bottom" | "isometric_ne" | "isometric_nw" | "isometric_se" | "isometric_sw";
export type ProjectionMode = "perspective" | "orthographic";

interface SelectedBlock {
  position: { x: number; y: number; z: number };
  palette: PaletteEntry;
}

interface WorkspaceState {
  build: BuildSummary | null;
  palette: PaletteEntry[];
  selected: SelectedBlock | null;
  layerMin: number;
  layerMax: number;
  showGrid: boolean;
  cameraPreset: CameraPreset;
  projection: ProjectionMode;
  setBuild: (build: BuildSummary | null) => void;
  setPalette: (palette: PaletteEntry[]) => void;
  setSelected: (selected: SelectedBlock | null) => void;
  setLayerRange: (minimum: number, maximum: number) => void;
  toggleGrid: () => void;
  setShowGrid: (visible: boolean) => void;
  setCameraPreset: (preset: CameraPreset) => void;
  toggleProjection: () => void;
  setProjection: (projection: ProjectionMode) => void;
}

export const useWorkspace = create<WorkspaceState>((set) => ({
  build: null,
  palette: [],
  selected: null,
  layerMin: -2048,
  layerMax: 2048,
  showGrid: true,
  cameraPreset: "isometric_se",
  projection: "perspective",
  setBuild: (build) => set({ build, layerMin: build?.bounds.min.y ?? -2048, layerMax: build?.bounds.max.y ?? 2048 }),
  setPalette: (palette) => set({ palette }),
  setSelected: (selected) => set({ selected }),
  setLayerRange: (layerMin, layerMax) => set({ layerMin, layerMax }),
  toggleGrid: () => set((state) => ({ showGrid: !state.showGrid })),
  setShowGrid: (showGrid) => set({ showGrid }),
  setCameraPreset: (cameraPreset) => set({ cameraPreset }),
  toggleProjection: () => set((state) => ({ projection: state.projection === "perspective" ? "orthographic" : "perspective" })),
  setProjection: (projection) => set({ projection }),
}));
