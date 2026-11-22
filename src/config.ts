import "dotenv/config";

function need(key: string): string {
  const v = process.env[key];
  if (!v) throw new Error(`Missing ${key} in .env`);
  return v;
}

export const cfg = {
  get sourceFolderId() { return need("SOURCE_FOLDER_ID"); },
  destRootName: process.env.DEST_ROOT_NAME ?? "Signed Reports",
  credentialsPath: process.env.GOOGLE_CREDENTIALS ?? "credentials.json",
  tokenPath: process.env.GOOGLE_TOKEN ?? "token.json",
  workDir: process.env.WORK_DIR ?? "D:\\dsc-work",
  signedDir: process.env.SIGNED_DIR ?? "D:\\signed",
  redisUrl: process.env.REDIS_URL ?? "redis://127.0.0.1:6379",
  python: process.env.PYTHON ?? "python",
  queueName: "sign-reports",
};

export interface SignJob {
  fileId: string;
  name: string;
  relPath: string[]; // folder names from the source root down to the file
}
