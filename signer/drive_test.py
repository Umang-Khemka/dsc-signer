"""
Logs in to Google Drive (browser opens the first time only), then lists every file
inside the BLR folder, going into all subfolders.
  python signer/drive_test.py
"""
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

import sign_worker  # only here so .env gets loaded

SCOPES = ["https://www.googleapis.com/auth/drive"]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CREDS_FILE = os.path.join(ROOT, "credentials.json")
TOKEN_FILE = os.path.join(ROOT, "token.json")
FOLDER_ID = os.environ["SOURCE_FOLDER_ID"]


def get_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def walk(drive, folder_id, path=""):
    """Print every file under folder_id, going into subfolders. Returns the file count."""
    page = None
    count = 0
    while True:
        res = drive.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType)",
            pageSize=100,
            pageToken=page,
        ).execute()
        for f in res["files"]:
            if f["mimeType"].endswith("folder"):
                count += walk(drive, f["id"], path + f["name"] + "/")
            else:
                print(path + f["name"], f["id"])
                count += 1
        page = res.get("nextPageToken")
        if not page:
            return count


if __name__ == "__main__":
    total = walk(get_service(), FOLDER_ID)
    print(total, "files")