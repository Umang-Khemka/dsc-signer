import fs from "node:fs";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { google, drive_v3 } from "googleapis";
import { authenticate } from "@google-cloud/local-auth";
import { cfg } from "./config.js";

// readonly: read the shared folder. drive.file: only files/folders THIS app creates (the signed copies).
const SCOPES = [
  "https://www.googleapis.com/auth/drive.readonly",
  "https://www.googleapis.com/auth/drive.file",
];

const FOLDER = "application/vnd.google-apps.folder";
const SHORTCUT = "application/vnd.google-apps.shortcut";

export interface PdfEntry {
  fileId: string;
  name: string;
  relPath: string[];
}

export async function getDrive(): Promise<drive_v3.Drive> {
  const keys = JSON.parse(fs.readFileSync(cfg.credentialsPath, "utf8"));
  const k = keys.installed ?? keys.web;
  let auth: any;
  if (fs.existsSync(cfg.tokenPath)) {
    auth = new google.auth.OAuth2(k.client_id, k.client_secret, k.redirect_uris?.[0]);
    auth.setCredentials(JSON.parse(fs.readFileSync(cfg.tokenPath, "utf8")));
  } else {
    auth = await authenticate({ scopes: SCOPES, keyfilePath: cfg.credentialsPath });
    fs.writeFileSync(cfg.tokenPath, JSON.stringify(auth.credentials));
  }
  return google.drive({ version: "v3", auth });
}

const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/'/g, "\\'");

async function* children(drive: drive_v3.Drive, folderId: string) {
  let pageToken: string | undefined;
  do {
    const res = await drive.files.list({
      q: `'${folderId}' in parents and trashed = false`,
      fields: "nextPageToken, files(id, name, mimeType)",
      pageSize: 1000,
      pageToken,
      supportsAllDrives: true,
      includeItemsFromAllDrives: true,
    });
    for (const f of res.data.files ?? []) yield f;
    pageToken = res.data.nextPageToken ?? undefined;
  } while (pageToken);
}

/** Walk the source folder recursively and return every PDF with its folder path. */
export async function walkPdfs(
  drive: drive_v3.Drive,
  folderId: string,
  relPath: string[] = [],
  skipped: string[] = [],
): Promise<{ pdfs: PdfEntry[]; skipped: string[] }> {
  const pdfs: PdfEntry[] = [];
  for await (const f of children(drive, folderId)) {
    if (!f.id || !f.name) continue;
    if (f.mimeType === FOLDER) {
      const sub = await walkPdfs(drive, f.id, [...relPath, f.name], skipped);
      pdfs.push(...sub.pdfs);
    } else if (f.mimeType === "application/pdf") {
      pdfs.push({ fileId: f.id, name: f.name, relPath });
    } else {
      skipped.push(`${[...relPath, f.name].join("/")} (${f.mimeType}${f.mimeType === SHORTCUT ? ", shortcut" : ""})`);
    }
  }
  return { pdfs, skipped };
}

export async function downloadFile(drive: drive_v3.Drive, fileId: string, dest: string) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const res = await drive.files.get(
    { fileId, alt: "media", supportsAllDrives: true },
    { responseType: "stream" },
  );
  await pipeline(res.data as NodeJS.ReadableStream, fs.createWriteStream(dest));
}

export async function findByName(drive: drive_v3.Drive, parentId: string, name: string, folder = false) {
  const res = await drive.files.list({
    q: `'${parentId}' in parents and name = '${esc(name)}' and trashed = false` +
       (folder ? ` and mimeType = '${FOLDER}'` : ""),
    fields: "files(id, name)",
    pageSize: 1,
  });
  return res.data.files?.[0]?.id ?? null;
}

export async function ensureFolder(drive: drive_v3.Drive, parentId: string, name: string) {
  const existing = await findByName(drive, parentId, name, true);
  if (existing) return existing;
  const res = await drive.files.create({
    requestBody: { name, mimeType: FOLDER, parents: [parentId] },
    fields: "id",
  });
  return res.data.id!;
}

const folderCache = new Map<string, string>();
export async function ensureFolderPath(drive: drive_v3.Drive, rootId: string, relPath: string[]) {
  let parent = rootId;
  const trail: string[] = [];
  for (const part of relPath) {
    trail.push(part);
    const key = `${rootId}/${trail.join("/")}`;
    let id = folderCache.get(key);
    if (!id) {
      id = await ensureFolder(drive, parent, part);
      folderCache.set(key, id);
    }
    parent = id;
  }
  return parent;
}

export async function uploadPdf(drive: drive_v3.Drive, parentId: string, name: string, filePath: string) {
  const res = await drive.files.create({
    requestBody: { name, parents: [parentId] },
    media: { mimeType: "application/pdf", body: fs.createReadStream(filePath) },
    fields: "id",
  });
  return res.data.id!;
}
