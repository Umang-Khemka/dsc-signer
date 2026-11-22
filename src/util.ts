/** Make a Drive name safe to use as a Windows file or folder name (local copy only). */
export function safeName(name: string): string {
  const cleaned = name.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").replace(/[. ]+$/, "");
  return cleaned || "_";
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
