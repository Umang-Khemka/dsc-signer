"""
Downloads PDFs from the BLR folder (all subfolders), signs each one with the token,
and saves it to SIGNED_DIR in the same folder layout. Nothing is uploaded to Drive.
  python signer/sign_drive.py --limit 5     # test on the first 5 PDFs
  python signer/sign_drive.py               # all PDFs (skips ones already done)
"""
import getpass
import os
import re
import sys

from googleapiclient.http import MediaIoBaseDownload

import sign_worker  # loads .env
from drive_test import FOLDER_ID, ROOT, get_service

WORK_DIR = os.environ.get("WORK_DIR", r"D:\dsc-work")
SIGNED_DIR = os.environ.get("SIGNED_DIR", r"D:\signed")
DONE_FILE = os.path.join(ROOT, "done.txt")      # ids of files already signed
FAILED_FILE = os.path.join(ROOT, "failed.txt")  # files that errored, with the reason


def clean(name):
    """Make a Drive name safe for a Windows file or folder name."""
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")


def pdfs(drive, folder_id, path=""):
    """Yield (id, name, folder path) for every PDF under folder_id."""
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
                yield from pdfs(drive, f["id"], os.path.join(path, clean(f["name"])))
            elif f["mimeType"] == "application/pdf" and not f["name"].endswith("_signed.pdf"):
                yield f["id"], f["name"], path
        page = res.get("nextPageToken")
        if not page:
            return


def download(drive, file_id, dst):
    with open(dst, "wb") as out:
        dl = MediaIoBaseDownload(out, drive.files().get_media(fileId=file_id))
        done = False
        while not done:
            _, done = dl.next_chunk()


if __name__ == "__main__":
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    done_ids = set(open(DONE_FILE).read().split()) if os.path.exists(DONE_FILE) else set()

    pin = getpass.getpass("Token PIN: ")
    signer = sign_worker.build_pkcs11_signer(sign_worker.open_session(pin))
    print("Signing as:", signer.signing_cert.subject.human_friendly)
    tsa = sign_worker.build_timestamper()

    drive = get_service()
    os.makedirs(WORK_DIR, exist_ok=True)
    n = 0
    for file_id, name, path in pdfs(drive, FOLDER_ID):
        if file_id in done_ids:
            continue
        if limit is not None and n >= limit:
            break
        out_dir = os.path.join(SIGNED_DIR, path)
        os.makedirs(out_dir, exist_ok=True)
        dst = os.path.join(out_dir, clean(os.path.splitext(name)[0]) + "_signed.pdf")
        src = os.path.join(WORK_DIR, file_id + ".pdf")
        try:
            download(drive, file_id, src)
            sign_worker.sign_pdf(signer, src, dst, tsa)
            with open(DONE_FILE, "a") as f:
                f.write(file_id + "\n")
            n += 1
            print("OK", os.path.join(path, name))
        except Exception as e:
            with open(FAILED_FILE, "a", encoding="utf-8") as f:
                f.write(f"{file_id} {os.path.join(path, name)} {type(e).__name__}: {e}\n")
            print("FAILED", os.path.join(path, name), type(e).__name__)
        finally:
            if os.path.exists(src):
                os.remove(src)
    print(n, "signed ->", SIGNED_DIR)