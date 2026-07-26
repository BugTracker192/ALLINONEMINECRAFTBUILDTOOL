import { useWorkspace } from "../state/workspace";

export function Inspector() {
  const selected = useWorkspace((state) => state.selected);
  if (!selected) return <aside className="panel inspector"><h2>Inspector</h2><p>Select a block in the viewport.</p></aside>;
  return (
    <aside className="panel inspector">
      <h2>Block inspector</h2>
      <dl>
        <dt>Coordinate</dt><dd>{selected.position.x}, {selected.position.y}, {selected.position.z}</dd>
        <dt>State</dt><dd><code>{selected.palette.canonical_state}</code></dd>
        <dt>Palette</dt><dd>{selected.palette.palette_id}</dd>
        <dt>Render layer</dt><dd>{selected.palette.render_category}</dd>
        <dt>Asset support</dt><dd>{selected.palette.diagnostics.length ? selected.palette.diagnostics.join(", ") : "resource model or visible fallback"}</dd>
      </dl>
    </aside>
  );
}
