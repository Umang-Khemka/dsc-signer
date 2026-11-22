import fs from "node:fs";
import path from "node:path";
import { Worker } from "bullmq";
import { cfg, SignJob } from "./config.js";
import { downloadFile, ensureFolder, ensureFolderPath, findByName, getDrive, uploadPdf } from "./drive.js";
import { makeConnection } from "./queue.js";
import { askHidden } from "./pin.js";
import { PySigner } from "./signer.js";
import { safeName } from "./util.js";

const MAX_CONSECUTIVE_FAILURES = 3;

const pin = await askHidden("Token PIN: ");
let signer: PySigner;
try {
  signer = await PySigner.start(pin);
} catch (e) {
  console.error(`Could not open the token: ${(e as Error).message}`);
  console.error("Check: token plugged in, PIN correct (don't retry blindly, tokens lock), CERT_LABEL set.");
  process.exit(1);
}
console.log(`Signer ready: ${signer.signerName}`);

const drive = await getDrive();
const destRoot = await ensureFolder(drive, "root", cfg.destRootName);
console.log(`Uploading signed copies to My Drive / ${cfg.destRootName}`);

let consecutiveFailures = 0;

const worker = new Worker<SignJob>(
  cfg.queueName,
  async (job) => {
    const { fileId, name, relPath } = job.data;
    const destParent = await ensureFolderPath(drive, destRoot, relPath);

    // Resume safety: already uploaded -> skip
    if (await findByName(drive, destParent, name)) return { skipped: true };

    const inPath = path.join(cfg.workDir, "in", `${fileId}.pdf`);
    const outDir = path.join(cfg.signedDir, ...relPath.map(safeName));
    const outPath = path.join(outDir, safeName(name));
    fs.mkdirSync(outDir, { recursive: true });

    await downloadFile(drive, fileId, inPath);
    await signer.sign(inPath, outPath); // one signature at a time (concurrency 1)
    await uploadPdf(drive, destParent, name, outPath);
    fs.rmSync(inPath, { force: true });
    return { signed: true };
  },
  { connection: makeConnection(), concurrency: 1 },
);

worker.on("completed", (job, result) => {
  consecutiveFailures = 0;
  console.log(`${result?.skipped ? "skip" : "done"}  ${[...job.data.relPath, job.data.name].join("/")}`);
});

worker.on("failed", async (job, err) => {
  consecutiveFailures++;
  console.error(`FAIL  ${job ? [...job.data.relPath, job.data.name].join("/") : "?"}: ${err.message}`);
  if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
    console.error(`\n${consecutiveFailures} failures in a row. Stopping so nothing is hammered.`);
    console.error("Check the token is plugged in and the network is up, then run `npm run worker` again to resume.");
    await worker.close();
    signer.close();
    process.exit(2);
  }
});

process.on("SIGINT", async () => {
  console.log("\nStopping after the current file...");
  await worker.close();
  signer.close();
  process.exit(0);
});
