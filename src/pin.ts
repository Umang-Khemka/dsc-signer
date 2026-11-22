/** Read the token PIN from the terminal without echoing it. Never stored. */
export function askHidden(prompt: string): Promise<string> {
  return new Promise((resolve) => {
    const stdin = process.stdin;
    process.stdout.write(prompt);
    stdin.setRawMode?.(true);
    stdin.resume();
    stdin.setEncoding("utf8");
    let pin = "";
    const onData = (chunk: string) => {
      for (const ch of chunk) {
        if (ch === "\r" || ch === "\n") {
          stdin.setRawMode?.(false);
          stdin.pause();
          stdin.removeListener("data", onData);
          process.stdout.write("\n");
          resolve(pin);
          return;
        } else if (ch === "\u0003") {
          process.exit(130); // Ctrl+C
        } else if (ch === "\u007f" || ch === "\b") {
          pin = pin.slice(0, -1);
        } else {
          pin += ch;
        }
      }
    };
    stdin.on("data", onData);
  });
}
