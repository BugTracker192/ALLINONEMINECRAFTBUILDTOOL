import { useState } from "react";
import { beginImport, getJob, uploadBuild } from "../lib/api";

interface Props { onImported: (buildId: string) => void }

export function UploadPanel({ onImported }: Props) {
  const [status, setStatus] = useState("Drop or choose a .schem, .schematic, or .litematic file.");
  const [progress, setProgress] = useState(0);
  const [busy, setBusy] = useState(false);

  const process = async (file: File) => {
    setBusy(true);
    try {
      setStatus("Uploading…");
      setProgress(0.05);
      const upload = await uploadBuild(file);
      const started = await beginImport(upload.uploadId, upload.filename);
      let job = started;
      while (!["completed", "failed", "cancelled"].includes(job.status)) {
        await new Promise((resolve) => setTimeout(resolve, 350));
        job = await getJob(job.job_id);
        setStatus(job.stage.replaceAll("_", " "));
        setProgress(job.progress);
      }
      if (job.status !== "completed" || !job.result) throw new Error(job.error?.message ?? `Import ${job.status}`);
      setStatus("Import complete");
      setProgress(1);
      onImported(job.result.buildId);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="upload-card">
      <h1>Minecraft Build Intelligence</h1>
      <p>Exact symbolic voxels, deterministic visual evidence, transactional editing.</p>
      <label className="drop-zone">
        <span>{busy ? "Processing…" : "Choose structure file"}</span>
        <input
          disabled={busy}
          type="file"
          accept=".schem,.schematic,.litematic"
          onChange={(event) => event.target.files?.[0] && void process(event.target.files[0])}
        />
      </label>
      <progress value={progress} max={1} />
      <output>{status}</output>
    </section>
  );
}
