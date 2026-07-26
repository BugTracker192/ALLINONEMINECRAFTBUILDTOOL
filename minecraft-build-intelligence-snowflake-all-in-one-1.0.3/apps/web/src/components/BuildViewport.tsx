import { BlockScene, ResourcePackClient, fitCamera } from "@mbi/renderer";
import type { CanonicalBlock, PaletteEntry } from "@mbi/protocol";
import { useEffect, useRef } from "react";
import {
  AmbientLight,
  Box3,
  Camera,
  Color,
  DirectionalLight,
  GridHelper,
  InstancedMesh,
  Mesh,
  OrthographicCamera,
  PerspectiveCamera,
  Plane,
  Raycaster,
  Scene,
  Vector2,
  Vector3,
  WebGLRenderer,
} from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { API_BASE } from "../lib/api";
import { useWorkspace } from "../state/workspace";

interface Props {
  blocks: CanonicalBlock[];
  palette: PaletteEntry[];
}

export function BuildViewport({ blocks, palette }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const setSelected = useWorkspace((state) => state.setSelected);
  const layerMin = useWorkspace((state) => state.layerMin);
  const layerMax = useWorkspace((state) => state.layerMax);
  const showGrid = useWorkspace((state) => state.showGrid);
  const cameraPreset = useWorkspace((state) => state.cameraPreset);
  const projection = useWorkspace((state) => state.projection);
  const clippingRef = useRef<[Plane, Plane] | null>(null);
  const gridRef = useRef<GridHelper | null>(null);

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    const parameters = new URLSearchParams(location.search);
    const headless = parameters.get("headless") === "1";
    const transparent = parameters.get("transparent") === "1";
    const scene = new Scene();
    scene.background = transparent ? null : new Color(0x0c1119);
    const perspective = new PerspectiveCamera(50, 1, 0.05, 20000);
    const orthographic = new OrthographicCamera(-10, 10, 10, -10, 0.05, 20000);
    const activeCamera: Camera = projection === "orthographic" ? orthographic : perspective;
    const renderer = new WebGLRenderer({ antialias: true, powerPreference: "high-performance", alpha: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    renderer.shadowMap.enabled = true;
    container.appendChild(renderer.domElement);
    const controls = new OrbitControls(activeCamera, renderer.domElement);
    controls.enableDamping = !matchMedia("(prefers-reduced-motion: reduce)").matches;
    controls.dampingFactor = 0.08;
    scene.add(new AmbientLight(0xffffff, 1.45));
    const key = new DirectionalLight(0xffffff, 2.5);
    key.position.set(-60, 100, -40);
    key.castShadow = true;
    scene.add(key);
    const grid = new GridHelper(512, 512, 0x526173, 0x263140);
    grid.position.y = -0.01;
    scene.add(grid);
    if (headless) grid.visible = false;
    gridRef.current = grid;
    const blockScene = new BlockScene(new ResourcePackClient(API_BASE));
    scene.add(blockScene.root);
    const minPlane = new Plane(new Vector3(0, 1, 0), -layerMin);
    const maxPlane = new Plane(new Vector3(0, -1, 0), layerMax + 1);
    clippingRef.current = [minPlane, maxPlane];

    let frame = 0;
    let disposed = false;
    let modelBounds = new Box3();
    const resize = () => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      const aspect = width / height;
      renderer.setSize(width, height, false);
      perspective.aspect = aspect;
      perspective.updateProjectionMatrix();
      if (!modelBounds.isEmpty()) {
        const fit = fitCamera(
          { min: modelBounds.min.toArray() as [number, number, number], max: modelBounds.max.toArray() as [number, number, number] },
          cameraPreset,
          aspect,
        );
        orthographic.left = -fit.orthographicHalfWidth;
        orthographic.right = fit.orthographicHalfWidth;
        orthographic.top = fit.orthographicHalfHeight;
        orthographic.bottom = -fit.orthographicHalfHeight;
        orthographic.near = fit.near;
        orthographic.far = fit.far;
        orthographic.updateProjectionMatrix();
      }
    };
    const observer = new ResizeObserver(resize);
    observer.observe(container);
    resize();

    void blockScene.build(blocks, palette).then(() => {
      if (disposed) return;
      modelBounds = new Box3().setFromObject(blockScene.root);
      if (modelBounds.isEmpty()) modelBounds.set(new Vector3(0, 0, 0), new Vector3(1, 1, 1));
      const fit = fitCamera(
        { min: modelBounds.min.toArray() as [number, number, number], max: modelBounds.max.toArray() as [number, number, number] },
        cameraPreset,
        Math.max(1, container.clientWidth) / Math.max(1, container.clientHeight),
      );
      activeCamera.position.set(...fit.position);
      activeCamera.near = fit.near;
      activeCamera.far = fit.far;
      if (activeCamera instanceof PerspectiveCamera) activeCamera.updateProjectionMatrix();
      if (activeCamera instanceof OrthographicCamera) {
        activeCamera.left = -fit.orthographicHalfWidth;
        activeCamera.right = fit.orthographicHalfWidth;
        activeCamera.top = fit.orthographicHalfHeight;
        activeCamera.bottom = -fit.orthographicHalfHeight;
        activeCamera.updateProjectionMatrix();
      }
      controls.target.set(...fit.target);
      controls.update();
      const metadata = {
        visibleBounds: { min: modelBounds.min.toArray(), max: modelBounds.max.toArray() },
        cameraPosition: activeCamera.position.toArray(),
        cameraTarget: controls.target.toArray(),
        viewMatrix: activeCamera.matrixWorldInverse.toArray(),
        projectionMatrix: activeCamera.projectionMatrix.toArray(),
        projection,
        cameraPreset,
        resolution: [renderer.domElement.width, renderer.domElement.height],
      };
      (window as unknown as { __MBI_RENDER_READY?: boolean; __MBI_RENDER_METADATA?: unknown }).__MBI_RENDER_METADATA = metadata;
      (window as unknown as { __MBI_RENDER_READY?: boolean }).__MBI_RENDER_READY = true;
      for (const child of blockScene.root.children) {
        if (!(child instanceof Mesh)) continue;
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach((material) => { material.clippingPlanes = [minPlane, maxPlane]; });
      }
      resize();
    });

    const raycaster = new Raycaster();
    const pointer = new Vector2();
    const click = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
      raycaster.setFromCamera(pointer, activeCamera);
      const hit = raycaster.intersectObjects(blockScene.root.children, false)[0];
      if (hit) setSelected(blockScene.pickIntersection(hit));
    };
    renderer.domElement.addEventListener("pointerdown", click);
    const animate = () => {
      controls.update();
      renderer.render(scene, activeCamera);
      frame = requestAnimationFrame(animate);
    };
    animate();
    const contextLost = (event: Event) => event.preventDefault();
    const contextRestored = () => void blockScene.build(blocks, palette);
    renderer.domElement.addEventListener("webglcontextlost", contextLost);
    renderer.domElement.addEventListener("webglcontextrestored", contextRestored);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", click);
      renderer.domElement.removeEventListener("webglcontextlost", contextLost);
      renderer.domElement.removeEventListener("webglcontextrestored", contextRestored);
      controls.dispose();
      blockScene.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      (window as unknown as { __MBI_RENDER_READY?: boolean; __MBI_RENDER_METADATA?: unknown }).__MBI_RENDER_READY = false;
      delete (window as unknown as { __MBI_RENDER_METADATA?: unknown }).__MBI_RENDER_METADATA;
    };
  }, [blocks, palette, setSelected, cameraPreset, projection]);

  useEffect(() => {
    const planes = clippingRef.current;
    if (!planes) return;
    planes[0].constant = -layerMin;
    planes[1].constant = layerMax + 1;
  }, [layerMin, layerMax]);

  useEffect(() => {
    if (gridRef.current) gridRef.current.visible = showGrid;
  }, [showGrid]);

  return <div className="viewport" ref={host} role="application" tabIndex={0} aria-label="Interactive Minecraft build viewport. Drag to orbit, right-drag to pan, and scroll to zoom." />;
}
