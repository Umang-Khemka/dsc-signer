import { makeQueue } from "./queue.js";

const queue = makeQueue();
const c = await queue.getJobCounts("waiting", "active", "completed", "failed", "delayed");
console.log(c);

if (process.argv.includes("--failed")) {
  for (const j of await queue.getFailed(0, 200)) {
    console.log(`${[...j.data.relPath, j.data.name].join("/")}  ->  ${j.failedReason}`);
  }
}
if (process.argv.includes("--retry")) {
  const failed = await queue.getFailed(0, 5000);
  for (const j of failed) await j.retry();
  console.log(`Re-queued ${failed.length} failed jobs. Run \`npm run worker\`.`);
}
await queue.close();
process.exit(0);
