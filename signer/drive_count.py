"""
Counts everything under the BLR folder by type, so we can see why the total differs.
  python signer/drive_count.py 2>/dev/null
Writes the non-PDF items to nonpdf.txt in the dsc-signer folder.
"""
import os
from collections import Counter

from drive_test import FOLDER_ID, ROOT, get_service

counts = Counter()
others = []


def walk(drive, folder_id, path=""):
    page = None
    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType,shortcutDetails)",
            pageSize=100,
            pageToken=page,
        ).execute()
        for f in res["files"]:
            mime = f["mimeType"]
            counts[mime] += 1
            if mime.endswith("folder"):
                walk(drive, f["id"], path + f["name"] + "/")
            elif mime != "application/pdf":
                others.append(f"{mime}  {path}{f['name']}")
        page = res.get("nextPageToken")
        if not page:
            return


if __name__ == "__main__":
    walk(get_service(), FOLDER_ID)
    for mime, n in counts.most_common():
        print(n, mime)
    print("total items:", sum(counts.values()))
    with open(os.path.join(ROOT, "nonpdf.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(others))