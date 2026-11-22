import fs from "node:fs";
import path from "node:path";
import { cfg } from "./config.js";
import { getDrive, walkPdfs } from "./drive.js";
import { makeQueue } from "./queue.js";

const drive = await getDrive();
console.log("Walking the shared folder (this can take a minute)...");
const { pdfs, skipped } = await walkPdfs(drive, cfg.sourceFolderId);

// Warn about duplicate names in the same folder (they would collide in the signed folder)
const seen = new Map<string, number>();
for (const p of pdfs) {
  const key = [...p.relPath, p.name].join("/");
  seen.set(key, (seen.get(key) ?? 0) + 1);
}
const dupes = [...seen].filter(([, n]) => n > 1);

fs.mkdirSync(cfg.workDir, { recursive: true });
fs.writeFileSync(path.join(cfg.workDir, "manifest.json"), JSON.stringify(pdfs, null, 2));

const queue = makeQueue();
await queue.addBulk(
  pdfs.map((p) => ({
    name: "sign",
    data: p,
    opts: {
      jobId: p.fileId, // re-running enqueue never creates duplicates
      attempts: 3,
      backoff: { type: "exponential", delay: 5000 },
      removeOnComplete: false,
      removeOnFail: false,
    },
  })),
);

console.log(`Queued ${pdfs.length} PDFs (manifest saved to ${path.join(cfg.workDir, "manifest.json")}).`);
if (skipped.length) console.log(`Ignored ${skipped.length} non-PDF items, e.g. ${skipped.slice(0, 5).join("; ")}`);
if (dupes.length) console.warn(`WARNING: ${dupes.length} duplicate file names in the same folder, e.g. ${dupes[0][0]}`);
await queue.close();
process.exit(0);
