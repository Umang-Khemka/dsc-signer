import { spawn, ChildProcessByStdio } from "node:child_process";
import type { Readable, Writable } from "node:stream";
import readline from "node:readline";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { cfg } from "./config.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const SCRIPT = path.resolve(here, "..", "signer", "sign_worker.py");

type Pending = { resolve: () => void; reject: (e: Error) => void };

/** One long-lived Python process that holds the token session open (PIN entered once). */
export class PySigner {
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private dead: Error | null = null;
  signerName = "";

  private constructor(private proc: ChildProcessByStdio<Writable, Readable, null>) {}

  static async start(pin: string): Promise<PySigner> {
    const proc = spawn(cfg.python, [SCRIPT], { stdio: ["pipe", "pipe", "inherit"], env: process.env });
    const s = new PySigner(proc);
    const rl = readline.createInterface({ input: proc.stdout });

    const ready = new Promise<void>((resolve, reject) => {
      rl.on("line", (line) => {
        let msg: any;
        try { msg = JSON.parse(line); } catch { return; }
        if (msg.event === "ready") { s.signerName = msg.signer; resolve(); }
        else if (msg.event === "error") reject(new Error(msg.error));
        else if (msg.id !== undefined) {
          const p = s.pending.get(msg.id);
          if (!p) return;
          s.pending.delete(msg.id);
          msg.ok ? p.resolve() : p.reject(new Error(msg.error));
        }
      });
      proc.on("exit", (code) => {
        s.dead = new Error(`signer process exited (code ${code})`);
        for (const p of s.pending.values()) p.reject(s.dead);
        s.pending.clear();
        reject(s.dead);
      });
    });

    proc.stdin.write(pin + "\n");
    await ready;
    return s;
  }

  sign(src: string, dst: string): Promise<void> {
    if (this.dead) return Promise.reject(this.dead);
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.proc.stdin.write(JSON.stringify({ id, src, dst }) + "\n");
    });
  }

  close() { this.proc.stdin.end(); }
}
