"""
Uploads each signed PDF from SIGNED_DIR into the SAME Drive folder as its original,
named <original name>_signed.pdf. Files already there are skipped, so it is safe to re-run.
  python signer/upload_in_place.py --limit 5   # test with 5 files
  python signer/upload_in_place.py             # everything
"""
import os
import sys

from drive_test import FOLDER_ID, ROOT, get_service
from sign_drive import clean
from upload_signed import SIGNED_DIR, find, upload

FAILED_FILE = os.path.join(ROOT, "failed_upload.txt")


def originals(drive, folder_id, path=""):
    """Yield (name, local folder path, Drive folder id) for every original PDF."""
    page = None
    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType)",
            pageSize=100,
            pageToken=page,
        ).execute()
        for f in res["files"]:
            if f["mimeType"].endswith("folder"):
                yield from originals(drive, f["id"], os.path.join(path, clean(f["name"])))
            elif f["mimeType"] == "application/pdf" and not f["name"].endswith("_signed.pdf"):
                yield f["name"], path, folder_id
        page = res.get("nextPageToken")
        if not page:
            return


if __name__ == "__main__":
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    drive = get_service()
    uploaded = skipped = missing = 0
    for name, path, parent in originals(drive, FOLDER_ID):
        if limit is not None and uploaded >= limit:
            break
        stem = os.path.splitext(name)[0]
        local = os.path.join(SIGNED_DIR, path, clean(stem) + "_signed.pdf")
        shown = os.path.join(path, name)
        if not os.path.exists(local):
            missing += 1
            continue
        try:
            if find(drive, parent, stem + "_signed.pdf"):
                skipped += 1
                continue
            upload(drive, parent, local, stem + "_signed.pdf")
            uploaded += 1
            print("UPLOADED", shown)
        except Exception as e:
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(f"{shown} {type(e).__name__}: {e}\n")
            print("FAILED", shown, type(e).__name__)
    print(uploaded, "uploaded,", skipped, "already there,", missing, "with no signed copy")