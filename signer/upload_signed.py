"""
Uploads the signed PDFs from SIGNED_DIR to a folder called "BLR Signed" in YOUR Drive,
keeping the same folder layout. Files already uploaded are skipped, so it is safe to re-run.
  python signer/upload_signed.py --limit 5   # test with 5 files
  python signer/upload_signed.py             # everything
"""
import os
import sys
import time

from googleapiclient.http import MediaFileUpload

from drive_test import ROOT, get_service  # also loads .env

SIGNED_DIR = os.environ.get("SIGNED_DIR", r"D:\signed")
ROOT_NAME = "BLR Signed"
FAILED_FILE = os.path.join(ROOT, "failed_upload.txt")
FOLDER_MIME = "application/vnd.google-apps.folder"


def find(drive, parent, name, folder=False):
    esc = name.replace("\\", "\\\\").replace("'", "\\'")
    q = f"'{parent}' in parents and name='{esc}' and trashed=false"
    if folder:
        q += f" and mimeType='{FOLDER_MIME}'"
    res = drive.files().list(q=q, fields="files(id)", pageSize=1).execute()
    return res["files"][0]["id"] if res["files"] else None


def get_folder(drive, parent, name):
    return find(drive, parent, name, True) or drive.files().create(
        body={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]},
        fields="id",
    ).execute()["id"]


def upload(drive, parent, path, name):
    for attempt in range(3):
        try:
            media = MediaFileUpload(path, mimetype="application/pdf", resumable=True)
            drive.files().create(
                body={"name": name, "parents": [parent]}, media_body=media, fields="id"
            ).execute()
            return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3)


def local_files():
    for dirpath, dirs, files in os.walk(SIGNED_DIR):
        dirs.sort()
        rel = os.path.relpath(dirpath, SIGNED_DIR)
        rel = "" if rel == "." else rel
        for name in sorted(files):
            if name.endswith("_signed.pdf"):
                yield rel, name


if __name__ == "__main__":
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    drive = get_service()
    folder_ids = {"": get_folder(drive, "root", ROOT_NAME)}

    def folder_for(rel):
        if rel not in folder_ids:
            parent_rel, name = os.path.split(rel)
            folder_ids[rel] = get_folder(drive, folder_for(parent_rel), name)
        return folder_ids[rel]

    uploaded = skipped = 0
    for rel, name in local_files():
        if limit is not None and uploaded >= limit:
            break
        shown = os.path.join(rel, name)
        try:
            parent = folder_for(rel)
            if find(drive, parent, name):
                skipped += 1
                continue
            upload(drive, parent, os.path.join(SIGNED_DIR, rel, name), name)
            uploaded += 1
            print("UPLOADED", shown)
        except Exception as e:
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(f"{shown} {type(e).__name__}: {e}\n")
            print("FAILED", shown, type(e).__name__)
    print(uploaded, "uploaded,", skipped, "already there")